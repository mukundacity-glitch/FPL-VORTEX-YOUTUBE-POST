"""Regression cases for factual, dynamic SELL explanations and notebook wiring."""

from __future__ import annotations

import ast
import copy
import json
from pathlib import Path
import re
import unittest

import numpy as np
import pandas as pd

from day3.run_notebook import _prepare_code_cells
from day3.sell_reasoning import (
    analyse_sell, patch_sell_reasoning_source, sell_narration, sell_projection_benchmarks,
)


class SellReasoningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.record = {
            "player_id": 8001, "team_id": 1, "position": "MID", "action": "SELL",
            "xpts": 6.2, "has_projection": True, "next_5_xpts": 25.0, "has_horizon": True,
            "next_fixture": "Example (H)", "next_fdr": 2.7, "next_fdr_class": "fdr-2",
            "transfers_out": 50000, "net_transfers": -45000,
            "recent_performance": {"points": 6, "gameweeks": 3,
                                   "source": "CURRENT_SEASON_COMPLETED_FPL_GAMEWEEKS"},
        }
        self.status = {
            "verified": True, "health_clear": True, "blocked": False,
            "label": "AVAILABLE", "status": "a", "has_fixture": True,
            "starting_status": "PROJECTED STARTER", "start_probability": .95,
            "expected_minutes": 85, "last_started": True,
        }
        self.benchmarks = {"MID": {
            "xpts": {"sample": 8, "lower_quartile": 3.0, "upper_quartile": 5.5},
            "next_5_xpts": {"sample": 8, "lower_quartile": 15.0, "upper_quartile": 25.0},
        }}

    def analysis(self, record=None, status=None):
        return analyse_sell(self.record if record is None else record,
                            self.status if status is None else status, self.benchmarks)

    def codes(self, analysis, field="reasons"):
        return {row["code"] for row in analysis[field]}

    def test_poor_returns_and_strong_projection_produce_a_patience_case(self) -> None:
        analysis = self.analysis()
        self.assertEqual(self.codes(analysis), {"RECENT_RETURNS"})
        self.assertIn("STRONG_PROJECTION", self.codes(analysis, "counterpoints"))
        self.assertEqual(analysis["assessment"], "PATIENCE_CASE")
        record = {**self.record, "sell_analysis": analysis}
        text = sell_narration(record, "Example from Club", self.status)
        self.assertIn("6.2 point projection is still strong", text)
        self.assertIn("6 points across 3 completed Gameweeks", text)
        self.assertIn("against a rushed sale", text)

    def test_verified_injury_and_suspension_take_priority_over_high_xpts(self) -> None:
        for label, code, status in (("INJURED", "INJURY", "i"),
                                    ("SUSPENDED", "SUSPENSION", "s")):
            with self.subTest(label=label):
                state = {**self.status, "health_clear": False, "blocked": True,
                         "label": label, "status": status,
                         "news": "Expected back after an official update"}
                analysis = self.analysis(status=state)
                self.assertEqual(analysis["reasons"][0]["code"], code)
                self.assertIn("RECENT_RETURNS", self.codes(analysis))
                self.assertNotIn("STRONG_PROJECTION", self.codes(analysis, "counterpoints"))
                self.assertIn("CONDITIONAL_PROJECTION", self.codes(analysis, "counterpoints"))
                self.assertEqual(analysis["assessment"], "AVAILABILITY_FIRST")
                self.assertIn("official update", analysis["advice"])

    def test_a_return_date_does_not_clear_the_official_flag(self) -> None:
        status = {**self.status, "health_clear": False, "blocked": True,
                  "label": "INJURED", "news": "Expected back 1 January 2001"}
        self.assertEqual(self.analysis(status=status)["assessment"], "AVAILABILITY_FIRST")

    def test_doubt_and_minutes_risk_are_specific_reasons(self) -> None:
        doubtful = {**self.status, "health_clear": False, "label": "DOUBTFUL"}
        self.assertIn("DOUBTFUL", self.codes(self.analysis(status=doubtful)))
        minutes = {**self.status, "starting_status": "MINUTES RISK",
                   "start_probability": .25, "expected_minutes": 25, "last_started": False}
        analysis = self.analysis(status=minutes)
        self.assertEqual(analysis["reasons"][0]["code"], "MINUTES_RISK")
        self.assertIn("25 percent starting chance", analysis["reasons"][0]["sentence"])
        self.assertIn("25 expected minutes", analysis["reasons"][0]["sentence"])

    def test_blank_fixture_is_not_described_as_favourable(self) -> None:
        status = {**self.status, "has_fixture": False}
        analysis = self.analysis(status=status)
        self.assertEqual(analysis["reasons"][0]["code"], "BLANK_GAMEWEEK")
        self.assertNotIn("FAVOURABLE_FIXTURE", self.codes(analysis, "counterpoints"))
        text = sell_narration({**self.record, "sell_analysis": analysis}, "Example from Club",
                              status, fixture_text="Example at home")
        self.assertNotIn("Next up", text)

    def test_fixture_difficulty_uses_the_existing_canonical_model_class(self) -> None:
        record = {**self.record, "next_fdr": 4.3, "next_fdr_class": "fdr-5",
                  "recent_performance": {"points": 24, "gameweeks": 3}}
        analysis = self.analysis(record=record)
        self.assertEqual(self.codes(analysis), {"DIFFICULT_FIXTURE"})
        self.assertIn("4.3", analysis["reasons"][0]["sentence"])
        self.assertNotIn("FAVOURABLE_FIXTURE", self.codes(analysis, "counterpoints"))

    def test_five_week_weakness_and_next_week_upside_are_both_retained(self) -> None:
        record = {**self.record, "next_5_xpts": 9}
        analysis = self.analysis(record=record)
        self.assertIn("LOW_FIVE_WEEK_OUTLOOK", self.codes(analysis))
        self.assertIn("STRONG_PROJECTION", self.codes(analysis, "counterpoints"))

    def test_missing_projection_zeroes_are_not_treated_as_bad_forecasts(self) -> None:
        record = {**self.record, "xpts": 0, "next_5_xpts": 0,
                  "has_projection": False, "has_horizon": False}
        analysis = self.analysis(record=record)
        self.assertIsNone(analysis["xpts"])
        self.assertIsNone(analysis["next_5_xpts"])
        self.assertFalse({"LOW_NEXT_GW_OUTLOOK", "LOW_FIVE_WEEK_OUTLOOK"} & self.codes(analysis))
        text = sell_narration({**record, "sell_analysis": analysis}, "Example from Club", self.status)
        self.assertNotIn("0.0 point", text)

    def test_unverified_flags_do_not_become_confirmed_injuries(self) -> None:
        status = {**self.status, "verified": False, "health_clear": False,
                  "label": "INJURED", "blocked": True}
        analysis = self.analysis(status=status)
        self.assertNotIn("INJURY", self.codes(analysis))
        self.assertIn("live_availability", analysis["missing_evidence"])
        self.assertIn("Verify current team news", analysis["advice"])

    def test_strong_evidence_does_not_invent_a_sell_reason_from_transfer_volume(self) -> None:
        record = {**self.record, "recent_performance": {"points": 24, "gameweeks": 3}}
        analysis = self.analysis(record=record)
        self.assertEqual(analysis["reasons"], [])
        self.assertEqual(analysis["assessment"], "MARKET_ONLY")
        text = sell_narration({**record, "sell_analysis": analysis}, "Example from Club", self.status)
        self.assertIn("Transfer activity alone is not a reason to sell", text)
        self.assertNotIn("replacement gains", text)

    def test_missing_and_malformed_evidence_does_not_invent_any_reason(self) -> None:
        record = {"xpts": float("nan"), "has_projection": True, "next_5_xpts": float("inf"),
                  "has_horizon": True, "next_fdr": "bad", "next_fdr_class": "fdr-5",
                  "recent_performance": {"points": "bad", "gameweeks": 0}}
        analysis = self.analysis(record=record, status={})
        self.assertEqual(analysis["reasons"], [])
        self.assertEqual(analysis["assessment"], "MARKET_ONLY")
        json.dumps(analysis, allow_nan=False)

    def test_official_form_fallback_is_labelled_as_form(self) -> None:
        analysis = self.analysis(record={**self.record, "recent_performance": {
            "form": 1.5, "source": "OFFICIAL_FPL_FORM"}})
        self.assertEqual(analysis["reasons"][0]["code"], "RECENT_FORM")
        self.assertIn("Official recent form", analysis["reasons"][0]["sentence"])
        self.assertNotIn("completed Gameweeks", analysis["reasons"][0]["sentence"])

    def test_projection_strength_changes_with_eligible_same_position_peers(self) -> None:
        projections = pd.DataFrame([
            {"player_id": index, "position": "MID" if index < 5 else "GK",
             "xpts": index, "next_5_xpts": index * 4}
            for index in range(1, 7)
        ] + [{"player_id": 7, "position": "MID", "xpts": 1000, "next_5_xpts": 5000}])
        first = sell_projection_benchmarks(projections, {1, 2, 3, 4, 5, 6})
        self.assertAlmostEqual(first["MID"]["xpts"]["upper_quartile"], 3.25)
        self.assertNotIn("xpts", first["GK"])
        projections.loc[projections.position.eq("MID"), "xpts"] *= 10
        second = sell_projection_benchmarks(projections, {1, 2, 3, 4, 5, 6})
        self.assertAlmostEqual(second["MID"]["xpts"]["upper_quartile"], 32.5)
        self.assertIn("STRONG_PROJECTION", self.codes(
            analyse_sell(self.record, self.status, first), "counterpoints"))
        self.assertIn("LOW_NEXT_GW_OUTLOOK", self.codes(
            analyse_sell(self.record, self.status, second)))

    def test_brief_final_cards_still_have_a_real_reason(self) -> None:
        record = {**self.record, "sell_analysis": self.analysis()}
        text = sell_narration(record, "Example from Club", self.status, brief=True)
        self.assertIn("Recent returns are quiet", text)
        self.assertIn("6.2 point projection is still strong", text)

    def test_names_and_ids_do_not_change_the_analysis(self) -> None:
        first = self.analysis()
        renamed = {**self.record, "player_id": 99999, "name": "Renamed"}
        self.assertEqual(first, self.analysis(record=renamed))

    def test_evidence_report_round_trips_without_mutating_inputs(self) -> None:
        record, status = copy.deepcopy(self.record), copy.deepcopy(self.status)
        analysis = self.analysis()
        self.assertEqual(json.loads(json.dumps(analysis, allow_nan=False)), analysis)
        self.assertEqual(self.record, record)
        self.assertEqual(self.status, status)

    def test_changed_notebook_contract_fails_before_rendering(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "notebook contract changed"):
            patch_sell_reasoning_source("pass\n")


