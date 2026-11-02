"""Day 1 lion-logo fallback uses approved opening rather than stale Drive file ID."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "restore_day1_logo.sh"


@unittest.skipUnless(shutil.which("ffprobe") and shutil.which("ffmpeg"), "requires ffmpeg")
class Day1LogoRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.assets = self.root / "assets"
        self.assets.mkdir()
        self.logo = self.root / "elements" / "logo.png"
        self.env = dict(os.environ, DAY1_ASSET_DIR=str(self.assets),
                        DAY1_LOGO_FILE=str(self.logo))

    def command(self):
        return subprocess.run(["bash", str(SCRIPT)], env=self.env, capture_output=True,
                              text=True, check=False)

    def make_intro(self):
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                        "-f", "lavfi", "-i", "color=c=green:s=1280x720:r=8:d=8",
                        "-c:v", "mpeg4", str(self.assets / "opening.mp4")], check=True)

    def test_approved_intro_provides_logo(self):
        self.make_intro()
        original = (self.assets / "opening.mp4").read_bytes()
        outcome = self.command()
        self.assertEqual(outcome.returncode, 0, outcome.stderr)
        self.assertTrue(self.logo.is_file())
        self.assertEqual((self.assets / "opening.mp4").read_bytes(), original)
        codec = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams",
            "v:0", "-show_entries", "stream=codec_name", "-of", "csv=p=0",
            str(self.logo)], text=True).strip()
        self.assertEqual(codec, "png")

    def test_existing_valid_logo_preserved(self):
        self.logo.parent.mkdir(parents=True)
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                        "-f", "lavfi", "-i", "color=c=blue:s=128x128",
                        "-frames:v", "1", str(self.logo)], check=True)
        old = self.logo.read_bytes()
        outcome = self.command()
        self.assertEqual(outcome.returncode, 0, outcome.stderr)
        self.assertEqual(self.logo.read_bytes(), old)

    def test_logo_and_approved_intro_both_missing_fails(self):
        outcome = self.command()
        self.assertNotEqual(outcome.returncode, 0)
        self.assertIn("brand logo missing", outcome.stderr)
        self.assertFalse(self.logo.exists())

    def test_short_intro_does_not_create_unbranded_logo(self):
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                        "-f", "lavfi", "-i", "color=c=black:s=640x360:r=8:d=2",
                        "-c:v", "mpeg4", str(self.assets / "opening.mp4")], check=True)
        outcome = self.command()
        self.assertNotEqual(outcome.returncode, 0)
        self.assertFalse(self.logo.exists())

    def test_workflow_uses_source_based_logo_recovery(self):
        workflow = (ROOT / ".github/workflows/day-1.yml").read_text()
        self.assertIn("bash scripts/restore_day1_logo.sh", workflow)
        self.assertIn("test_day1_logo_restore.py", workflow)
        self.assertNotIn("1Lxt7hDn5VAVj3njo9n6H2ymXY_gd2vP8", workflow)


if __name__ == "__main__":
    unittest.main()
