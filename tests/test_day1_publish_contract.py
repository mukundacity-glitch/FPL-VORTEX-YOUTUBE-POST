"""Day 1 #88 regression: review visuals must be retrospective, yet transcript is valid.

Tests use fully synthetic Gameweeks/players; no live FPL or connected secrets.
"""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from vortex.day1_publish_contract import (
    snapshot_review_animation_segments,
    assert_review_animation_manifest_current,
    assert_review_script_current,
)


ROOT = Path(__file__).resolve().parents[1]
DISCLOSURE = "Expected points are forecasts, not guaranteed returns"


def synthetic_segments():
    segments = [{
        "id": "headline", "t0": 0.0, "t1": 2.0,
        "text": "Gameweek review. No predictions on the review screen.",
        "editorial_source": ["forward Vortex xPts"],
        "forecast": {"xpts": 8.75},
    }]
    for i in range(15):
        start = 3.0 + i * 2.1
        player = {
            "id": f"player_{i+1}", "player_id": i+1,
            "kind": "starter" if i < 11 else "bench",
            "t0": start, "t1": start + 2.0,
            "speech_end_at": start + 1.9,
            "reveal_at": start + 0.3,
            "text": f"Verified Player {i+1} returned safely this week.",
            "editorial_source": ["verified FPL", "model xPts - should not appear in animation"],
            "model_projection": {"xpts": 6.3, "next_gw_xpts": 8.1},
            "words": [{"start": start, "text": "Player"}],
        }
        if i < 11:
            player.update(hero_on=start+0.3, hero_exit_at=start+1.2, hero_off=start+1.9)
        segments.append(player)
    segments.append({
        "id": "editorial_verdict", "t0": 40.0, "t1": 43.0,
        "text": f"Conditional verdict. {DISCLOSURE}.",
        "editorial_source": ["live projection xPts"],
    })
    return segments


class Day1PublishContractTests(unittest.TestCase):
    def test_animation_metadata_is_well_formed_and_forecast_free(self):
        segments = synthetic_segments()
        original = json.dumps(segments, sort_keys=True)
        visual = snapshot_review_animation_segments(segments)
        self.assertEqual(len(visual), len(segments))
        self.assertEqual(len([seg for seg in visual if seg.get("player_id")]), 15)
        self.assertEqual(len([seg for seg in visual if seg.get("kind") == "starter"]), 11)
        raw = json.dumps(visual).casefold()
        self.assertNotIn("xpts", raw)
        self.assertNotIn("model_projection", raw)
        self.assertNotIn("editorial_source", raw)
        self.assertNotIn("verified player", raw)
        self.assertEqual(original, json.dumps(segments, sort_keys=True),
                         "Sanitization must not mutate original creator script")
        self.assertAlmostEqual(visual[1]["hero_on"], 3.3)
        self.assertAlmostEqual(visual[12]["reveal_at"], 26.4)

    def test_manifest_rejects_stale_games_and_extra_forward_data(self):
        segments = synthetic_segments()
        manifest = {
            "gw": 10,
            "segments": snapshot_review_animation_segments(segments),
            "timeline": {"pitch_at": 0.0},
        }
        self.assertIsNone(assert_review_animation_manifest_current(manifest, segments, 10))
        with self.assertRaisesRegex(ValueError, "Stale GW"):
            assert_review_animation_manifest_current(manifest, segments, 9)
        altered = dict(manifest, xpts={"model": 3.5})
        with self.assertRaisesRegex(ValueError, "forward-looking"):
            assert_review_animation_manifest_current(altered, segments, 10)
        before_filtering = dict(manifest, segments=segments)
        with self.assertRaisesRegex(ValueError, "unfiltered"):
            assert_review_animation_manifest_current(before_filtering, segments, 10)

    def test_missing_player_or_invalid_hero_sync_still_fails_closed(self):
        segments = synthetic_segments()
        with self.assertRaisesRegex(ValueError, "eleven starters"):
            snapshot_review_animation_segments(segments[:-2] + [segments[-1]])
        segments = synthetic_segments()
        segments[1]["hero_off"] = segments[1]["hero_on"]
        with self.assertRaisesRegex(ValueError, "hero fade"):
            snapshot_review_animation_segments(segments)

    def test_legitimate_current_transcript_is_allowed_and_stale_is_rejected(self):
        segments = synthetic_segments()
        with TemporaryDirectory() as tmp:
            script = Path(tmp) / "gw_review_final_script.txt"
            script.write_text("\n\n".join(s["text"] for s in segments), encoding="utf-8")
            self.assertIsNone(assert_review_script_current(script, segments))
            script.write_text("Stale script from another Gameweek", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Stale/mismatched"):
                assert_review_script_current(script, segments)
            script.unlink()
            with self.assertRaisesRegex(ValueError, "Missing or empty"):
                assert_review_script_current(script, segments)

    def test_unknown_txt_and_missing_disclosure_are_blocked(self):
        segments = synthetic_segments()
        with TemporaryDirectory() as tmp:
            other = Path(tmp) / "other.txt"
            other.write_text("\n\n".join(s["text"] for s in segments), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Unexpected"):
                assert_review_script_current(other, segments)
            segments[-1]["text"] = "Watch next week for more news."
            script = Path(tmp) / "gw_review_final_script.txt"
            script.write_text("\n\n".join(s["text"] for s in segments), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "disclosure"):
                assert_review_script_current(script, segments)

    def test_real_source_consumers_use_safe_segments_and_exact_transcript(self):
        source = (ROOT / "1_final_day1.py").read_text(encoding="utf-8")
        self.assertIn('ANIMATION_SEGMENTS = snapshot_review_animation_segments(pkg["segments"])', source)
        self.assertIn('"segments":ANIMATION_SEGMENTS,', source)
        self.assertIn('"segments":ANIMATION_SEGMENTS\n}', source)
        self.assertIn('assert_review_animation_manifest_current(manifest, pkg["segments"], pkg["gw"])', source)
        self.assertIn('assert_review_script_current(', source)
        self.assertIn('and path.name == "gw_review_final_script.txt"', source)
        self.assertIn('invalid_data_artifact:{path.name}', source)
        self.assertIn('vx_phase0_assert_cleanroom("pre-publish")', source)
        self.assertIn('assert_review_animation_manifest_current(\n        _vx17_manifest,', source)
        self.assertIn('invalid_current_run_review_manifest', source)

    def test_workflow_guards_run_before_expensive_full_video(self):
        workflow = (ROOT / ".github/workflows/day-1.yml").read_text(encoding="utf-8")
        self.assertIn("test_day1_publish_contract.py", workflow)
        self.assertLess(workflow.index("test_day1_publish_contract.py"),
                        workflow.index("Execute Day 1 cells once in order"))
        qa = (ROOT / ".github/workflows/day1-editorial-qa.yml").read_text(encoding="utf-8")
        self.assertIn("test_day1_publish_contract.py", qa)


if __name__ == "__main__":
    unittest.main()
