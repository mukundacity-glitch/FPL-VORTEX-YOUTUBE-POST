from __future__ import annotations

import ast
import asyncio
import inspect
import json
import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import pandas as pd

from test_day1_player_hero import example as hero_example
from vortex.day1_player_hero import analyze

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

    def test_player_hero_scene_passes_the_production_cleanroom_gate(self):
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        gate_functions = [
            node for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and (node.name.startswith("_vx_phase0") or node.name == "vx_phase0_assert_cleanroom")
        ]
        scene = next(
            node for node in tree.body
            if isinstance(node, ast.If)
            and ast.unparse(node.test) == "SLIDE_SELECTION.get('03_projected_goals', True)"
            and any(isinstance(child, ast.ImportFrom) and "day1_player_hero" in ast.unparse(child)
                    for child in node.body)
        )
        bootstrap, fixtures, live = hero_example()

        def fetch(_session, endpoint):
            return fixtures if endpoint == "/fixtures/" else {"history": []}

        async def skip_screenshot(*_args):
            pass

        with TemporaryDirectory() as work:
            folder = Path(work)
            namespace = {
                "pd": pd, "re": re, "inspect": inspect, "Path": Path, "json": json,
                "DATA_DIR": folder, "boot": bootstrap, "live": live, "REVIEW_GW": 8,
                "SLIDE_SELECTION": {"03_projected_goals": True},
                "_fpl_module": SimpleNamespace(_vx_http_session=lambda: None, _vx_get_json=fetch),
                "resolve_player_photo": lambda _player: "",
                "vx_narration_player": lambda player: player["name"],
                "team_meta_by_id": {1: {"badge": ""}}, "vortex_logo_html": "",
                "XG_HTML_PATH": folder / "hero.html", "XG_PNG_PATH": folder / "hero.png",
                "export_4k_png": skip_screenshot,
            }
            exec(compile(ast.Module(body=gate_functions, type_ignores=[]), str(SOURCE), "exec"), namespace)
            execute_scene = compile(ast.Module(body=[scene], type_ignores=[]), str(SOURCE),
                                    "exec", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
            asyncio.run(eval(execute_scene, namespace))
            gate = namespace["vx_phase0_assert_cleanroom"]
            self.assertTrue(gate("pre-publish"))
            html = (folder / "hero.html").read_text(encoding="utf-8")
            self.assertEqual(html.count('class="profile"'), 3)
            # Confirm the existing gate still rejects the exact failing binding.
            namespace["analyze"] = analyze
            with self.assertRaisesRegex(RuntimeError, "helper_source:analyze"):
                gate("pre-publish")

    def test_measured_voice_and_subtitles_replace_short_report(self):
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn("review_voice_profile(mood, variation=", source)
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
        self.assertIn('VORTEX_DAY1_COMPACT: "1"', workflow)
        self.assertIn('VORTEX_DAY1_VIDEO_TARGET_SECONDS: "330"', workflow)
        self.assertIn('Day 1 soft 7-minute goal exceeded', workflow)
        self.assertIn('Day 1 final MP4 has missing or invalid duration', workflow)
        self.assertNotIn('Day 1 exceeds strict 7-minute MP4 limit', workflow)
        self.assertLess(workflow.index("Day 1 soft 7-minute goal exceeded"),
                        workflow.index("Upload final 4K video privately to YouTube"))


if __name__ == "__main__":
    unittest.main()
