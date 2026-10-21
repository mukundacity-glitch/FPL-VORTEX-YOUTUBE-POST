from __future__ import annotations

import ast
import shutil
import tempfile
import textwrap
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from PIL import Image, ImageChops, ImageDraw

from day3.run_notebook import _patch_transition_titles


FIXTURE = Path(__file__).with_name("fixtures") / "transition_overlay_source.txt"
HEADINGS = (
    "INTRO",
    "PROJECTED GOALS + CS ODDS",
    "DEFCON",
    "FINAL SHORTLISTS",
    "TRANSFER DECISION DESK",
    "05 • GAMEWEEK REVIEW",
    "MY PLAN • PLANNED CHIP",
    "ELITE TOP 10K • OWNERSHIP DASHBOARD",
    "MY PLAN • ROLL",
    "MY PLAN • TRANSFER",
    "BENCHING DILEMMA",
    "OUTRO",
)


class TransitionTitleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.preview = self.root / "preview.png"
        Image.new("RGB", (320, 180), "#123456").save(self.preview)
        self.source = FIXTURE.read_text(encoding="utf-8")

    def render(
        self, heading: str, resolution: tuple[int, int], *, fixed: bool = True,
    ) -> tuple[Image.Image, Image.Image, Image.Image]:
        namespace: dict[str, Any] = {
            "Path": Path, "W": resolution[0], "H": resolution[1],
            "ASSEMBLY_WORK": self.root, "HTML_WORK_DIR": self.root / "html",
        }
        source = _patch_transition_titles(self.source) if fixed else self.source
        exec(textwrap.dedent(source), namespace)
        original_text = ImageDraw.ImageDraw.text
        calls: list[tuple[Image.Image, tuple[float, float], str, dict[str, Any]]] = []

        def capture_text(draw: ImageDraw.ImageDraw, position: Any, text: str, *args: Any, **kwargs: Any) -> None:
            if draw._image.mode == "L":
                calls.append((draw._image, position, text, kwargs))
            original_text(draw, position, text, *args, **kwargs)

        with patch.object(ImageDraw.ImageDraw, "text", capture_text):
            output = namespace["_vx21_build_transition_overlay"](heading, self.preview, 1)
        with Image.open(output) as image:
            overlay = image.copy()
        self.assertTrue(calls)
        mask = calls[0][0]
        margin = resolution[1]
        reference = Image.new("L", (mask.width + margin * 2, mask.height + margin * 2))
        reference_draw = ImageDraw.Draw(reference)
        for actual_mask, position, text, kwargs in calls:
            self.assertIs(actual_mask, mask)
            original_text(reference_draw, (position[0] + margin, position[1] + margin), text, **kwargs)
        return overlay, mask, reference

    def assert_complete_title(self, mask: Image.Image, reference: Image.Image, margin: int) -> None:
        bounds = reference.getbbox()
        self.assertIsNotNone(bounds)
        self.assertGreaterEqual(bounds[0], margin)
        self.assertGreaterEqual(bounds[1], margin)
        self.assertLessEqual(bounds[2], margin + mask.width)
        self.assertLessEqual(bounds[3], margin + mask.height)
        expected = reference.crop((margin, margin, margin + mask.width, margin + mask.height))
        self.assertIsNone(ImageChops.difference(mask, expected).getbbox())

    def test_original_renderer_reproduces_the_missing_bottom_of_the_title(self) -> None:
        font_directory = self.root / "premium_fonts"
        font_directory.mkdir()
        shutil.copyfile(
            Path(__file__).parents[1] / "day2/assets/BarlowCondensed-SemiBold.ttf",
            font_directory / "BarlowCondensed-Bold.ttf",
        )
        _, mask, reference = self.render("PROJECTED GOALS + CS ODDS", (1280, 720), fixed=False)
        self.assertGreater(reference.getbbox()[3], 720 + mask.height)

    def test_every_transition_keeps_all_letter_pixels_with_cached_and_fallback_fonts(self) -> None:
        for cached in (False, True):
            if cached:
                font_directory = self.root / "premium_fonts"
                font_directory.mkdir()
                shutil.copyfile(
                    Path(__file__).parents[1] / "day2/assets/BarlowCondensed-SemiBold.ttf",
                    font_directory / "BarlowCondensed-Bold.ttf",
                )
            for heading in HEADINGS:
                with self.subTest(cached=cached, heading=heading):
                    _, mask, reference = self.render(heading, (1280, 720))
                    self.assert_complete_title(mask, reference, 720)
                    self.assertLessEqual(mask.width, int(1280 * .535))
                    self.assertLessEqual(mask.height, int(720 * .905) - int(720 * .755))

    def test_full_hd_and_4k_titles_fit_without_overlapping_preview_or_footer(self) -> None:
        for width, height in ((1920, 1080), (3840, 2160)):
            for heading in (HEADINGS[1], HEADINGS[7], "Agility, gyp & player availability"):
                with self.subTest(resolution=(width, height), heading=heading):
                    _, mask, reference = self.render(heading, (width, height))
                    self.assert_complete_title(mask, reference, height)
                    left = int(width * .052) + int(width * .036)
                    self.assertLess(left + mask.width, int(width * .646))
                    self.assertLessEqual(int(height * .755) + mask.height, int(height * .905))

    def test_non_title_pixels_and_transition_duration_stay_unchanged(self) -> None:
        width, height = 1280, 720
        original, _, _ = self.render(HEADINGS[1], (width, height), fixed=False)
        fixed, _, _ = self.render(HEADINGS[1], (width, height))
        difference = ImageChops.difference(original, fixed)
        difference.paste((0, 0, 0, 0), (
            int(width * .052) + int(width * .036), int(height * .755),
            int(width * .646), int(height * .905),
        ))
        self.assertTrue(all(channel.getbbox() is None for channel in difference.split()))
        duration = "    TRANSITION_SECONDS = 0.2\n"
        patched = _patch_transition_titles(self.source + duration)
        self.assertTrue(patched.endswith(duration))
        self.assertIn("TITLE-FIT-V1", patched)

    def test_empty_titles_and_changed_source_fail_clearly(self) -> None:
        with self.assertRaisesRegex(ValueError, "must not be empty"):
            self.render(" • ", (1280, 720))
        with self.assertRaisesRegex(ValueError, "cannot fit safely"):
            self.render("X" * 2000, (1280, 720))
        for source in ("pass\n", self.source + self.source):
            with self.subTest(length=len(source)), self.assertRaisesRegex(RuntimeError, "Transition title fit"):
                _patch_transition_titles(source)

    def test_patch_only_changes_title_renderer_and_assembly_cache_version(self) -> None:
        patched = _patch_transition_titles(self.source)
        original_tree = ast.parse(textwrap.dedent(self.source))
        fixed_tree = ast.parse(textwrap.dedent(patched))
        original_function = original_tree.body[1]
        fixed_function = fixed_tree.body[1]
        for tree in (original_function, fixed_function):
            for assignment in ast.walk(tree):
                if isinstance(assignment, ast.Assign) and any(
                    isinstance(target, ast.Name) and target.id == "title_x" for target in assignment.targets
                ):
                    title_start = assignment.lineno
                    break
            for node in tree.body:
                if node.lineno >= title_start and isinstance(node, ast.Assign) and any(
                    isinstance(target, ast.Name) and target.id == "card_w" for target in node.targets
                ):
                    preview_start = node.lineno
                    break
            tree.body = [node for node in tree.body if node.lineno < title_start or node.lineno >= preview_start]
        self.assertEqual(ast.dump(original_function), ast.dump(fixed_function))


if __name__ == "__main__":
    unittest.main()
