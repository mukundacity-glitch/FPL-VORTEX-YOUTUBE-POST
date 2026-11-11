import unittest

from vortex.day1_scene3 import build_scene, market_board, market_narration, narration, tile_rating, timing


class Day1Scene3Tests(unittest.TestCase):
    def test_ratings_round_before_assigning_the_colour(self):
        for value, band, display in (
            (2.54, "easy", "2.5"), (2.55, "medium", "2.6"),
            (3.05, "hard", "3.1"), (4.05, "very-hard", "4.1"),
            (float("nan"), "missing", "N/A"),
        ):
            with self.subTest(value=value):
                self.assertEqual(tile_rating(value), {"band": band, "rating": display})

    def test_fixture_identity_retains_doubles_blanks_and_separate_model_values(self):
        teams = {i: {"name": f"Club {i}", "short": f"C{i}", "badge": ""} for i in range(1, 4)}
        fixtures = [{"event": 11, "id": 70, "team_h": 1, "team_a": 2},
                    {"event": 11, "id": 71, "team_h": 3, "team_a": 1}]
        model = [{"fixture_id": 70, "team_id": 1, "attack_fdr_model": 2.54, "defence_fdr_model": 4.5}]
        scene = build_scene(11, fixtures, teams, [], model, lambda _: {}, lambda _: "", "QA", "2026/27")
        self.assertEqual(len(scene["fixtures"]), 2)
        first_week, second_week, *_ = scene["rows"][0]["weeks"]
        self.assertEqual([(tile["opponent"], tile["venue"]) for tile in first_week], [("C2", "H"), ("C3", "A")])
        self.assertEqual(first_week[0]["attack"]["rating"], "2.5")
        self.assertEqual(first_week[0]["defence"]["rating"], "4.5")
        self.assertEqual(first_week[1]["attack"]["rating"], "N/A")
        self.assertEqual(second_week, [])
        self.assertEqual(narration(scene)[-1][0], "transition")

    def test_market_board_ranks_fdr_and_keeps_market_odds_separate(self):
        teams = {i: {"name": str(i)} for i in range(1, 4)}
        fixtures = [{"id": 5, "event": 11, "team_h": 1, "team_a": 2},
                    {"id": 6, "event": 12, "team_h": 2, "team_a": 3}]
        model = [{"fixture_id": 5, "team_id": 1, "attack_fdr_model": 2.54},
                 {"fixture_id": 5, "team_id": 2, "attack_fdr_model": 2.51},
                 {"fixture_id": 6, "team_id": 2, "attack_fdr_model": 1.0}]
        market = [{"fixture_id": 5, "market_home_win_probability": .7,
                   "market_away_win_probability": .15, "model_away_clean_sheet_probability": .35}]
        a, b = market_board(11, fixtures, teams, model, market, "QA")["targets"]
        self.assertEqual((a["team"]["name"], a["venue"], a["win"], a["clean_sheet"]), ("2", "A", .15, None))
        self.assertEqual((b["team"]["name"], b["venue"], b["win"]), ("1", "H", .7))

    def test_missing_market_odds_do_not_repeat_filler_sentences(self):
        scene = {
            "gw": 11,
            "targets": [
                {"team": {"name": f"Club {i}"}, "opponent": {"name": f"Rival {i}"},
                 "venue": "H", "rating": "2.0", "win": None, "clean_sheet": None}
                for i in range(5)
            ],
        }
        script = " ".join(line for _, line in market_narration(scene))
        self.assertNotIn("Market win chance: unavailable.", script)
        self.assertNotIn("Clean sheet chance: unavailable.", script)
        for i in range(5):
            self.assertIn(f"unavailable for Club {i}.", script)
        import re
        sentences = [x.strip().lower() for x in re.split(r"(?<=[.!?])\\s+", script) if x.strip()]
        self.assertEqual(len(sentences), len(set(sentences)))

    def test_measured_cues_must_remain_in_order(self):
        beats = [("opening", "Welcome."), ("fixtures", "Here is the full schedule."), ("heatmap", "Five week map.")]
        def span(words, phrase, **_):
            return words[phrase.rstrip(".")], .5
        normalizer = lambda line, **_: line
        self.assertEqual([x["at"] for x in timing(beats, {"Here is the full schedule": 7, "Five week map": 28}, span, normalizer)], [0, 7, 28])
        with self.assertRaisesRegex(ValueError, "out of order"):
            timing(beats, {"Here is the full schedule": 28, "Five week map": 7}, span, normalizer)
