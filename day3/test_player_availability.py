from __future__ import annotations

import json
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


if __name__ == "__main__":
    unittest.main()
