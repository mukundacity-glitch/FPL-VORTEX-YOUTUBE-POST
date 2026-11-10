"""Frame the current Day 1 scene outputs with the shared broadcast rails."""

import hashlib
import json
from pathlib import Path
import subprocess

from PIL import Image, ImageDraw

REVIEW_PANEL_CSS = Path(__file__).with_name("day1_review_panels.css")
PROJECT = Path(__file__).resolve().parents[1] / "tools" / "day1-broadcast"
# Crop windows describe the native renderer's furniture at 1920×1080.
SCENES = {
    "00_intro": (1, "The Gameweek Brief", 150, 1080),
    "gw_review": (2, "Gameweek Review", 198, 1042),
    "02_fdr": (3, "Players & Fixtures", 78, 1080),
    "03_projected_goals": (4, "Numbers & Market Outlook", 109, 990),
}


def scene_manifest(reports, review_gw, next_gw, fps, logo, *, review_status, latest_completed):
    if not isinstance(review_gw, int) or not isinstance(next_gw, int) or not 1 <= review_gw < next_gw <= 38:
        raise ValueError("Expected a completed review gameweek and an upcoming planning gameweek")
    if review_status != "FINAL" or review_gw != latest_completed or review_gw != next_gw - 1:
        raise ValueError("Premium Day 1 needs the preceding gameweek to be final before rendering")
    result = []
    for report in reports:
        key = report["key"]
        if key not in SCENES:
            continue
        number, title, top, bottom = SCENES[key]
        frames = round(report["duration"] * fps)
        if frames < 1:
            raise ValueError(f"{key} has no usable video frames")
        result.append(dict(number=number, title=title, top=top, bottom=bottom, frames=frames,
                           label=f"GW{review_gw if key == 'gw_review' else next_gw}", logo=logo))
    return result


def presentation_digest():
    digest = hashlib.sha256()
    for path in (Path(__file__), PROJECT / "index.jsx", PROJECT / "broadcast.css",
                 PROJECT / "render-rails.cjs", PROJECT / "package-lock.json"):
        digest.update(path.read_bytes())
    return digest.hexdigest()


def render_rails(scenes, work):
    work.mkdir(parents=True, exist_ok=True)
    manifest = work / "scenes.json"
    manifest.write_text(json.dumps(scenes), encoding="utf-8")
    if scenes:
        subprocess.run(["node", str(PROJECT / "render-rails.cjs"), str(manifest.resolve())], check=True)


def video_filter(scene, index, rails_index, work, width, height, fps):
    """Keep source timing and aspect ratio. Rail rasters have transparent content windows."""
    number = scene["number"]
    scale = min(1, 868 / (scene["bottom"] - scene["top"]))
    out_w = 2 * int(width * scale / 2)
    out_h = 2 * int(height * (scene["bottom"] - scene["top"]) * scale / 2160)
    x = 2 * ((width - out_w) // 4)
    y = 2 * int((112 * height / 1080 + (868 * height / 1080 - out_h) / 2) / 2)
    crop_y = 2 * int(scene["top"] * height / 2160)
    crop_h = 2 * int((scene["bottom"] - scene["top"]) * height / 2160)
    inputs = []
    for label in ("settled", "entrance"):
        source = work / f"rail-{number}-{label}.png"
        target = work / f"alpha-{number}-{label}.png"
        with Image.open(source) as rail:
            rgba = rail.convert("RGBA").resize((width, height), Image.Resampling.LANCZOS)
            ImageDraw.Draw(rgba).rectangle((x, y, x + out_w - 1, y + out_h - 1), fill=(0, 0, 0, 0))
            rgba.save(target)
        inputs += ["-framerate", str(fps), "-i", str(target)]
    filters = [
        f"[{index}:v:0]scale={width}:{height}:flags=lanczos,crop={width}:{crop_h}:0:{crop_y},"
        f"scale={out_w}:{out_h},pad={width}:{height}:{x}:{y},fps={fps},setsar=1,setpts=PTS-STARTPTS[b{index}]",
        f"[b{index}][{rails_index}:v]overlay=eof_action=repeat[r{index}]",
        f"[{rails_index + 1}:v]format=rgba,loop=loop={round(.8 * fps)}:size=1:start=0,fade=t=out:st=0:d=0.8:alpha=1[e{index}]",
        f"[r{index}][e{index}]overlay=eof_action=pass,format=yuv420p[v{index}]",
    ]
    return inputs, filters
