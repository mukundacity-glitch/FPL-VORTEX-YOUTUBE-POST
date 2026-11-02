"""Regression for run #87: spoken intro must pass the real shared Ryan TTS gate.

This test extracts the production intro f-string and production full-word
validator from the 33-cell source, rather than duplicating validator regexes.
No live API, secrets, TTS call, rendering or YouTube upload is required.
"""
from __future__ import annotations

import ast
from copy import deepcopy
import html
from pathlib import Path
import re
import unittest

from vortex.day1_agenda import build_intro_agenda, spoken_intro_agenda


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "1_final_day1.py"


def _production_intro_and_validator():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
    intros = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
            for key, value in zip(node.value.keys, node.value.values):
                if isinstance(key, ast.Constant) and key.value == "00_intro":
                    intros.append(value)
    if len(intros) != 1:
        raise AssertionError(f"Expected exactly one source intro f-string, got {len(intros)}")

    names = {
        "_vx_replace_narration_phrase",
        "vx_assert_full_word_narration",
        "vx_full_word_narration",
    }
    functions = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    if {func.name for func in functions} != names or len(functions) != 3:
        raise AssertionError("Production narration contract functions are missing")
    namespace = {
        "_vx_html": html,
        "_vx_re": re,
        "VX_NARRATION_PLAYER_BY_ID": {},
        "VX_NARRATION_TEAM_SHORT_ALIASES": set(),
        "VX_NARRATION_PLAYER_TEXT_ALIASES": [],
        "VX_NARRATION_TEAM_TEXT_ALIASES": [],
    }
    isolated = ast.fix_missing_locations(ast.Module(body=functions, type_ignores=[]))
    exec(compile(isolated, str(SOURCE), "exec"), namespace)
    return intros[0], namespace["vx_full_word_narration"]


def _review_beats():
    return [
        {"id": identifier, "text": "data-derived example"}
        for identifier in (
            "headline", "editorial_squad_context", "editorial_comparison",
            "editorial_routes", "editorial_verdict",
        )
    ]


class IntroSpeechContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.expression, cls.full_word = _production_intro_and_validator()

    def _actual_intro(self, next_gw, cards):
        return eval(
            compile(ast.Expression(body=deepcopy(self.expression)), str(SOURCE), "eval"),
            {
                "NEXT_GW": next_gw,
                "VX_INTRO_AGENDA_SPOKEN": spoken_intro_agenda(cards),
            },
        ).strip()

    def test_default_intro_and_other_scene_combinations_pass_production_gate(self):
        for next_gw in (2, 11, 38):
            for selected in (
                ["00_intro", "gw_review"],
                ["00_intro", "gw_review", "02_fdr", "04_clean_sheets"],
                ["00_intro", "03_projected_goals"],
            ):
                with self.subTest(next_gw=next_gw, selected=selected):
                    review = "gw_review" in selected
                    cards = build_intro_agenda(
                        selected, next_gw=next_gw,
                        review_gw=next_gw - 1 if review else None,
                        review_status="LIVE/PARTIAL",
                        review_segments=_review_beats() if review else None,
                    )
                    original = self._actual_intro(next_gw, cards)
                    spoken = self.full_word(original, context="shared narration 00_intro")
                    self.assertEqual(spoken, original)
                    self.assertIn(f"Gameweek {next_gw}", spoken)
                    self.assertIn("Fantasy Premier League Vortex", spoken)
                    self.assertNotRegex(spoken, r"\b(?:FPL|VORTEX)\b")
                    for card in cards:
                        hits = re.findall(re.escape(card["anchor"]), spoken, flags=re.I)
                        self.assertEqual(len(hits), 1, card["key"])

    def test_brand_acronym_expansion_is_safe_but_unknown_caps_still_fail(self):
        self.assertEqual(
            self.full_word("Welcome back to FPL VORTEX."),
            "Welcome back to Fantasy Premier League Vortex.",
        )
        self.assertEqual(
            self.full_word("Compare FPL picks before the deadline."),
            "Compare Fantasy Premier League picks before the deadline.",
        )
        with self.assertRaisesRegex(RuntimeError, "capital abbreviations.*XYZ"):
            self.full_word("This is an XYZ shortlist.")
        with self.assertRaisesRegex(RuntimeError, "API-style fields"):
            self.full_word("Read the next_gw_xpts field.")

    def test_visible_brand_stays_unchanged_and_qa_runs_before_expensive_work(self):
        script = SOURCE.read_text(encoding="utf-8")
        self.assertIn('<div class="channelName">FPL VORTEX</div>', script)
        workflow = (ROOT / ".github/workflows/day-1.yml").read_text(encoding="utf-8")
        self.assertIn("test_day1_intro_voice_gate.py", workflow)
        self.assertLess(
            workflow.index("test_day1_intro_voice_gate.py"),
            workflow.index("Execute Day 1 cells once in order"),
        )
        editorial_qa = (ROOT / ".github/workflows/day1-editorial-qa.yml").read_text(encoding="utf-8")
        self.assertIn("test_day1_intro_voice_gate.py", editorial_qa)


if __name__ == "__main__":
    unittest.main()
