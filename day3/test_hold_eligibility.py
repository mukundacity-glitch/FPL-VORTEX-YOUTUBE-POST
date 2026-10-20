"""HOLD requires current availability and starting evidence, regardless of EO."""

from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
import unittest

import pandas as pd

from day3.player_availability import AvailabilityContext
from day3.run_notebook import _prepare_code_cells
from day3.transfer_desk import select_transfer_desk


class HoldEligibilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime.now(timezone.utc)
        self.season = str(self.now.year)
        self.base_id = 7000
        self.events = [{"id": 8, "is_current": True}, {"id": 9, "is_next": True}]

    def snapshot(
        self, *, starting: bool = True, last_minutes: float = 90,
        start_probability: float = .95, expected_minutes: float = 85,
        status: str = "a", stale_role: bool = False,
        verified: bool = True, eligible_fallback: bool = True, position: int = 1,
    ) -> tuple[AvailabilityContext, pd.DataFrame, dict[int, dict[str, int]]]:
        ids = [self.base_id + index for index in range(4)]
        players = pd.DataFrame([
            {"id": player_id, "code": player_id + 100_000, "team": 1,
             "web_name": f"Example {player_id}", "element_type": position,
             "selected_by_percent": 60 if index == 2 else 20,
             "minutes": 500, "status": status if index == 2 else "a",
             "chance_of_playing_next_round": 100,
             "transfers_in_event": 1000 if index == 0 else 0,
             "transfers_out_event": 1000 if index == 1 else 0}
            for index, player_id in enumerate(ids)
        ])
        fixtures = pd.DataFrame([
            {"event": 8, "team_h": 1, "team_a": 2, "finished": True,
             "kickoff_time": (self.now - timedelta(days=2)).isoformat()},
            {"event": 9, "team_h": 1, "team_a": 2, "finished": False,
             "kickoff_time": (self.now + timedelta(days=3)).isoformat()},
        ])
        features = pd.DataFrame([
            {"player_id": ids[2], "start_probability": start_probability,
             "expected_minutes": expected_minutes},
            {"player_id": ids[3], "start_probability": .95 if eligible_fallback else .2,
             "expected_minutes": 85 if eligible_fallback else 15},
        ])
        roles = pd.DataFrame([
            {"player_code": ids[2] + 100_000, "season_label": self.season,
             "match_id": "example-prem-recent", "minutes_played": last_minutes,
             "is_starting": starting,
             "match_date": (self.now - timedelta(days=30 if stale_role else 2)).isoformat()},
            {"player_code": ids[3] + 100_000, "season_label": self.season,
             "match_id": "example-prem-recent", "minutes_played": 90,
             "is_starting": True,
             "match_date": (self.now - timedelta(days=2)).isoformat()},
        ])
        context = AvailabilityContext(
            {"events": self.events, "elements": players.to_dict("records")},
            fixtures, 9,
            {"source": "LIVE_FPL_API", "fallback_used": not verified},
        )
        context.bind_model(features, roles, players, self.season)
        # Zero returns alone must never turn a reserve into a patient HOLD.
        recent = {player_id: {"points": 0, "gameweeks": 3} for player_id in ids}
        return context, players, recent

    def choose(
        self, context: AvailabilityContext, players: pd.DataFrame,
        recent: dict[int, dict[str, int]],
    ) -> dict[str, list[dict[str, Any]]]:
        return select_transfer_desk(
            players, total_managers=1_000_000, recent_performance=recent, count=1,
            eligible_hold_ids=context.eligible_ids(),
        )

    def test_omitted_or_missing_eligibility_never_enables_unchecked_holds(self) -> None:
        context, players, recent = self.snapshot()
        args = dict(total_managers=1_000_000, recent_performance=recent, count=1)
        for extra in ({}, {"eligible_hold_ids": None}, {"eligible_hold_ids": set()}):
            with self.subTest(extra=extra):
                groups = select_transfer_desk(players, **args, **extra)
                self.assertEqual(groups["HOLD"], [])
                self.assertEqual(groups["BUY"][0]["player_id"], self.base_id)
                self.assertEqual(groups["SELL"][0]["player_id"], self.base_id + 1)

    def test_healthy_current_starter_remains_a_hold(self) -> None:
        context, players, recent = self.snapshot()
        groups = self.choose(context, players, recent)
        self.assertEqual(groups["HOLD"][0]["player_id"], self.base_id + 2)

    def test_reserve_keeper_with_high_ownership_and_past_minutes_is_excluded(self) -> None:
        for minutes in (0, 25, 65):
            with self.subTest(last_minutes=minutes):
                context, players, recent = self.snapshot(starting=False, last_minutes=minutes)
                groups = self.choose(context, players, recent)
                self.assertFalse(context.eligible(self.base_id + 2))
                self.assertEqual(groups["HOLD"][0]["player_id"], self.base_id + 3)

    def test_all_positions_use_the_same_starting_role_gate(self) -> None:
        for position in (1, 2, 3, 4):
            with self.subTest(position=position):
                context, players, recent = self.snapshot(starting=False, position=position)
                self.assertEqual(self.choose(context, players, recent)["HOLD"][0]["player_id"],
                                 self.base_id + 3)

    def test_forecast_or_stale_lineup_cannot_support_an_unproven_start(self) -> None:
        for changes in ({"start_probability": .4}, {"expected_minutes": 25},
                        {"last_minutes": 35}, {"stale_role": True}):
            with self.subTest(changes=changes):
                context, players, recent = self.snapshot(**changes)
                self.assertEqual(self.choose(context, players, recent)["HOLD"][0]["player_id"],
                                 self.base_id + 3)

    def test_injury_suspension_doubt_and_unverified_data_exclude_holds(self) -> None:
        for changes in ({"status": "i"}, {"status": "s"}, {"status": "d"},
                        {"verified": False}):
            with self.subTest(changes=changes):
                context, players, recent = self.snapshot(**changes)
                groups = self.choose(context, players, recent)
                self.assertNotIn(self.base_id + 2, [row["player_id"] for row in groups["HOLD"]])
                self.assertEqual(groups["BUY"][0]["player_id"], self.base_id)
                self.assertEqual(groups["SELL"][0]["player_id"], self.base_id + 1)

    def test_fitness_clearance_needs_starting_evidence_before_reentry(self) -> None:
        for changes, expected in (
            ({"status": "i"}, self.base_id + 3),
            ({"status": "a", "starting": False}, self.base_id + 3),
            ({"status": "a", "starting": True}, self.base_id + 2),
        ):
            with self.subTest(changes=changes):
                context, players, recent = self.snapshot(**changes)
                self.assertEqual(self.choose(context, players, recent)["HOLD"][0]["player_id"],
                                 expected)

    def test_no_qualifying_starters_leaves_holds_empty(self) -> None:
        context, players, recent = self.snapshot(starting=False, eligible_fallback=False)
        self.assertEqual(self.choose(context, players, recent)["HOLD"], [])

    def test_player_identity_changes_need_no_selection_source_changes(self) -> None:
        for base_id in (400, 19_000):
            with self.subTest(base_id=base_id):
                self.base_id = base_id
                context, players, recent = self.snapshot(starting=False)
                players["web_name"] = [f"Renamed {index}" for index in range(4)]
                self.assertEqual(self.choose(context, players, recent)["HOLD"][0]["player_id"],
                                 base_id + 3)


