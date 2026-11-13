"""Pure offline regression tests: Day 1 deduplicates by official FPL season/GW."""
from __future__ import annotations

import io
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from vortex.youtube_private_upload import (
    _find_existing_gameweek_video,
    _official_season_identity,
    upload_private,
)


class Day1SeasonDedupeTests(unittest.TestCase):
    def _client(self, *, tags, published="2026-11-03T12:00:00Z", next_page=None,
                privacy="private"):
        youtube = Mock()
        youtube.channels.return_value.list.return_value.execute.return_value = {
            "items": [{
                "contentDetails": {"relatedPlaylists": {"uploads": "owned-upload-playlist"}}
            }]
        }
        youtube.playlistItems.return_value.list.return_value.execute.return_value = {
            "items": [{"contentDetails": {"videoId": "test-video-123"}}],
            "nextPageToken": next_page,
        }
        youtube.videos.return_value.list.return_value.execute.return_value = {
            "items": [{
                "id": "test-video-123",
                "status": {"privacyStatus": privacy},
                "snippet": {"tags": tags, "publishedAt": published},
            }]
        }
        return youtube

    def test_season_is_derived_from_official_deadline(self):
        response = io.BytesIO(json.dumps({"events": [
            {"id": 12, "deadline_time": "2026-11-06T11:00:00Z"},
            {"id": 13, "deadline_time": "2026-11-20T18:00:00Z"},
        ]}).encode("utf-8"))
        with patch("urllib.request.urlopen", return_value=response):
            season, since = _official_season_identity(12)
        self.assertEqual(season, "2026-2027")
        self.assertEqual(since, datetime(2026, 7, 1, tzinfo=timezone.utc))

    def test_new_season_marker_blocks_duplicate_private_video(self):
        marker = "fpl-vortex-2026-2027-gw12-video-1-of-3"
        found = _find_existing_gameweek_video(
            self._client(tags=[marker]),
            marker=marker,
            legacy_marker="fpl-vortex-auto-gw12-video-1-of-3",
            season_start=datetime(2026, 7, 1, tzinfo=timezone.utc),
        )
        self.assertEqual(found["video_id"], "test-video-123")
        self.assertEqual(found["privacy_status"], "private")

    def test_only_the_same_render_revision_can_reuse_a_private_draft(self):
        marker = "fpl-vortex-2026-2027-gw12-video-1-of-3"
        revision = "fpl-vortex-day1-" + "a" * 40
        lookup = dict(marker=marker, legacy_marker="legacy", revision_tag=revision,
                      season_start=datetime(2026, 7, 1, tzinfo=timezone.utc))
        self.assertIsNone(_find_existing_gameweek_video(self._client(tags=[marker]), **lookup))
        found = _find_existing_gameweek_video(self._client(tags=[marker, revision]), **lookup)
        self.assertEqual(found["video_id"], "test-video-123")

    def test_legacy_video_is_reused_only_in_current_season(self):
        marker = "fpl-vortex-2026-2027-gw12-video-1-of-3"
        old = "fpl-vortex-auto-gw12-video-1-of-3"
        since = datetime(2026, 7, 1, tzinfo=timezone.utc)
        found = _find_existing_gameweek_video(
            self._client(tags=[old]),
            marker=marker, legacy_marker=old, season_start=since,
        )
        self.assertIsNotNone(found)
        ignored = _find_existing_gameweek_video(
            self._client(tags=[old], published="2025-10-15T08:00:00Z"),
            marker=marker, legacy_marker=old, season_start=since,
        )
        self.assertIsNone(ignored)

    def test_published_video_does_not_block_a_new_private_draft(self):
        marker = "fpl-vortex-2026-2027-gw12-video-1-of-3"
        for privacy in ("public", "unlisted"):
            with self.subTest(privacy=privacy):
                youtube = self._client(tags=[marker], privacy=privacy)
                found = _find_existing_gameweek_video(
                    youtube, marker=marker,
                    legacy_marker="fpl-vortex-auto-gw12-video-1-of-3",
                    season_start=datetime(2026, 7, 1, tzinfo=timezone.utc),
                )
                self.assertIsNone(found, "Published copy cannot masquerade as a private draft")

    def test_private_draft_found_even_if_public_copy_precedes_it(self):
        marker = "fpl-vortex-2026-2027-gw12-video-1-of-3"
        youtube = self._client(tags=[marker], privacy="public")
        youtube.playlistItems.return_value.list.return_value.execute.return_value = {
            "items": [
                {"contentDetails": {"videoId": "published-123"}},
                {"contentDetails": {"videoId": "private-456"}},
            ]
        }
        youtube.videos.return_value.list.return_value.execute.return_value = {
            "items": [
                {"id": "published-123", "status": {"privacyStatus": "public"},
                 "snippet": {"tags": [marker]}},
                {"id": "private-456", "status": {"privacyStatus": "private"},
                 "snippet": {"tags": [marker]}},
            ]
        }
        found = _find_existing_gameweek_video(
            youtube, marker=marker,
            legacy_marker="fpl-vortex-auto-gw12-video-1-of-3",
            season_start=datetime(2026, 7, 1, tzinfo=timezone.utc),
        )
        self.assertEqual(found, {"video_id": "private-456", "privacy_status": "private"})

    def test_unknown_existing_video_privacy_fails_closed(self):
        marker = "fpl-vortex-2026-2027-gw12-video-1-of-3"
        with self.assertRaisesRegex(RuntimeError, "Cannot verify privacy"):
            _find_existing_gameweek_video(
                self._client(tags=[marker], privacy=""),
                marker=marker,
                legacy_marker="fpl-vortex-auto-gw12-video-1-of-3",
                season_start=datetime(2026, 7, 1, tzinfo=timezone.utc),
            )

    def test_cannot_verify_owners_uploads_fails_closed(self):
        youtube = Mock()
        youtube.channels.return_value.list.return_value.execute.return_value = {"items": []}
        with self.assertRaisesRegex(RuntimeError, "exactly one"):
            _find_existing_gameweek_video(
                youtube, marker="marker", legacy_marker="old",
                season_start=datetime(2026, 7, 1, tzinfo=timezone.utc),
            )

    def test_reused_upload_never_calls_insert(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "DATA").mkdir()
            with (
                patch("vortex.youtube_private_upload._validate_package",
                      return_value={"package_path": root / "DATA" / "package.json",
                                    "metadata": {"preview_gw": 12},
                                    "upload_tags": ["FPL"]}),
                patch("vortex.youtube_private_upload._official_season_identity",
                      return_value=("2026-2027", datetime(2026, 7, 1, tzinfo=timezone.utc))),
                patch("vortex.youtube_private_upload._youtube_service", return_value=Mock()),
                patch("vortex.youtube_private_upload._verify_channel",
                      return_value={"id": "owned-channel", "title": "VORTEX"}),
                patch("vortex.youtube_private_upload._find_existing_gameweek_video",
                      return_value={"video_id": "existing-private", "privacy_status": "private"}),
                patch("vortex.youtube_private_upload._insert_private_video") as insert,
            ):
                report = upload_private(root)
            insert.assert_not_called()
            self.assertEqual(report["status"], "already_uploaded")
            self.assertTrue(report["duplicate_prevented"])
            self.assertEqual(report["preview_gw"], 12)
            persisted = json.loads((root / "DATA" / "youtube_private_upload.json").read_text())
            self.assertEqual(persisted["season_id"], "2026-2027")


if __name__ == "__main__":
    unittest.main()
