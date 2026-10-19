from __future__ import annotations

import ast
import math
import unittest
from pathlib import Path
from typing import Any

SOURCE = Path(__file__).resolve().parents[1] / "1_final_day1.py"


def review_functions() -> dict[str, Any]:
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
    names = {
        "_review_fixture_state",
        "fixture_for",
        "vx_review_number",
        "vx_review_full_name",
        "vx_review_player_result_state",
        "vx_review_creator_player_text",
        "_vx_build_review_timeline",
    }
    nodes = [
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in names
    ]
    found = {node.name for node in nodes}
    if found != names:
        raise AssertionError(f"Day 1 review helpers missing: {sorted(names - found)}")
    namespace: dict[str, Any] = {
        "Any": Any,
        "math": math,
        "review_fx": [],
        "review_teams": {},
        "vx_narration_player": lambda player: player["name"],
        "_review_narration_context": {},
        "vx_review_return_reason": lambda player: "",
        "vx_review_recent_phrase": lambda context: "",
        "vx_review_schedule": lambda context, named=False: "",
        "vx_review_price": lambda value: str(value),
    }
    module = ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[]))
    exec(compile(module, str(SOURCE), "exec"), namespace)
    return namespace


class Day1ReviewContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.env = review_functions()

    def test_short_spoken_name_overrides_legal_name(self) -> None:
        names = {1: "João Pedro", 2: "van Hecke"}
        self.env["vx_narration_player"] = lambda player: names[int(player["id"])]
        name = self.env["vx_review_full_name"]
        self.assertEqual(
            name({"id": 1, "first_name": "João Pedro", "second_name": "Junqueira de Jesus", "name": "João Pedro"}),
            "João Pedro",
        )
        self.assertEqual(
            name({"id": 2, "full_name": "Jan Paul van Hecke", "name": "van Hecke"}),
            "van Hecke",
        )

    def test_pending_vs_actual_zero_and_substitution(self) -> None:
        status = self.env["vx_review_player_result_state"]
        self.assertEqual(status({"review_state": "PENDING", "minutes": 0}), "AWAITING")
        self.assertEqual(status({"review_state": "LIVE", "minutes": 0}), "AWAITING")
        self.assertEqual(status({"review_state": "PARTIAL", "minutes": 90}), "PROVISIONAL")
        self.assertEqual(status({"review_state": "FINAL", "minutes": 90, "points": 0}), "COMPLETE")
        self.assertEqual(status({"review_state": "FINAL", "minutes": 0}), "DID_NOT_PLAY")
        self.assertEqual(status({"review_state": "UNKNOWN", "minutes": 0}), "UNKNOWN")

    def test_team_fixture_state_checks_all_matches(self) -> None:
        self.env["review_teams"] = {
            1: {"short_name": "AAA"}, 2: {"short_name": "BBB"},
            3: {"short_name": "CCC"},
        }
        pending = {"team_h": 1, "team_a": 2, "started": False, "minutes": 0}
        done = {
            "team_h": 1, "team_a": 3, "started": True, "minutes": 90,
            "finished": True, "team_h_score": 1, "team_a_score": 0,
        }
        live = {"team_h": 1, "team_a": 2, "started": True, "minutes": 45}
        fixture = self.env["fixture_for"]
        self.env["review_fx"] = [pending]
        self.assertEqual(fixture(1)["state"], "PENDING")
        self.env["review_fx"] = [done]
        self.assertEqual(fixture(1)["state"], "FINAL")
        self.env["review_fx"] = [done, pending]
        self.assertEqual(fixture(1)["state"], "PARTIAL")
        self.env["review_fx"] = [done, live]
        self.assertEqual(fixture(1)["state"], "LIVE")
        self.assertEqual(fixture(999)["state"], "UNKNOWN")

    def test_spoken_result_status_not_false_zero(self) -> None:
        render = self.env["vx_review_creator_player_text"]
        self.env["_review_narration_context"] = {
            1: {"full_name": "A Test", "stats": {"total_points": 0, "minutes": 0}},
            2: {"full_name": "B Test", "stats": {"total_points": 0, "minutes": 85}},
            3: {"full_name": "C Test", "stats": {"total_points": 0, "minutes": 0}},
        }
        base = {"pos": "DEF", "squad_position": 1, "points": 0}
        pending = render({"id": 1, "review_state": "PENDING", "minutes": 0, **base}, 0)
        self.assertIn("not played yet", pending)
        self.assertNotIn("0 points", pending)
        final_zero = render({"id": 2, "review_state": "FINAL", "minutes": 85, **base}, 0)
        self.assertIn("0", final_zero)
        self.assertNotIn("not played yet", final_zero)
        did_not_play = render({"id": 3, "review_state": "FINAL", "minutes": 0, **base}, 0)
        self.assertIn("did not feature", did_not_play)
        self.assertNotIn("0 points", did_not_play)

    def test_no_fixed_eight_second_opening(self) -> None:
        timing = {
            "first_player_at": 0.0,
            "goalkeeper_card_out": 23.0,
            "hero_fade_out": 0.34,
            "final_hold": 3.0,
        }
        package = {
            "starters": [{"id": 71, "pos": "GK"}],
            "segments": [
                {"id": "headline", "duration": 3.0, "words": []},
                {
                    "id": "player_71", "player_id": 71, "kind": "starter",
                    "duration": 6.0, "name_time": 0.8, "words": [],
                },
            ],
        }
        timeline = self.env["_vx_build_review_timeline"](package, timing)
        self.assertAlmostEqual(package["segments"][1]["t0"], 3.0)
        self.assertAlmostEqual(timing["first_player_at"], 3.8)
        self.assertAlmostEqual(package["segments"][1]["reveal_at"], 3.8)
        self.assertAlmostEqual(timeline["narration_end"], 9.0)

    def test_first_frame_motion_is_configured(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        for field in ("premier_league_logo_at", "review_title_at", "pitch_at"):
            self.assertIn(f'"{field}": 0.0', source)
        self.assertIn('Number(timing.pitch_at ?? 0)', source)


if __name__ == "__main__":
    unittest.main()
