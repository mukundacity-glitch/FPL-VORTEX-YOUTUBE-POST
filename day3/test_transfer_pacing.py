"""Verify PCM pacing preserves speech bytes and the production card clock."""

from array import array
import asyncio
import ast
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import wave

from day3.transfer_pacing import compact_transfer_pcm
from day3 import test_transfer_desk_timeline as timeline_contract


RATE = 48000


def pcm(seconds, amplitude=0):
    values = array("h", [amplitude]) * round(seconds * RATE)
    if sys.byteorder != "little":
        values.byteswap()
    return values.tobytes()


class TransferPcmTests(unittest.TestCase):
    def test_long_silence_is_cut_without_losing_speech_or_word_durations(self):
        frames = pcm(2) + pcm(.4, 5000) + pcm(4) + pcm(.4, -5000) + pcm(3)
        words = [dict(text="First", start=2, duration=.4),
                 dict(text="Next", start=6.4, duration=.4)]
        result, updated = compact_transfer_pcm(frames, words)
        self.assertAlmostEqual(len(result) / (2 * RATE), 1.39)
        self.assertAlmostEqual(updated[0]["start"], .12)
        self.assertAlmostEqual(updated[1]["start"], .87)
        self.assertEqual([round(w["duration"], 6) for w in updated], [.4, .4])
        self.assertEqual(result, pcm(.12) + pcm(.4, 5000) + pcm(.35) +
                         pcm(.4, -5000) + pcm(.12))
        self.assertEqual(words[0]["start"], 2)

    def test_short_natural_pause_is_preserved_exactly(self):
        frames = pcm(.4, 5000) + pcm(.6) + pcm(.4, -5000)
        words = [dict(text="First", start=0, duration=.4),
                 dict(text="Next", start=1, duration=.4)]
        result, updated = compact_transfer_pcm(frames, words)
        self.assertEqual(result, frames)
        self.assertEqual(updated, words)

    def test_sound_inside_a_word_clock_gap_is_never_cut(self):
        frames = pcm(.4, 5000) + pcm(4, 200) + pcm(.4, -5000)
        words = [dict(text="First", start=0, duration=.4),
                 dict(text="Next", start=4.4, duration=.4)]
        result, updated = compact_transfer_pcm(frames, words)
        self.assertEqual(result, frames)
        self.assertEqual(updated, words)

    def test_quiet_syllables_inside_a_word_are_protected(self):
        frames = pcm(.4, 5000) + pcm(2, 10) + pcm(.4, -5000)
        words = [dict(text="Unbroken", start=0, duration=2.8)]
        result, updated = compact_transfer_pcm(frames, words)
        self.assertEqual(result, frames)
        self.assertEqual(updated, words)

    def test_overlapping_word_spans_remain_unchanged(self):
        frames = pcm(.4, 5000) + pcm(2) + pcm(.4, -5000)
        words = [dict(text="First", start=0, duration=2.5),
                 dict(text="Next", start=2.4, duration=.4)]
        result, updated = compact_transfer_pcm(frames, words)
        self.assertEqual(result, frames)
        self.assertEqual(updated, words)

    def test_invalid_word_clocks_fail_before_audio_is_published(self):
        for words in ([], [dict(start=-1)], [dict(start=float("nan"))],
                      [dict(start=0, duration=10)], [dict(start=.5), dict(start=.1)]):
            with self.subTest(words=words), self.assertRaises(ValueError):
                compact_transfer_pcm(pcm(1), words)


