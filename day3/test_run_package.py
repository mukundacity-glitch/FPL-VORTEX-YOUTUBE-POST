from __future__ import annotations

import ast
import contextlib
import hashlib
import io
import json
import os
import socket
import sys
import tempfile
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from day3.run_package import RunPackage, capture_safely, start_package


ROOT = Path(__file__).resolve().parents[1]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode()


def contents(root: Path) -> dict[str, bytes]:
    return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}


class OfflineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.network_patches = [patch.object(socket.socket, "connect", side_effect=AssertionError("NETWORK_FORBIDDEN")),
                               patch.object(socket, "getaddrinfo", side_effect=AssertionError("DNS_FORBIDDEN"))]
        cls.network_mocks = [item.start() for item in cls.network_patches]

    @classmethod
    def tearDownClass(cls) -> None:
        try:
            for mock in cls.network_mocks:
                mock.assert_not_called()
        finally:
            for item in reversed(cls.network_patches):
                item.stop()

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.notebook = self.root / "input.ipynb"
        self.notebook.write_text(json.dumps({"cells": [{"cell_type": "code", "source": "value = 1\n"}]}))
        self.package_root = self.root / "packages"
        self.environment = {"GITHUB_RUN_ID": "123456", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_SHA": "a" * 40}
        self.clock = lambda: datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)
        self.cells = [(1, "value = 2\n"), (2, "result = value + 3\n")]
        self.output = self.root / "output"
        self.output.mkdir()
        self.output_file = self.output / "forecast.json"
        self.output_file.write_bytes(b'[{"fixture_id":77,"goals":1.75}]\n')
        self.history = self.root / "historical.jsonl"
        self.history.write_bytes(b'{"fixture_id":51,"forecast_timestamp":"2026-10-04"}\n')
        self.odds = self.root / "provider_snapshot.json"
        self.odds.write_bytes(b'{"decimal_odds":2.1}\n')
        self.phase7 = self.root / "phase7_validation_summary.json"
        self.phase9 = self.root / "phase9_validation_summary.json"
        self.phase7.write_text(json.dumps({"validation_status": "ACCUMULATING:0/80", "completed_fixtures": 0}))
        self.phase9.write_text(json.dumps({"validation_status": "WAITING_FOR_HISTORY", "live_blend_active": False}))
        self.namespace = {
            "CURRENT_SEASON": "2026-27", "NEXT_GW": 8, "MARKET_ODDS": True,
            "PHASE4_POISSON_MODEL_VERSION": "VORTEX-V1-PHASE4-BASELINE-POISSON",
            "PHASE4_OUTPUT_MODEL_VERSION": "VORTEX-V1-PHASE4-POISSON-CS-FDR",
            "fixtures_raw": [{"id": 77, "event": 8}],
            "PHASE7_HISTORY_PATH": self.history, "PHASE5_HISTORY_PATH": self.odds,
            "DATA_DIR": self.output, "PHASE7_SUMMARY_PATH": self.phase7, "PHASE9_SUMMARY_PATH": self.phase9,
        }

    def recorder(self, **overrides: object) -> RunPackage:
        arguments = {"repository_root": ROOT, "environment": self.environment,
                     "package_root": self.package_root, "clock": self.clock}
        arguments.update(overrides)
        return RunPackage(self.notebook, self.cells, **arguments)

    def finish(self, recorder: RunPackage) -> dict[str, object]:
        for index, source in self.cells:
            recorder.before_cell(index, source, self.namespace)
            recorder.after_cell(index, self.namespace)
        recorder.finish(self.namespace)
        return json.loads((recorder.directory / "manifest.json").read_text())

    def test_exact_original_and_runtime_patched_source(self) -> None:
        recorder = self.recorder()
        manifest = self.finish(recorder)
        self.assertEqual((recorder.directory / "source/original.ipynb").read_bytes(), self.notebook.read_bytes())
        captured = json.loads((recorder.directory / "source/submitted_cells.json").read_text())
        self.assertEqual([(row["cell_index"], row["source"]) for row in captured], self.cells)
        for row, (index, source) in zip(manifest["submitted_sources"], self.cells, strict=True):
            self.assertEqual(row["cell_index"], index)
            self.assertEqual((recorder.directory / row["path"]).read_bytes(), source.encode())
        self.assertEqual(manifest["package_status"], "COMPLETE")

    def test_all_source_config_input_output_and_manifest_hashes_verify(self) -> None:
        recorder = self.recorder()
        manifest = self.finish(recorder)
        expected = manifest.pop("manifest_sha256")
        self.assertEqual(expected, sha(canonical(manifest)))
        for row in manifest["source_files"]:
            data = (recorder.directory / row["path"]).read_bytes()
            self.assertEqual(row["sha256"], sha(data))
            self.assertEqual(row["size_bytes"], len(data))
        for row in manifest["configuration_snapshots"]:
            self.assertEqual(row["sha256"], sha(canonical(row["values"])))
        for row in manifest["input_fingerprints"]:
            data = Path(row["path"]).read_bytes() if row["kind"] == "file" else canonical(self.namespace[row["name"]])
            self.assertEqual(row["sha256"], sha(data))
        self.assertEqual(manifest["output_fingerprints"][0]["sha256"], sha(self.output_file.read_bytes()))

    def test_configuration_records_effective_changes(self) -> None:
        recorder = self.recorder()
        recorder.before_cell(1, self.cells[0][1], self.namespace)
        self.namespace["MARKET_ODDS"] = False
        self.namespace["PHASE4_POISSON_MAX_GOALS"] = 8
        recorder.after_cell(1, self.namespace)
        snapshots = recorder.manifest["configuration_snapshots"]
        self.assertTrue(snapshots[0]["values"]["MARKET_ODDS"])
        self.assertFalse(snapshots[-1]["values"]["MARKET_ODDS"])
        self.assertEqual(snapshots[-1]["values"]["PHASE4_POISSON_MAX_GOALS"], 8)

    def test_changed_input_and_output_produce_new_fingerprints(self) -> None:
        first = self.recorder()
        manifest1 = self.finish(first)
        self.namespace["fixtures_raw"][0]["id"] = 78
        self.output_file.write_bytes(b'[{"fixture_id":78,"goals":2.25}]\n')
        second = self.recorder(environment={**self.environment, "GITHUB_RUN_ATTEMPT": "2"})
        manifest2 = self.finish(second)
        self.assertNotEqual(manifest1["input_fingerprints"][0]["sha256"], manifest2["input_fingerprints"][0]["sha256"])
        self.assertNotEqual(manifest1["output_fingerprints"], manifest2["output_fingerprints"])

    def test_same_material_has_same_fingerprints_across_attempts(self) -> None:
        first = self.finish(self.recorder())
        second = self.finish(self.recorder(environment={**self.environment, "GITHUB_RUN_ATTEMPT": "2"}))
        self.assertEqual(first["input_fingerprints"], second["input_fingerprints"])
        self.assertEqual(first["output_fingerprints"], second["output_fingerprints"])
        self.assertEqual(first["configuration_snapshots"], second["configuration_snapshots"])

    def test_collision_preserves_existing_package(self) -> None:
        self.finish(self.recorder())
        before = contents(self.package_root)
        with self.assertRaises(FileExistsError):
            self.recorder()
        self.assertEqual(before, contents(self.package_root))

    def test_preserves_outputs_odds_credentials_and_historical_records(self) -> None:
        credential = self.root / "credentials.json"
        credential.write_text('{"private":"existing-credential-fixture"}')
        originals = {path: path.read_bytes() for path in [self.notebook, self.output_file, self.history, self.odds, credential]}
        self.finish(self.recorder())
        self.assertEqual(originals, {path: path.read_bytes() for path in originals})

    def test_environment_and_namespace_secret_values_are_excluded(self) -> None:
        sentinel = "sentinel-odds-credential-938271"
        self.environment["ODDS_API_KEY"] = sentinel
        self.namespace.update({"ODDS_API_KEY": sentinel, "ARBITRARY_PRIVATE_OBJECT": {"secret": sentinel}})
        recorder = self.recorder()
        self.finish(recorder)
        self.assertNotIn(sentinel.encode(), b"\n".join(contents(recorder.directory).values()))

    def test_known_secret_in_source_is_never_written(self) -> None:
        sentinel = "sentinel-source-credential-938271"
        self.environment["ODDS_API_KEY"] = sentinel
        self.cells = [(1, f"value = {sentinel!r}")]
        recorder = self.recorder()
        manifest = self.finish(recorder)
        self.assertEqual(manifest["package_status"], "INCOMPLETE")
        self.assertIn("SOURCE_CAPTURE_FAILED", manifest["diagnostics"])
        self.assertNotIn(sentinel.encode(), b"\n".join(contents(recorder.directory).values()))

    def test_unknown_credential_literal_is_rejected(self) -> None:
        self.cells = [(1, 'api_key = "unknown-literal-938271"')]
        recorder = self.recorder()
        manifest = self.finish(recorder)
        self.assertEqual(manifest["package_status"], "INCOMPLETE")
        self.assertNotIn(b"unknown-literal-938271", b"\n".join(contents(recorder.directory).values()))

    def test_authenticated_url_is_not_captured(self) -> None:
        self.namespace["PHASE5_PROVIDER_URL"] = "https://example.invalid/odds?apiKey=private-value-938271"
        recorder = self.recorder()
        manifest = self.finish(recorder)
        self.assertEqual(manifest["package_status"], "INCOMPLETE")
        self.assertNotIn(b"private-value-938271", b"\n".join(contents(recorder.directory).values()))

    def test_failure_records_incomplete_without_exception_message(self) -> None:
        recorder = self.recorder()
        recorder.before_cell(1, self.cells[0][1], self.namespace)
        recorder.finish(self.namespace, ValueError("exception-secret-938271"))
        manifest = json.loads((recorder.directory / "manifest.json").read_text())
        self.assertEqual(manifest["execution_status"], "FAILED")
        self.assertEqual(manifest["package_status"], "INCOMPLETE")
        self.assertNotIn(b"exception-secret-938271", b"\n".join(contents(recorder.directory).values()))

    def test_missing_validation_never_fabricates_history(self) -> None:
        self.namespace.pop("PHASE7_SUMMARY_PATH")
        self.namespace.pop("PHASE9_SUMMARY_PATH")
        before = self.history.read_bytes()
        manifest = self.finish(self.recorder())
        self.assertEqual(manifest["validation"]["phase7"]["status"], "MISSING")
        self.assertEqual(manifest["package_status"], "INCOMPLETE")
        self.assertEqual(self.history.read_bytes(), before)

    def test_insufficient_validation_remains_insufficient(self) -> None:
        manifest = self.finish(self.recorder())
        self.assertEqual(manifest["validation"]["phase7"]["values"]["validation_status"], "ACCUMULATING:0/80")
        self.assertFalse(manifest["validation"]["phase9"]["values"]["live_blend_active"])
        self.assertFalse(manifest["replay_ready"])
        self.assertFalse(manifest["historical_provenance_fully_verified"])

    def test_missing_required_configuration_is_explicit(self) -> None:
        self.namespace.pop("NEXT_GW")
        manifest = self.finish(self.recorder())
        self.assertIn("NEXT_GW", manifest["missing_required_configuration"])
        self.assertEqual(manifest["package_status"], "INCOMPLETE")

    def test_changed_submitted_source_is_recorded_and_flagged(self) -> None:
        recorder = self.recorder()
        actual = "value = 987\n"
        recorder.before_cell(1, actual, self.namespace)
        recorder.after_cell(1, self.namespace)
        recorder.finish(self.namespace)
        row = recorder.manifest["submitted_sources"][0]
        self.assertEqual((recorder.directory / row["path"]).read_text(), actual)
        self.assertIn("SUBMITTED_SOURCE_CHANGED", recorder.manifest["diagnostics"])
        self.assertEqual(recorder.manifest["package_status"], "INCOMPLETE")

    def test_symlink_input_does_not_get_followed(self) -> None:
        link = self.root / "linked-history.jsonl"
        link.symlink_to(self.history)
        self.namespace["PHASE7_HISTORY_PATH"] = link
        manifest = self.finish(self.recorder())
        self.assertIn("INPUT_CAPTURE_FAILED", manifest["diagnostics"])
        self.assertEqual(manifest["package_status"], "INCOMPLETE")

    def test_invalid_ids_cannot_escape_package_root(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "INVALID_RUN_ID"):
            self.recorder(environment={"VORTEX_RUN_ID": "../existing"})
        self.assertFalse(self.package_root.exists())

    def test_invalid_cell_sequence_is_rejected(self) -> None:
        self.cells = [(1, "pass"), (1, "pass")]
        with self.assertRaisesRegex(RuntimeError, "DUPLICATE_CELL_INDEX"):
            self.recorder()

    def test_late_discovered_secret_is_not_persisted_in_sources_or_configuration(self) -> None:
        sentinel = "late-discovered-credential-938271"
        self.cells = [(1, f"ordinary_alias = {sentinel!r}\n")]
        recorder = self.recorder()
        self.namespace["PHASE5_UNRECOGNIZED_ALIAS"] = sentinel
        recorder.before_cell(1, self.cells[0][1], self.namespace)
        self.assertNotIn(sentinel.encode(), b"\n".join(contents(recorder.directory).values()))
        self.namespace["ODDS_API_KEY"] = sentinel
        recorder.after_cell(1, self.namespace)
        recorder.finish(self.namespace)
        self.assertNotIn(sentinel.encode(), b"\n".join(contents(recorder.directory).values()))
        self.assertEqual(recorder.manifest["package_status"], "INCOMPLETE")

    def test_missing_input_history_is_recorded_without_creating_it(self) -> None:
        missing = self.root / "not-retained-history.jsonl"
        self.namespace["PHASE7_HISTORY_PATH"] = missing
        manifest = self.finish(self.recorder())
        self.assertFalse(missing.exists())
        self.assertEqual(manifest["missing_input_files"][0]["status"], "NOT_PRESENT")
        self.assertEqual(manifest["package_status"], "INCOMPLETE")

    def test_runtime_overrides_record_only_the_explicit_allowlist(self) -> None:
        self.environment.update({"DAY3_PLAN": "ROLL", "DAY3_TRANSFER_MODE": "AUTO",
                                 "UNRELATED_PRIVATE_SETTING": "do-not-capture-938271"})
        manifest = self.finish(self.recorder())
        self.assertEqual(manifest["runtime_overrides"], {"DAY3_PLAN": "ROLL", "DAY3_TRANSFER_MODE": "AUTO"})
        self.assertNotIn("do-not-capture-938271", json.dumps(manifest))

    def test_escaped_secret_value_is_excluded(self) -> None:
        sentinel = "private-value-938271\nsecond-line"
        self.environment["ODDS_API_KEY"] = sentinel
        self.namespace["PHASE5_UNEXPECTED_ALIAS"] = sentinel
        recorder = self.recorder()
        manifest = self.finish(recorder)
        self.assertEqual(manifest["package_status"], "INCOMPLETE")
        for data in contents(recorder.directory).values():
            self.assertNotIn(json.dumps(sentinel)[1:-1].encode(), data)

    def test_late_secret_in_runtime_override_is_excluded(self) -> None:
        sentinel = "late-override-credential-938271"
        self.environment["DAY3_PLAN"] = sentinel
        recorder = self.recorder()
        self.assertNotIn(sentinel.encode(), b"\n".join(contents(recorder.directory).values()))
        self.namespace["ODDS_API_KEY"] = sentinel
        manifest = self.finish(recorder)
        self.assertNotIn(sentinel.encode(), b"\n".join(contents(recorder.directory).values()))
        self.assertEqual(manifest["package_status"], "INCOMPLETE")

    def test_packaging_error_is_sanitized_and_not_raised(self) -> None:
        recorder = self.recorder()
        error_output = io.StringIO()
        with patch.object(recorder, "before_cell", side_effect=OSError("secret-error-938271")):
            with contextlib.redirect_stderr(error_output):
                capture_safely(recorder, "before_cell", 1, "pass", {})
        self.assertNotIn("secret-error-938271", error_output.getvalue())
        self.assertEqual(recorder.manifest["package_status"], "INCOMPLETE")

    def runner(self, shell: object, recorder_factory: object) -> object:
        tree = ast.parse((ROOT / "day3/run_notebook.py").read_text())
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "run_notebook")
        namespace = {
            "Path": Path, "__file__": str(ROOT / "day3/run_notebook.py"),
            "_prepare_code_cells": lambda path: self.cells,
            "_install_colab_compatibility": lambda: None,
            "InteractiveShell": types.SimpleNamespace(instance=lambda: shell),
            "NOTEBOOK_CONTROL_CELL_INDEX": 1,
            "purge_shortlist_artifacts": lambda *args: None,
            "capture_safely": capture_safely, "start_package": recorder_factory,
        }
        exec(compile(ast.Module(body=[function], type_ignores=[]), "run_notebook.py", "exec"), namespace)
        return namespace["run_notebook"]

    def fake_shell(self) -> object:
        class Shell:
            def __init__(self, initial: dict[str, object]) -> None:
                self.user_ns = dict(initial)
                self.submitted: list[str] = []

            def run_cell(self, source: str, **options: object) -> object:
                self.submitted.append(source)
                try:
                    exec(compile(source, "offline-fixture", "exec"), self.user_ns)
                except BaseException as error:
                    return types.SimpleNamespace(error_before_exec=None, error_in_exec=error)
                return types.SimpleNamespace(error_before_exec=None, error_in_exec=None)

        return Shell({**self.namespace, "OUTPUT_ROOT": self.root, "WORK_ROOT": self.root})

    def test_runner_outputs_identical_with_capture_enabled_and_disabled(self) -> None:
        self.cells = [(1, "value = 7\n"), (2, "(DATA_DIR / 'fixture.json').write_text(str(value * value))\n")]
        evidence = types.ModuleType("day3.verify_evidence")
        evidence.finalize_evidence_bundle = lambda namespace: None
        disabled = self.fake_shell()
        enabled = self.fake_shell()
        recorder = self.recorder()
        with patch.dict(sys.modules, {"day3.verify_evidence": evidence}), contextlib.redirect_stdout(io.StringIO()):
            self.runner(disabled, lambda *args: None)(self.notebook)
            before = contents(self.output)
            self.runner(enabled, lambda *args: recorder)(self.notebook)
        self.assertEqual(contents(self.output), before)
        self.assertEqual(enabled.submitted, disabled.submitted)
        for row, source in zip(recorder.manifest["submitted_sources"], enabled.submitted, strict=True):
            self.assertEqual((recorder.directory / row["path"]).read_text(), source)

    def test_runner_preserves_original_exception_chain(self) -> None:
        self.cells = [(1, "raise original_failure\n")]
        shell = self.fake_shell()
        failure = ValueError("original-private-error-938271")
        shell.user_ns["original_failure"] = failure
        recorder = self.recorder()
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, "Day 3 notebook cell 1 failed") as raised:
                self.runner(shell, lambda *args: recorder)(self.notebook)
        self.assertIs(raised.exception.__cause__, failure)
        self.assertEqual(recorder.manifest["execution_status"], "FAILED")
        self.assertEqual(recorder.manifest["package_status"], "INCOMPLETE")

    def test_runner_preserves_failure_when_packaging_also_fails(self) -> None:
        self.cells = [(1, "raise original_failure\n")]
        shell = self.fake_shell()
        failure = ValueError("original-private-error-938271")
        shell.user_ns["original_failure"] = failure
        recorder = self.recorder()
        with patch.object(recorder, "finish", side_effect=OSError("packaging-private-error-938271")):
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(RuntimeError) as raised:
                    self.runner(shell, lambda *args: recorder)(self.notebook)
        self.assertIs(raised.exception.__cause__, failure)

    def test_start_collision_is_nonfatal_and_does_not_overwrite(self) -> None:
        self.finish(self.recorder())
        before = contents(self.package_root)
        env = {**self.environment, "VORTEX_RUN_PACKAGE_ROOT": str(self.package_root)}
        with patch.dict(os.environ, env, clear=True), contextlib.redirect_stderr(io.StringIO()):
            self.assertIsNone(start_package(self.notebook, self.cells, ROOT))
        self.assertEqual(contents(self.package_root), before)


if __name__ == "__main__":
    unittest.main()
