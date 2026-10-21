from __future__ import annotations

import json
import re
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from day3.availability_visuals import decorate_availability_html, install_availability_presentation
from day3.player_availability import AvailabilityContext, chance_field, player_health
from day3.transfer_desk import select_transfer_desk


class AvailabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime.now(timezone.utc)
        self.season = f"{self.now.year}-{str(self.now.year + 1)[-2:]}"
        self.events = [{"id": 8, "is_current": True}, {"id": 9, "is_next": True}]
        self.player = {
            "id": 901, "code": 9901, "team": 1, "web_name": "Example",
            "status": "a", "chance_of_playing_this_round": 0,
            "chance_of_playing_next_round": 100, "news": "",
        }
        self.fixtures = pd.DataFrame([
            {"id": 80, "event": 8, "team_h": 1, "team_a": 2, "finished": True,
             "kickoff_time": (self.now - timedelta(days=2)).isoformat()},
            {"id": 90, "event": 9, "team_h": 1, "team_a": 2, "finished": False,
             "kickoff_time": (self.now + timedelta(days=3)).isoformat()},
        ])
        self.features = pd.DataFrame([{
            "player_id": 901, "start_probability": 0.95, "expected_minutes": 85,
        }])
        self.roles = pd.DataFrame([{
            "player_code": 9901, "season_label": self.season, "match_id": "test-prem-80",
            "match_date": (self.now - timedelta(days=2)).isoformat(),
            "minutes_played": 90, "is_starting": True,
        }])

    def context(self, player=None, source=None, roles=None, features=None, fixtures=None):
        player = self.player if player is None else player
        context = AvailabilityContext(
            {"elements": [player], "events": self.events},
            self.fixtures if fixtures is None else fixtures, 9,
            source if source is not None else {"source": "LIVE_FPL_API", "fallback_used": False},
        )
        context.bind_model(
            self.features if features is None else features,
            self.roles if roles is None else roles,
            pd.DataFrame([player]), self.season,
        )
        return context

    def test_round_probability_uses_official_event_pointer(self) -> None:
        self.assertEqual(chance_field(self.events, 8), "chance_of_playing_this_round")
        self.assertEqual(chance_field(self.events, 9), "chance_of_playing_next_round")
        self.assertIsNone(chance_field(self.events, 10))
        self.assertEqual(player_health(self.player, self.events, 8, verified=True)["probability"], 0)
        self.assertEqual(player_health(self.player, self.events, 9, verified=True)["probability"], 1)

    def test_explicit_unavailability_wins_over_one_hundred_percent_and_strong_history(self) -> None:
        for status in ("i", "s", "u", "n"):
            with self.subTest(status=status):
                context = self.context({**self.player, "status": status,
                                        "news": "Expected back after the next fixture"})
                state = context.state(901)
                self.assertEqual(context.probability(901), 0)
                self.assertFalse(context.eligible(901))
                self.assertEqual(state["color"], "red")
                self.assertIn("official availability update", context.caution(901))

    def test_no_calendar_based_return_or_player_name_exceptions(self) -> None:
        for name in ("Arbitrary Player", "Renamed Keeper", "Different Midfielder"):
            with self.subTest(name=name):
                context = self.context({**self.player, "web_name": name, "status": "s",
                                        "news": "Suspended until 1 January 2001"})
                self.assertFalse(context.eligible(901))
                self.assertEqual(context.probability(901), 0)
        cleared = self.context({**self.player, "status": "a", "news": ""})
        self.assertTrue(cleared.eligible(901))
        self.assertEqual(cleared.state(901)["starting_status"], "PROJECTED STARTER")
        self.assertIn("not a confirmed lineup", cleared.state(901)["reason"])

    def test_fitness_clearance_without_a_starting_role_is_not_a_recommendation(self) -> None:
        for starts, minutes in ((False, 0), (False, 25), (True, 35)):
            with self.subTest(starts=starts, minutes=minutes):
                roles = self.roles.copy()
                roles["is_starting"], roles["minutes_played"] = starts, minutes
                context = self.context(roles=roles)
                self.assertFalse(context.eligible(901))
                self.assertEqual(context.state(901)["label"], "MINUTES RISK")
        features = self.features.copy()
        features["start_probability"] = 0.4
        self.assertFalse(self.context(features=features).eligible(901))

    def test_shared_cautions_keep_each_sentence_specific_to_the_player(self) -> None:
        for label in ("MINUTES RISK", "SUSPENDED", "STATUS UNVERIFIED", "BLANK GAMEWEEK"):
            for include_news in (True, False):
                with self.subTest(label=label, include_news=include_news):
                    context = self.context()
                    context.players.clear()
                    for index in range(5):
                        player_id = 1000 + index
                        state = player_health({**self.player, "id": player_id,
                                               "web_name": f"Player {player_id}"},
                                              self.events, 9, verified=True)
                        state.update(
                            label=label, recommendation_eligible=False,
                            health_clear=label in {"MINUTES RISK", "BLANK GAMEWEEK"},
                            blocked=label == "SUSPENDED",
                            reason=("A secure starting role is not supported by current forecasts "
                                    "and the latest completed league lineup.")
                            if label == "MINUTES RISK" else "Shared provider notice. Awaiting an update.",
                            start_probability=0.4, expected_minutes=35.0,
                        )
                        context.players[player_id] = state
                    text = " ".join(context.caution(player_id, include_news=include_news)
                                    for player_id in context.players)
                    sentences = [re.sub(r"\s+", " ", sentence.strip().lower())
                                 for sentence in re.split(r"(?<=[.!?])\s+", text) if sentence.strip()]
                    self.assertEqual(len(sentences), len(set(sentences)))
                    for player_id in context.players:
                        self.assertIn(f"Player {player_id}", context.caution(player_id))
                    if label == "MINUTES RISK" and include_news:
                        self.assertIn("40 percent", text)
                        self.assertIn("35 expected minutes", text)

    def test_missing_forecasts_do_not_become_zero_minute_claims(self) -> None:
        context = self.context(roles=pd.DataFrame(), features=pd.DataFrame([{
            "player_id": 901, "start_probability": None, "expected_minutes": float("nan"),
        }]))
        text = context.caution(901)
        self.assertIn("secure starting role", text)
        self.assertNotIn("0 expected minutes", text)
        self.assertNotIn("nan", text)

    def test_old_missing_and_cup_lineups_never_confirm_a_league_start(self) -> None:
        for change in (
            {"match_date": (self.now - timedelta(days=30)).isoformat()},
            {"match_id": "test-cup-80"},
            {"season_label": f"{self.now.year - 1}-{str(self.now.year)[-2:]}"},
        ):
            with self.subTest(change=change):
                roles = self.roles.copy()
                for key, value in change.items():
                    roles[key] = value
                self.assertFalse(self.context(roles=roles).eligible(901))
        self.assertFalse(self.context(roles=pd.DataFrame()).eligible(901))

    def test_doubtful_missing_or_invalid_status_and_stale_source_are_not_assumed_safe(self) -> None:
        for status, chance in (("d", 75), ("d", None), ("a", 50), ("", 100), ("unexpected", 100)):
            with self.subTest(status=status, chance=chance):
                self.assertFalse(self.context({
                    **self.player, "status": status, "chance_of_playing_next_round": chance,
                }).eligible(901))
        for source in (
            {}, {"source": "RECENT_LAST_KNOWN_GOOD", "fallback_used": True},
            {"source": "LIVE_FPL_API", "fallback_used": True},
        ):
            context = self.context(source=source)
            self.assertFalse(context.eligible(901))
            self.assertEqual(context.probability(901), 0)
            self.assertEqual(context.state(901)["label"], "STATUS UNVERIFIED")
        self.assertFalse(self.context().eligible(999999))

    def test_malformed_chance_does_not_become_available(self) -> None:
        for invalid in ("bad", -1, 101, float("nan")):
            with self.subTest(chance=invalid):
                context = self.context({**self.player, "chance_of_playing_next_round": invalid})
                self.assertFalse(context.eligible(901))
                self.assertEqual(context.probability(901), 0)

    def test_available_with_null_chance_and_live_status_is_supported(self) -> None:
        self.assertTrue(self.context({
            **self.player, "chance_of_playing_next_round": None,
        }).eligible(901))

    def test_blank_gameweek_and_audit_are_explicit(self) -> None:
        context = self.context(fixtures=self.fixtures.head(1))
        self.assertFalse(context.eligible(901))
        self.assertEqual(context.state(901)["label"], "BLANK GAMEWEEK")
        with tempfile.TemporaryDirectory() as directory:
            context.save_audit(Path(directory))
            report = json.loads((Path(directory) / "player_availability_audit.json").read_text())
            self.assertFalse(report["players"]["901"]["recommendation_eligible"])
            self.assertEqual(report["gameweek"], 9)

    def test_annotated_high_scoring_suspended_player_ranks_after_safe_targets(self) -> None:
        context = self.context()
        context.players[902] = player_health({
            **self.player, "id": 902, "status": "s", "web_name": "Historical Leader",
        }, self.events, 9, verified=True)
        candidates = pd.DataFrame([
            {"player_id": 902, "cumulative_dc": 9999},
            {"player_id": 901, "cumulative_dc": 10},
        ])
        ranked = context.annotate(candidates).sort_values(
            ["recommendation_eligible", "cumulative_dc"], ascending=[False, False],
        )
        self.assertEqual(ranked.player_id.tolist(), [901, 902])
        self.assertEqual(ranked.iloc[1].official_status_label, "SUSPENDED")

    def test_hold_selection_replaces_ineligible_players_without_affecting_market_trends(self) -> None:
        players = pd.DataFrame([
            {"id": 1, "selected_by_percent": 10, "transfers_in_event": 100, "transfers_out_event": 0},
            {"id": 2, "selected_by_percent": 10, "transfers_in_event": 0, "transfers_out_event": 100},
            {"id": 3, "selected_by_percent": 30, "transfers_in_event": 0, "transfers_out_event": 0},
            {"id": 4, "selected_by_percent": 20, "transfers_in_event": 0, "transfers_out_event": 0},
        ])
        recent = {player_id: {"points": 2, "gameweeks": 2} for player_id in (1, 2, 3, 4)}
        result = select_transfer_desk(
            players, total_managers=10000, recent_performance=recent, count=1,
            eligible_hold_ids={4},
        )
        self.assertEqual([row["player_id"] for row in result["BUY"]], [1])
        self.assertEqual([row["player_id"] for row in result["SELL"]], [2])
        self.assertEqual([row["player_id"] for row in result["HOLD"]], [4])
        empty = select_transfer_desk(
            players, total_managers=10000, recent_performance=recent, count=1,
            eligible_hold_ids=set(),
        )
        self.assertEqual(empty["HOLD"], [])

    def test_html_status_is_injected_once_and_escapes_provider_text(self) -> None:
        context = self.context({**self.player, "status": "s", "news": '</script><script>alert("bad")</script>'})
        html = decorate_availability_html("<html><head></head><body></body></html>", context.public_registry())
        again = decorate_availability_html(html, context.public_registry())
        self.assertEqual(again.count('id="vx-player-status-runtime"'), 1)
        self.assertEqual(again.count('id="vx-player-status-css"'), 1)
        self.assertNotIn('</script><script>alert', again)
        self.assertIn("SUSPENDED", again)
        namespace = {"DAY3_AVAILABILITY": context, "vx_polish_branding": lambda html, **kwargs: html}
        install_availability_presentation(namespace)
        original = namespace["vx_polish_branding"]
        install_availability_presentation(namespace)
        self.assertIs(namespace["vx_polish_branding"], original)
        self.assertIn("VX_PLAYER_AVAILABILITY", original("<html><head></head><body></body></html>"))



