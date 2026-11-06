from __future__ import annotations

import unittest
from pathlib import Path

from vortex.day1_agenda import (
    build_intro_agenda, render_intro_agenda, spoken_intro_agenda,
)

ROOT = Path(__file__).resolve().parents[1]


def review_segments(comparison=True):
    names = ["headline", "editorial_squad_context", "editorial_tradeoff",
             "editorial_routes", "editorial_verdict"]
    if comparison:
        names.append("editorial_comparison")
    return [{"id": n, "text": "Verified example"} for n in names]


class Day1AgendaTests(unittest.TestCase):
    def test_default_review_has_five_matched_voiceover_beats(self):
        cards = build_intro_agenda(
            ["00_intro", "gw_review"], next_gw=12, review_gw=11,
            review_status="FINAL", review_segments=review_segments(),
        )
        self.assertEqual([c["key"] for c in cards],
                         ["review", "squad", "alternatives", "routes", "verdict"])
        self.assertEqual(cards[0]["title"], "GAMEWEEK REVIEW — THE REAL STORY")
        self.assertIn("GW11", cards[0]["subtitle"])
        self.assertEqual([item["title"] for item in cards], [
            "GAMEWEEK REVIEW — THE REAL STORY",
            "SQUAD PRESSURE — WHAT NEEDS FIXING?",
            "TRANSFER TARGETS — BUY / HOLD / SELL",
            "TRANSFER PLANS — ROLL, MOVE OR TAKE A HIT?",
            "THE FINAL VORTEX VERDICT",
        ])
        self.assertEqual(render_intro_agenda(cards).count('class="agenda-card '), 5)
        narration = spoken_intro_agenda(cards).lower()
        for c in cards:
            self.assertEqual(narration.count(c["anchor"].lower()), 1)

    def test_provisional_uses_safe_language_and_no_invented_target(self):
        cards = build_intro_agenda(
            ["00_intro", "gw_review"], next_gw=12, review_gw=11,
            review_status="LIVE/PARTIAL", review_segments=review_segments(False),
        )
        self.assertIn("MAY CHANGE", cards[0]["subtitle"])
        self.assertEqual(cards[2]["key"], "tradeoffs")
        self.assertNotIn("realistic alternatives", spoken_intro_agenda(cards).lower())

    def test_enabled_scenes_only_and_no_duplicate_review_sections(self):
        cards = build_intro_agenda(
            ["00_intro", "gw_review", "02_fdr", "03_projected_goals", "04_clean_sheets"],
            next_gw=24, review_gw=23, review_status="FINAL",
            review_segments=review_segments(),
        )
        self.assertEqual([c["key"] for c in cards],
                         ["review", "squad", "alternatives", "routes", "verdict"])
        one = build_intro_agenda(["00_intro", "04_clean_sheets"], next_gw=24)
        self.assertEqual([c["key"] for c in one], ["defence"])
        self.assertEqual(build_intro_agenda(["gw_review"], next_gw=24), [])

    def test_blocks_unsupported_review_or_gameweek(self):
        with self.assertRaisesRegex(ValueError, "missing editorial"):
            build_intro_agenda(["00_intro", "gw_review"], next_gw=10,
                               review_gw=9, review_segments=[{"id": "headline"}])
        with self.assertRaisesRegex(ValueError, "inconsistent"):
            build_intro_agenda(["00_intro", "gw_review"], next_gw=9,
                               review_gw=9, review_segments=review_segments())
        with self.assertRaisesRegex(ValueError, "Unknown"):
            build_intro_agenda(["00_intro", "mystery"], next_gw=12)

    def test_safe_html_and_mobile_friendly_short_subtitles(self):
        html = render_intro_agenda([{
            "key": "one", "title": "<script>", "subtitle": "A & B",
            "anchor": "One", "speech": "One",
        }])
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("<script>", html)
        self.assertIn("A &amp; B", html)
        self.assertIn('class="agenda-card agenda-1"', html)

    def test_existing_source_binds_intro_visuals_speech_and_timing(self):
        source = (ROOT / "1_final_day1.py").read_text(encoding="utf-8")
        self.assertIn("VX_INTRO_AGENDA = build_intro_agenda(", source)
        self.assertIn("VX_INTRO_AGENDA_SPOKEN = spoken_intro_agenda(VX_INTRO_AGENDA)", source)
        self.assertIn("INTRO = render_brief(VX_BRIEF, logo_html=vortex_logo_html, cards=VX_INTRO_AGENDA)", source)
        self.assertNotIn("agenda_cards=VX_INTRO_AGENDA_HTML", source)
        self.assertIn("{VX_INTRO_AGENDA_SPOKEN}", source)
        self.assertIn("for _agenda_index, _agenda in enumerate(VX_INTRO_AGENDA, 1)", source)
        self.assertIn('context=f"00_intro agenda {_agenda_index}"', source)
        self.assertIn('"agenda":VX_INTRO_AGENDA if key=="00_intro" else []', source)
        self.assertIn("fixture_grid_window", source)
        self.assertNotIn('data-vx-type="MY GAMEWEEK REVIEW"', source)


if __name__ == "__main__":
    unittest.main()
