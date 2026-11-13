"""Validate Day 1 scene timing and capture evidence from the finished MP4."""
from __future__ import annotations

import math
from pathlib import Path
import subprocess

from PIL import Image, ImageChops

from .day1_broadcast import SCENES

SCENE_KEYS = tuple(SCENES)
MIN_SCENE_SECONDS = 10


def scene_timeline(qa, video_seconds):
    sections = qa.get("sections") or []
    if tuple(qa.get("scene_keys") or ()) != SCENE_KEYS or tuple(
        section.get("key") for section in sections
    ) != SCENE_KEYS:
        raise RuntimeError("Final Day 1 export must contain all five scenes in order")

    elapsed = 0.0
    timeline = []
    for section in sections:
        key = section["key"]
        seconds = float(section.get("duration") or 0)
        if not math.isfinite(seconds) or seconds < MIN_SCENE_SECONDS:
            raise RuntimeError(f"Day 1 scene {key} is missing usable chapter duration")
        recorded_start = float(section.get("start_seconds", elapsed))
        if not math.isfinite(recorded_start) or abs(recorded_start - elapsed) > 0.5:
            raise RuntimeError(f"Day 1 scene {key} has inconsistent start timing")
        number, title, _, _ = SCENES[key]
        timeline.append(dict(key=key, number=number, title=title,
                             start_seconds=elapsed, duration=seconds))
        elapsed += seconds

    if not math.isfinite(video_seconds) or abs(video_seconds - elapsed) > 0.5:
        raise RuntimeError("Final MP4 duration does not match its five scene sections")
    return timeline


def capture_scene_evidence(video, timeline, slide_dir):
    frames = []
    for scene in timeline:
        sample = scene["start_seconds"] + scene["duration"] / 2
        path = slide_dir / f"final-scene-{scene['number']:02d}-{scene['key']}.png"
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-ss", f"{sample:.6f}", "-i", str(video), "-map", "0:v:0",
            "-frames:v", "1", "-threads", "1", str(path),
        ], check=True)
        with Image.open(path) as image:
            if image.size != (3840, 2160):
                raise RuntimeError(f"Final scene {scene['number']} frame is not 4K")
            frame = image.convert("L").resize((192, 108))
        dark_pixels = sum(frame.histogram()[:24])
        if dark_pixels >= frame.width * frame.height * .98:
            raise RuntimeError(f"Final scene {scene['number']} sample is black")
        if any(ImageChops.difference(frame, previous).getbbox() is None for previous in frames):
            raise RuntimeError(f"Final scene {scene['number']} duplicates another scene frame")
        frames.append(frame)
        scene["sample_seconds"] = sample
        scene["screenshot"] = path.name
    return timeline
