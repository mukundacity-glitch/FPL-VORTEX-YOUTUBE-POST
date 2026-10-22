from __future__ import annotations

import ast
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw

from wc_fh.masterplan_capture import (VERSION, heading_fraction, masterplan_browser_arguments,
                                      patch_masterplan_capture, replace_masterplan_runtime, verify_masterplan_capture)


RUNTIME = '''
def _vx_masterplan_safe_render_video(self, audio, duration, target, profile):
    cli = _vx_remotion_cli(self.project)
    browser = _vx_remotion_browser_arguments(self.project)
    encode(browser)
    return target

def _vx_masterplan_safe_frame(self, seconds):
    cli = _vx_remotion_cli(self.project)
    return capture([cli, *_vx_remotion_browser_arguments(self.project)])
'''
CELL = f"_VX_REMOTION_RENDER_SAFE_PATCH = {RUNTIME!r}\nVX_RENDERER_VERSION = 'original'\n"


class MasterplanBrowserTests(unittest.TestCase):
    def test_only_pinned_shell_is_used_even_when_full_chrome_is_configured(self):
        with tempfile.TemporaryDirectory() as directory, patch("wc_fh.masterplan_capture.subprocess.run") as run:
            project = Path(directory)
            shell = project / "node_modules/.remotion/chrome-headless-shell/linux/chrome-headless-shell"
            shell.parent.mkdir(parents=True)
            shell.touch()
            with patch.dict(os.environ, {"VX_REMOTION_BROWSER_EXECUTABLE": "/full/chrome"}):
                args = masterplan_browser_arguments(project, "/pinned/remotion")
            self.assertEqual(args, [f"--browser-executable={shell}", "--chrome-mode=headless-shell"])
            run.assert_called_once_with(["/pinned/remotion", "browser", "ensure", "--chrome-mode=headless-shell"],
                                        cwd=project, check=True)

    def test_failed_or_missing_shell_never_falls_back_to_full_chrome(self):
        with tempfile.TemporaryDirectory() as directory, patch("wc_fh.masterplan_capture.subprocess.run") as run:
            with self.assertRaisesRegex(RuntimeError, "requires exactly one"):
                masterplan_browser_arguments(Path(directory), "remotion")
            run.side_effect = subprocess.CalledProcessError(1, "remotion")
            with self.assertRaises(subprocess.CalledProcessError):
                masterplan_browser_arguments(Path(directory), "remotion")

    def test_patch_guards_video_and_still_and_invalidates_existing_cache(self):
        namespace = {"_VX_MASTERPLAN_SOURCE": RUNTIME}
        exec(patch_masterplan_capture(CELL), namespace)
        runtime = namespace["_VX_REMOTION_RENDER_SAFE_PATCH"]
        compile(runtime, "patched-runtime", "exec")
        functions = {node.name: ast.get_source_segment(runtime, node) for node in ast.parse(runtime).body
                     if isinstance(node, ast.FunctionDef)}
        for name in ("_vx_masterplan_safe_render_video", "_vx_masterplan_safe_frame"):
            self.assertIn("masterplan_browser_arguments(self.project, cli)", functions[name])
            self.assertNotIn("_vx_remotion_browser_arguments(self.project)", functions[name])
        self.assertIn("verify_masterplan_capture(target, duration", functions["_vx_masterplan_safe_render_video"])
        self.assertIn(VERSION, namespace["VX_RENDERER_VERSION"])
        self.assertIn("verify_masterplan_capture(target, duration", namespace["_VX_MASTERPLAN_SOURCE"])

    def test_existing_embedded_safe_functions_are_replaced_without_dropping_other_code(self):
        source = "from __future__ import annotations\n" + RUNTIME + "\nunrelated = 'preserved'\n"
        replacement = RUNTIME.replace("encode(browser)", "verify_masterplan_capture(target, duration, 24)")
        updated = replace_masterplan_runtime(source, replacement)
        self.assertIn("unrelated = 'preserved'", updated)
        self.assertIn("verify_masterplan_capture(target, duration, 24)", updated)
        with self.assertRaisesRegex(ValueError, "contract changed"):
            replace_masterplan_runtime("pass", replacement)

    def test_changed_upstream_source_fails_instead_of_silently_skipping_fix(self):
        for source in ("pass", CELL.replace("browser = ", "different = "),
                       CELL.replace("VX_RENDERER_VERSION", "OTHER_VERSION")):
            with self.subTest(source=source), self.assertRaisesRegex(ValueError, "contract changed"):
                patch_masterplan_capture(source)


@unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg required")
class MasterplanFrameTests(unittest.TestCase):
    def encode(self, path: Path, *, corrupt: bool = False) -> None:
        frames = []
        for index in range(4):
            image = Image.new("RGB", (320, 180), "#09233f")
            if not corrupt or index != 2:
                ImageDraw.Draw(image).rectangle((72, 3, 198, 17), fill="#fbe2a0")
            else:
                # Match the reported failure: the whole composition becomes repeated green tiles.
                draw = ImageDraw.Draw(image)
                for left in range(0, 320, 64):
                    for top in range(0, 180, 32):
                        draw.rectangle((left, top, left + 62, top + 30), fill="#006539")
            frames.append(image.tobytes())
        subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                        "-s", "320x180", "-r", "24", "-i", "pipe:0", "-an", "-c:v", "libx264",
                        "-crf", "0", "-pix_fmt", "yuv420p", str(path)],
                       input=b"".join(frames), capture_output=True, check=True)

    def test_continuous_frames_pass_and_single_tiled_frame_blocks_delivery(self):
        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory) / "masterplan.mp4"
            self.encode(video)
            self.assertEqual(verify_masterplan_capture(video, 4 / 24, 24)["frames_checked"], 4)
            video.with_suffix(".capture_qa.json").unlink()
            self.encode(video, corrupt=True)
            with self.assertRaisesRegex(ValueError, r"frame 2 \(0.083s\)"):
                verify_masterplan_capture(video, 4 / 24, 24)
            self.assertFalse(video.with_suffix(".capture_qa.json").exists())

    def test_truncated_decode_or_missing_frames_cannot_pass(self):
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            heading_fraction(b"short")
        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory) / "masterplan.mp4"
            self.encode(video)
            with self.assertRaisesRegex(ValueError, "frame count"):
                verify_masterplan_capture(video, 1, 24)


if __name__ == "__main__":
    unittest.main()
