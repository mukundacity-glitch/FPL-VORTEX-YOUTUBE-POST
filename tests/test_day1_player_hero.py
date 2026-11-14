import re
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
    for pid, name, cost, owned, points, xg in (
        (5, "Value Name", 40, "14.2", 8, ".21"),
        (6, "Differential Name", 60, "4.3", 6, ".40"),
        (7, "Other Name", 105, "18.0", 9, ".40"),
    ):
        bootstrap["elements"].append({"id": pid, "web_name": name, "team": 1,
                                      "element_type": 3, "now_cost": cost, "selected_by_percent": owned})
        live["elements"].append({"id": pid, "stats": {
            "minutes": 70, "total_points": points, "goals_scored": 1, "expected_goals": xg,
        }, "explain": [{"fixture": 21, "stats": [
            {"identifier": "minutes", "points": 2},
            {"identifier": "goals_scored", "points": 5},
            {"identifier": "bonus" if points >= 7 else "yellow_cards", "points": points - 7},
        ]}]})
    return bootstrap, fixtures, live


class PlayerHeroTests(unittest.TestCase):
    def test_checked_gameweek_and_reconciled_points(self):
        report = analyze(*example(), 8)
        self.assertEqual([p["name"] for p in report["players"]],
                         ["Hero Name", "Value Name", "Differential Name"])
        hero = report["players"][0]
        self.assertEqual(report["candidates_analyzed"], 4)
        self.assertEqual(sum(hero["breakdown"].values()), 10)
        self.assertEqual(hero["captain_points"], 20)
        with self.assertRaisesRegex(ValueError, "latest completed"):
            analyze(*example(), 9)
        bootstrap, fixtures, live = example()
        live["elements"][0]["stats"]["total_points"] = 11
        self.assertNotIn(4, [p["player_id"] for p in analyze(bootstrap, fixtures, live, 8)["players"]])
        live["elements"][1]["stats"]["total_points"] = 12
        with self.assertRaisesRegex(ValueError, "reconcile"):
            analyze(bootstrap, fixtures, live, 8)

    def test_visible_metrics_and_spoken_reasons_omit_unknowns(self):
        report = analyze(*example(), 8)
        add_recent_context(report["players"][0], [{"round": week, "minutes": 65} for week in (5, 6, 7)], 8)
        names = [p["name"] for p in report["players"]]
        script = narration(report, names)
        self.assertIn("195 minutes", script)
        self.assertIn("5 from goals", script)
        html = render(report, [3, 35, 70], dict.fromkeys([4, 5, 6], ("", "")), "")
        self.assertNotIn("Shots", html)
        self.assertEqual(html.count('class="profile"'), 3)
        self.assertLess(len(narration(report, names, compact=True).split()), len(script.split()))
        self.assertNotIn("Long forename", script)
        self.assertIn("1 lost to yellow cards", spoken_scoring({"yellow_cards": -1}))


    def test_shared_match_and_takeaway_are_narrated_once(self):
        report = analyze(*example(), 8)
        for player in report["players"]:
            player["takeaway"] = "Goals ran ahead of chance quality. Check whether the chances recur."
        names = [p["name"] for p in report["players"]]
        for compact in (False, True):
            with self.subTest(compact=compact):
                script = narration(report, names, compact=compact)
                sentences = [" ".join(s.lower().split())
                             for s in re.split(r"(?<=[.!?])\s+", script)]
                self.assertEqual(len(sentences), len(set(sentences)))
                self.assertEqual(script.count("Check whether the chances recur."), 1)
                self.assertEqual(script.count("The match against Example Town"), int(not compact))
                self.assertTrue(all(name in script for name in names))

    def test_exceptional_defender_can_fill_third_slot_when_no_differential_qualifies(self):
        bootstrap, fixtures, live = example()
        bootstrap["elements"][2]["selected_by_percent"] = "12"
        bootstrap["element_types"].append({"id": 2, "singular_name": "Defender"})
        bootstrap["elements"][3]["element_type"] = 2
        live["elements"][3]["explain"][0]["stats"][2]["identifier"] = "clean_sheets"
        result = analyze(bootstrap, fixtures, live, 8)
        self.assertEqual(result["players"][2]["selection"]["category"], "Defensive standout")
