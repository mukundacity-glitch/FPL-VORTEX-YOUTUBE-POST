"""Exercise Day 2's production logo command without Drive or YouTube access."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/day-2.yml"


def recovery_command():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    command = "bash day2/restore_logo.sh"
    if workflow.count(command) != 1:
        raise AssertionError("Day 2 logo recovery command missing or duplicated")
    return command


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "requires ffmpeg")
class Day2LogoRecoveryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.assets = Path(temp.name) / "day2-assets"
        self.assets.mkdir()
        self.logo = self.assets / "logo1.png"
        self.env = dict(os.environ, DAY2_ASSET_DIR=str(self.assets))

    def recover(self):
        return subprocess.run(
            ["bash", "-euo", "pipefail", "-c", recovery_command()],
            cwd=ROOT, env=self.env, text=True, capture_output=True,
        )

    def intro(self, seconds=8):
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", f"color=c=green:s=1280x720:r=8:d={seconds}",
            "-c:v", "mpeg4", str(self.assets / "opening.mp4"),
        ], check=True)

    def test_approved_opening_creates_the_exact_logo_path_used_by_notebook(self):
        self.intro()
        source = (self.assets / "opening.mp4").read_bytes()
        result = self.recover()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.logo.is_file())
        self.assertEqual((self.assets / "opening.mp4").read_bytes(), source)
        codec = subprocess.check_output([
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=codec_name", "-of", "csv=p=0", str(self.logo),
        ], text=True).strip()
        self.assertEqual(codec, "png")
        self.assertEqual({p.name for p in self.assets.iterdir()}, {"opening.mp4", "logo1.png"})

    def test_valid_existing_logo_is_preserved_without_opening(self):
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "color=c=blue:s=128x128",
            "-frames:v", "1", str(self.logo),
        ], check=True)
        original = self.logo.read_bytes()
        result = self.recover()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.logo.read_bytes(), original)

    def test_corrupt_logo_is_replaced_from_approved_opening(self):
        self.intro()
        self.logo.write_bytes(b"invalid png")
        result = self.recover()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.logo.read_bytes().startswith(b"\x89PNG"))

    def test_missing_source_stops_before_rendering(self):
        result = self.recover()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("brand logo missing", result.stderr)
        self.assertFalse(self.logo.exists())

    def test_failed_recovery_preserves_old_file_and_cleans_temporary_files(self):
        self.logo.write_bytes(b"invalid png")
        result = self.recover()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.logo.read_bytes(), b"invalid png")
        self.assertEqual({p.name for p in self.assets.iterdir()}, {"logo1.png"})

    def test_recovery_cannot_overwrite_day1_logo_from_inherited_environment(self):
        self.intro()
        day1_logo = self.assets.parent / "day1-logo.png"
        day1_logo.write_bytes(b"protected Day 1 logo")
        self.env["DAY1_LOGO_FILE"] = str(day1_logo)
        result = self.recover()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(day1_logo.read_bytes(), b"protected Day 1 logo")
        self.assertTrue(self.logo.is_file())

    def test_short_intro_is_rejected_without_creating_logo(self):
        self.intro(seconds=2)
        result = self.recover()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("too short", result.stdout + result.stderr)
        self.assertFalse(self.logo.exists())


class Day2WorkflowTests(unittest.TestCase):
    def test_restore_no_longer_depends_on_deleted_logo_id(self):
        source = WORKFLOW.read_text(encoding="utf-8")
        self.assertNotIn("1Lxt7hDn5VAVj3njo9n6H2ymXY_gd2vP8", source)
        self.assertLess(source.index("test_asset_recovery.py"), source.index("python -m day2.drive_io restore"))
        self.assertLess(source.index(recovery_command().splitlines()[0].strip()),
                        source.index("Execute fresh Day 2 notebook"))


if __name__ == "__main__":
    unittest.main()