def check_notebook_availability(notebook_path: Path) -> None:
    import ast
    import re
    import numpy as np
    from day3.run_notebook import _prepare_code_cells

    cells = dict(_prepare_code_cells(notebook_path))

    def load_function(cell_index, name, namespace):
        tree = ast.parse(cells[cell_index])
        functions = [node for node in ast.walk(tree)
                     if isinstance(node, ast.FunctionDef) and node.name == name]
        if len(functions) != 1:
            raise AssertionError(f"Expected one actual notebook function: {name}")
        exec(compile(ast.Module(body=functions, type_ignores=[]), name, "exec"), namespace)
        return namespace[name]

    fixture = AvailabilityTests()
    fixture.setUp()
    context = fixture.context({**fixture.player, "status": "s", "news": "Suspended until official clearance"})
    namespace = {"DAY3_AVAILABILITY": context, "pd": pd, "np": np, "re": re}
    probability = load_function(18, "_vx_phase10_availability", namespace)
    assert probability({"player_id": 901, "status": "a", "chance_of_playing_next_round": 100}) == 0
    for name in ("_d3_plan_player_text", "_d3_transfer_plan_player_text"):
        namespace["vx_narration_player"] = lambda player_id: f"Player {player_id}"
        text = load_function(30, name, namespace)({"id": 901})
        assert "Suspended" in text and "official availability update" in text
        assert "He starts" not in text
    context.players.clear()
    records = []
    for index in range(20):
        player_id = 1000 + index
        state = player_health({
            **fixture.player, "id": player_id, "status": "s" if index == 0 else "a",
            "web_name": f"Player {player_id}",
            "news": "Official suspension notice" if index == 0 else "",
        }, fixture.events, 9, verified=True)
        state["recommendation_eligible"] = index != 0
        context.players[player_id] = state
        records.append({
            "player_id": player_id, "player_name": f"Player {player_id}", "team_id": 1,
            "defcon_eligible": True, "minutes_per_appearance": 90.0,
            "cumulative_dc": 1000 - index, "dc_per90": 12.0,
            "previous_defcon": 10.0, "xdefcon": 0.0 if index == 0 else 11.0,
            "next_fixtures": [{"fixture": "Example (H)"}],
        })
    candidates = context.annotate(pd.DataFrame(records))
    namespace.update(_d3_def_features=candidates, PHASE10_DEFCON_MIN_AVG_MINUTES=70)
    assignments = [
        node for node in ast.parse(cells[24]).body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "_d3_def_cards" for target in node.targets)
        and "recommendation_eligible" in ast.unparse(node.value)
    ]
    assert len(assignments) == 1
    exec(compile(ast.Module(body=assignments, type_ignores=[]), "actual-defcon-ranking", "exec"), namespace)
    ranked = namespace["_d3_def_cards"]
    assert ranked.iloc[0].player_id == 1001 and ranked.iloc[-1].player_id == 1000

    teams = pd.DataFrame([{
        "team_id": index + 1, "team_name": f"Club {index + 1}",
        "dc_for": 1000 - index, "dc_for_per_game": 50.0 + index, "xdefcon": 55.0 + index,
    } for index in range(20)])
    namespace.update(
        DAY3_DEFCON_PLAYERS=ranked, DAY3_DEFCON_TARGETS=ranked.head(5),
        DAY3_DEFCON_TEAMS=teams, DAY3_DEFCON_TOP_TEAMS=teams.head(5),
        DAY3_DEFCON_AVOID_TEAMS=teams.tail(3),
        vx_narration_player=lambda player_id: f"Player {player_id}",
        vx_narration_team=lambda team_id: f"Club {team_id}",
    )
    narrate = load_function(32, "_d3_defcon_narration", namespace)

    def check_sentence_guard(text: str) -> None:
        guards = [node for node in ast.walk(ast.parse(cells[32]))
                  if isinstance(node, ast.For) and isinstance(node.target, ast.Tuple)
                  and [getattr(target, "id", None) for target in node.target.elts]
                  == ["_scene_key", "_scene_text"] and "_duplicates =" in ast.unparse(node)]
        assert len(guards) == 1
        guard_namespace = {**namespace, "scripts": {"03_defcon": text}, "_scene_sentence_sets": {}}
        exec(compile(ast.Module(body=guards, type_ignores=[]), "actual-scene-sentence-guard", "exec"),
             guard_namespace)

    safe_text = narrate()
    check_sentence_guard(safe_text)
    assert "Official suspension notice" not in safe_text
    assert len(namespace["DEFCON_NARRATION_CUES"]["individual"]) == 5

    # Sparse evidence remains an honest watchlist; it never promotes blocked players.
    for state in context.players.values():
        state.update(recommendation_eligible=False, health_clear=False, blocked=True,
                     label="SUSPENDED", color="red", reason="Suspended: Official suspension notice")
    watch_text = narrate()
    check_sentence_guard(watch_text)
    assert watch_text.count("not an active target") == 5
    assert "Official suspension notice" in watch_text
    assert len(namespace["DEFCON_NARRATION_CUES"]["individual"]) == 5

    # Run #121 failed with several healthy players sharing the same minutes-risk warning.
    for state in context.players.values():
        state.update(health_clear=True, blocked=False, label="MINUTES RISK", color="yellow",
                     reason="A secure starting role is not supported by current forecasts and the latest completed league lineup.",
                     start_probability=0.4, expected_minutes=35.0)
    risk_text = narrate()
    check_sentence_guard(risk_text)
    assert risk_text.count("not an active target") == 5
    assert [row["player_id"] for row in namespace["DEFCON_NARRATION_CUES"]["individual"]] == ranked.head(5).player_id.tolist()

    for state in context.players.values():
        state.update(health_clear=False, blocked=True, label="SUSPENDED",
                     reason="Suspended: Official suspension notice")

    namespace.update(
        DAY3_TRANSFER_DESK={"BUY": [{"player_id": 1001, "team_id": 1,
                                    "next_fixture": "Example (H)", "next_fdr": 3, "xpts": 0}],
                           "HOLD": [], "SELL": []},
    )
    desk_text = load_function(24, "_d3_desk_narr", namespace)("BUY", 0)
    assert "not an active recommendation" in desk_text and "Official suspension notice" in desk_text
    assert "leading target" not in desk_text
    print("Actual notebook integration: availability, DEFCON ranking/narration, squad plans, market warnings and cue identities PASS")


if __name__ == "__main__":
    unittest.main()

