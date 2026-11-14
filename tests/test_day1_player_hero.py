import unittest

from vortex.day1_player_hero import add_recent_context, analyze, narration, render, spoken_scoring


def example():
    bootstrap = {
        "events": [{"id": 8, "finished": True, "data_checked": True},
                   {"id": 9, "finished": True, "data_checked": False}],
        "teams": [{"id": 1, "name": "Example City"}, {"id": 2, "name": "Example Town"}],
        "element_types": [{"id": 3, "singular_name": "Midfielder"}],
        "elements": [{"id": 4, "web_name": "Hero Name", "first_name": "Long forename",
                      "team": 1, "element_type": 3, "now_cost": 80}],
    }
    fixtures = [{"id": 21, "event": 8, "finished": True, "team_h": 1, "team_a": 2,
                 "team_h_score": 2, "team_a_score": 0, "team_h_difficulty": 3}]
    live = {"elements": [{"id": 4, "stats": {
        "minutes": 90, "total_points": 10, "goals_scored": 1, "expected_goals": ".5",
    }, "explain": [{"fixture": 21, "stats": [
        {"identifier": "minutes", "points": 2}, {"identifier": "goals_scored", "points": 5},
        {"identifier": "bonus", "points": 3},
    ]}]}]}
    return bootstrap, fixtures, live


class PlayerHeroTests(unittest.TestCase):
    def test_checked_gameweek_and_reconciled_points(self):
        hero = analyze(*example(), 8)
        self.assertEqual(hero["name"], "Hero Name")
        self.assertEqual(sum(hero["breakdown"].values()), 10)
        self.assertEqual(hero["captain_points"], 20)
        with self.assertRaisesRegex(ValueError, "latest completed"):
            analyze(*example(), 9)
        bootstrap, fixtures, live = example()
        live["elements"][0]["stats"]["total_points"] = 11
        with self.assertRaisesRegex(ValueError, "reconciles"):
            analyze(bootstrap, fixtures, live, 8)

    def test_visible_metrics_and_spoken_reasons_omit_unknowns(self):
        hero = analyze(*example(), 8)
        add_recent_context(hero, [{"round": week, "minutes": 65} for week in (5, 6, 7)])
        script = narration(hero, hero["name"])
        self.assertIn("195 minutes", script)
        self.assertIn("5 from goals", script)
        self.assertNotIn("Shots", render(hero, {}, "", "", ""))
        self.assertNotIn("Long forename", script)
        self.assertIn("1 lost to yellow cards", spoken_scoring({"yellow_cards": -1}))
