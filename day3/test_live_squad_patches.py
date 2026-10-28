from __future__ import annotations

import os
import unittest
from typing import Any
from unittest.mock import patch

from day3 import run_notebook as runner


class _Column:
    def __init__(self, values: list[int]):
        self.values = values

    def astype(self, _: Any) -> "_Column":
        return self

    def tolist(self) -> list[int]:
        return list(self.values)


class _Frame(dict):
    def __init__(self, ids: list[int]):
        super().__init__(player_id=_Column(ids))


LIVE_IDS = [1, 173, 31, 332, 115, 40, 427, 124, 154, 411, 346, 623, 165, 112, 289]


class FplEntryIdPatchTests(unittest.TestCase):
    SOURCE = 'FPL_ID = 145784 # @param {type:"integer"}\nFPL_TEAM_ID = int(FPL_ID)\n'

    def test_entry_id_is_taken_from_the_workflow_env(self):
        with patch.dict(os.environ, {"FPL_ENTRY_ID": "999001"}, clear=False):
            patched = runner._patch_fpl_entry_id(self.SOURCE)
        self.assertIn('FPL_ID = 999001  # @param {type:"integer"}', patched)
        compile(patched, "<control-cell>", "exec")

    def test_missing_env_leaves_notebook_default_intact(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(runner._patch_fpl_entry_id(self.SOURCE), self.SOURCE)

    def test_bad_env_fails_loudly(self):
        with patch.dict(os.environ, {"FPL_ENTRY_ID": "not-a-number"}, clear=False):
            with self.assertRaisesRegex(ValueError, "must be an integer"):
                runner._patch_fpl_entry_id(self.SOURCE)

    def test_missing_anchor_fails_loudly(self):
        with patch.dict(os.environ, {"FPL_ENTRY_ID": "999001"}, clear=False):
            with self.assertRaisesRegex(RuntimeError, "FPL entry id"):
                runner._patch_fpl_entry_id("FPL_ID = 145784\n")


class LiveSquadContractPatchTests(unittest.TestCase):
    SOURCE = (
        "_vx_build_my_plan_player_picker()\n\n"
        "MY_PLAN_SCENARIOS = tuple(MY_PLAN_SCENARIO_MAP.values())\n"
        "print(MY_PLAN_SCENARIOS)\n"
    )

    def test_guard_is_injected_before_scenarios_and_compiles(self):
        patched = runner.patch_live_squad_contract(self.SOURCE)
        self.assertIn("from day3.fpl_squad import", patched)
        self.assertIn("DAY3_LIVE_SQUAD_IDS", patched)
        self.assertIn("validate_transfer_selections", patched)
        self.assertLess(
            patched.index("_d3_resolve_live_squad"),
            patched.index("MY_PLAN_SCENARIOS = tuple("),
        )
        compile(patched, "<control-cell>", "exec")

    def test_snapshot_path_is_read_from_the_workflow_env(self):
        patched = runner.patch_live_squad_contract(self.SOURCE)
        self.assertIn(
            'os.environ.get("DAY3_LIVE_SQUAD_JSON", "")',
            patched.replace("_d3_live_os.", "os."),
        )

    def test_missing_anchor_fails(self):
        with self.assertRaisesRegex(RuntimeError, "live squad contract"):
            runner.patch_live_squad_contract("print(1)\n")


class Phase11GuardTests(unittest.TestCase):
    INDENTED_SOURCE = (
        "def build():\n"
        "    phase11_current_squad_state = rows.copy()\n"
        "    # Merge xPts and decision features onto the squad.\n"
        "    if not phase11_current_squad_state.empty:\n"
        "        pass\n"
    )

    def test_guard_keeps_the_anchor_indentation_and_compiles(self):
        patched = runner.patch_phase11_live_squad_guard(self.INDENTED_SOURCE)
        self.assertIn("Day 3 current squad does not match", patched)
        self.assertIn("    # Day 3 runner:", patched)
        compile(patched, "<phase11>", "exec")

    @staticmethod
    def _executable(note: str) -> str:
        source = (
            "# Merge xPts and decision features onto the squad.\n"
            f"{note}\n"
        )
        return runner.patch_phase11_live_squad_guard(source)

    def test_guard_rejects_a_stale_squad(self):
        patched = self._executable("print(1)")
        namespace: dict[str, Any] = {
            "DAY3_LIVE_SQUAD_IDS": tuple(LIVE_IDS),
            "DAY3_LIVE_SQUAD_GW": 8,
            "phase11_current_squad_state": _Frame(LIVE_IDS[:-1] + [999]),
        }
        with self.assertRaisesRegex(RuntimeError, "does not match the live official FPL entry"):
            exec(compile(patched, "<phase11>", "exec"), namespace)

    def test_guard_accepts_the_live_squad(self):
        patched = self._executable("print(1)")
        namespace: dict[str, Any] = {
            "DAY3_LIVE_SQUAD_IDS": tuple(LIVE_IDS),
            "DAY3_LIVE_SQUAD_GW": 8,
            "phase11_current_squad_state": _Frame(LIVE_IDS),
        }
        exec(compile(patched, "<phase11>", "exec"), namespace)
        self.assertEqual(set(namespace["_d3_phase11_ids"]), set(LIVE_IDS))


class MyPlanTransferGuardTests(unittest.TestCase):
    @staticmethod
    def _source(outs: list[int], ins: list[int]) -> str:
        return (
            "def build():\n"
            "    if _manual_transfer_mode:\n"
            f"        _outs = {outs!r}\n"
            f"        _ins = {ins!r}\n"
            "        if len(_outs) != len(_ins) or not 1 <= len(_outs) <= 5:\n"
            "            raise ValueError('bad pairs')\n"
            "        raise RuntimeError('guard passed')\n"
            "build()\n"
        )

    def _patched(self, outs: list[int], ins: list[int]) -> str:
        return runner.patch_my_plan_transfer_live_squad_guard(self._source(outs, ins))

    def test_guard_inherits_nested_indentation_and_compiles(self):
        patched = self._patched([1], [109])
        self.assertIn("        # Day 3 runner:", patched)
        self.assertIn("SLIDE_CURRENT_SQUAD", patched)
        compile(patched, "<my-plan-5b>", "exec")

    def _namespace(self, **overrides: Any) -> dict[str, Any]:
        namespace: dict[str, Any] = {
            "DAY3_LIVE_SQUAD_IDS": tuple(LIVE_IDS),
            "SLIDE_CURRENT_SQUAD": _Frame(LIVE_IDS),
            "_manual_transfer_mode": True,
        }
        namespace.update(overrides)
        return namespace

    def test_guard_rejects_stale_out_players(self):
        patched = self._patched([109], [999])
        with self.assertRaisesRegex(RuntimeError, "OUT players are not in the live FPL squad"):
            exec(compile(patched, "<my-plan-5b>", "exec"), self._namespace())

    def test_guard_rejects_a_stale_base_squad(self):
        patched = self._patched([1], [109])
        with self.assertRaisesRegex(RuntimeError, "base squad is stale"):
            exec(
                compile(patched, "<my-plan-5b>", "exec"),
                self._namespace(SLIDE_CURRENT_SQUAD=_Frame(LIVE_IDS[:-1] + [109])),
            )

    def test_guard_rejects_in_players_already_owned(self):
        patched = self._patched([1], [173])
        with self.assertRaisesRegex(RuntimeError, "IN players are already"):
            exec(compile(patched, "<my-plan-5b>", "exec"), self._namespace())

    def test_guard_accepts_live_out_players(self):
        patched = self._patched([1], [109])
        with self.assertRaisesRegex(RuntimeError, "guard passed"):
            exec(compile(patched, "<my-plan-5b>", "exec"), self._namespace())

    def test_missing_anchor_fails(self):
        with self.assertRaisesRegex(RuntimeError, "MY PLAN 5B live squad guard"):
            runner.patch_my_plan_transfer_live_squad_guard("print(1)\n")


if __name__ == "__main__":
    unittest.main()
