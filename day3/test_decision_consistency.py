"""Regression checks for cross-slide SELL and START/BENCH consistency."""

from __future__ import annotations

import unittest

from day3.decision_consistency import bench_sell_note, patch_bench_sell_source


class BenchSellConsistencyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fit = {
            "recommendation_eligible": True,
            "health_clear": True,
            "blocked": False,
        }
        self.sell = [{
            "player_id": 123,
            "sell_analysis": {
                "assessment": "REVIEW_SELL",
                "reasons": [{"short": "QUIET RECENT RETURNS"}],
            },
        }]

    def note(self, decision: str, *, player_id: int = 123, status=None, sell=None) -> str:
        return bench_sell_note(
            player_id, decision, self.sell if sell is None else sell,
            self.fit if status is None else status,
            player_name="Example Player", expected_points=6.2, fixture_difficulty=3.2,
        )

    def test_matching_player_id_gets_start_if_retained_with_reason_and_fixture(self) -> None:
        text = self.note("START")
        for expected in ("Example Player", "quiet recent returns", "if you keep him", "6.2", "3.2", "start group"):
            self.assertIn(expected, text)

    def test_unrelated_sell_id_cannot_taint_start_or_bench(self) -> None:
        self.assertEqual(self.note("START", player_id=124), "")
        self.assertEqual(self.note("BENCH", player_id=124), "")

    def test_injured_or_unverified_player_never_gets_positive_start_language(self) -> None:
        for state in ({**self.fit, "blocked": True},
                      {**self.fit, "health_clear": False},
                      {**self.fit, "recommendation_eligible": False}):
            with self.subTest(state=state):
                text = self.note("START", status=state)
                self.assertIn("does not support recommending a start", text)
                self.assertNotIn("supports a start", text)

    def test_sell_condition_conflicting_with_clearance_does_not_promote_start(self) -> None:
        for assessment in ("AVAILABILITY_FIRST", "CONDITIONAL_REVIEW"):
            with self.subTest(assessment=assessment):
                sell = [{"player_id": 123, "sell_analysis": {"assessment": assessment}}]
                self.assertIn("does not support recommending a start", self.note("START", sell=sell))

    def test_market_only_does_not_become_a_false_sell_recommendation(self) -> None:
        sell = [{"player_id": 123, "sell_analysis": {"assessment": "MARKET_ONLY"}}]
        text = self.note("START", sell=sell)
        self.assertIn("market activity alone is not a sell reason", text)
        self.assertIn("if you keep him", text)

    def test_patience_case_preserves_current_start_if_retained(self) -> None:
        sell = [{"player_id": 123, "sell_analysis": {"assessment": "PATIENCE_CASE"}}]
        self.assertIn("case for patience", self.note("START", sell=sell))

    def test_sell_and_bench_advice_agrees_on_one_week_lineup(self) -> None:
        text = self.note("BENCH")
        self.assertIn("sell watchlist", text)
        self.assertIn("if you keep him, benching is preferred", text)
        self.assertNotIn("start group", text)

    def test_invalid_decision_is_not_silently_treated_as_start(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported Day 3"):
            self.note("UNKNOWN")

    def test_narration_injection_is_exact_and_fails_closed(self) -> None:
        sample = (
            '    def _d3_bench_narr(frame, index, avoid=False):\n'
            '        return {"player_id": pid, "anchor": anchor, "text": line}\n'
        )
        patched = patch_bench_sell_source(sample)
        self.assertEqual(patched.count("note = bench_sell_note("), 1)
        self.assertEqual(patched.count("return {\"player_id\": pid"), 1)
        with self.assertRaisesRegex(RuntimeError, "contract changed"):
            patch_bench_sell_source(patched)


if __name__ == "__main__":
    unittest.main()
