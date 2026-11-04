"""Regression for the actual Day 1 IPython runner (Actions failure diagnostics).

Exercises the exact loop embedded in day-1.yml with synthetic success,
syntax, execution, and shell failures, without calling cloud services.
"""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import re
import textwrap
import unittest
from types import SimpleNamespace


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/day-1.yml"


def extract_runner() -> str:
    content = WORKFLOW.read_text(encoding="utf-8")
    start_marker = "          import sys\n          import traceback\n"
    end_marker = '          print("Day 1 execution: PASS")'
    assert content.count(start_marker) == 1, "Runner imports are missing or duplicated"
    start = content.index(start_marker)
    end = content.index(end_marker, start)
    runner = textwrap.dedent(content[start:end])
    compile(runner, "day1-actions-execution-loop", "exec")
    return runner


class TestDay1Diagnostics(unittest.TestCase):
    def run_loop(self, *, result=None, thrown=None):
        calls = []

        class Shell:
            def run_cell(self, cell, **kwargs):
                calls.append((cell, kwargs))
                if thrown is not None:
                    raise thrown
                return result

        env = {"cells": ["# CELL 18 — INTRO NARRATION\nprint('run')"],
               "shell": Shell(), "re": re}
        output = StringIO()
        error = None
        with redirect_stdout(output):
            try:
                exec(extract_runner(), env)
            except RuntimeError as exc:
                error = exc
        return output.getvalue(), error, calls

    def test_success_does_not_emit_error(self):
        value = SimpleNamespace(success=True, error_before_exec=None, error_in_exec=None)
        output, error, calls = self.run_loop(result=value)
        self.assertIsNone(error)
        self.assertIn("::group::Day 1 block 01/33 — CELL 18", output)
        self.assertIn("::endgroup::", output)
        self.assertNotIn("::error::", output)
        self.assertEqual(calls[0][1], {"store_history": False, "silent": False})

    def test_runtime_exception_is_visible_after_closed_group_and_chained(self):
        try:
            raise ValueError("original cell eighteen error")
        except ValueError as exc:
            original = exc
        failed = SimpleNamespace(success=False, error_before_exec=None,
                                 error_in_exec=original)
        output, error, _ = self.run_loop(result=failed)
        self.assertIsNotNone(error)
        self.assertIs(error.__cause__, original)
        self.assertIn("::error::Block 1 (CELL 18", output)
        self.assertIn("ValueError: original cell eighteen error", output)
        self.assertLess(output.index("::endgroup::"), output.index("::error::"))
        self.assertIn("Traceback (most recent call last):", output)

    def test_syntax_error_is_reported_from_error_before_exec(self):
        try:
            compile("if True print('oops')", "sample-cell", "exec")
        except SyntaxError as exc:
            original = exc
        failed = SimpleNamespace(success=False, error_before_exec=original,
                                 error_in_exec=None)
        output, error, _ = self.run_loop(result=failed)
        self.assertIs(error.__cause__, original)
        self.assertIn("::error::Block 1 (CELL 18", output)
        self.assertIn("SyntaxError:", output)
        self.assertLess(output.index("::endgroup::"), output.index("::error::"))

    def test_shell_exception_closes_group_before_reporting(self):
        try:
            raise OSError("shell itself failed")
        except OSError as exc:
            original = exc
        output, error, _ = self.run_loop(thrown=original)
        self.assertIs(error.__cause__, original)
        self.assertLess(output.index("::endgroup::"), output.index("::error::"))
        self.assertIn("OSError: shell itself failed", output)

    def test_failure_without_exception_is_explicit(self):
        failed = SimpleNamespace(success=False, error_before_exec=None,
                                 error_in_exec=None)
        output, error, _ = self.run_loop(result=failed)
        self.assertIsInstance(error, RuntimeError)
        self.assertIn("cell execution unsuccessful without an exception", output)

    def test_market_contract_runs_after_its_pandas_dependency_is_installed(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        install = workflow.index('"pandas>=2.2,<3"')
        market_check = workflow.index("test_day1_market_desk.py")
        self.assertLess(install, market_check)
        self.assertLess(market_check, workflow.index("Execute Day 1 cells once in order"))

    def test_checks_run_before_full_day1_video_generation(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("test_day1_runner_diagnostics.py", workflow)
        self.assertLess(workflow.index("test_day1_runner_diagnostics.py"),
                        workflow.index("Execute Day 1 cells once in order"))


if __name__ == "__main__":
    unittest.main()
