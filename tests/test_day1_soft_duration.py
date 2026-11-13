"""Regression guard: preferred seven minutes is advisory; natural TTS is retained.

All checks are offline and work against the actual single Day 1 source/workflow.
The video's 15-player identity, 33 cells, 4K size and Private-only constraints
remain guarded by the existing tests.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Day1SoftDurationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.notebook = (ROOT / "1_final_day1.py").read_text(encoding="utf-8")
        cls.workflow = (ROOT / ".github/workflows/day-1.yml").read_text(encoding="utf-8")
        cls.package = (ROOT / "vortex/youtube_studio_package.py").read_text(encoding="utf-8")
        cls.editorial = (ROOT / "vortex/day1_editorial.py").read_text(encoding="utf-8")

    def test_complete_mp4_can_exceed_420_seconds_without_discard(self):
        self.assertIn("Day 1 soft 7-minute goal exceeded", self.workflow)
        self.assertIn("Day 1 final MP4 has missing or invalid duration", self.workflow)
        self.assertNotIn("Day 1 exceeds strict 7-minute MP4 limit", self.workflow)
        self.assertNotIn("Day 1 packaged video exceeds the seven-minute cap", self.package)
        self.assertIn("DAY1_MAX_EXPORT_SECONDS = 535.0", self.package)
        self.assertIn("combined MP4 has missing or invalid duration", self.package)

    def test_rerender_only_for_real_integrity_errors_not_pacing(self):
        snippet = self.notebook.split('if not _editorial_audio_report["within_target"]:', 1)[1]
        snippet = snippet.split("# 4. VTT", 1)[0]
        self.assertIn("pacing advisory", snippet)
        self.assertIn("print(", snippet)
        self.assertNotIn("raise RuntimeError", snippet)
        check = self.workflow.split('if narration.get("within_target") is not True:', 1)[1]
        check = check.split("if \"Expected points are forecasts", 1)[0]
        self.assertIn("Soft narration pacing target missed", check)
        self.assertNotIn("raise SystemExit", check)

    def test_no_auto_speech_rate_increase_to_meet_duration(self):
        self.assertNotIn("_needed_speed", self.notebook)
        self.assertNotIn("rate_override=_new_rate", self.notebook)
        self.assertNotIn("automatic Ryan pacing correction", self.notebook)
        self.assertIn("no voice speed correction", self.notebook)
        # WordBoundary reveal/caption mapping must remain intact.
        self.assertIn("seg[\"name_time\"]", self.notebook)
        self.assertIn("review_voice_profile(mood, variation=", self.notebook)

    def test_brief_nonspotlights_while_preserving_original_fpl_maths(self):
        self.assertIn("if not spotlight:\n        return first", self.editorial)
        self.assertIn("spotlight=int(p['id']) in spotlight_ids", self.editorial)
        self.assertIn("xpts, xmins = _model(player)", self.editorial)
        self.assertIn("Vortex model estimates", self.editorial)


if __name__ == "__main__":
    unittest.main()
