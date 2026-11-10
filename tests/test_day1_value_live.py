import unittest

from vortex.day1_value_live import make_live_value_board, select_next_gw


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

    def test_missing_next_gw_fails_closed(self):
        with self.assertRaises(ValueError):
            select_next_gw([{"id": 11, "is_next": False}])

    def test_timed_fixture_and_captain_adjusted_plan(self):
        snap = snapshot()
        snap["fixtures"][0]["kickoff_time"] = "2026-11-21T12:30:00Z"
        board = make_live_value_board(snapshot=snap)
        fixture = board["nextFixtures"][0]
        self.assertEqual(fixture["kickoffLabel"], "Sat 21 Nov 12:30 GMT")
        self.assertTrue(fixture["homeBadge"].endswith("t801.png"))
        players = {p["id"]: p for p in board["starters"] + board["bench"]}
        for plan in board["weeklyPlans"]:
            captain = players[plan["captainId"]]
            self.assertIn(captain["id"], plan["starters"])
            self.assertIn(plan["viceCaptainId"], plan["starters"])
            self.assertNotEqual(plan["captainId"], plan["viceCaptainId"])
            base = sum(players[pid]["weekly"][plan["gameweek"]] for pid in plan["starters"])
            self.assertEqual(plan["startingXiXpts"], round(base, 2))
            self.assertEqual(plan["captainAdjustedXpts"], round(base + captain["weekly"][plan["gameweek"]], 2))


if __name__ == "__main__":
    unittest.main()
