import unittest

from vortex.day1_value_board import build_value_board


def sample():
    squad, forecasts, teams, fixtures = [], [], {}, []
    counts = ((1, 2), (2, 5), (3, 5), (4, 3))
    for team_id in range(1, 16):
        teams[team_id] = {"name": f"Club {team_id}", "short": f"C{team_id}", "badge": ""}
    index = 0
    for position, count in counts:
        for _ in range(count):
            index += 1
            squad.append({"id": index, "element_type": position, "team": index,
                          "web_name": f"Player {index}", "now_cost": 50})
            for gw in range(11, 16):
                forecasts.append({"player_id": index, "gameweek": gw,
                                  "gameweek_expected_points": float(index) / 10})
    return squad, forecasts, teams, fixtures


class ValueBoardTests(unittest.TestCase):
    def build(self):
        squad, forecasts, teams, fixtures = sample()
        return build_value_board(gameweek=11, squad=squad, forecasts=forecasts,
                                 fixtures=fixtures, teams=teams)

    def test_15_player_board_and_legal_xi(self):
        board = self.build()
        self.assertEqual(len(board["starters"]), 11)
        self.assertEqual(len(board["bench"]), 4)
        self.assertEqual(board["totalCost"], 75.0)
        self.assertEqual(board["bank"], 25.0)
        self.assertEqual(len(board["projections"]), 5)
        self.assertEqual(sum(p["captain"] for p in board["starters"]), 1)
        self.assertEqual(sum(p["viceCaptain"] for p in board["starters"]), 1)
        from collections import Counter
        formation = Counter(p["position"] for p in board["starters"])
        self.assertEqual(formation["GK"], 1)
        self.assertGreaterEqual(formation["DEF"], 3)
        self.assertGreaterEqual(formation["MID"], 2)
        self.assertGreaterEqual(formation["FWD"], 1)

    def test_missing_projection_fails_closed(self):
        squad, forecasts, teams, fixtures = sample()
        with self.assertRaisesRegex(ValueError, "Missing player projection"):
            build_value_board(gameweek=11, squad=squad, forecasts=forecasts[:-1],
                              fixtures=fixtures, teams=teams)

    def test_invalid_squad_rejected(self):
        squad, forecasts, teams, fixtures = sample()
        with self.assertRaisesRegex(ValueError, "15 unique"):
            build_value_board(gameweek=11, squad=squad[:-1], forecasts=forecasts,
                              fixtures=fixtures, teams=teams)

    def test_budget_rejected(self):
        squad, forecasts, teams, fixtures = sample()
        squad[0]["now_cost"] = 400
        with self.assertRaisesRegex(ValueError, "exceeds"):
            build_value_board(gameweek=11, squad=squad, forecasts=forecasts,
                              fixtures=fixtures, teams=teams)

    def test_no_unverified_fixture_data_fabricated(self):
        board = self.build()
        self.assertEqual(board["nextFixtures"], [])
        self.assertEqual(board["starters"][0]["fixtures"], [])


if __name__ == "__main__":
    unittest.main()