def check_notebook_hold_eligibility(path: Path) -> None:
    """Execute the production notebook's selection call with real gate computation."""
    cells = dict(_prepare_code_cells(path))
    assignments = [
        node for node in ast.parse(cells[24]).body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "_d3_desk_selection"
                for target in node.targets)
    ]
    if len(assignments) != 1:
        raise AssertionError("Expected one production Transfer Desk selection assignment")
    module = ast.Module(body=assignments, type_ignores=[])
    fixture = HoldEligibilityTests()
    fixture.setUp()
    for changes, expected in (
        ({}, fixture.base_id + 2),
        ({"starting": False}, fixture.base_id + 3),
        ({"status": "s"}, fixture.base_id + 3),
        ({"status": "i"}, fixture.base_id + 3),
        ({"starting": False, "eligible_fallback": False}, None),
        ({"verified": False}, None),
    ):
        context, players, recent = fixture.snapshot(**changes)

        def select_one(*args, **kwargs):
            return select_transfer_desk(*args, count=1, **kwargs)

        namespace = {
            "select_transfer_desk": select_one, "players": players,
            "data": {"bootstrap": {"total_players": 1_000_000}},
            "_d3_desk_recent_performance": lambda player_id: recent[player_id],
            "_d3_players_by_id": players.set_index("id"),
            "_d3_bench_eo_map": {}, "DAY3_AVAILABILITY": context,
        }
        exec(compile(module, "production_hold_selection", "exec"), namespace)
        groups = namespace["_d3_desk_selection"]
        actual = [row["player_id"] for row in groups["HOLD"]]
        assert actual == ([] if expected is None else [expected]), (changes, actual)
        assert groups["BUY"][0]["player_id"] == fixture.base_id
        assert groups["SELL"][0]["player_id"] == fixture.base_id + 1
    print("Production HOLD selection passed: starters, reserves, injury, suspension, "
          "missing evidence and empty qualified lists; market rankings preserved.")


if __name__ == "__main__":
    unittest.main()
