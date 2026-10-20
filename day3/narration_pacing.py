from __future__ import annotations

import math
import re
import subprocess
from pathlib import Path
from typing import Any


MAX_NARRATION_GAP_SECONDS = 1.0
EDGE_GUARD_SECONDS = 0.12
SILENCE_THRESHOLD_DB = -60
SILENCE_MIN_SECONDS = 0.02


def _positive_number(value: Any, name: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{name} must be finite and positive: {value!r}")
    return number


def narration_transition_seconds(fps: float) -> float:
    rate = _positive_number(fps, "fps")
    return math.ceil(0.2 * rate) / rate


def _speech_bounds(log: str, duration: float) -> tuple[float, float]:
    intervals: list[tuple[float, float]] = []
    pending: float | None = None
    for event, value in re.findall(r"silence_(start|end):\s*(-?\d+(?:\.\d+)?)", log):
        position = min(duration, max(0.0, float(value)))
        if event == "start":
            pending = position
        elif pending is not None:
            intervals.append((pending, position))
            pending = None
    if pending is not None:
        intervals.append((pending, duration))
    first, last = 0.0, duration
    if intervals and intervals[0][0] <= 1e-6:
        first = intervals[0][1]
    if intervals and intervals[-1][1] >= duration - 1e-5:
        last = intervals[-1][0]
    if first >= last:
        raise RuntimeError("Selected scene contains no audible narration")
    return first, last


def measure_speech_bounds(path: Path, duration: float) -> tuple[float, float]:
    length = _positive_number(duration, "scene duration")
    if not path.is_file():
        raise FileNotFoundError(path)
    audio_filter = (
        "aresample=48000:async=1:first_pts=0,"
        f"apad=pad_dur={length:.9f},atrim=duration={length:.9f},"
        "asetpts=PTS-STARTPTS,"
        f"silencedetect=noise={SILENCE_THRESHOLD_DB}dB:d={SILENCE_MIN_SECONDS}"
    )
    result = subprocess.run(
        ["ffmpeg", "-nostdin", "-hide_banner", "-i", str(path),
         "-map", "0:a:0", "-af", audio_filter, "-f", "null", "-"],
        capture_output=True, text=True, timeout=180, check=False,
    )
    if result.returncode:
        raise RuntimeError(f"Cannot measure narration for {path.name}: {result.stderr[-2000:]}")
    return _speech_bounds(result.stderr, length)


def apply_narration_pacing(timeline: list[dict[str, Any]], fps: float) -> dict[str, Any]:
    """Trim only scene edges; all in-scene animation and speech retain their relative timing."""
    rate = _positive_number(fps, "fps")
    scenes: list[dict[str, Any]] = []
    for item in timeline:
        if item["kind"] != "scene":
            continue
        original_duration = _positive_number(item["duration"], "scene duration")
        speech_start, speech_end = measure_speech_bounds(Path(item["path"]), original_duration)
        start_frame = math.floor(max(0.0, speech_start - EDGE_GUARD_SECONDS) * rate)
        end_frame = math.ceil(min(original_duration, speech_end + EDGE_GUARD_SECONDS) * rate)
        trim_start, trim_end = start_frame / rate, end_frame / rate
        if trim_start > speech_start or trim_end < speech_end or end_frame <= start_frame:
            raise RuntimeError(f"Unsafe narration trim for {item['key']}")
        item.update(
            source_duration=original_duration,
            trim_start=trim_start,
            trim_end=trim_end,
            duration=(end_frame - start_frame) / rate,
            speech_start=speech_start - trim_start,
            speech_end=speech_end - trim_start,
        )
        scenes.append(item)

    boundaries: list[dict[str, Any]] = []
    previous: dict[str, Any] | None = None
    between = 0.0
    for item in timeline:
        if item["kind"] != "scene":
            if previous is not None:
                between += float(item["duration"])
            continue
        if previous is not None:
            gap = previous["duration"] - previous["speech_end"] + between + item["speech_start"]
            if gap > MAX_NARRATION_GAP_SECONDS + 1e-6:
                raise RuntimeError(f"Narration gap {previous['key']} -> {item['key']} is {gap:.3f}s")
            boundaries.append({"from": previous["key"], "to": item["key"], "seconds": gap})
        previous, between = item, 0.0

    return {
        "max_allowed_seconds": MAX_NARRATION_GAP_SECONDS,
        "max_measured_seconds": max((row["seconds"] for row in boundaries), default=0.0),
        "boundaries": boundaries,
        "trimmed_seconds": sum(row["source_duration"] - row["duration"] for row in scenes),
        "scenes": [
            {name: row[name] for name in (
                "key", "source_duration", "trim_start", "trim_end", "duration",
                "speech_start", "speech_end",
            )}
            for row in scenes
        ],
    }


def narration_scene_filters(
    item: dict[str, Any], media_index: int, timeline_index: int,
    width: int, height: int, fps: float, voice_gain: float,
) -> list[str]:
    start = float(item["trim_start"])
    end = float(item["trim_end"])
    duration = _positive_number(item["duration"], "trimmed scene duration")
    if not (math.isfinite(start) and math.isfinite(end) and 0 <= start < end):
        raise ValueError("Invalid scene trim window")
    return [
        (
            f"[{media_index}:v:0]trim=start={start:.9f}:end={end:.9f},setpts=PTS-STARTPTS,"
            f"scale={int(width)}:{int(height)}:flags=lanczos,fps={float(fps):.9f},"
            f"tpad=stop_mode=clone:stop_duration={duration:.9f},"
            f"trim=duration={duration:.9f},setsar=1,format=yuv420p[v{timeline_index}]"
        ),
        (
            f"[{media_index}:a:0]aresample=48000:async=1:first_pts=0,"
            f"atrim=start={start:.9f}:end={end:.9f},asetpts=PTS-STARTPTS,"
            f"aformat=channel_layouts=stereo,volume={float(voice_gain):.4f},"
            f"alimiter=limit=0.97:latency=1,apad=pad_dur={duration:.9f},"
            f"atrim=duration={duration:.9f},asetpts=PTS-STARTPTS[a{timeline_index}]"
        ),
    ]


def patch_narration_pacing_source(source: str) -> str:
    replacements = (
        (
            '    ASSEMBLER_VERSION = "VX21-PRODUCTION-PACKAGING-V9-DEFCON-LEFT20-RIGHT20"',
            '    ASSEMBLER_VERSION = "VX21-PRODUCTION-PACKAGING-V10-NARRATION-PACING"',
        ),
        (
            "    TRANSITION_SECONDS = 4.0",
            "    from day3.narration_pacing import (\n"
            "        apply_narration_pacing, narration_scene_filters, narration_transition_seconds,\n"
            "    )\n"
            "    TRANSITION_SECONDS = narration_transition_seconds(FPS)",
        ),
        (
            '        expected_duration = sum(float(item["duration"]) for item in ASSEMBLY_TIMELINE)',
            '        NARRATION_PACING = apply_narration_pacing(ASSEMBLY_TIMELINE, FPS)\n'
            '        expected_duration = sum(float(item["duration"]) for item in ASSEMBLY_TIMELINE)',
        ),
        (
            '                            _fade_out_start = max(0.0, _duration - 0.55)',
            '                            _transition_fade = min(0.08, _duration / 3.0)\n'
            '                            _fade_out_start = max(0.0, _duration - _transition_fade)',
        ),
        (
            '                                f"fade=t=in:st=0:d=0.42:alpha=1,"',
            '                                f"fade=t=in:st=0:d={_transition_fade:.6f}:alpha=1,"',
        ),
        (
            '                                f"fade=t=out:st={_fade_out_start:.6f}:d=0.50:alpha=1,"',
            '                                f"fade=t=out:st={_fade_out_start:.6f}:d={_transition_fade:.6f}:alpha=1,"',
        ),
        (
            '''                        filters.append(
                            f"[{media_index}:v:0]scale={W}:{H}:flags=lanczos,"
                            f"fps={FPS},setsar=1,format=yuv420p,setpts=PTS-STARTPTS[v{timeline_index}]"
                        )
                        filters.append(
                            f"[{media_index}:a:0]aresample=48000:async=1:first_pts=0,"
                            f"aformat=channel_layouts=stereo,"
                            f"volume={SCENE_VOICE_GAIN:.4f},alimiter=limit=0.97,"
                            f"asetpts=PTS-STARTPTS[a{timeline_index}]"
                        )''',
            '''                        filters.extend(narration_scene_filters(
                            item, media_index, timeline_index, W, H, FPS, SCENE_VOICE_GAIN,
                        ))''',
        ),
        (
            '{TRANSITION_SECONDS:.0f}s',
            '{TRANSITION_SECONDS:.2f}s',
        ),
    )
    for old, new in replacements:
        count = source.count(old)
        if count != 1:
            raise RuntimeError(f"Narration pacing: expected one assembly contract, found {count}: {old[:80]}")
        source = source.replace(old, new, 1)
    marker = '                "transition_seconds": TRANSITION_SECONDS,'
    if source.count(marker) != 2:
        raise RuntimeError("Narration pacing: expected fingerprint and final QA packaging")
    source = source.replace(marker, marker + '\n                "narration_pacing": NARRATION_PACING,')
    return source
