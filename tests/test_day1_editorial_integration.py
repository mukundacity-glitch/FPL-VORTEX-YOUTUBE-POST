from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "1_final_day1.py"
EDITORIAL = ROOT / "vortex" / "day1_editorial.py"
WORKFLOW = ROOT / ".github" / "workflows" / "day-1.yml"


class Day1EditorialIntegrationTests(unittest.TestCase):
    def test_original_33_cells_still_compile(self):
        text = SOURCE.read_text(encoding="utf-8")
        marker = re.compile(r"(?m)(?=^# ={20,}\n# [^\n]*\bCELL\s+\d+[A-Za-z]?\b[^\n]*\n)")
        cells = [piece for piece in marker.split(text) if piece.strip()]
        self.assertEqual(len(cells), 33)
        for i, cell in enumerate(cells, 1):
            with self.subTest(cell=i):
                compile(cell, f"1_final_day1.py:cell-{i}", "exec",
                        flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT, dont_inherit=True)

    def test_real_script_builder_is_wired_into_current_data_flow(self):
        source = SOURCE.read_text(encoding="utf-8")
        self.assertEqual(source.count("build_editorial_review("), 1)
        self.assertIn("official_players=list(boot.get(\"elements\") or [])", source)
        self.assertIn("model_rows=_review_horizon_by_id", source)
        self.assertIn("review_status=GW_REVIEW_STATUS_LOCAL", source)
        self.assertIn('if event.get("is_next")', source)
        self.assertIn("validate_narration(", source)
        self.assertIn("gw_review_final_script.txt", source)

    def test_measured_voice_and_subtitles_replace_short_report(self):
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn("profile = review_voice_profile(mood)", source)
        self.assertIn('word_timed_vtt(pkg["segments"], max_words=8, max_seconds=3.8)', source)
        self.assertIn("measured_audio_report(", source)
        self.assertIn("gw_review_editorial_qa.json", source)
        self.assertNotIn("GW_REVIEW_NARRATION_WORDS>900", source)
        self.assertNotIn('profile = {"rate": "+0%", "pitch": "+0Hz", "volume": "+0%"}', source)

    def test_no_static_player_recommendations_in_editorial(self):
        source = EDITORIAL.read_text(encoding="utf-8")
        for prohibited in ("145784", "GW10", "Gibbs-White", "Tavernier", "Raya", "João Pedro"):
            with self.subTest(prohibited=prohibited):
                self.assertNotIn(prohibited, source)
        self.assertIn("current_transfer_state_verified':False", source)
        self.assertIn("Expected points are forecasts, not guaranteed returns", source)

    def test_existing_day1_pipeline_is_gatechecked_before_private_upload(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("test_day1_editorial.py", workflow)
        self.assertIn("test_day1_editorial_integration.py", workflow)
        self.assertIn("VORTEX_DAY1_VIDEO_TARGET_SECONDS", workflow)
        self.assertIn("word-level review captions", workflow)
        self.assertLess(workflow.index("Final video does not meet the eight-minute"),
                        workflow.index("Upload final 4K video privately to YouTube"))


if __name__ == "__main__":
    unittest.main()
