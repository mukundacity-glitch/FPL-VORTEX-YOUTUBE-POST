import ast
import hashlib
import math
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from vortex.fixture_forecast import build_weekly_frame, fixture_values, model, validate_rows, patch_weekly_source, weekly_clean_sheets


class SharedFixtureTests(unittest.TestCase):
    def setUp(self):
        self.fixtures = [dict(id=10, event=7, team_h=1, team_a=2, finished=False,
                              kickoff_time="2026-10-30T15:00:00Z", team_h_difficulty=5, team_a_difficulty=1)]
        self.rows = [dict(fixture_id=10, gameweek=7, home_team_id=1, away_team_id=2,
                         model_lambda_home=2.16, model_lambda_away=0.73,
                         model_lambda_home_nonpenalty=1.96, model_lambda_home_penalty=.2,
                         model_lambda_away_nonpenalty=.63, model_lambda_away_penalty=.1,
                         home_clean_sheet_probability=math.exp(-.73), away_clean_sheet_probability=math.exp(-2.16),
                         data_snapshot_timestamp="2026-10-27T20:00:00+00:00")]

    def test_all_consumers_keep_identical_goals_cs_and_position_fdr(self):
        namespace = dict(teams=pd.DataFrame([dict(id=1), dict(id=2)]),
                         events=pd.DataFrame([dict(id=7)]), players=pd.DataFrame(), fixtures=pd.DataFrame(self.fixtures))
        columns = list(self.rows[0]) + ['model_lambda_home_low', 'model_lambda_home_high', 'model_confidence']
        namespace.update(fixture_context_phase2=pd.DataFrame([{k: self.rows[0][k] for k in
            ('fixture_id', 'gameweek', 'home_team_id', 'away_team_id')}]),
            team_strength_updated=pd.DataFrame([dict(team_id=1), dict(team_id=2)]),
            team_priors=pd.DataFrame([dict(team_id=1), dict(team_id=2)]),
            PHASE3_OUTPUT_FIELDS=columns, model_version='test',
            _phase0_is_pre_deadline=lambda gw: True,
            _vx_phase3_team_uncertainty=lambda *args: .25,
            _vx_phase3_lambda_range=lambda lam, u: (lam * math.exp(-u), lam * math.exp(u)))
        with patch("vortex.fixture_forecast.forecast_rows", return_value=self.rows):
            weekly = build_weekly_frame(namespace)
        self.assertEqual(list(weekly.columns), columns)
        self.assertEqual(weekly.iloc[0].gameweek, 7)
        self.assertEqual(weekly.iloc[0].model_confidence, math.exp(-math.sqrt(.25 ** 2 + .25 ** 2)))
        for team, side in ((1, "home"), (2, "away")):
            for position in ("GK", "DEF", "MID", "FWD"):
                wc = fixture_values(self.rows, 10, team, position)
                self.assertEqual(float(weekly.iloc[0][f"model_lambda_{side}"]), wc["projected_goals"])
                opponent = "away" if side == "home" else "home"
                self.assertEqual(math.exp(-float(weekly.iloc[0][f"model_lambda_{opponent}"])), wc["clean_sheet_probability"])
        self.assertNotEqual(fixture_values(self.rows, 10, 1, "DEF")['fdr'], fixture_values(self.rows, 10, 1, "MID")['fdr'])
        self.assertEqual(weekly.iloc[0].model_lambda_home_nonpenalty + weekly.iloc[0].model_lambda_home_penalty, 2.16)
        self.assertEqual(weekly_clean_sheets(namespace, 10, 2.16, .73), (math.exp(-.73), math.exp(-2.16)))
        with self.assertRaisesRegex(ValueError, 'snapshot drift'):
            weekly_clean_sheets(namespace, 10, 2.17, .73)

    def test_incomplete_duplicate_swapped_or_invalid_forecasts_fail(self):
        validate_rows(self.rows, self.fixtures)
        cases = [[], self.rows * 2]
        for change in (dict(home_team_id=2), dict(gameweek=8), dict(model_lambda_home=float("nan")),
                       dict(home_clean_sheet_probability=.99)):
            cases.append([dict(self.rows[0], **change)])
        for rows in cases:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                validate_rows(rows, self.fixtures)

    def test_double_gameweek_keeps_two_forecasts(self):
        fixtures = self.fixtures + [dict(self.fixtures[0], id=11, kickoff_time="2026-10-31T15:00:00Z")]
        rows = self.rows + [dict(self.rows[0], fixture_id=11, model_lambda_home=1.3,
                               away_clean_sheet_probability=math.exp(-1.3))]
        validate_rows(rows, fixtures)
        self.assertEqual(len(rows), 2)

    def test_exact_wc_formulas_and_boundaries(self):
        for goals in (.4, .73, 1.5, 2.16, 3.2):
            self.assertAlmostEqual(model.vx_phase4_attack_fdr(goals), min(5, max(1, 1 + 4 * (3.2 - goals) / 2.8)))
        self.assertEqual(model.vx_phase4_attack_fdr(3.2), 1)
        self.assertEqual(model.vx_phase4_attack_fdr(.4), 5)
        self.assertEqual(model.vx_phase4_defence_fdr(math.exp(-.4)), 1)
        self.assertEqual(model.vx_phase4_defence_fdr(math.exp(-3.2)), 5)

    def test_weekly_patch_rejects_source_drift(self):
        for source in ('pass', 'def vx_phase4_attack_fdr(x):\n    return x\n'):
            with self.assertRaises(ValueError):
                patch_weekly_source(source)

    def test_day1_cards_use_shared_fixture_numbers(self):
        from day1.roundup import upcoming
        snapshot = {"bootstrap": {"teams": [{"id": 1, "name": "Home", "short_name": "HOM"}, {"id": 2, "name": "Away", "short_name": "AWA"}]}, "fixtures": self.fixtures}
        player = {"id": 99, "team": 1, "element_type": 2}
        first = upcoming(player, snapshot, self.rows, self.rows[0]["gameweek"])[0]["fixtures"][0]
        self.assertEqual(first["projected_goals"], 2.16)
        self.assertEqual(first["clean_sheet_probability"], math.exp(-.73))
        self.assertEqual(first["fdr"], model.vx_phase4_defence_fdr(math.exp(-.73)))
        attack = upcoming(dict(player, element_type=3), snapshot, self.rows, self.rows[0]["gameweek"])[0]["fixtures"][0]
        self.assertEqual(attack["fdr"], model.vx_phase4_attack_fdr(2.16))

    def test_vendored_math_is_ast_identical_to_wc_pin(self):
        # Only extra diagnostic fields may differ from the checksum-verified
        # reference. Any change to evidence checks or mathematics fails here.
        tree = ast.parse(Path(model.__file__).read_text())
        reference_keys = {'fixture_id', 'gameweek', 'home_team_id', 'away_team_id',
            'model_lambda_home', 'model_lambda_away', 'home_clean_sheet_probability',
            'away_clean_sheet_probability', 'data_snapshot_timestamp', 'source_name'}
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                keys = {k.value for k in node.keys if isinstance(k, ast.Constant)}
                if reference_keys <= keys:
                    pairs = [(k, v) for k, v in zip(node.keys, node.values) if k.value in reference_keys]
                    node.keys, node.values = [k for k, _ in pairs], [v for _, v in pairs]
        self.assertEqual(hashlib.sha256(ast.dump(tree).encode()).hexdigest(),
                         '03b9a5236aab44c6846d37710703f98dbaaaf686f14fff66e8c419bf40922ed1')


if __name__ == "__main__":
    unittest.main()
