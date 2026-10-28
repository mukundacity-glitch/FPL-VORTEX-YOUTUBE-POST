import math
import unittest

from day2.fixture_forecast import fixture_map, rating
from vortex.fixture_forecast import fixture_values


class Day2FixtureReplacementTests(unittest.TestCase):
    def setUp(self):
        self.fixtures = [dict(id=10, event=7, team_h=1, team_a=2, finished=False,
                              kickoff_time='2026-10-30T15:00:00Z', team_h_difficulty=5, team_a_difficulty=1)]
        self.rows = [dict(fixture_id=10, gameweek=7, home_team_id=1, away_team_id=2,
                         model_lambda_home=2.16, model_lambda_away=.73,
                         home_clean_sheet_probability=math.exp(-.73), away_clean_sheet_probability=math.exp(-2.16))]
        self.teams = {1: dict(name='One', short_name='ONE'), 2: dict(name='Two', short_name='TWO')}

    def test_all_position_ratings_match_wc_fh_without_integer_rounding(self):
        for team in (1, 2):
            for raw, position in ((1, 'GK'), ('GKP', 'GK'), (2, 'DEF'), (3, 'MID'), (4, 'FWD')):
                value = rating(self.rows, 10, team, raw)
                self.assertEqual(value, fixture_values(self.rows, 10, team, position)['fdr'])
                self.assertNotEqual(value, int(value))

    def test_map_keeps_exact_goals_and_cs_and_does_not_invent_blank_fixtures(self):
        cards = fixture_map(self.fixtures, self.teams, self.rows, [7, 8])
        self.assertEqual(cards[1][7]['projected_goals'], 2.16)
        self.assertEqual(cards[1][7]['clean_sheet_probability'], math.exp(-.73))
        self.assertNotIn(8, cards[1])
        self.assertEqual(set(cards[1]), {7})

    def test_double_keeps_existing_single_card_and_all_math_records(self):
        fixtures = self.fixtures + [dict(self.fixtures[0], id=11, kickoff_time='2026-10-31T15:00:00Z')]
        rows = self.rows + [dict(self.rows[0], fixture_id=11, model_lambda_home=1.3,
                               away_clean_sheet_probability=math.exp(-1.3))]
        cards = fixture_map(list(reversed(fixtures)), self.teams, rows, [7, 8])
        self.assertEqual(cards[1][7]['fixture_id'], 10)
        self.assertNotEqual(rating(rows, 10, 1, 'MID'), rating(rows, 11, 1, 'MID'))
        self.assertEqual(len(rows), 2)


if __name__ == '__main__':
    unittest.main()