def exercise_real_audio(testcase, namespace, script):
    """Use real FFmpeg encoding and decoding; synthesize repeatable speech pulses."""
    original_words = []

    async def synthesize(path, text, profile):
        words = []
        frames = pcm(1.5)
        cursor = 1.5
        for index, token in enumerate(text.split()):
            words.append(dict(text=token, start=cursor, duration=.08))
            frames += pcm(.08, 5000 if index % 2 else -5000)
            cursor += .08
            # Simulate a bad TTS pause in the middle as well as at the edges.
            pause = 2.5 if index == 4 else .02
            frames += pcm(pause)
            cursor += pause
        frames += pcm(2)
        source = Path(path).with_suffix(".input.wav")
        with wave.open(str(source), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(RATE)
            output.writeframes(frames)
        original_words.extend(word["text"] for word in words)
        return dict(audio=str(source), words=words)

    def duration(path):
        return float(subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(path)],
            check=True, capture_output=True, text=True).stdout)

    namespace["vx_synthesize_audio"] = synthesize
    namespace["vx_media_duration"] = duration
    info = asyncio.run(namespace["_d3_transfer_audio"]({}))
    cues = info["sync_cues"]
    testcase.assertEqual(cues["silent_intervals"], [])
    testcase.assertTrue(all(window["narrated"] for window in cues["windows"]))
    testcase.assertEqual([word["text"] for word in info["words"]], original_words)
    testcase.assertEqual(info["script"], script)
    for previous, current in zip(info["words"], info["words"][1:]):
        testcase.assertLessEqual(current["start"] - previous["start"] - previous["duration"], 1.0)
    testcase.assertLess(info["words"][0]["start"], .13)
    testcase.assertLess(info["duration"] - info["words"][-1]["start"] -
                        info["words"][-1]["duration"], .2)
    for window in cues["windows"]:
        word_start = namespace["vx_phrase_time"](info["words"], window["anchor"], required=True)
        testcase.assertLessEqual(window["start"], word_start)
        testcase.assertLess(word_start, window["settle"])
    namespace["validate_animation"]("05_transfer_decision_desk", info)
    namespace["validate_payload"]("05_transfer_decision_desk", {})
    log = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", info["audio"], "-af",
         "silencedetect=noise=-50dB:d=1", "-f", "null", "-"],
        check=True, capture_output=True, text=True).stderr
    testcase.assertNotIn("silence_start:", log)
    return info


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required")
class TransferEncodedAudioTests(unittest.TestCase):
    def test_real_encoder_has_no_long_gaps_with_full_or_empty_holds(self):
        for hold_count in (0, 5):
            with self.subTest(hold_count=hold_count), tempfile.TemporaryDirectory() as directory:
                namespace, _ = timeline_contract.TransferDeskTimelineTests().namespace(Path(directory), hold_count)
                script = namespace["_d3_transfer_full_narration"]()
                exercise_real_audio(self, namespace, script)


def check_notebook_transfer_pacing(path):
    """Exercise the actual patched production functions, beyond fixture contracts."""
    from day3.run_notebook import _prepare_code_cells
    import numpy as np
    import pandas as pd

    cells = dict(_prepare_code_cells(Path(path)))
    functions = {}
    for cell in (24, 32):
        tree = ast.parse(cells[cell])
        wanted = {"_d3_desk_narr", "_d3_transfer_full_narration", "_d3_transfer_audio"}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in wanted:
                functions[node.name] = node
    if len(functions) != 3:
        raise AssertionError("Missing production Transfer Desk functions")
    class Availability:
        def eligible(self, pid):
            return pid != 4
        def caution(self, pid):
            return "He is suspended; wait for confirmed clearance."
        def state(self, pid):
            return {"health_clear": self.eligible(pid)}

    for hold_count in range(6):
        with tempfile.TemporaryDirectory() as directory:
            ns, _ = timeline_contract.TransferDeskTimelineTests().namespace(Path(directory), hold_count)
            ns.update(pd=pd, np=np, DAY3_AVAILABILITY=Availability())
            for rows in ns["DAY3_TRANSFER_DESK"].values():
                for row in rows:
                    row.update(next_fixture="Club (H)", next_fdr=2.5, xpts=4.1,
                               next_5_xpts=20, has_projection=True, has_horizon=True,
                               recent_performance={"points":6,"gameweeks":3})
            module = ast.Module(body=list(functions.values()), type_ignores=[])
            exec(compile(module, "production_transfer_pacing", "exec"), ns)
            script = ns["_d3_transfer_full_narration"]()
            ns["check_spoken_cards"]()
            info = exercise_real_audio(unittest.TestCase(), ns, script)
            assert len(info["sync_cues"]["windows"]) == 10 + hold_count
    print("Production Transfer Desk narration/PCM/card cues passed for 0–5 holds.")


if __name__ == "__main__":
    unittest.main()
