"""No-network editorial source guards: never recycle a prior GW's advice."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch

from vortex.expert_editorial import source_brief, _url, _gameweek

NOW = datetime(2026, 11, 6, 12, tzinfo=timezone.utc)
URL = "https://allaboutfpl.com/2026/11/fpl-gw10-team-selection-drafts-transfer-plans-and-watchlist/"
FEED = (f"<rss><channel><item><title>FPL GW10 Team Selection and Transfer Plans</title>"
        f"<link>{URL}</link><pubDate>Wed, 04 Nov 2026 12:00:00 +0000</pubDate>"
        f"</item></channel></rss>").encode()
BOOT = {"events": [{"id": 10, "is_next": True, "deadline_time": "2026-11-06T18:30:00Z"}]}
OPINION = {"gw": 10, "url": URL, "author": "Srini", "topic": "transfers",
           "decision": "He is leaning toward rolling his transfer."}


class VerifiedCommunityEditorialTests(unittest.TestCase):
    def test_verified_current_gameweek_author_position(self):
        data = source_brief(BOOT, FEED, NOW, [OPINION])
        self.assertEqual(data["gameweek"], 10)
        self.assertEqual(data["status"], "verified_author_opinions")
        self.assertEqual(data["opinions"][0]["author"], "Srini")

    def test_future_gameweek_does_not_reuse_old_opinions(self):
        future = {"events": [{"id": 11, "is_next": True,
                              "deadline_time": "2026-11-14T18:30:00Z"}]}
        data = source_brief(future, FEED, NOW, [OPINION])
        self.assertEqual(data["opinions"], [])
        self.assertEqual(data["status"], "no_current_articles")

    def test_old_rss_is_rejected_even_with_current_gw_label(self):
        data = source_brief(BOOT, FEED, NOW + timedelta(days=9), [OPINION])
        self.assertEqual(data["opinions"], [])

    def test_opinion_without_live_matching_article_is_not_spoken(self):
        wrong = dict(OPINION, url="https://allaboutfpl.com/2026/11/other-article/")
        data = source_brief(BOOT, FEED, NOW, [wrong])
        self.assertEqual(data["status"], "article_discovery_only")
        self.assertEqual(data["opinions"], [])

    def test_other_domains_or_ambiguous_gameweeks_are_rejected(self):
        with self.assertRaises(ValueError):
            _url("https://wrong.example/2026/11/story/")
        with self.assertRaises(ValueError):
            _gameweek({"events": [{"id": 10, "is_next": True},
                                  {"id": 11, "is_next": True}]})

    def test_source_unavailable_never_falls_back_to_static_opinions(self):
        with patch("vortex.expert_editorial._fetch", side_effect=OSError("offline")):
            data = source_brief()
        self.assertEqual(data["status"], "source_unavailable")
        self.assertEqual(data["opinions"], [])


if __name__ == "__main__":
    unittest.main()
