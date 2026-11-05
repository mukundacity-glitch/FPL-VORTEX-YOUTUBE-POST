"""Offline integration gates for Day 1 current-GW recommendation extraction."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from vortex.day1_live_editorial import (
    build_day1_brief, extract_article_opinions, presenter_note, source_credits,
)
from vortex.day1_agenda import render_intro_agenda

NOW = datetime(2026, 11, 6, 12, tzinfo=timezone.utc)
URL = "https://allaboutfpl.com/2026/11/fpl-gw10-team-selection-drafts-transfer-plans-and-watchlist/"
BOOT = {
    "events": [{"id": 10, "is_next": True, "deadline_time": "2026-11-06T18:30:00Z"}],
    "elements": [
        {"id": 10, "web_name": "Haaland", "team": 4, "status": "a", "element_type": 4},
        {"id": 11, "web_name": "Gabriel", "team": 1, "status": "a", "element_type": 2},
        {"id": 12, "web_name": "Tavernier", "team": 2, "status": "a", "element_type": 3},
        {"id": 13, "web_name": "Rayan", "team": 2, "status": "a", "element_type": 3},
        {"id": 14, "web_name": "Gibbs-White", "team": 3, "status": "a", "element_type": 3},
        {"id": 15, "web_name": "De Cuyper", "team": 5, "status": "a", "element_type": 2},
    ]
}
RSS = (f"<rss><channel><item><title>FPL GW10 Team Selection and Transfer Plans</title>"
       f"<link>{URL}</link><pubDate>Wed, 04 Nov 2026 12:00:00 +0000</pubDate>"
       f"</item></channel></rss>").encode()
HTML = (
    "<html><body><article>"
    "<h2>Srini’s GW10 Team Selection</h2>"
    "<p>I have one Free Transfer and plan to very likely roll the Transfer this week.</p>"
    "<h3>Captaincy</h3>"
    "<p>I am leaning towards captaining Haaland over Gabriel at the moment.</p>"
    "<h2>Surya’s GW10 Team Selection</h2>"
    "<h3>Transfer Plans</h3>"
    "<p>I am planning to move Gibbs-White to Tavernier or Rayan this week.</p>"
    "<p>I would not buy Rayan because I have doubts about his minutes.</p>"
    "<h3>Benching Dilemmas</h3>"
    "<p>I am leaning towards starting De Cuyper right now.</p>"
    "</article></body></html>"
).encode()


class LiveEditorialDay1Tests(unittest.TestCase):
    def report(self, **kwargs):
        return build_day1_brief(bootstrap=BOOT, feed_xml=RSS,
                                article_pages={URL: HTML}, now=NOW, **kwargs)

    def test_live_article_yields_only_explicit_current_author_opinions(self):
        data = self.report()
        self.assertEqual(data["status"], "verified_author_opinions")
        self.assertEqual(data["gameweek"], 10)
        self.assertTrue(all(x["extraction"] == "explicit_author_statement_current_article"
                            for x in data["opinions"]))
        labels = {(x["author"], x["action"]) for x in data["opinions"]}
        self.assertIn(("Srini", "ROLL"), labels)
        self.assertIn(("Srini", "CAPTAIN_COMPARE"), labels)
        self.assertIn(("Surya", "BUY_CONSIDER"), labels)
        self.assertIn(("Surya", "START"), labels)
        buys = [x for x in data["opinions"] if x["action"] == "BUY_CONSIDER"]
        self.assertEqual(len(buys), 1, "Negative BUY wording must be excluded")
        self.assertEqual({p["id"] for p in buys[0]["players"]}, {12, 13})

    def test_captaincy_between_players_for_me_is_explicit_opinion(self):
        article = {"url": URL, "title": "GW10 Team Selection",
                   "gameweek": 10, "published_at": NOW.isoformat()}
        source = (b"<article><h3>Captaincy</h3>"
                  b"<p>Captaincy is between Haaland and Gabriel at the moment for me.</p>"
                  b"</article>")
        picks = extract_article_opinions(source, article, BOOT["elements"])
        self.assertEqual(len(picks), 1)
        self.assertEqual(picks[0]["action"], "CAPTAIN_COMPARE")
        self.assertEqual({p["name"] for p in picks[0]["players"]},
                         {"Haaland", "Gabriel"})

    def test_club_team_selection_is_not_fpl_start_bench_recommendation(self):
        article = {"url": URL, "title": "GW10 Team Selection",
                   "gameweek": 10, "published_at": NOW.isoformat()}
        page = (b"<article><h3>Team News</h3>"
                b"<p>I am expecting Saliba to start for Arsenal next weekend.</p>"
                b"<p>I think Gabriel will play 90 minutes.</p></article>")
        players = BOOT["elements"] + [{"id": 19, "web_name": "Saliba",
                                     "team": 1, "status": "a", "element_type": 2}]
        self.assertEqual(extract_article_opinions(page, article, players), [])

    def test_sell_scope_excludes_unrelated_defender_names(self):
        article = {"url": URL, "title": "GW10 Transfer Plans",
                   "gameweek": 10, "published_at": NOW.isoformat()}
        page = (b"<article><h3>Transfer Plans</h3>"
                b"<p>I plan on removing Konsa and Calafiori later on, "
                b"while Gabriel and Saliba are alternatives.</p></article>")
        players = BOOT["elements"] + [
            {"id": 19, "web_name": "Saliba", "team": 1, "status": "a", "element_type": 2},
            {"id": 20, "web_name": "Konsa", "team": 1, "status": "a", "element_type": 2},
            {"id": 21, "web_name": "Calafiori", "team": 1, "status": "a", "element_type": 2},
        ]
        found = extract_article_opinions(page, article, players)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["action"], "SELL_CONSIDER")
        self.assertEqual({p["name"] for p in found[0]["players"]},
                         {"Konsa", "Calafiori"})

    def test_no_names_or_verified_fpl_player_ids_means_no_buy_opinion(self):
        article = {"url": URL, "title": "GW10 Transfer Plans",
                   "gameweek": 10, "published_at": NOW.isoformat()}
        source = b"<article><p>I am planning to bring in A Fictional Player.</p></article>"
        self.assertFalse(extract_article_opinions(source, article, BOOT["elements"]))

    def test_fresh_gw11_does_not_reuse_gw10_article(self):
        future = dict(BOOT, events=[{"id": 11, "is_next": True,
                         "deadline_time": "2026-11-20T18:30:00Z"}])
        report = build_day1_brief(bootstrap=future, feed_xml=RSS,
                                  article_pages={URL: HTML}, now=NOW)
        self.assertEqual(report["status"], "no_current_articles")
        self.assertFalse(report["opinions"])

    def test_deadline_passed_and_old_feed_fail_closed(self):
        late = build_day1_brief(
            bootstrap=BOOT, feed_xml=RSS, article_pages={URL: HTML},
            now=NOW + timedelta(hours=7))
        self.assertEqual(late["status"], "deadline_passed")
        outdated = dict(BOOT, events=[{"id": 10, "is_next": True,
                              "deadline_time": "2026-11-20T18:30:00Z"}])
        result = build_day1_brief(bootstrap=outdated, feed_xml=RSS,
                                  article_pages={URL: HTML},
                                  now=NOW + timedelta(days=9))
        self.assertEqual(result["status"], "no_current_articles")

    def test_live_wordpress_index_fallback_uses_current_publication_date(self):
        index = [{"title": {"rendered": "GW10 Transfer Plans and Team Selection"},
                  "link": URL, "date_gmt": "2026-11-04T12:00:00"}]
        def fake_fetch(url):
            if url.endswith("/feed/"):
                raise OSError("RSS blocked")
            if "wp-json/wp/v2/posts" in url:
                return json.dumps(index).encode()
            if url == URL:
                return HTML
            raise AssertionError("Unexpected external URL")
        with patch("vortex.day1_live_editorial._fetch", side_effect=fake_fetch):
            report = build_day1_brief(bootstrap=BOOT, now=NOW)
        self.assertEqual(report["status"], "verified_author_opinions")
        self.assertGreater(len(report["opinions"]), 1)

    def test_unavailable_source_never_reuses_curated_gw10_json(self):
        with patch("vortex.day1_live_editorial._fetch", side_effect=OSError("offline")):
            data = build_day1_brief()
        self.assertEqual(data["status"], "source_unavailable")
        self.assertEqual(data["opinions"], [])

    def test_presenter_voice_and_youtube_credit_use_current_attributed_source(self):
        data = self.report()
        data["retrieved_at"] = datetime.now(timezone.utc).isoformat()
        with TemporaryDirectory() as dirname:
            path = Path(dirname) / "source.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            with patch.dict(os.environ, {"VORTEX_EDITORIAL_BRIEF": str(path)}):
                voice = presenter_note(10, [{"id": 12}, {"id": 11}], max_items=2)
                credits = source_credits(10)
                self.assertIn("There's another angle I'm checking", voice)
                self.assertIn("Tavernier", voice)
                self.assertIn("AllAboutFPL", credits)
                self.assertIn(URL, credits)
                self.assertEqual(presenter_note(11, [{"id": 12}]), "")
                self.assertEqual(source_credits(11), "")

    def test_premium_design_scoped_to_agenda_not_original_player_card(self):
        page = render_intro_agenda([{
            "key": "squad", "title": "SQUAD PRESSURE",
            "subtitle": "OFFICIAL PLAYER DATA", "anchor": "Squad",
            "speech": "Squad pressure",
        }])
        self.assertIn('id="vx-day1-agenda-premium"', page)
        self.assertIn("background:linear-gradient(135deg,#ffffff", page)
        self.assertIn(".agendaWrap .agenda-card", page)
        self.assertNotIn(".vx-player-card", page)
        self.assertEqual(page.count('class="agenda-card '), 1)


if __name__ == "__main__":
    unittest.main()
