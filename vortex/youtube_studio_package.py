"""Build the private YouTube metadata package for FPL VORTEX Video 1/3.

This module never contacts YouTube. It validates the final true-4K video and
creates JSON containing the dynamic title, description, hashtags, tags,
chapters, and the private-upload safety policy for the existing uploader.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from datetime import datetime, timezone
import math
import json
import os
import re
import subprocess

from .day1_final_scenes import capture_scene_evidence, scene_timeline


DEFAULT_OUTPUT_ROOT = Path("/content/drive/MyDrive/FPL_VORTEX/FIRST VIDEO")
YT_VIDEO_PART = 1
YT_VIDEO_TOTAL = 3
YT_VIDEO_SIZE = (3840, 2160)
DAY1_MAX_EXPORT_SECONDS = 535.0


def _vx23_required_file(path, label):
    path = Path(path)
    if not path.is_file() or path.stat().st_size <= 0:
        raise FileNotFoundError(f"Required {label} is missing or empty: {path}")
    return path


def _vx23_single_file(folder, pattern, label):
    matches = sorted(path for path in Path(folder).glob(pattern) if path.is_file())
    if len(matches) != 1:
        raise RuntimeError(
            f"Expected exactly one {label} matching {pattern!r} in {folder}; "
            f"found {len(matches)}"
        )
    return _vx23_required_file(matches[0], label)


def _vx23_probe_video(path):
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,codec_name,avg_frame_rate",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    streams = payload.get("streams") or []
    if len(streams) != 1:
        raise RuntimeError(f"Expected one video stream in {path}; found {len(streams)}")
    stream = streams[0]
    rate = str(stream.get("avg_frame_rate") or "0/1")
    try:
        numerator, denominator = rate.split("/", 1)
        fps = float(numerator) / float(denominator)
    except (TypeError, ValueError, ZeroDivisionError):
        fps = 0.0
    return {
        "width": int(stream.get("width") or 0),
        "height": int(stream.get("height") or 0),
        "codec": str(stream.get("codec_name") or ""),
        "fps": fps,
        "duration": float(payload.get("format", {}).get("duration") or 0.0),
    }


def _vx23_read_json(path, label):
    path = _vx23_required_file(path, label)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"Expected {label} to be a JSON object: {path}")
    return payload


def _vx23_atomic_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    os.replace(temporary, path)



def _vx23_timestamp(total_seconds):
    whole = max(0, int(float(total_seconds)))
    hours, remainder = divmod(whole, 3600)
    minutes, seconds = divmod(remainder, 60)
    return (
        f"{hours}:{minutes:02d}:{seconds:02d}"
        if hours
        else f"{minutes}:{seconds:02d}"
    )


def _vx23_chapters(timeline, review_gw):
    return [
        f"{_vx23_timestamp(scene['start_seconds'])} "
        + (f"GW{review_gw} Review — The Real Story" if scene["key"] == "gw_review"
           else scene["title"])
        for scene in timeline
    ]


def _vx23_metadata(preview_gw, review_gw, review_status, timeline, board=None):
    title = f"FPL GW{preview_gw} | Transfer Market Outlook & Best £100m Squad"
    status = "provisional" if review_status == "LIVE/PARTIAL" else "final"
    hashtags = ["#FPL", "#FantasyPremierLeague", f"#FPLGameweek{preview_gw}"]
    chapters = _vx23_chapters(timeline, review_gw)
    captain = next((p for p in (board or {}).get("starters", []) if p.get("captain")), None)
    captain_name = str((captain or {}).get("name") or "").strip()
    captain_line = (
        f"{captain_name} gets the armband on the Value Board, based on the strongest "
        "projected return in its starting eleven."
        if captain_name else
        "The Value Board highlights the captain with the strongest projected return in its starting eleven."
    )
    description = "\n".join([
        f"FPL VORTEX reviews the latest results and looks ahead to Gameweek {preview_gw}.",
        "",
        f"The {status} Gameweek {review_gw} review looks at the points, rank movement and the decision "
        "that shaped the result. Then I look ahead to the fixtures and where recent minutes give us "
        "a better idea of who can actually take advantage of the schedule.",
        "",
        "The Numbers Behind the Points profiles one player from the completed gameweek "
        "using official scoring actions and available underlying numbers. The market chapter "
        "compares the leading transfer activity ahead of the next deadline.",
        "",
        captain_line + " The Value Board shows the recommended 15-player squad, "
        "with each player’s price and next-gameweek expected points.",
        "",
        "Which position are you weighing up? Tell me if you’d make the move or keep the transfer for another week.",
        "",
        *chapters,
        "",
        " ".join(hashtags),
    ])
    tags = [
        "FPL",
        "Fantasy Premier League",
        f"FPL GW{preview_gw}",
        f"Gameweek {preview_gw}",
        "FPL review",
        "FPL VORTEX",
        "FPL Value Board",
    ]
    if len(title) > 70:
        raise RuntimeError(f"YouTube title exceeds 70 characters: {len(title)}")
    if len(description.encode("utf-8")) > 5000:
        raise RuntimeError("YouTube description exceeds 5,000 UTF-8 bytes")
    if sum(len(tag) for tag in tags) + max(0, len(tags) - 1) > 500:
        raise RuntimeError("YouTube tags exceed the 500-character limit")
    return {
        "title": title,
        "description": description,
        "hashtags": hashtags,
        "tags": tags,
        "chapters": chapters,
        "category": "Sports",
        "category_id": "17",
        "language": "en-GB",
        "recommended_visibility": "Private",
        "made_for_kids": False,
        "notify_subscribers_before_manual_publish": False,
        "series": {"part": YT_VIDEO_PART, "total": YT_VIDEO_TOTAL},
        "preview_gw": int(preview_gw),
        "review_gw": int(review_gw),
        "review_status": review_status,
    }


def build_youtube_studio_package(output_root):
    output_root = Path(output_root).resolve()
    video_dir = output_root / "MP4"
    data_dir = output_root / "DATA"
    for folder in (video_dir, data_dir):
        if not folder.is_dir():
            raise FileNotFoundError(f"Required Day 1 output directory is missing: {folder}")

    qa = _vx23_read_json(data_dir / "final_video_qa.json", "final video QA")
    review = _vx23_read_json(
        data_dir / "gw_review_package.json",
        "Gameweek review package",
    )
    if qa.get("passed") is not True:
        raise RuntimeError("Final video QA has not passed; refusing YouTube packaging")
    if qa.get("external_media_integration", {}).get("applied") is not True:
        raise RuntimeError(
            "Opening/music integration must pass before the YouTube Studio package is built"
        )

    configured_video = str(qa.get("final_file") or "").strip()
    if configured_video:
        candidate = Path(configured_video)
        final_video = video_dir / candidate.name
        if final_video.resolve().parent != video_dir.resolve():
            raise RuntimeError(f"Final QA points outside the MP4 directory: {candidate}")
        final_video = _vx23_required_file(final_video, "final 4K MP4")
    else:
        final_video = _vx23_single_file(
            video_dir,
            "*COMBINED*.mp4",
            "combined final MP4",
        )

    video_probe = _vx23_probe_video(final_video)
    if not math.isfinite(video_probe["duration"]) or video_probe["duration"] <= 0:
        raise RuntimeError("Day 1 combined MP4 has missing or invalid duration")
    if video_probe["duration"] > DAY1_MAX_EXPORT_SECONDS:
        raise RuntimeError(
            f"Day 1 final export is {video_probe['duration']:.2f}s. "
            f"The private upload requires {DAY1_MAX_EXPORT_SECONDS:.0f}s or less."
        )
    if (video_probe["width"], video_probe["height"]) != YT_VIDEO_SIZE:
        raise RuntimeError(
            "YouTube Studio package requires a true 4K final MP4; "
            f"found {video_probe['width']}x{video_probe['height']}"
        )
    if list(qa.get("video_output") or []) != [3840, 2160]:
        raise RuntimeError(
            f"Final video QA is not true 4K: {qa.get('video_output')}"
        )

    match = re.search(r"(?:^|_)GW(\d{1,2})(?:_|$)", final_video.name, re.I)
    preview_gw = int(match.group(1)) if match else 0
    review_gw = int(review.get("gw") or 0)
    if not 1 <= preview_gw <= 38 or not 1 <= review_gw <= 38:
        raise RuntimeError(
            f"Invalid dynamic Gameweeks: preview={preview_gw}, review={review_gw}"
        )

    review_status = str(review.get("status") or "FINAL").upper()
    if review_status not in {"FINAL", "LIVE/PARTIAL"}:
        raise RuntimeError(f"Invalid Gameweek review status: {review_status!r}")

    board = _vx23_read_json(data_dir / "scene05_value_board.json", "Value Board")
    if board.get("nextGameweek") != preview_gw:
        raise RuntimeError("Value Board Gameweek does not match the rendered video")
    timeline = scene_timeline(qa, video_probe["duration"])
    capture_scene_evidence(final_video, timeline, output_root / "SLIDE")
    metadata = _vx23_metadata(preview_gw, review_gw, review_status, timeline, board)
    qa["verified_final_scenes"] = timeline
    _vx23_atomic_json(data_dir / "final_video_qa.json", qa)
    chapters = metadata["chapters"]
    for chapter in chapters:
        print(f"[DAY 1 SCENE] {chapter}")
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with Path(summary_path).open("a", encoding="utf-8") as summary:
            summary.write("## Day 1 final video chapters\n\n")
            summary.writelines(f"- {chapter}\n" for chapter in chapters)
            summary.write("\nFive frames from the final MP4 are included in the Day 1 output artifact.\n")

    package = {
        "version": "FPL-VORTEX-YOUTUBE-PRIVATE-AUTO-V4",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "render_revision": os.environ.get("GITHUB_SHA") or None,
        "manual_upload_only": False,
        "youtube_api_upload_enabled": True,
        "automatic_publication_enabled": False,
        "upload_policy": {
            "privacy_status": "private",
            "notify_subscribers": False,
            "automatic_publish": False,
            "automatic_schedule": False,
            "manual_publication_required": True,
        },
        "video": {
            "file": str(final_video),
            "sha256": qa["external_media_integration"]["final_sha256"],
            "resolution": [video_probe["width"], video_probe["height"]],
            "codec": video_probe["codec"],
            "fps": video_probe["fps"],
            "duration_seconds": video_probe["duration"],
        },
        "metadata": metadata,
        "studio_checklist": [
            "GitHub uploads the packaged 4K MP4 to the verified channel as Private.",
            "GitHub applies this generated title, description, and tags.",
            "Add your thumbnail manually in YouTube Studio after reviewing the Private upload.",
            "Open the video in YouTube Studio and review every field.",
            "Only change Visibility to Public manually when the video is ready.",
        ],
    }
    package_path = data_dir / "youtube_video_1_of_3_package.json"
    _vx23_atomic_json(package_path, package)

    print("\n" + "=" * 74)
    print("✅ PRIVATE YOUTUBE UPLOAD PACKAGE — VIDEO 1/3")
    print("=" * 74)
    print("✅ YouTube API upload enabled: Private only; automatic publishing disabled")
    print(f"✅ Dynamic preview/review: GW{preview_gw} / GW{review_gw} ({review_status})")
    print(f"✅ Copy/paste package: {package_path}")
    print("\nTITLE\n" + metadata["title"])
    print("\nDESCRIPTION\n" + metadata["description"])
    return package


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Create the dynamic SEO metadata package for automatic Private "
            "YouTube upload without generating an image"
        )
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path(os.environ.get("DAY1_OUTPUT_ROOT", DEFAULT_OUTPUT_ROOT)),
    )
    args = parser.parse_args()
    build_youtube_studio_package(args.output_root)


if __name__ == "__main__":
    main()

