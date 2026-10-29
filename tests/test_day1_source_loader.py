from __future__ import annotations

import ast
from contextlib import redirect_stdout
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock

import pandas as pd


SOURCE = Path(__file__).resolve().parents[1] / "1_final_day1.py"


def loader_namespace(root: Path):
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    names = {"PHASE1_MATCH_FIELDS", "PHASE0_CONTROL_FIELDS", "_MATCH_CANDIDATES"}
    nodes = [
        node for node in tree.body
        if (
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id in names for t in node.targets)
        ) or (
            isinstance(node, ast.FunctionDef)
            and node.name == "_vx_read_phase1_match_source"
        )
    ]
    namespace = {
        "PHASE1_RAW_INPUT_DIR": root,
        "PHASE1_FPL_CORE_ADAPTER_ERROR": None,
        "PHASE1_FPL_CORE_SOURCE_USED": False,
        "_vx_try_build_fpl_core_team_match_raw": Mock(return_value=(None, None)),
        "vx_phase0_assert_no_forbidden_columns": Mock(),
        "model_version": "test-model",
        "data_snapshot_timestamp": "2026-10-29T12:00:00+00:00",
        "datetime": datetime,
        "timezone": timezone,
        "pd": pd,
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), "exec"), namespace)
    return namespace


class Day1SourceLoaderTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.env = loader_namespace(self.root)

    def read(self):
        with redirect_stdout(StringIO()):
            return self.env["_vx_read_phase1_match_source"]()

    def test_missing_archive_and_no_manual_file_does_not_invent_data(self):
        self.env["_vx_try_build_fpl_core_team_match_raw"].side_effect = RuntimeError(
            "FPL_CORE adapter: no matches.csv under archive"
        )
        self.assertEqual(self.read(), (None, None))
        self.assertIn("no matches.csv", self.env["PHASE1_FPL_CORE_ADAPTER_ERROR"])
        self.assertFalse(self.env["PHASE1_FPL_CORE_SOURCE_USED"])

    def test_manual_csv_is_loaded_with_schema_and_provenance(self):
        path = self.root / "team_match_xg_raw.csv"
        pd.DataFrame([{field: 1 for field in self.env["PHASE1_MATCH_FIELDS"]}]).to_csv(
            path, index=False
        )
        frame, source = self.read()
        self.assertEqual(source, path)
        self.assertEqual(len(frame), 1)
        self.assertEqual(frame.loc[0, "source_name"], "RAW_INPUT:team_match_xg_raw.csv")
        self.assertIsNone(frame.loc[0, "forecast_timestamp"])
        self.env["vx_phase0_assert_no_forbidden_columns"].assert_called_once()

    def test_incomplete_manual_csv_is_rejected(self):
        (self.root / "team_match_xg_raw.csv").write_text("team_id\n1\n")
        with self.assertRaisesRegex(RuntimeError, "missing required fields"):
            self.read()

    def test_canonical_data_keeps_priority_over_manual_file(self):
        (self.root / "team_match_xg_raw.csv").write_text("invalid\n1\n")
        canonical = pd.DataFrame([{"npxg_for": 1.5}])
        source = self.root / "canonical"
        self.env["_vx_try_build_fpl_core_team_match_raw"].return_value = canonical, source
        frame, actual_source = self.read()
        self.assertEqual(actual_source, source)
        self.assertEqual(frame.loc[0, "npxg_for"], 1.5)
        self.assertTrue(self.env["PHASE1_FPL_CORE_SOURCE_USED"])


if __name__ == "__main__":
    unittest.main()
