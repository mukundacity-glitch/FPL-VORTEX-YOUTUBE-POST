"""Source-level contract for the Day 1 side-hero player card.

The pixel-level "never overlaps scene text" proof is tools/hero_card_audit
(needs Chromium); these tests pin the data mapping and hero-slot geometry.
"""
from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "1_final_day1.py").read_text(encoding="utf-8")


def _string_literal(name: str) -> str:
    for node in ast.parse(SOURCE).body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name) and node.targets[0].id == name):
            return ast.literal_eval(node.value)
    raise AssertionError(f"{name} not found")


def _load_helpers(*names: str) -> dict:
    wanted = set(names)
    nodes = [n for n in ast.parse(SOURCE).body
             if isinstance(n, ast.FunctionDef) and n.name in wanted]
    assert {n.name for n in nodes} == wanted
    namespace: dict = {}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "card-helpers", "exec"), namespace)
    return namespace


class Day1PlayerCardTests(unittest.TestCase):
    def test_design_version_and_runtime_agree(self):
        version = re.search(r'PLAYER_CARD_DESIGN_VERSION = "([^"]+)"', SOURCE).group(1)
        self.assertEqual(version, "V6.0_SIDE_HERO_SAMPLE")
        self.assertIn(f'version:"{version}"', _string_literal("PLAYER_CARD_JS"))

    def test_card_has_the_supplied_sample_sections(self):
        js = _string_literal("PLAYER_CARD_JS")
        for section in ("NEXT 5 FIXTURES", "OWNERSHIP", "PRICE", "FDR:", "EASY", "VERY HARD"):
            with self.subTest(section=section):
                self.assertIn(section, js)
        self.assertIn("slice(0,6)", js, "exactly six stat rows")
        self.assertIn("slice(0,5)", js, "exactly five fixtures")

    def test_hero_slot_pops_up_on_the_left_clear_of_edge_and_pitch(self):
        css = _string_literal("CSS")
        slot = re.search(r"#vxHeroWrap\{(.*?)\}", css, flags=re.S).group(1)
        # .left starts at x=54 and the pitch at x=1286: 24px from the screen
        # edge, and 18px of the 1202px column to spare before the pitch.
        self.assertIn("left:-30px", slot)
        self.assertIn("right:-12px", slot)
        self.assertIn("transform-origin:left center", slot)
        self.assertIn("translateX", _string_literal("JS"))

    def test_clean_sheet_percentage_is_current_season_and_honest(self):
        h = _load_helpers("_pc_pct_per90")
        self.assertEqual(h["_pc_pct_per90"](9, 1557), "52%")
        self.assertEqual(h["_pc_pct_per90"](0, 900), "0%")
        self.assertEqual(h["_pc_pct_per90"](3, 0), "—")
        self.assertEqual(h["_pc_pct_per90"](None, 900), "—")

    def test_stat_rows_follow_the_sample_order_for_every_position(self):
        block = re.search(r'pos = str\(p\.get\("pos", ""\)\)\.upper\(\)\n(.*?)\n    fixture = p\.get', SOURCE, re.S).group(1)
        labels = re.findall(r'"label":"([^"]+)"', block)
        defender = ["xG PER 90", "xA PER 90", "GOALS PER 90", "ASSISTS PER 90",
                    "CLEAN SHEETS %", "POINTS PER MATCH"]
        outfield = ["xG PER 90", "xA PER 90", "GOALS PER 90", "ASSISTS PER 90",
                    "xGI PER 90", "POINTS PER MATCH"]
        goalkeeper = ["SAVES PER 90", "CONCEDED PER 90", "xGC PER 90",
                      "CLEAN SHEETS %", "MINUTES PER START", "POINTS PER MATCH"]
        self.assertEqual(labels, goalkeeper + defender + outfield)
        # Values come from official season data; no projections or xPts.
        self.assertNotIn("xpts", block.lower())

    def test_card_payload_still_supplies_every_field_the_runtime_reads(self):
        payload = SOURCE[SOURCE.index('p["card"] = {'):]
        payload = payload[:payload.index("\n    }\n")]
        for key in ("first_name", "surname", "club", "club_badge", "player_image", "price",
                    "ownership", "position_label", "verdict_sub", "display_stats",
                    "fixtures", "season_label", "captain", "vice"):
            with self.subTest(key=key):
                self.assertIn(f'"{key}"', payload)


if __name__ == "__main__":
    unittest.main()
