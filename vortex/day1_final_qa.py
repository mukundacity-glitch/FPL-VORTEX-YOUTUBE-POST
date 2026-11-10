"""Decode the delivered Day 1 MP4 and retain review frames from each scene."""
import json
from pathlib import Path
import re

from .day1_broadcast import SCENES
from .day1_media import _probe, _run, _stream, _write_json_atomic


def verify(root: Path):
    data = root / "DATA"
    assembly = json.loads((data / "final_video_qa.json").read_text())
    video = Path(assembly["final_file"])
    if video.parent.resolve() != (root / "MP4").resolve():
        raise ValueError("Final MP4 is outside the Day 1 output folder")
    sections = assembly["sections"]
    if [section["key"] for section in sections] != list(SCENES):
        raise ValueError("Final MP4 evidence must contain exactly five ordered scenes")
    media = _probe(video)
    image, audio = _stream(media, "video"), _stream(media, "audio")
    if (image["width"], image["height"], image["codec_name"], audio["codec_name"]) != (
        3840, 2160, "h264", "aac"
    ):
        raise ValueError("Final MP4 must contain 3840 × 2160 H.264 and AAC")

    diagnostics = _run([
        "ffmpeg", "-hide_banner", "-v", "info", "-xerror", "-i", str(video),
        "-map", "0:v:0", "-map", "0:a:0",
        "-vf", "blackdetect=d=0.10:pix_th=0.10",
        "-af", "silencedetect=n=-50dB:d=0.60,volumedetect",
        "-f", "null", "-",
    ]).stderr
    black = re.findall(r"black_start:([\d.]+).*?black_end:([\d.]+)", diagnostics)
    silence = re.findall(r"silence_start:\s*([\d.]+)", diagnostics)
    peak = re.search(r"max_volume: ([-\d.]+) dB", diagnostics)

    elapsed = 0.0
    frames = []

    def capture(name, timestamp, scene):
        _run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
              "-ss", f"{timestamp:.3f}", "-i", str(video), "-frames:v", "1",
              str(root / "SLIDE" / name)])
        frames.append({"file": name, "scene": scene, "seconds": timestamp})

    for number, section in enumerate(sections, 1):
        seconds = float(section["duration"])
        start = float(section.get("start_seconds", elapsed))
        if seconds <= 0 or abs(start - elapsed) > 0.5:
            raise ValueError(f"Invalid scene timing for {section['key']}")
        timestamp = start + seconds / 2
        capture(f"final-scene-{number:02d}.png", timestamp, section["key"])
        elapsed = start + seconds

    board = json.loads((data / "scene05_value_board.json").read_text())
    weekly_cues = {
        cue["gameweek"]: cue for cue in board["narrationCues"] if cue.get("gameweek")
    }
    expected_weeks = [plan["gameweek"] for plan in board["weeklyPlans"]]
    if len(expected_weeks) != 5 or set(weekly_cues) != set(expected_weeks):
        raise ValueError("Scene 05 is missing measured cues for its five weekly plans")
    for week in expected_weeks:
        cue = weekly_cues[week]
        if not 0 <= cue["start"] < cue["end"] <= seconds:
            raise ValueError(f"Scene 05 timing is invalid for GW{week}")
        capture(f"final-scene-05-gw{week:02d}.png",
                start + (cue["start"] + cue["end"]) / 2, sections[-1]["key"])

    length = float(media["format"]["duration"])
    passed = not black and not silence and peak is not None and float(peak[1]) < 0
    passed = passed and abs(length - elapsed) <= 0.5
    result = {"passed": passed, "duration": length, "resolution": [3840, 2160],
              "video_codec": "h264", "audio_codec": "aac",
              "black_intervals": black, "silence_starts": silence,
              "sample_peak_dbfs": float(peak[1]) if peak else None, "frames": frames}
    _write_json_atomic(data / "day1_final_media_scan.json", result)
    if not passed:
        raise RuntimeError(f"Final media scan failed: {result}")


if __name__ == "__main__":
    verify(Path("/content/drive/MyDrive/FPL_VORTEX/FIRST VIDEO"))
