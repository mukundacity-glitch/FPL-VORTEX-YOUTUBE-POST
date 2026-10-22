from __future__ import annotations

import ast
import types
import unittest
from unittest.mock import patch

from wc_fh.forecast_compat import install_team_aliases, patch_forecast_loader


class ForecastCompatibilityTests(unittest.TestCase):
    def model(self):
        model = types.ModuleType('vortex_upstream_fdr')
        def original(value):
            name = ' '.join(str(value or '').strip().lower().replace('&', 'and').replace('.', '').split())
            return {'spurs': 'tottenham hotspur', 'man city': 'manchester city',
                    'brighton': 'brighton and hove albion'}.get(name, name)
        model._vx_norm_team_name = original
        return model

    def test_provider_names_share_canonical_identity(self):
        model = self.model()
        install_team_aliases(model)
        for first, second in [('AFC Bournemouth', 'Bournemouth'),
                              ('Brighton & Hove Albion', 'Brighton Hove Albion'),
                              ('Sunderland A.F.C.', 'Sunderland'),
                              ('Ipswich', 'Ipswich Town'), ('Leicester', 'Leicester City'),
                              ('Spurs', 'Tottenham Hotspur'), ('Man City', 'Manchester City')]:
            with self.subTest(club=first):
                self.assertEqual(model._vx_norm_team_name(first), model._vx_norm_team_name(second))

    def test_distinct_clubs_and_unknown_names_are_not_guessed(self):
        model = self.model()
        install_team_aliases(model)
        for first, second in [('Manchester City', 'Manchester United'),
                              ('Bournemouth', 'Sunderland'), ('Newcastle United', 'Newcastle Jets'),
                              ('AFC Wimbledon', 'Wimbledon'), ('United', 'Manchester United')]:
            with self.subTest(club=first):
                self.assertNotEqual(model._vx_norm_team_name(first), model._vx_norm_team_name(second))
        self.assertEqual(model._vx_norm_team_name('Unknown FC'), 'unknown fc')

    def test_repeated_install_does_not_nest_wrappers(self):
        model = self.model()
        install_team_aliases(model)
        first = model._vx_norm_team_name
        install_team_aliases(model)
        self.assertIs(model._vx_norm_team_name, first)

    def test_missing_upstream_contract_fails_clearly(self):
        with self.assertRaisesRegex(ValueError, 'team-name contract changed'):
            install_team_aliases(types.ModuleType('changed_model'))

    def test_loader_installs_before_first_model_use(self):
        model = self.model()
        source = ('verified = True\nimport vortex_upstream_fdr\n'
                  "result = vortex_upstream_fdr._vx_norm_team_name('AFC Bournemouth')\n")
        patched = patch_forecast_loader(source)
        namespace = {}
        with patch.dict('sys.modules', {'vortex_upstream_fdr': model}):
            exec(patched, namespace)
        self.assertEqual(namespace['result'], 'bournemouth')

    def test_integrity_failure_still_prevents_import(self):
        source = "raise RuntimeError('hash mismatch')\nimport vortex_upstream_fdr\n"
        with self.assertRaisesRegex(RuntimeError, 'hash mismatch'):
            exec(patch_forecast_loader(source), {})

    def test_loader_refuses_missing_or_duplicate_import(self):
        for source in ('pass\n', 'import vortex_upstream_fdr\nimport vortex_upstream_fdr\n',
                       'import vortex_upstream_fdr as other\n'):
            with self.subTest(source=source), self.assertRaisesRegex(ValueError, 'loader contract changed'):
                patch_forecast_loader(source)

    def test_prepare_cells_routes_forecast_cell_through_compatibility(self):
        # Execute the real loader with the runner's required cells and ordinary controls.
        from wc_fh.run_notebook import prepare_cells
        from wc_fh.controls import request_controls
        notebook = {'cells': [{'cell_type': 'code', 'source': f'#@title CELL {label} - test\npass\n'}
                             for label in ('0', '1', '2', '8', '10', '11', '12', '13', '14', '15', '17')]}
        with patch('wc_fh.run_notebook.patch_setup', side_effect=lambda source, _: source), \
             patch('wc_fh.run_notebook.patch_forecast_loader', side_effect=RuntimeError('loader reached')):
            with self.assertRaisesRegex(RuntimeError, 'loader reached'):
                prepare_cells(notebook, request_controls({}))


if __name__ == '__main__':
    unittest.main()
