from __future__ import annotations

import subprocess
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from wc_fh.forecast_compat import CORE_TREE_URL, fetch_core_git_tree, install_team_aliases, patch_forecast_loader


class ForecastCompatibilityTests(unittest.TestCase):
    def model(self):
        model = types.ModuleType('vortex_upstream_fdr')
        def original(value):
            name = ' '.join(str(value or '').strip().lower().replace('&', 'and').replace('.', '').split())
            return {'spurs': 'tottenham hotspur', 'man city': 'manchester city',
                    'brighton': 'brighton and hove albion'}.get(name, name)
        model._vx_norm_team_name = original
        model.refresh_fpl_core = lambda boot, fixtures, root, now, client: client.get(
            CORE_TREE_URL, required=True, timeout=8,
        )
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

    def test_forecast_uses_current_git_tree_when_rest_returns_403(self):
        model = self.model()
        espn_url = "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/summary?event=123"
        model.refresh_fpl_core = lambda boot, fixtures, root, now, client: (
            client.get(CORE_TREE_URL, required=True, timeout=8),
            client.get(espn_url, required=True, timeout=6),
        )
        client = Mock()
        client.get.side_effect = [RuntimeError("Required current source unavailable; HTTPError HTTP 403"), {"rosters": []}]
        git_result = {"sha": "a" * 40, "tree": [{"path": "data/teams.csv", "type": "blob", "sha": "b" * 40}]}

        with patch.dict('sys.modules', {'vortex_upstream_fdr': model}), \
             patch('wc_fh.forecast_compat.fetch_core_git_tree', return_value=git_result) as fallback:
            exec(patch_forecast_loader('import vortex_upstream_fdr\n'), {})
            self.assertEqual(model.refresh_fpl_core(None, None, None, None, client), (git_result, {"rosters": []}))

        fallback.assert_called_once_with()
        client.get.assert_called_with(espn_url, required=True, timeout=6)

    def test_complete_rest_tree_is_used_without_cloning(self):
        model = self.model()
        rest_result = {"sha": "a" * 40, "tree": [{"path": "data/teams.csv", "type": "blob", "sha": "b" * 40}]}
        client = Mock()
        client.get.return_value = rest_result
        with patch.dict('sys.modules', {'vortex_upstream_fdr': model}), \
             patch('wc_fh.forecast_compat.fetch_core_git_tree') as fallback:
            exec(patch_forecast_loader('import vortex_upstream_fdr\n'), {})
            self.assertIs(model.refresh_fpl_core(None, None, None, None, client), rest_result)
        fallback.assert_not_called()

    def test_incomplete_rest_tree_and_git_timeout_fail_with_both_causes(self):
        model = self.model()
        client = Mock()
        client.get.return_value = {"sha": "a" * 40, "tree": [{"path": "data/teams.csv"}], "truncated": True}
        with patch.dict('sys.modules', {'vortex_upstream_fdr': model}), \
             patch('wc_fh.forecast_compat.fetch_core_git_tree', side_effect=subprocess.TimeoutExpired('git', 60)):
            exec(patch_forecast_loader('import vortex_upstream_fdr\n'), {})
            with self.assertRaisesRegex(RuntimeError, r'REST .*incomplete tree.* Git .*timed out'):
                model.refresh_fpl_core(None, None, None, None, client)

    def test_git_listing_returns_commit_and_blob_ids_for_paths_with_spaces(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def git(*args):
                return subprocess.check_output(['git', *args], cwd=root, text=True, stderr=subprocess.PIPE).strip()

            git('init', '-b', 'main')
            git('config', 'uploadpack.allowFilter', 'true')
            path = 'data/By Tournament/Premier League/teams.csv'
            (root / path).parent.mkdir(parents=True)
            (root / path).write_text('id,name\n1,Arsenal\n', encoding='utf-8')
            (root / 'README').write_text('fixture\n', encoding='utf-8')
            git('add', '.')
            git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-m', 'Test source')
            with patch('wc_fh.forecast_compat.CORE_REPOSITORY', root.as_uri()):
                listing = fetch_core_git_tree()

            self.assertEqual(listing['sha'], git('rev-parse', 'HEAD'))
            self.assertEqual(listing['tree'], [{'path': path, 'type': 'blob', 'sha': git('rev-parse', f'HEAD:{path}')}])

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
