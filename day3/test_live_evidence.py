from __future__ import annotations

import copy
import json
import math
import os
import re
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from day3.evidence_narration import next_fixture_packs, player_analysis, team_analysis, validated_fixture_forecasts
from day3.live_evidence import (
    VERSION, assert_snapshot_current, audit_fixture_rows, availability, build_evidence, dc_forecast, digest,
    live_role, material_state, player_projection, save_snapshot,
)
from day3.verify_evidence import file_hash, verify_bundle


def sample_inputs() -> tuple[dict, list[dict], dict[int, dict], str]:
    now = datetime.now(timezone.utc)
    cutoff = now.isoformat()
    bootstrap = {
        "teams": [{"id": 1, "name": "Club Alpha"}, {"id": 2, "name": "Club Beta"}],
        "element_types": [{"id": 2, "singular_name_short": "DEF"}],
        "events": [{"id": 1, "deadline_time": (now - timedelta(days=7)).isoformat(), "finished": True, "data_checked": True},
                   {"id": 2, "deadline_time": (now + timedelta(days=2)).isoformat(), "finished": False, "data_checked": False}],
        "elements": [{"id": 11, "code": 1011, "team": 1, "element_type": 2, "first_name": "Alex", "second_name": "Same",
                      "web_name": "Same", "now_cost": 45, "minutes": 90, "defensive_contribution": 12,
                      "status": "a", "starts": 1, "chance_of_playing_next_round": None, "news": ""},
                     {"id": 22, "code": 1022, "team": 2, "element_type": 2, "first_name": "Jamie", "second_name": "Same",
                      "web_name": "Same", "now_cost": 40, "minutes": 80, "defensive_contribution": 8,
                      "status": "a", "starts": 1, "chance_of_playing_next_round": None, "news": ""}],
    }
    fixtures = [{"id": 1, "event": 1, "team_h": 1, "team_a": 2,
                 "kickoff_time": (now - timedelta(days=6)).isoformat(), "started": True,
                 "finished": True, "finished_provisional": True, "team_h_score": 1, "team_a_score": 3,
                 "stats": [{"identifier": "defensive_contribution", "h": [{"element": 11, "value": 12}],
                            "a": [{"element": 22, "value": 8}]}]},
                {"id": 2, "event": 2, "team_h": 2, "team_a": 1,
                 "kickoff_time": (now + timedelta(days=3)).isoformat(), "started": False,
                 "finished": False, "finished_provisional": False, "team_h_score": None, "team_a_score": None, "stats": []}]
    live = {1: {"elements": [
        {"id": player_id, "stats": {"minutes": minutes, "starts": 1, "defensive_contribution": dc},
         "explain": [{"fixture": 1, "stats": [{"identifier": "minutes", "value": minutes, "points": 2},
                                                {"identifier": "defensive_contribution", "value": dc, "points": points}]}]}
        for player_id, minutes, dc, points in ((11, 90, 12, 2), (22, 80, 8, 0))
    ]}}
    return bootstrap, fixtures, live, cutoff


class EvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bootstrap, self.fixtures, self.events, self.cutoff = sample_inputs()

    def snapshot(self) -> dict:
        return build_evidence(self.bootstrap, self.fixtures, self.events, self.cutoff)

    def test_identity_per90_and_recent_minutes_use_official_records(self) -> None:
        snapshot = self.snapshot()
        self.assertNotEqual(snapshot["players"][11]["name"], snapshot["players"][22]["name"])
        self.assertEqual(snapshot["players"][22]["rate90"], 9)
        self.assertEqual(live_role(snapshot, 11)["mean"], 90)
        self.assertEqual(live_role(snapshot, 22)["start"], 1)
        self.assertEqual(player_projection(snapshot, 11)["actions"], 12)
        self.assertEqual(player_projection(snapshot, 22)["actions"], 8)

    def test_snapshot_excludes_legacy_fixture_difficulty_fields(self) -> None:
        baseline = self.snapshot()
        for fixture in self.fixtures:
            fixture.update(team_a_difficulty=4, team_h_difficulty=2)

        snapshot = self.snapshot()
        forbidden = {"team_a_difficulty", "team_h_difficulty"}
        self.assertEqual(snapshot["source_hash"], baseline["source_hash"])
        self.assertTrue(all(forbidden.isdisjoint(fixture) for fixture in snapshot["fixtures"]))
        self.assertTrue(all(forbidden.issubset(fixture.keys()) for fixture in self.fixtures))

        with tempfile.TemporaryDirectory() as directory:
            save_snapshot(snapshot, Path(directory))
            serialized = (Path(directory) / "day3_live_evidence.json").read_text(encoding="utf-8")
        self.assertNotIn("team_a_difficulty", serialized)
        self.assertNotIn("team_h_difficulty", serialized)

    def test_missing_forecast_is_not_a_blank_or_zero(self) -> None:
        snapshot = self.snapshot()
        features = pd.DataFrame([{"player_id": 11, "team_id": 1, "position": "DEF"}])
        rows = pd.DataFrame(columns=["gameweek", "player_id", "fixture_id"])
        result = validated_fixture_forecasts(features, rows, snapshot).iloc[0]
        self.assertIsNone(result["xdefcon"])
        self.assertEqual(result["next_fixture_count"], 1)
        self.assertEqual(result["projection_status"], "MISSING_FIXTURE_FORECAST")
        _, text = player_analysis(snapshot, 11, 1, result.to_dict())
        self.assertIn("forecast is unavailable", text)
        self.assertNotIn("0.0", text)

    def test_suspension_and_blank_have_different_verified_reasons(self) -> None:
        self.bootstrap["elements"][0].update(status="s", chance_of_playing_next_round=0, news="Suspended until next month")
        snapshot = self.snapshot()
        self.assertEqual(player_projection(snapshot, 11)["reason"], "SUSPENDED")
        self.assertEqual(player_projection(snapshot, 11)["actions"], 0)
        _, text = player_analysis(snapshot, 11, 1)
        self.assertIn("Suspended until next month", text)
        self.assertNotIn("injured", text)
        self.fixtures[1]["event"] = None
        snapshot = self.snapshot()
        self.assertEqual(player_projection(snapshot, 11)["reason"], "BLANK_GAMEWEEK")

    def test_conflicting_availability_does_not_invent_an_injury(self) -> None:
        player = dict(self.bootstrap["elements"][0], chance_of_playing_next_round=0)
        self.assertEqual(availability(player), (None, "CONFLICTING_AVAILABILITY"))
        self.assertEqual(availability(dict(player, status="d", chance_of_playing_next_round=None)),
                         (None, "AVAILABILITY_UNCONFIRMED"))

    def test_no_finite_rate_does_not_become_zero(self) -> None:
        for value in (None, math.nan, math.inf):
            expected, probability = dc_forecast(value, "DEF", [(90, 1)])
            self.assertTrue(math.isnan(expected))
            self.assertTrue(math.isnan(probability))
        self.assertEqual(dc_forecast(0, "DEF", [(90, 1)]), (0, 0))

    def test_double_gameweek_scores_each_fixture_separately(self) -> None:
        second = dict(self.fixtures[1], id=3)
        self.fixtures.append(second)
        result = player_projection(self.snapshot(), 22)
        self.assertEqual(result["actions"], 16)
        self.assertLess(result["dc_points"], 4)
        self.assertEqual(len(result["fixtures"]), 2)
        single = dc_forecast(9, "DEF", [(80, 1)])[1]
        self.assertAlmostEqual(result["dc_points"], 4 * single)

    def test_duplicate_mapping_and_bad_arithmetic_are_rejected(self) -> None:
        snapshot = self.snapshot()
        features = pd.DataFrame([{"player_id": 11, "team_id": 1, "position": "DEF"}])
        valid = {"gameweek": 2, "player_id": 11, "fixture_id": 2, "expected_minutes": 90,
                 "defcon_expected_contributions": 12, "defcon_points": 1.5}
        with self.assertRaisesRegex(RuntimeError, "Duplicate"):
            validated_fixture_forecasts(features, pd.DataFrame([valid, valid]), snapshot)
        for field, value in (("defcon_expected_contributions", 0), ("defcon_points", 4), ("expected_minutes", 91)):
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                validated_fixture_forecasts(features, pd.DataFrame([dict(valid, **{field: value})]), snapshot)
        wrong = features.copy()
        wrong["team_id"] = 2
        with self.assertRaisesRegex(RuntimeError, "identity"):
            validated_fixture_forecasts(wrong, pd.DataFrame([valid]), snapshot)

    def test_bootstrap_and_event_conflicts_stop_generation(self) -> None:
        self.events[1]["elements"][0]["stats"]["defensive_contribution"] = 11
        with self.assertRaisesRegex(RuntimeError, "DC conflict"):
            self.snapshot()

    def test_minutes_explanations_must_reconcile(self) -> None:
        self.events[1]["elements"][0]["explain"][0]["stats"][0]["value"] = 89
        with self.assertRaisesRegex(RuntimeError, "minutes do not reconcile"):
            self.snapshot()

    def test_busy_defence_is_not_automatically_a_clean_sheet_target(self) -> None:
        _, text = team_analysis(self.snapshot(), 1, 1, "high", 0.1)
        self.assertIn("3 goals", text)
        self.assertIn("10 percent", text)
        self.assertIn("does not establish a strong clean-sheet target", text)

    def test_defcon_analysis_avoids_repeating_dynamic_sentences(self) -> None:
        """Different subjects must make repeated template values safe for shared narration QA."""
        snapshot = self.snapshot()
        _, alpha = team_analysis(snapshot, 1, 1, "high", 0.25)
        _, beta = team_analysis(snapshot, 2, 2, "high", 0.25)
        for player in snapshot["players"].values():
            player["recent_minutes"][-1] = 45
        _, first_player = player_analysis(snapshot, 11, 1)
        _, second_player = player_analysis(snapshot, 22, 2)
        sentences = [sentence.casefold() for text in (alpha, beta, first_player, second_player)
                     for sentence in re.split(r"(?<=[.!?])\\s+", text) if sentence]
        duplicates = {sentence for sentence in sentences if sentences.count(sentence) > 1}
        self.assertFalse(duplicates, duplicates)

    def test_changed_position_and_transfer_are_not_name_mapped(self) -> None:
        self.bootstrap["element_types"].append({"id": 3, "singular_name_short": "MID"})
        self.bootstrap["elements"][0]["element_type"] = 3
        snapshot = self.snapshot()
        self.assertEqual(snapshot["players"][11]["position"], "MID")
        # Historical actions remain attached to fixture sides even after a club change.
        self.bootstrap["teams"].append({"id": 3, "name": "Club Gamma"})
        self.bootstrap["elements"][0]["team"] = 3
        snapshot = self.snapshot()
        self.assertTrue(snapshot["players"][11]["transferred"])
        with self.assertRaisesRegex(RuntimeError, "current-club"):
            live_role(snapshot, 11)

    def test_api_outage_and_changed_material_state_fail_publication(self) -> None:
        snapshot = self.snapshot()
        def loader(path: str):
            return copy.deepcopy(self.bootstrap if path == "/bootstrap-static/" else self.fixtures)
        assert_snapshot_current(snapshot, loader)
        self.bootstrap["elements"][0]["status"] = "i"
        with self.assertRaisesRegex(RuntimeError, "changed"):
            assert_snapshot_current(snapshot, loader)
        def failed_loader(path: str):
            raise OSError("API unavailable")
        with self.assertRaises(OSError):
            assert_snapshot_current(snapshot, failed_loader)

    def test_integral_float_normalization_does_not_fake_source_changes(self) -> None:
        self.assertEqual(digest({"value": 1}), digest({"value": 1.0}))
        self.assertNotEqual(digest({"value": None}), digest({"value": 0}))

    def test_invalid_pmf_is_not_silently_normalized(self) -> None:
        for pmf in ([(90, 0.7)], [(91, 1)], [(90, -1)], [(math.nan, 1)]):
            with self.subTest(pmf=pmf), self.assertRaises(ValueError):
                dc_forecast(12, "DEF", pmf)

    def test_fixture_cards_keep_real_gameweeks_in_a_double_and_blank(self) -> None:
        self.fixtures.append(dict(self.fixtures[1], id=3))
        snapshot = self.snapshot()
        snapshot['event_ids'] += [3]
        frame = pd.DataFrame([{'fixture_id': 2, 'defence_fdr_away': 2.3},
                              {'fixture_id': 3, 'defence_fdr_away': 3.1}])
        packs = next_fixture_packs(snapshot, frame, 1, 'DEF', 3)
        self.assertEqual([row['gw'] for row in packs], [2, 2, 3])
        self.assertEqual([row['fdr_value'] for row in packs], [2.3, 3.1, None])
        self.assertEqual(packs[2]['fixture'], 'BLANK')

    def test_return_from_injury_is_a_probability_not_a_confirmed_absence(self) -> None:
        self.bootstrap['elements'][0].update(status='i', chance_of_playing_next_round=75, news='Back in training')
        snapshot = self.snapshot()
        projection = player_projection(snapshot, 11)
        self.assertEqual(projection['actions'], 9)
        _, text = player_analysis(snapshot, 11, 1)
        self.assertIn('75 percent', text)
        self.assertNotIn('no playing time', text)

    def test_stale_snapshot_is_rejected_even_if_source_hash_matches(self) -> None:
        snapshot = self.snapshot()
        snapshot['cutoff'] = (datetime.now(timezone.utc) - timedelta(hours=7)).isoformat()
        with self.assertRaisesRegex(RuntimeError, 'stale'):
            assert_snapshot_current(snapshot, lambda path: None)

    def test_expected_points_engine_cannot_reintroduce_unexplained_zero(self) -> None:
        snapshot = self.snapshot()
        row = {'player_id': 11, 'player_code': 1011, 'fixture_id': 2, 'team_id': 1,
               'gameweek': 2, 'position': 'DEF', 'expected_minutes': 90,
               'appearance_probability': 1, 'defcon_expected_contributions': 12}
        audit_fixture_rows(pd.DataFrame([row]), snapshot)
        for changes in ({'expected_minutes': 0}, {'gameweek': 3}, {'player_code': 1022},
                        {'defcon_expected_contributions': 0}, {'appearance_probability': 0.5}):
            with self.subTest(changes=changes), self.assertRaises(RuntimeError):
                audit_fixture_rows(pd.DataFrame([dict(row, **changes)]), snapshot)

    def test_publication_bundle_rejects_tampered_script_or_video(self) -> None:
        snapshot = self.snapshot()
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"GITHUB_RUN_ID": "test-run"}):
            root = Path(directory)
            data = root / "DATA"; data.mkdir()
            video = root / "MP4"; video.mkdir()
            (video / "COMBINED.mp4").write_bytes(b"verified-video")
            scripts = {"Slide_03.txt": "Current researched script."}
            (data / "Slide_03.txt").write_text(scripts["Slide_03.txt"])
            (data / "day3_live_evidence.json").write_text(json.dumps(snapshot))
            evidence = {"version": VERSION, "source_hash": snapshot["source_hash"], "next_gw": 2,
                        "run_id": "test-run", "scripts": scripts, "scripts_hash": digest(scripts),
                        "video": "COMBINED.mp4", "video_sha256": file_hash(video / "COMBINED.mp4")}
            (data / "day3_script_evidence.json").write_text(json.dumps(evidence))
            loader = lambda path: self.bootstrap if path == "/bootstrap-static/" else self.fixtures
            verify_bundle(root, loader)
            (data / "Slide_03.txt").write_text("Old script.")
            with self.assertRaisesRegex(RuntimeError, "export changed"):
                verify_bundle(root, loader)
            (data / "Slide_03.txt").write_text(scripts["Slide_03.txt"])
            (video / "COMBINED.mp4").write_bytes(b"old-video")
            with self.assertRaisesRegex(RuntimeError, "Final video"):
                verify_bundle(root, loader)


if __name__ == "__main__":
    unittest.main()
