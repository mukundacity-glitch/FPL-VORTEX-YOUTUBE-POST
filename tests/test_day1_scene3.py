import unittest

from vortex.day1_scene3 import build_scene, narration, tile_rating, timing


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

    def test_measured_cues_must_remain_in_order(self):
        beats = [("opening", "Welcome."), ("fixtures", "Here is the full schedule."), ("heatmap", "Five week map.")]
        def span(words, phrase, **_):
            return words[phrase.rstrip(".")], .5
        normalizer = lambda line, **_: line
        self.assertEqual([x["at"] for x in timing(beats, {"Here is the full schedule": 7, "Five week map": 28}, span, normalizer)], [0, 7, 28])
        with self.assertRaisesRegex(ValueError, "out of order"):
            timing(beats, {"Here is the full schedule": 28, "Five week map": 7}, span, normalizer)
