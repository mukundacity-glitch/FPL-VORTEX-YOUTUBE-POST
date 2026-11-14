import unittest

from vortex.day1_value_live import _hero_stats, _optimise, _resolve_picks, make_live_value_board, select_next_gw
from vortex.day1_value_render import narration_parts

import numpy as np


def snapshot():
    team_ids = range(1, 21)
    teams = [{"id": i, "name": f"Club {i}", "short_name": f"C{i}",
              "code": i + 800} for i in team_ids]
    players = []
    position_counts = {1: 3, 2: 7, 3: 6, 4: 4}
    idx = 0
    for position, count in position_counts.items():
        for j in range(count):
            idx += 1
            players.append({
                "id": idx, "code": idx + 9000, "web_name": f"P{idx}",
                "first_name": "Player", "second_name": str(idx),
                "team": idx, "element_type": position,
                "status": "i" if idx == 20 else "a",
                "selected_by_percent": "14.0",
                "transfers_in_event": 2000 + idx,
                "transfers_out_event": 1000,
                "minutes": 900, "starts": 10,
                "points_per_game": "4.2", "form": "4.4",
                "expected_goal_involvements_per_90": "0.2",
                "ep_next": "4.4", "now_cost": 45 if j else 40,
            })
    fixtures = []
    for week in range(11, 16):
        for j in range(10):
            fixtures.append({
                "id": week*100+j, "event": week, "team_h": 2*j+1,
                "team_a": 2*j+2, "team_h_difficulty": 3,
                "team_a_difficulty": 3, "kickoff_time": None,
            })
    return {"bootstrap": {"events": [{"id": 11, "is_next": True}],
                           "elements": players, "teams": teams},
            "fixtures": fixtures}


class LiveValueTests(unittest.TestCase):
    def test_injury_budget_formation_and_five_weeks(self):
        board = make_live_value_board(snapshot=snapshot())
        self.assertEqual(board["nextGameweek"], 11)
        self.assertEqual(len(board["starters"]), 11)
        self.assertEqual(len(board["bench"]), 4)
        self.assertLessEqual(board["totalCost"], 100)
        self.assertEqual(len(board["weeklyPlans"]), 5)
        self.assertEqual(len(board["projections"]), 5)
        self.assertNotIn(20, {p["id"] for p in board["starters"]+board["bench"]})
        self.assertEqual(len(board["nextFixtures"]), 10)
        self.assertTrue(all("ownership" in p and "minutesPerAppearance" in p
                            and "clubSpeechName" in p for p in board["starters"]))

    def test_gw_without_matches_has_no_points(self):
        snap = snapshot()
        snap["fixtures"] = [x for x in snap["fixtures"] if x["event"] != 15]
        board = make_live_value_board(snapshot=snap)
        self.assertEqual(board["projections"][-1]["xpts"], 0.0)

    def test_playing_keeper_filter_and_hero_narration(self):
        snap = snapshot()
        snap["bootstrap"]["elements"][0].update(minutes=0, starts=0)
        board = make_live_value_board(snapshot=snap)
        picks = board["starters"] + board["bench"]
        self.assertEqual({p["id"] for p in picks if p["position"] == "GK"}, {2, 3})
        parts = narration_parts(board)
        self.assertCountEqual([pid for pid, _ in parts if pid], [p["id"] for p in picks])
        self.assertIn("ten defensive actions", " ".join(line for _, line in parts))

    def test_defcon_uses_only_played_appearances_before_deadline(self):
        history = [{"round": gw, "minutes": minutes, "starts": int(minutes >= 60),
                    "defensive_contribution": actions}
                   for gw, minutes, actions in [(8, 90, 10), (9, 0, 0), (10, 70, 9), (11, 90, 12)]]
        stats = _hero_stats({"minutes": 160, "goals_scored": 1}, history, 11)
        self.assertEqual((stats["defconHits"], stats["defconAppearances"]), (1, 2))
        self.assertEqual(stats["minutesPerStart"], 80)
        self.assertEqual(stats["goals90"], .56)
        self.assertIsNone(stats["xa90"])

    def test_budget_retains_preferred_core_and_uses_midfield_replacement(self):
        players = snapshot()["bootstrap"]["elements"]
        preferred = {i: players[i - 1]["element_type"]
                     for i in [1, 2, 4, 5, 6, 7, 8, 11, 12, 13, 14, 15, 17, 18, 19]}
        costs = [6.0] * len(players)
        costs[10] = 19
        scores = [5.0] * len(players)
        choices = _optimise(players, costs, scores, scores, np.full(len(players), 90.0),
                            budget=101, preferred=preferred, options={16: 11})
        self.assertEqual({p["id"] for p in choices}, set(preferred) - {11} | {16})

    def test_requested_alias_resolves_without_an_id(self):
        preferences = dict(goalkeepers=[], defenders=[], midfielders=["Bruno Fernandes"],
                           forwards=[], alternatives={"Bruno Fernandes": ["Pascal Groß"]})
        players = [
            dict(id=1, element_type=3, first_name="Bruno", second_name="Borges Fernandes", web_name="B.Fernandes"),
            dict(id=2, element_type=3, first_name="Pascal", second_name="Groß", web_name="Groß"),
        ]
        self.assertEqual(_resolve_picks(players, preferences), ({1: 3}, {2: 1}, []))

    def test_missing_next_gw_fails_closed(self):
        with self.assertRaises(ValueError):
            select_next_gw([{"id": 11, "is_next": False}])


if __name__ == "__main__":
    unittest.main()
