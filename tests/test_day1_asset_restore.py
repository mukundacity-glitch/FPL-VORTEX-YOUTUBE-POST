"""Regression tests for removal of Drive-hosted Day 1 media assets."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "restore_day1_assets.sh"
FAKE_RCLONE = r'''#!/usr/bin/env python3
import os
import pathlib
import shutil
import sys
root = pathlib.Path(os.environ["FAKE_DRIVE_ROOT"])
command, *args = sys.argv[1:]
def resolve(value):
    if value == "day1-assets:":
        return root / "primary"
    if value == "vortex-drive:FPL_VORTEX_DATA/01_DAY1_MEDIA_BACKUP":
        return root / "backup"
    return pathlib.Path(value)
if command == "lsf":
    sys.exit(0 if resolve(args[0]).is_dir() else 1)
if command == "mkdir":
    resolve(args[0]).mkdir(parents=True, exist_ok=True)
    sys.exit(0)
if command == "copy":
    src, dst = resolve(args[0]), resolve(args[1])
    if not src.is_dir():
        print("Rclone source directory absent", file=sys.stderr)
        sys.exit(1)
    dst.mkdir(parents=True, exist_ok=True)
    for name in ("opening.mp4", "Background_music.mp3", "outro.mp3"):
        if (src / name).exists():
            shutil.copy2(src / name, dst / name)
    sys.exit(0)
print("Unsupported rclone command", command, file=sys.stderr)
sys.exit(2)
'''

@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "requires FFmpeg")
class Day1AssetRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.primary = self.root / "primary"
        self.primary.mkdir()
        self.backup = self.root / "backup"
        self.assets = self.root / "downloaded"
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        rclone = bin_dir / "rclone"
        rclone.write_text(FAKE_RCLONE, encoding="utf-8")
        rclone.chmod(0o755)
        self.env = dict(os.environ, DAY1_ASSET_DIR=str(self.assets),
                        DAY1_ASSET_FOLDER_ID="test-folder-id", FAKE_DRIVE_ROOT=str(self.root),
                        PATH=f"{bin_dir}:{os.environ['PATH']}")

    def create_assets(self, folder):
        folder.mkdir(parents=True, exist_ok=True)
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
            "-i", "color=c=black:s=160x90:r=8:d=1.2", "-f", "lavfi",
            "-i", "sine=frequency=440:duration=1.2", "-shortest", "-c:v", "mpeg4",
            "-c:a", "aac", str(folder / "opening.mp4")], check=True)
        for name, freq, dur in (("Background_music.mp3", 330, 1.5),
                                 ("outro.mp3", 550, 6.2)):
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                            "-f", "lavfi", "-i", f"sine=frequency={freq}:duration={dur}",
                            "-c:a", "libmp3lame", str(folder / name)], check=True)

    def run_restore(self):
        return subprocess.run(["bash", str(SCRIPT)], env=self.env, text=True,
                              capture_output=True, check=False)

    def test_primary_assets_seed_independent_backup(self):
        self.create_assets(self.primary)
        result = self.run_restore()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for name in ("opening.mp4", "Background_music.mp3", "outro.mp3"):
            self.assertEqual((self.primary / name).read_bytes(), (self.backup / name).read_bytes())
            self.assertEqual((self.primary / name).read_bytes(), (self.assets / name).read_bytes())

    def test_fallback_recovers_missing_primary_assets(self):
        self.create_assets(self.backup)
        result = self.run_restore()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Checking backup", result.stderr)
        self.assertEqual((self.backup / "opening.mp4").read_bytes(),
                         (self.assets / "opening.mp4").read_bytes())

    def test_missing_everywhere_is_error_not_fake_success(self):
        result = self.run_restore()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("original media unavailable in primary AND backup", result.stderr)
        self.assertIn("opening.mp4", result.stderr)
        self.assertFalse(self.backup.exists())

    def test_corrupt_media_cannot_poison_backup(self):
        self.create_assets(self.primary)
        (self.primary / "opening.mp4").write_bytes(b"broken video")
        result = self.run_restore()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Invalid Day 1 asset", result.stderr)
        self.assertFalse(self.backup.exists())

    def test_workflow_calls_asset_restore_script(self):
        workflow = (ROOT / ".github/workflows/day-1.yml").read_text(encoding="utf-8")
        self.assertIn("bash scripts/restore_day1_assets.sh", workflow)
        self.assertIn("test_day1_asset_restore.py", workflow)

if __name__ == "__main__":
    unittest.main()
