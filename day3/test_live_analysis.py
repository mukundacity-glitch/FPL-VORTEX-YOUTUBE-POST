from __future__ import annotations

import copy
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
import json
import subprocess
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd
import requests

from day3.defcon_analysis import annotate_players, forecast_text, narration, rank_profiles
from day3.live_evidence import EvidenceChangedError, collect, core_fingerprint, fingerprint, research_news
from day3.player_availability import AvailabilityContext
from day3.publication_validation import save_render_contract, validate_publication
from day3.run_validated import run_validated
from day3 import publish_private


class LiveAnalysisTests(unittest.TestCase):
    def setUp(self):
        now = datetime.now(timezone.utc)
        self.finished_at = (now - timedelta(days=2)).isoformat()
        self.players = [{"id": 800 + index, "code": 1800 + index, "team": 1 if index < 4 else 2,
                         "web_name": f"Surname{index}", "first_name": f"First{index}", "second_name": f"Surname{index}",
                         "element_type": 2 if index % 2 == 0 else 3, "status": "a", "minutes": 90,
                         "can_select": True, "news": "", "chance_of_playing_next_round": 100,
                         "transfers_in_event": index, "transfers_out_event": 10 - index, "selected_by_percent": "4.5"}
                        for index in range(8)]
        self.bootstrap = {"elements": self.players, "teams": [{"id": 1, "name": "Example Club"}, {"id": 2, "name": "Another Club"}],
                          "events": [{"id": 7, "is_current": True}, {"id": 8, "is_next": True,
                                      "deadline_time": (now + timedelta(days=2)).isoformat()}],
                          "element_types": [{"id": 2, "singular_name_short": "DEF"}, {"id": 3, "singular_name_short": "MID"}],
                          "game_config": {"scoring": {"defensive_contribution": {"DEF": 2, "MID": 2, "FWD": 2}}}}
        self.fixtures = [{"id": 70, "event": 7, "team_h": 1, "team_a": 2, "finished": True, "kickoff_time": self.finished_at},
                         {"id": 80, "event": 8, "team_h": 1, "team_a": 2, "finished": False,
                          "kickoff_time": (now + timedelta(days=2)).isoformat()}]
        self.research = {"checked_at": now.isoformat(), "gameweek": 8, "bootstrap": self.bootstrap, "fixtures": self.fixtures,
                         "scoring": {"thresholds": {"DEF": 10, "MID": 12, "FWD": 12},
                                     "points_by_position": {"DEF": 2, "MID": 2, "FWD": 2}},
                         "news": {"players": {}, "coverage": {"1": {"primary": True}, "2": {"press_search": True}}, "fingerprint": "news"},
                         "histories": {str(row["id"]): {"history": [{"element": row["id"], "fixture": 70, "round": 7,
                             "was_home": row["team"] == 1, "kickoff_time": self.finished_at,
                             "starts": 1, "minutes": 90, "defensive_contribution": 12}]} for row in self.players}}
        self.research["core_fingerprint"] = core_fingerprint(self.bootstrap, self.fixtures, 8)
        self.features = pd.DataFrame([{"player_id": row["id"], "team_id": row["team"],
                                      "position": "DEF" if row["element_type"] == 2 else "MID",
                                      "start_probability": .95, "expected_minutes": 85} for row in self.players])
        self.model = self.features.assign(fixture_id=80, gameweek=8, calculation_status="READY", fixture_expected_points=5,
                                          defcon_expected_contributions=11, defcon_points=1.5)

    def context(self):
        context = AvailabilityContext(self.bootstrap, pd.DataFrame(self.fixtures), 8,
                                      {"source": "LIVE_FPL_API", "fallback_used": False}, research=self.research)
        context.bind_model(self.features, pd.DataFrame(), pd.DataFrame(self.players), str(datetime.now().year))
        return context

    def board(self, context, model):
        frame = self.features.assign(cumulative_dc=[99, 90, 80, 70, 60, 50, 40, 30], dc_per90=12,
                                     minutes_per_appearance=85, xdefcon=11, next_dc_points=1.5,
                                     dc_hit_rate=.75, dc_hits=3, appearances=4)
        return annotate_players(frame, context, model)

    def test_suspension_overrides_strong_history_and_promotes_an_eligible_alternative(self):
        self.players[0]["status"] = "s"
        context = self.context()
        model = context.validate_projections(self.model)
        result = rank_profiles(self.board(context, model))
        self.assertFalse(context.eligible(800))
        self.assertEqual(context.state(800)["label"], "SUSPENDED")
        self.assertNotIn(800, result.head(5).player_id.tolist())
        self.assertIn(805, result.head(5).player_id.tolist())
        self.assertEqual(result.loc[result.player_id.eq(800), "cumulative_dc"].iloc[0], 99)

    def test_every_player_uses_the_same_injury_transfer_and_conflicting_report_rules(self):
        for player in self.players:
            for change in ({"status": "i"}, {"can_select": False}, {"removed": True}):
                original = dict(player)
                player.update(change)
                context = self.context()
                self.assertFalse(context.eligible(player["id"]))
                player.clear(); player.update(original)
            self.research["news"]["players"][str(player["id"])] = [{"unresolved_concern": True}]
            self.assertEqual(self.context().state(player["id"])["label"], "TEAM NEWS CHECK")
            self.research["news"]["players"].clear()

    def test_current_official_history_replaces_missing_or_stale_core_lineups(self):
        context = self.context()
        self.assertTrue(context.eligible(800))
        role = context.model_roles(pd.DataFrame(), 800, 1800, "current")
        self.assertEqual(role.iloc[0].minutes_played, 90)
        self.research["histories"]["800"]["history"][0].update(starts=0, minutes=0)
        self.assertFalse(self.context().eligible(800))
        self.research["histories"]["800"]["history"][0]["was_home"] = False
        self.assertEqual(self.context().current_history(800), [])

    def test_unknown_zero_missing_fixture_bad_identity_and_dgw_gaps_are_never_recommendations(self):
        mutations = [lambda frame: frame.assign(defcon_expected_contributions=0),
                     lambda frame: frame.assign(defcon_expected_contributions=float("nan")),
                     lambda frame: frame.assign(team_id=999), lambda frame: frame.assign(calculation_status="PENDING"),
                     lambda frame: frame.assign(expected_minutes=100), lambda frame: frame.iloc[:0]]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                context = self.context()
                result = context.validate_projections(mutate(self.model))
                self.assertFalse(context.eligible(800))
                if len(result): self.assertFalse(result.projection_verified.any())
        self.fixtures.append(dict(self.fixtures[1], id=81))
        context = self.context(); projected = context.validate_projections(self.model)
        self.assertFalse(context.eligible(800))
        self.assertEqual(forecast_text(self.board(context, projected).iloc[0]), "—")

    def test_true_zero_needs_explicit_zero_action_history_and_is_not_a_missing_value(self):
        for item in self.research["histories"].values(): item["history"][0]["defensive_contribution"] = 0
        context = self.context()
        result = context.validate_projections(self.model.assign(defcon_expected_contributions=0, defcon_points=0))
        self.assertTrue(result.projection_verified.all())
        self.assertEqual(forecast_text({"xdefcon": 0, "projection_verified": True}), "0.0")
        self.assertEqual(forecast_text({"xdefcon": 0, "projection_verified": False}), "—")

    def test_position_thresholds_and_narration_follow_live_classification(self):
        context = self.context(); model = context.validate_projections(self.model)
        board = rank_profiles(self.board(context, model)).head(5)
        self.assertEqual(board.loc[board.position.eq("DEF"), "positional_threshold"].iloc[0], 10)
        self.assertEqual(board.loc[board.position.eq("MID"), "positional_threshold"].iloc[0], 12)
        teams = pd.DataFrame([{"team_id": index, "dc_for": 100 - index, "dc_for_per_game": 15,
                               "xdefcon": 20, "projection_verified": True} for index in range(1, 7)])
        text, cues = narration({"DAY3_AVAILABILITY": context, "DAY3_DEFCON_TARGETS": board,
            "DAY3_DEFCON_TEAMS": teams, "DAY3_DEFCON_TOP_TEAMS": teams.head(5), "DAY3_DEFCON_AVOID_TEAMS": teams.tail(3),
            "vx_narration_player": lambda pid: f"Name{pid}", "vx_narration_team": lambda tid: f"Club{tid}"})
        self.assertIn("12-action threshold", text)
        self.assertIn("10-action threshold", text)
        self.assertIn("workload, not defensive quality", text)
        self.assertNotIn("number one", text)
        self.assertEqual(len(cues["individual"]), 5)
        self.assertEqual(cues["individual"][0]["player_id"], int(board.iloc[0].player_id))

    def test_research_uses_all_player_ids_and_blocks_unverified_or_mismatched_history(self):
        fixture = self
        class Client:
            def json(self, url):
                if url.endswith("bootstrap-static/"):return fixture.bootstrap
                if url.endswith("fixtures/"):return fixture.fixtures
                pid = url.rstrip("/").split("/")[-1]
                return fixture.research["histories"][pid]
            def text(self, url):
                if "2174909" in url:return "For 10 defensive contributions by a defender 2 For 12 defensive contributions by a midfielder 2 For 12 defensive contributions by a forward 2"
                return "<rss><channel></channel></rss>"
        result = collect(self.bootstrap, self.fixtures, 8, client=Client())
        self.assertEqual(set(result["histories"]), {str(row["id"]) for row in self.players})
        self.assertEqual(result["history_errors"], {})
        different = copy.deepcopy(self.bootstrap);different["elements"][0]["status"] = "s"
        with self.assertRaises(EvidenceChangedError):collect(different, self.fixtures, 8, client=Client())

    def test_material_fingerprint_ignores_transfer_count_drift_but_tracks_status_position_price_and_fixture_changes(self):
        original = core_fingerprint(self.bootstrap, self.fixtures, 8)
        changed = copy.deepcopy(self.bootstrap);changed["elements"][7]["transfers_in_event"] += 1
        self.assertEqual(original, core_fingerprint(changed, self.fixtures, 8))
        for key, value in (("status", "s"), ("element_type", 3), ("now_cost", 90), ("team", 2)):
            changed = copy.deepcopy(self.bootstrap);changed["elements"][0][key] = value
            self.assertNotEqual(original, core_fingerprint(changed, self.fixtures, 8))
        canonical = pd.DataFrame(self.fixtures).to_dict("records")
        self.assertEqual(original, core_fingerprint(self.bootstrap, canonical, 8))

    def test_news_matches_player_identity_and_its_own_sentence_without_inventing_clearance(self):
        self.players[0]["scout_news_link"] = "https://club.example/news/fitness"
        published = datetime.now(timezone.utc).isoformat()
        class Client:
            def text(self, url):
                if "club.example" in url:
                    return (f'<html><head><title>Team update</title><meta property="article:published_time" content="{published}"></head><body>'
                            '<p>First0 Surname0 is injured.</p><p>First1 Surname1 trained as usual.</p></body></html>')
                return "<rss><channel></channel></rss>"
        news = research_news(self.bootstrap, Client())
        self.assertTrue(news["players"]["800"][0]["unresolved_concern"])
        self.assertFalse(news["players"]["801"][0]["unresolved_concern"])
        self.assertEqual(news["players"]["800"][0]["certainty"], "REPORTED_NOT_MEDICAL_CLEARANCE")
        self.research["news"] = news
        self.assertFalse(self.context().eligible(800))
        self.assertTrue(self.context().eligible(801))

    def test_failed_or_stale_research_does_not_qualify_a_player(self):
        class Client:
            def text(self, url): raise requests.Timeout("source unavailable")
        self.research["news"] = research_news(self.bootstrap, Client())
        self.assertTrue(self.research["news"]["errors"])
        self.assertFalse(self.context().eligible(800))
        self.research["checked_at"] = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
        self.assertEqual(self.context().state(800)["label"], "EVIDENCE STALE")

    def test_positional_thresholds_are_read_again_instead_of_frozen_to_one_season(self):
        fixture = self
        class Client:
            def json(self, url):
                if url.endswith("bootstrap-static/"):return fixture.bootstrap
                if url.endswith("fixtures/"):return fixture.fixtures
                return fixture.research["histories"][url.rstrip("/").split("/")[-1]]
            def text(self, url):
                if "2174909" in url:return "For 11 defensive contributions by a defender 2 For 14 defensive contributions by a midfielder 2 For 14 defensive contributions by a forward 2"
                return "<rss><channel></channel></rss>"
        result = collect(self.bootstrap, self.fixtures, 8, client=Client())
        self.assertEqual(result["scoring"]["thresholds"], {"DEF": 11, "MID": 14, "FWD": 14})

    def test_publication_is_tied_to_current_evidence_and_the_actual_rendered_files(self):
        context = self.context()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary);(root/"SLIDE").mkdir();(root/"SLIDE"/"sample.png").write_bytes(b"image")
            save_render_contract({"DAY3_AVAILABILITY": context, "OUTPUT_ROOT": root})
            with patch("day3.publication_validation.collect", return_value=self.research):
                self.assertEqual(validate_publication(root)["gameweek"], 8)
                changed = copy.deepcopy(self.research); changed["news"]["fingerprint"] = "new report"
                with patch("day3.publication_validation.collect", return_value=changed):
                    with self.assertRaises(EvidenceChangedError):validate_publication(root)
                (root/"SLIDE"/"sample.png").write_bytes(b"changed")
                with self.assertRaises(EvidenceChangedError):validate_publication(root)

    def test_late_news_change_triggers_regeneration_with_no_schedule_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary);(root/"DATA").mkdir()
            (root/"DATA"/"analysis_render_contract.json").write_text(json.dumps({"artifacts": {}}))
            with patch("day3.run_validated.subprocess.run") as render, patch("day3.run_validated.validate_publication",
                    side_effect=[EvidenceChangedError("changed"), {"verified": True}]) as validate:
                run_validated(Path("notebook.ipynb"), root)
                self.assertEqual(render.call_count, 2)
                self.assertEqual(validate.call_count, 2)

    def test_change_at_the_final_upload_check_rebuilds_before_any_upload(self):
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            root = Path(temporary);(root/"DATA").mkdir()
            notebook = root/"source.ipynb";notebook.write_text("{}")
            stack.enter_context(patch.dict("os.environ", {"DAY3_NOTEBOOK_PATH": str(notebook)}))
            stack.enter_context(patch.object(publish_private, "_one_final_video", return_value=root/"video.mp4"))
            stack.enter_context(patch.object(publish_private, "_probe_video", return_value={"width":3840,"height":2160}))
            stack.enter_context(patch.object(publish_private, "_infer_gameweeks", return_value=(8,7)))
            stack.enter_context(patch.object(publish_private, "_build_thumbnail", return_value=root/"thumb.jpg"))
            stack.enter_context(patch.object(publish_private, "validate_publication", side_effect=[EvidenceChangedError("late news"), {}]))
            rebuild = stack.enter_context(patch.object(publish_private, "run_validated"))
            discard = stack.enter_context(patch.object(publish_private, "discard_rendered_artifacts"))
            stack.enter_context(patch.object(publish_private, "_youtube_service"))
            stack.enter_context(patch.object(publish_private, "_verify_channel", return_value={"id":"test"}))
            upload = stack.enter_context(patch.object(publish_private, "_upload_video", return_value="test-video"))
            stack.enter_context(patch.object(publish_private, "_set_thumbnail"))
            stack.enter_context(patch.object(publish_private, "_verify_private"))
            result = publish_private.publish(root,"ROLL","AUTO")
            rebuild.assert_called_once_with(notebook,root)
            discard.assert_called_once_with(root)
            upload.assert_called_once()
            self.assertEqual(result["status"],"private_draft_ready")

    def test_evidence_race_during_initial_collection_restarts_without_hiding_other_failures(self):
        with (patch("day3.run_validated.subprocess.run", side_effect=[subprocess.CalledProcessError(75, "render"), None]) as render,
              patch("day3.run_validated.validate_publication")):
            run_validated(Path("source.ipynb"), Path("output"))
            self.assertEqual(render.call_count, 2)
        with patch("day3.run_validated.subprocess.run", side_effect=subprocess.CalledProcessError(1, "render")):
            with self.assertRaises(subprocess.CalledProcessError):run_validated(Path("source.ipynb"), Path("output"))


if __name__ == "__main__":
    unittest.main()
