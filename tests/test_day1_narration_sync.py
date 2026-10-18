from __future__ import annotations

import ast
import re
import unicodedata
import unittest
from pathlib import Path

SOURCE_PATH = Path(__file__).resolve().parents[1] / "1_final_day1.py"


def normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    ascii_text = "".join(
        character for character in decomposed
        if not unicodedata.combining(character)
    )
    return re.sub(r"[^a-z0-9]+", " ", ascii_text.lower()).strip()


def narration_literals(source: str) -> dict[str, str]:
    source_tree = ast.parse(source, filename=str(SOURCE_PATH))
    scripts: dict[str, str] = {}
    for node in ast.walk(source_tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Dict):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "scripts"
            for target in node.targets
        ):
            continue
        for key, value in zip(node.value.keys, node.value.values):
            if not isinstance(key, ast.Constant) or key.value not in (
                "00_intro", "05_outro"
            ):
                continue
            expression = value
            if (
                isinstance(expression, ast.Call)
                and isinstance(expression.func, ast.Attribute)
                and expression.func.attr == "strip"
                and not expression.args
                and not expression.keywords
            ):
                expression = expression.func.value
            if isinstance(expression, ast.Constant) and isinstance(expression.value, str):
                scripts[key.value] = expression.value.strip()
            elif isinstance(expression, ast.JoinedStr):
                scripts[key.value] = "".join(
                    part.value
                    if isinstance(part, ast.Constant) and isinstance(part.value, str)
                    else " _dynamic_ "
                    for part in expression.values
                ).strip()
            else:
                raise AssertionError(f"{key.value} narration is not a literal string")
    return scripts


def required_animation_anchors(source: str) -> dict[str, list[str]]:
    animation_cell = source.split(
        "# CELL 19 — SHARED ANIMATION ENGINE", 1
    )[1].split("# CELL 20 —", 1)[0]
    intro_section = animation_cell.split('if key=="00_intro":', 1)[1].split(
        'if key=="02_fdr":', 1
    )[0]
    outro_events = animation_cell.split(
        "# Anchor section transitions to spoken Ryan words", 1
    )[1].split("# COMMON 4K CSS", 1)[0]
    outro_manifest = animation_cell.split('if key=="05_outro":', 1)[1].split(
        "page=src.read_text", 1
    )[0]

    sync_pattern = r'_sync\(\s*"([^"]+)"'
    required_pattern = (
        r'vx_phrase_time\(\s*words\s*,\s*"([^"]+)"'
        r'\s*,\s*required=True'
    )
    return {
        "00_intro": re.findall(sync_pattern, intro_section),
        "05_outro": (
            re.findall(sync_pattern, outro_events)
            + re.findall(required_pattern, outro_manifest)
        ),
    }


class TestDay1NarrationSync(unittest.TestCase):
    def test_narration_literals_accepts_stripped_strings(self) -> None:
        scripts = narration_literals(
            'scripts = {"00_intro": f"Welcome GW{gameweek}".strip(), '
            '"05_outro": "Subscribe now".strip()}'
        )
        self.assertEqual(scripts["00_intro"], "Welcome GW _dynamic_")
        self.assertEqual(scripts["05_outro"], "Subscribe now")

    def test_nonliteral_narration_is_rejected(self) -> None:
        with self.assertRaisesRegex(AssertionError, "00_intro"):
            narration_literals('scripts = {"00_intro": build_intro()}')

    def test_required_anchors_are_present_in_spoken_scripts(self) -> None:
        source = SOURCE_PATH.read_text(encoding="utf-8")
        scripts = narration_literals(source)
        anchors = required_animation_anchors(source)
        self.assertEqual(set(scripts), {"00_intro", "05_outro"})

        for scene_key, scene_anchors in anchors.items():
            self.assertGreater(len(scene_anchors), 0, scene_key)
            normalized_script = normalize(scripts[scene_key])
            for phrase in scene_anchors:
                with self.subTest(scene=scene_key, phrase=phrase):
                    self.assertIn(normalize(phrase), normalized_script)


if __name__ == "__main__":
    unittest.main()
