"""Offline tests for Day 1 private YouTube upload receipt gate."""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from vortex.day1_upload_status import validated_private_receipt


class Day1UploadStatusTests(unittest.TestCase):
    def _write_receipt(self, directory: Path, *, status="private_upload_complete",
                       privacy="private", video_id="dhKR-cv3Rzw") -> Path:
        path = directory / "youtube_private_upload.json"
        path.write_text(
            json.dumps({"status": status, "youtube": {
                "privacy_status": privacy, "video_id": video_id
            }}),
            encoding="utf-8"
        )
        return path

    def test_new_private_upload_returns_studio_url(self):
        with TemporaryDirectory() as tmp:
            result = validated_private_receipt(self._write_receipt(Path(tmp)))
            self.assertEqual(result["status"], "private_upload_complete")
            self.assertEqual(result["privacy_status"], "private")
            self.assertEqual(
                result["studio_url"],
                "https://studio.youtube.com/video/dhKR-cv3Rzw/edit",
            )

    def test_prior_private_copy_is_valid(self):
        with TemporaryDirectory() as tmp:
            result = validated_private_receipt(self._write_receipt(
                Path(tmp), status="already_uploaded"
            ))
            self.assertEqual(result["status"], "already_uploaded")

    def test_public_duplicate_cannot_be_reported_as_upload_success(self):
        with TemporaryDirectory() as tmp:
            for visibility in ("public", "unlisted", "", "unknown"):
                with self.subTest(visibility=visibility):
                    path = self._write_receipt(
                        Path(tmp), status="already_uploaded", privacy=visibility
                    )
                    with self.assertRaisesRegex(RuntimeError, "NOT a private draft"):
                        validated_private_receipt(path)

    def test_failed_or_incomplete_upload_rejected(self):
        with TemporaryDirectory() as tmp:
            for status in ("failed", "starting", "channel_verified", ""):
                with self.subTest(status=status):
                    path = self._write_receipt(Path(tmp), status=status)
                    with self.assertRaisesRegex(RuntimeError, "did not complete"):
                        validated_private_receipt(path)

    def test_missing_receipt_or_video_id_rejected(self):
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            with self.assertRaisesRegex(RuntimeError, "receipt is missing"):
                validated_private_receipt(base / "missing.json")
            with self.assertRaisesRegex(RuntimeError, "invalid video ID"):
                validated_private_receipt(self._write_receipt(base, video_id="bad"))


if __name__ == "__main__":
    unittest.main()
