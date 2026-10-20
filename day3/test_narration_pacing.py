from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from day3.narration_pacing import (
    _speech_bounds,
    apply_narration_pacing,
    measure_speech_bounds,
    narration_scene_filters,
    narration_transition_seconds,
    patch_narration_pacing_source,
)


class NarrationPacingTests(unittest.TestCase):
    def test_edge_parser_keeps_internal_silence(self) -> None:
        log = (
            "silence_start: 0\nsilence_end: 1.25\n"
            "silence_start: 2\nsilence_end: 3\n"
            "silence_start: 4.75\nsilence_end: 8\n"
        )
        self.assertEqual(_speech_bounds(log, 8.0), (1.25, 4.75))
        self.assertEqual(_speech_bounds("", 8.0), (0.0, 8.0))
        self.assertEqual(_speech_bounds("silence_start: 6", 8.0), (0.0, 6.0))

    def test_completely_silent_scene_is_rejected(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "no audible narration"):
            _speech_bounds("silence_start: 0\nsilence_end: 8", 8.0)

    def test_frame_rounding_never_cuts_speech_and_bounds_the_whole_gap(self) -> None:
        for fps in (5, 24):
            for offset in (0.001, 0.049, 0.101, 0.199):
                with self.subTest(fps=fps, offset=offset):
                    timeline = [
                        {"kind": "opening", "duration": 9.0},
                        {"kind": "scene", "key": "first", "path": "first.mp4", "duration": 12.0},
                        {"kind": "transition", "duration": narration_transition_seconds(fps)},
                        {"kind": "scene", "key": "second", "path": "second.mp4", "duration": 12.0},
                        {"kind": "closing_outro", "duration": 8.0},
                    ]
                    with patch("day3.narration_pacing.measure_speech_bounds",
                               return_value=(1.0 + offset, 7.0 + offset)):
                        report = apply_narration_pacing(timeline, fps)
                    self.assertLessEqual(report["max_measured_seconds"], 1.0)
                    self.assertEqual(len(report["boundaries"]), 1)
                    for scene in (timeline[1], timeline[3]):
                        self.assertLessEqual(scene["trim_start"], 1.0 + offset)
                        self.assertGreaterEqual(scene["trim_end"], 7.0 + offset)
                        self.assertAlmostEqual(scene["speech_end"] - scene["speech_start"], 6.0)
                        self.assertAlmostEqual(scene["duration"] * fps, round(scene["duration"] * fps))
                    self.assertEqual(timeline[0]["duration"], 9.0)
                    self.assertEqual(timeline[-1]["duration"], 8.0)

    def test_old_long_transition_cannot_pass_the_gap_contract(self) -> None:
        timeline = [
            {"kind": "scene", "key": "first", "path": "first.mp4", "duration": 8.0},
            {"kind": "transition", "duration": 4.0},
            {"kind": "scene", "key": "next", "path": "next.mp4", "duration": 8.0},
        ]
        with patch("day3.narration_pacing.measure_speech_bounds", return_value=(1.0, 5.0)):
            with self.assertRaisesRegex(RuntimeError, "Narration gap"):
                apply_narration_pacing(timeline, 24)

    def test_one_scene_and_invalid_inputs(self) -> None:
        timeline = [{"kind": "scene", "key": "one", "path": "one.mp4", "duration": 8.0}]
        with patch("day3.narration_pacing.measure_speech_bounds", return_value=(0.0, 8.0)):
            report = apply_narration_pacing(timeline, 24)
        self.assertEqual(report["boundaries"], [])
        self.assertEqual(timeline[0]["trim_start"], 0.0)
        self.assertEqual(timeline[0]["trim_end"], 8.0)
        for invalid in (0, -1, math.inf, math.nan):
            with self.subTest(fps=invalid), self.assertRaises(ValueError):
                narration_transition_seconds(invalid)
        with self.assertRaises(FileNotFoundError):
            measure_speech_bounds(Path("/missing/day3-scene.mp4"), 8.0)

    def test_failed_decoder_and_changed_notebook_fail_clearly(self) -> None:
        with tempfile.NamedTemporaryFile() as media:
            result = subprocess.CompletedProcess([], 1, "", "invalid audio")
            with patch("day3.narration_pacing.subprocess.run", return_value=result):
                with self.assertRaisesRegex(RuntimeError, "Cannot measure narration"):
                    measure_speech_bounds(Path(media.name), 8.0)
        with self.assertRaisesRegex(RuntimeError, "Narration pacing"):
            patch_narration_pacing_source("pass\n")


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg is required")
class NarrationPacingMediaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def ffmpeg(self, *arguments: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", *arguments],
            capture_output=True, check=True, timeout=60,
        )

    def source_clip(self, fps: int, amplitude: float = 0.3) -> Path:
        path = self.root / f"source-{fps}-{amplitude}.mp4"
        audio = (
            f"aevalsrc=if(between(t\\,1.13\\,1.53)+between(t\\,2.03\\,2.53)"
            f"\\,{amplitude}*sin(2*PI*440*t)\\,0):s=48000:d=7"
        )
        self.ffmpeg(
            "-f", "lavfi", "-i", f"color=c=black:s=160x90:r={fps}:d=7",
            "-f", "lavfi", "-i", audio,
            "-vf", "drawbox=x=0:y=0:w=iw:h=ih:color=white:t=fill:enable='between(t,1.13,2.53)'",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", str(path),
        )
        return path

    def media_duration(self, path: Path) -> tuple[float, list[dict]]:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
            capture_output=True, text=True, check=True, timeout=30,
        )
        payload = json.loads(probe.stdout)
        return float(payload["format"]["duration"]), payload["streams"]

    def silence_intervals(self, path: Path) -> list[tuple[float, float]]:
        probe = subprocess.run(
            ["ffmpeg", "-nostdin", "-hide_banner", "-i", str(path), "-vn",
             "-af", "silencedetect=noise=-60dB:d=0.02", "-f", "null", "-"],
            capture_output=True, text=True, check=True, timeout=30,
        )
        starts = [float(value) for value in re.findall(r"silence_start:\s*([\d.]+)", probe.stderr)]
        ends = [float(value) for value in re.findall(r"silence_end:\s*([\d.]+)", probe.stderr)]
        return list(zip(starts, ends))

    def test_real_draft_and_final_handoffs_preserve_speech_and_internal_pauses(self) -> None:
        for fps in (5, 24):
            with self.subTest(fps=fps):
                source = self.source_clip(fps)
                source_duration, _ = self.media_duration(source)
                transition = narration_transition_seconds(fps)
                timeline = [
                    {"kind": "scene", "key": "first", "path": source, "duration": source_duration},
                    {"kind": "transition", "duration": transition},
                    {"kind": "scene", "key": "next", "path": source, "duration": source_duration},
                ]
                report = apply_narration_pacing(timeline, fps)
                self.assertLess(report["max_measured_seconds"], 1.0)
                self.assertGreater(report["trimmed_seconds"], 8.0)
                filters = (
                    narration_scene_filters(timeline[0], 0, 0, 160, 90, fps, 1.15)
                    + narration_scene_filters(timeline[2], 1, 1, 160, 90, fps, 1.15)
                    + [
                        f"[2:v]trim=duration={transition:.9f},setpts=PTS-STARTPTS[vt]",
                        f"[3:a]atrim=duration={transition:.9f},asetpts=PTS-STARTPTS[at]",
                        "[v0][a0][vt][at][v1][a1]concat=n=3:v=1:a=1[v][a]",
                    ]
                )
                output = self.root / f"combined-{fps}.mp4"
                self.ffmpeg(
                    "-i", str(source), "-i", str(source),
                    "-f", "lavfi", "-i", f"color=c=black:s=160x90:r={fps}:d={transition:.9f}",
                    "-f", "lavfi", "-i", f"anullsrc=r=48000:cl=stereo:d={transition:.9f}",
                    "-filter_complex", ";".join(filters),
                    "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "ultrafast",
                    "-c:a", "aac", "-b:a", "192k", str(output),
                )
                duration, streams = self.media_duration(output)
                expected = sum(float(item["duration"]) for item in timeline)
                self.assertAlmostEqual(duration, expected, delta=0.05)
                stream_durations = [float(stream["duration"]) for stream in streams]
                self.assertLessEqual(max(stream_durations) - min(stream_durations), 1 / fps + 0.025)
                intervals = self.silence_intervals(output)
                interior = [(start, end) for start, end in intervals if start > 0.3 and end < duration - 0.3]
                self.assertEqual(len(interior), 3)
                self.assertTrue(all(end - start <= 1.0 for start, end in interior))
                self.assertAlmostEqual(interior[0][1] - interior[0][0], 0.5, delta=0.08)
                self.assertAlmostEqual(interior[-1][1] - interior[-1][0], 0.5, delta=0.08)
                raw = self.ffmpeg("-i", str(output), "-an", "-vf", "scale=16:16,format=gray", "-f", "rawvideo", "-").stdout
                frames = [raw[index:index + 256] for index in range(0, len(raw), 256)]
                first_bright = next(index for index, frame in enumerate(frames) if sum(frame) / len(frame) > 100) / fps
                speech_start, _ = measure_speech_bounds(output, duration)
                self.assertLessEqual(abs(first_bright - speech_start), 1 / fps + 0.06)

    def test_quiet_speech_is_not_removed_as_edge_silence(self) -> None:
        source = self.source_clip(24, amplitude=0.003)
        duration, _ = self.media_duration(source)
        first, last = measure_speech_bounds(source, duration)
        self.assertAlmostEqual(first, 1.13, delta=0.05)
        self.assertAlmostEqual(last, 2.53, delta=0.05)


if __name__ == "__main__":
    unittest.main()