def check_notebook_sell_reasoning(path: Path) -> None:
    cells = dict(_prepare_code_cells(path))
    tree = ast.parse(cells[24])
    functions = {node.name: node for node in ast.walk(tree)
                 if isinstance(node, ast.FunctionDef)
                 and node.name in {"_d3_desk_record", "_d3_desk_narr", "_d3_transfer_full_narration", "_d3_number"}}
    if len(functions) != 4:
        raise AssertionError("Actual SELL record/narration functions were not found")
    fixture = SellReasoningTests()
    fixture.setUp()

    class Availability:
        def __init__(self):
            self.states = {}
        def state(self, player_id):
            return self.states.get(player_id, dict(fixture.status))
        def eligible(self, player_id):
            return self.state(player_id).get("health_clear") is True
        def caution(self, player_id):
            return "Wait for official availability confirmation."
        def probability(self, player_id):
            return 1.0 if self.eligible(player_id) else 0.0

    availability = Availability()
    ns = {
        "pd": pd, "np": np, "re": re, "DAY3_AVAILABILITY": availability,
        "sell_narration": sell_narration,
        "vx_narration_player": lambda player_id: f"Example{player_id}",
        "vx_narration_team": lambda team_id: "Example Club",
        "DAY3_TRANSFER_DESK": {"BUY": [], "HOLD": [], "SELL": []}, "NEXT_GW": 9,
    }
    exec(compile(ast.Module(body=[functions["_d3_desk_narr"],
                                 functions["_d3_transfer_full_narration"]], type_ignores=[]),
                 "actual-sell-narration", "exec"), ns)
    cases = [
        ({**fixture.status, "health_clear": False, "blocked": True, "label": "INJURED",
          "status": "i", "news": "Leg injury"}, "INJURY"),
        ({**fixture.status, "health_clear": False, "blocked": True, "label": "SUSPENDED",
          "status": "s"}, "SUSPENSION"),
        (dict(fixture.status), "RECENT_RETURNS"),
        ({**fixture.status, "starting_status": "MINUTES RISK",
          "start_probability": .25, "expected_minutes": 25}, "MINUTES_RISK"),
        (dict(fixture.status), "RECENT_RETURNS"),
    ]
    for index, (status, expected) in enumerate(cases):
        record = {**fixture.record, "index": index, "player_id": 200 + index, "name": f"Example{index}"}
        record["sell_analysis"] = analyse_sell(record, status, fixture.benchmarks)
        assert record["sell_analysis"]["reasons"][0]["code"] == expected
        availability.states[record["player_id"]] = status
        ns["DAY3_TRANSFER_DESK"]["SELL"].append(record)
    for index, record in enumerate(ns["DAY3_TRANSFER_DESK"]["SELL"]):
        text = ns["_d3_desk_narr"]("SELL", index)
        assert f"Example{record['player_id']} from Example Club" in text
        assert record["sell_analysis"]["reasons"][0]["sentence"] in text
        if index < 3:
            assert "Example Club at home" in text
    # The actual record builder fills absent display metrics with zero, while
    # preserving flags that prevent those zeroes entering the SELL reasoning.
    exec(compile(ast.Module(body=[functions["_d3_number"], functions["_d3_desk_record"]],
                            type_ignores=[]), "actual-sell-record", "exec"), ns)
    ns.update(
        _d3_players_by_id=pd.DataFrame([{
            "id": 8001, "team": 1, "position": "MID", "price": 7, "web_name": "Example",
        }]).set_index("id", drop=False),
        _d3_desk_by_id=pd.DataFrame([{"player_id": 8001, "player_name": "Example"}]).set_index(
            "player_id", drop=False),
        team_meta_by_id={1: {"short": "EXA"}}, _d3_proj_by_id=pd.DataFrame(),
        _d3_desk_next_fdr=lambda team, position: {
            "score": 2.7, "score_text": "2.7", "visual_class": "fdr-2", "fixture": "Example (H)"},
        resolve_player_photo=lambda row: "", vx_team_jersey_data_uri=lambda team: "",
        _d3_desk_rank_map={}, DAY3_TRANSFER_DESK_SELECTION_MODE="TEST",
        _d3_desk_recent_performance=lambda player_id: fixture.record["recent_performance"],
    )
    raw_record = ns["_d3_desk_record"]("SELL", {
        "player_id": 8001, "ownership_score": 20, "ownership_source": "OFFICIAL_OWNERSHIP",
        "retained_percent_estimate": 95, "recent_average_points": 2,
    }, 0)
    assert raw_record["xpts"] == 0 and raw_record["has_projection"] is False
    assert raw_record["next_5_xpts"] == 0 and raw_record["has_horizon"] is False
    assert analyse_sell(raw_record, fixture.status, fixture.benchmarks)["xpts"] is None

    script = ns["_d3_transfer_full_narration"]()
    assert "Leg injury" in script and "suspension" in script and "6.2 point projection is still strong" in script
    assert len(ns["TRANSFER_DESK_NARRATION_PLAN"]["sections"][2]["players"]) == 5

    # Exercise the production enrichment before the selection audit is saved.
    for_loop = next(node for node in tree.body if isinstance(node, ast.For)
                    and isinstance(node.target, ast.Tuple)
                    and [item.id for item in node.target.elts if isinstance(item, ast.Name)] == ["_action", "_rows"])
    ns.update(
        _index=0, _d3_buy_rows=[], _d3_hold_rows=[],
        _d3_sell_rows=[{"player_id": 8001, "ownership_score": 20,
                       "ownership_source": "OFFICIAL_OWNERSHIP",
                       "retained_percent_estimate": 95, "recent_average_points": 2}],
        DAY3_TRANSFER_DESK={"BUY": [], "HOLD": [], "SELL": []},
        DAY3_TRANSFER_DESK_ORDER=[], DAY3_TRANSFER_DESK_SEQUENCE=[],
        _d3_sell_benchmarks=fixture.benchmarks, analyse_sell=analyse_sell,
    )
    exec(compile(ast.Module(body=[for_loop], type_ignores=[]), "actual-sell-enrichment", "exec"), ns)
    saved_record = ns["DAY3_TRANSFER_DESK"]["SELL"][0]
    assert saved_record["sell_analysis"]["assessment"] == "PATIENCE_CASE"
    json.dumps(saved_record, allow_nan=False)
    print("Actual production SELL narration and audit enrichment PASS: injury, suspension, "
          "minutes risk, poor returns, strong projections, home fixture and all five card cues.")


if __name__ == "__main__":
    unittest.main()
