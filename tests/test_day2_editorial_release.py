"""Day 2: no-network current-GW/editorial/video-release contract tests."""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import unittest

from day2 import editorial
from day2.release_contract import SCENES, verify_current_scene_package
from day2.youtube import _render_metadata
from day2.visuals import visual_css

ROOT = Path(__file__).resolve().parents[1]


def valid_report():
    return {
        "version": "DAY1-EXPERT-CURRENT-GW-V2", "gameweek": 10,
        "status": "verified_author_opinions",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "opinions": [
            {"gw": 10, "author": "Surya", "action": "BUY_CONSIDER",
             "topic": "transfers", "decision": "considering Tavernier or Rayan as a transfer option",
             "url": "https://allaboutfpl.com/2026/11/fpl-gw10-team-selection-drafts-transfer-plans-and-watchlist/",
             "players": [{"id": 12, "name": "Tavernier"}, {"id": 13, "name": "Rayan"}]},
            {"gw": 10, "author": "AK", "action": "BENCH", "topic": "bench",
             "decision": "leaning towards benching Schade",
             "url": "https://allaboutfpl.com/2026/11/aks-fpl-gw10-team-reveal-transfer-plans-3x-top-5k-finishes/",
             "players": [{"id": 99, "name": "Schade"}]},
            {"gw": 10, "author": "Srini", "action": "ROLL", "topic": "transfers",
             "decision": "considering keeping the free transfer",
             "url": "https://allaboutfpl.com/2026/11/fpl-gw10-team-selection-drafts-transfer-plans-and-watchlist/",
             "players": []},
        ],
    }


def model_data(gw=10):
    obj = {key: {"target_gw": gw, "model_version": "TEST-V1"} for key in SCENES}
    obj["scene_02_expected_minutes"]["featured_4"] = [
        {"id": i, "full_name": "Test Player " + str(i)} for i in range(1,5)
    ]
    obj["scene_05_top10_differentials"]["top_3_narrated"] = [
        {"id": i, "full_name": "Test Player " + str(i)} for i in range(11,14)
    ]
    return obj


class Day2EditorialTests(unittest.TestCase):
    def test_only_current_model_shortlist_influences_expert_commentary(self):
        with patch("day2.editorial._fresh", return_value=valid_report()):
            got = editorial.decisions(10, [{"id": 13}])
            self.assertEqual(got[0]["author"], "Surya")
            self.assertEqual(got[0]["action"], "BUY_CONSIDER")
            self.assertTrue(all(x["gw"] == 10 for x in got))

    def test_wrong_gw_and_missing_source_say_nothing(self):
        with patch("day2.editorial._fresh", return_value={}):
            self.assertEqual(editorial.spoken_comparison(10, [{"id": 12}]), "")
        with patch("day2.editorial._fresh", return_value=valid_report()):
            self.assertEqual(editorial.decisions(11, [{"id": 12}]), [])

    def test_voice_is_personal_not_claim_of_external_authority(self):
        with patch("day2.editorial._fresh", return_value=valid_report()):
            spoken = editorial.spoken_comparison(10, [{"id": 12}])
        self.assertIn("I've been checking", spoken)
        self.assertIn("Surya", spoken)
        self.assertIn("Tavernier or Rayan", spoken)
        self.assertIn("Vortex projections", spoken)
        self.assertNotIn("I bought Tavernier", spoken)
        self.assertNotIn("guaranteed points", spoken)

    def test_outside_model_expert_picks_are_discussed_not_promoted(self):
        model_selection = [{"id": 1}, {"id": 2}]
        with patch("day2.editorial._fresh", return_value=valid_report()):
            got = editorial.decisions(10, model_selection)
        self.assertEqual(got[0]["action"], "BUY_CONSIDER")
        self.assertEqual(got[0]["author"], "Surya")
        self.assertEqual(model_selection, [{"id": 1}, {"id": 2}],
                         "Expert talk must not modify ranked model player cards")
        self.assertTrue(all(x["gw"] == 10 for x in got))

    def test_verified_seven_scene_package(self):
        with TemporaryDirectory() as d:
            folder = Path(d) / "Data"
            folder.mkdir()
            (folder / "scene_data.json").write_text(json.dumps(model_data()), encoding="utf-8")
            context = verify_current_scene_package(d)
        self.assertEqual(context["gameweek"], 10)
        self.assertEqual(len(context["expected_minutes_players"]), 4)
        self.assertEqual(len(context["differential_players"]), 3)

    def test_mixed_gw_and_missing_roster_fail_closed(self):
        with TemporaryDirectory() as d:
            folder = Path(d) / "Data"
            folder.mkdir()
            bad = model_data()
            bad["scene_03_split_screen"]["target_gw"] = 11
            (folder / "scene_data.json").write_text(json.dumps(bad))
            with self.assertRaisesRegex(RuntimeError, "Mixed Gameweeks"):
                verify_current_scene_package(d)
            bad["scene_03_split_screen"]["target_gw"] = 10
            bad["scene_02_expected_minutes"]["featured_4"] = []
            (folder / "scene_data.json").write_text(json.dumps(bad))
            with self.assertRaisesRegex(RuntimeError, "four verified"):
                verify_current_scene_package(d)

    def test_current_gameweek_in_title_and_four_hashtags(self):
        config = json.loads((ROOT / "day2" / "metadata.json").read_text(encoding="utf-8"))
        scene_context = {"gameweek": 10,
                         "expected_minutes_players":[{"name":"Player Alpha"}] * 4,
                         "differential_players":[{"name":"Player Beta"}] * 3}
        with patch("day2.editorial.youtube_credits", return_value=""):
            item = _render_metadata(config, "2026-11-06", scene_context=scene_context)
        self.assertIn("GW10 Day 2", item["title"])
        self.assertIn("November 06", item["title"])
        self.assertIn("Player Alpha", item["description"])
        self.assertIn("Player Beta", item["description"])
        self.assertEqual(len(item["hashtags"]), 4)
        self.assertLessEqual(len(item["title"]), 100)

    def test_premium_treatments_never_change_player_card_css(self):
        css = visual_css()
        self.assertIn(".vx-topHeader", css)
        self.assertIn(".sceneTitle h1", css)
        self.assertIn("#D2AD62", css)
        self.assertNotIn(".vx-player-card", css)
        self.assertNotIn("@keyframes", css)
        source = (ROOT / "day2" / "run_notebook.py").read_text(encoding="utf-8")
        self.assertIn("_enforce_official_next_gameweek(payload)", source)
        self.assertIn("from day2.editorial import spoken_comparison", source)
        self.assertIn("scene7_audio_path", source)
        self.assertNotIn("from vortex.expert_editorial import narrator_note", source)


if __name__ == "__main__":
    unittest.main()
