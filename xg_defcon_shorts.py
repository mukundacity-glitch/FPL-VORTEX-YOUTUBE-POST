from __future__ import annotations

import json
import math
import os
import re
import subprocess
import textwrap
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps

from xg_defcon_pipeline import REPORTS, read_report_metadata, root_path

WIDTH = 1080
HEIGHT = 1920
FPS = 30
CLIP_SECONDS = 5.5
INTRO_SECONDS = 2.5
OUTRO_SECONDS = 2.5
TRANSITION_SECONDS = 0.35
SECTIONS_PER_REPORT = 3


def command(*arguments: str) -> None:
    subprocess.run(arguments, check=True)


def font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    try:
        return ImageFont.truetype(name, size)
    except OSError:
        return ImageFont.load_default()


def fit_lines(text: str, max_length: int, max_lines: int) -> list[str]:
    lines: list[str] = []
    normalized = re.sub(r"\s+", " ", text).strip()
    for line in textwrap.wrap(normalized, width=max_length, break_long_words=False):
        if len(lines) >= max_lines:
            break
        lines.append(line)
    return lines


def render_card(
    chart_path: Path,
    caption_path: Path,
    destination: Path,
    report: str,
    heading: str,
    gameweek: int,
    season: str,
    part: int,
) -> None:
    card = Image.new("RGB", (WIDTH, HEIGHT), "#07142B")
    painter = ImageDraw.Draw(card)
    for row in range(HEIGHT):
        shade = int(row * 22 / HEIGHT)
        painter.line((0, row, WIDTH, row), fill=(7 + shade // 4, 20 + shade // 3, 43 + shade))
    painter.rounded_rectangle((39, 36, 1041, 176), radius=28, fill="#122B4C")
    painter.text((70, 58), "FPL VORTEX  /  DATA-LED SHORTS", font=font(34, bold=True), fill="#74F4E8")
    painter.text((70, 112), f"PREMIER LEAGUE {season}  |  GAMEWEEK {gameweek}", font=font(28), fill="#D3E2F6")
    painter.text((47, 208), heading, font=font(58, bold=True), fill="#FFFFFF")
    painter.text(
        (48, 289),
        f"20 CLUBS  /  VIEW {part + 1} OF {SECTIONS_PER_REPORT}",
        font=font(32, bold=True),
        fill="#75F1EC",
    )
    panel = (43, 370, 1037, 1530)
    painter.rounded_rectangle(panel, radius=22, fill="#F4F2EE")
    with Image.open(chart_path) as image:
        chart = image.convert("RGB")
    available_width = panel[2] - panel[0] - 30
    available_height = panel[3] - panel[1] - 30
    # Retain the whole source width so club names, columns and badges cannot be cut off.
    image_height = max(1, round(chart.height * available_width / chart.width))
    chart = chart.resize((available_width, image_height), Image.Resampling.LANCZOS)
    if image_height > available_height:
        crop_start = round((image_height - available_height) * part / (SECTIONS_PER_REPORT - 1))
        visible = chart.crop((0, crop_start, available_width, crop_start + available_height))
    else:
        visible = chart
    target_y = panel[1] + 15 + (available_height - visible.height) // 2
    card.paste(visible, (panel[0] + 15, target_y))
    caption = caption_path.read_text(encoding="utf-8").strip()
    caption_lines = [
        line.strip()
        for line in caption.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    insight = caption_lines[min(part + 1, len(caption_lines) - 1)] if caption_lines else "Model-led Premier League statistics"
    painter.rounded_rectangle((43, 1561, 1037, 1794), radius=24, fill="#132C4B")
    painter.text((70, 1591), f"{report}  /  DATA SNAPSHOT", font=font(28, bold=True), fill="#74F4E8")
    for index, line in enumerate(fit_lines(insight, max_length=37, max_lines=3)):
        painter.text((70, 1646 + index * 42), line, font=font(34, bold=True), fill="#FFFFFF")
    painter.text((58, 1840), "FOLLOW FPL VORTEX FOR GAMEWEEK INTELLIGENCE", font=font(26), fill="#D3E2F6")
    destination.parent.mkdir(parents=True, exist_ok=True)
    card.save(destination, format="PNG", optimize=True)


def probe_video(path: Path) -> dict[str, Any]:
    completed = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height", "-show_entries", "format=duration",
         "-of", "json", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def normalize_drive_video(source: Path, destination: Path, duration: float) -> None:
    if not source.is_file() or source.stat().st_size == 0:
        raise RuntimeError(f"Required Google Drive intro/outro is unavailable: {source.name}")
    command(
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-stream_loop", "-1",
        "-i", str(source),
        "-t", str(duration),
        "-vf", f"fps={FPS},scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
               f"crop={WIDTH}:{HEIGHT},setsar=1,format=yuv420p",
        "-an", "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast",
        "-crf", "22", "-pix_fmt", "yuv420p", str(destination),
    )


def animate_still(source: Path, destination: Path) -> None:
    frame_count = math.ceil(CLIP_SECONDS * FPS)
    effect = (
        "zoompan=z='min(zoom+0.00042,1.06)':"
        "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"d={frame_count}:s={WIDTH}x{HEIGHT}:fps={FPS},"
        "setsar=1,format=yuv420p"
    )
    command(
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(source), "-vf", effect,
        "-frames:v", str(frame_count), "-r", str(FPS),
        "-an", "-c:v", "libx264", "-preset", "veryfast",
        "-crf", "21", "-pix_fmt", "yuv420p", str(destination),
    )


def assemble_video(clips: list[tuple[Path, float]], music: Path, final_path: Path) -> float:
    if not music.is_file() or music.stat().st_size < 1000:
        raise RuntimeError("Background_music.mp3 is required from Google Drive; refusing a silent Short")
    arguments = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
    for path, _ in clips:
        arguments += ["-i", str(path)]
    arguments += ["-stream_loop", "-1", "-i", str(music)]
    filters = [
        f"[{index}:v]fps={FPS},settb=AVTB,format=yuv420p[v{index}]"
        for index in range(len(clips))
    ]
    length = clips[0][1]
    latest = "v0"
    for index in range(1, len(clips)):
        next_name = f"cross{index}"
        offset = max(0, length - TRANSITION_SECONDS)
        filters.append(
            f"[{latest}][v{index}]xfade=transition=fade:"
            f"duration={TRANSITION_SECONDS:.2f}:offset={offset:.3f}[{next_name}]"
        )
        length = length + clips[index][1] - TRANSITION_SECONDS
        latest = next_name
    if length >= 59:
        raise RuntimeError(f"Short is {length:.1f}s; expected under 59 seconds")
    filters.append(f"[{latest}]format=yuv420p,setsar=1[video]")
    filters.append(
        f"[{len(clips)}:a]volume=0.16,"
        "afade=t=in:st=0:d=0.6,"
        f"afade=t=out:st={max(0, length - 0.9):.3f}:d=0.9,"
        f"atrim=duration={length:.3f},asetpts=PTS-STARTPTS[audio]"
    )
    arguments += [
        "-filter_complex", ";".join(filters),
        "-map", "[video]", "-map", "[audio]",
        "-t", f"{length:.3f}", "-r", str(FPS),
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
        "-movflags", "+faststart", str(final_path),
    ]
    command(*arguments)
    return length


def render() -> None:
    root = root_path()
    reports = read_report_metadata(root)
    season = str(reports["xG"]["season"])
    gameweek = int(reports["xG"]["gameweek"])
    frames = root / "shorts" / "frames"
    segments = root / "shorts" / "segments"
    frames.mkdir(parents=True, exist_ok=True)
    segments.mkdir(parents=True, exist_ok=True)
    assets = root / "source"
    intro = segments / "intro.mp4"
    outro = segments / "outro.mp4"
    normalize_drive_video(assets / "opening.mp4", intro, INTRO_SECONDS)
    normalize_drive_video(assets / "outro.mp4", outro, OUTRO_SECONDS)
    clips = [(intro, INTRO_SECONDS)]
    display_names = {
        "xG": "EXPECTED GOALS  /  xG",
        "DEFCON": "DEFENSIVE ACTIONS  /  DEFCON",
        "GAME_STATE": "GAME STATE  /  WIN-DRAW-LOSS",
    }
    for section in REPORTS:
        for part in range(SECTIONS_PER_REPORT):
            image_path = frames / f"{section.lower()}-{part}.png"
            video_path = segments / f"{section.lower()}-{part}.mp4"
            render_card(
                root / "output" / section / "1.png",
                root / "output" / section / "1.txt",
                image_path,
                section, display_names[section], gameweek, season, part,
            )
            animate_still(image_path, video_path)
            clips.append((video_path, CLIP_SECONDS))
    clips.append((outro, OUTRO_SECONDS))
    destination = root / "FPL_VORTEX_XG_DEFCON_GAME_STATE.mp4"
    planned_duration = assemble_video(clips, assets / "background.mp3", destination)
    if not destination.is_file() or destination.stat().st_size < 100_000:
        raise RuntimeError("Short export failed or generated an empty video")
    measured = probe_video(destination)
    video = (measured.get("streams") or [{}])[0]
    measured_duration = float((measured.get("format") or {}).get("duration", 0))
    if (video.get("width"), video.get("height")) != (WIDTH, HEIGHT):
        raise RuntimeError(f"Invalid Shorts aspect ratio: {video}")
    if not (10 <= measured_duration < 59):
        raise RuntimeError(f"Invalid Shorts duration: {measured_duration}s")
    info = {
        "format": "youtube_shorts", "orientation": "9:16",
        "width": WIDTH, "height": HEIGHT, "duration_seconds": measured_duration,
        "estimated_duration_seconds": planned_duration,
        "music_source": "Google Drive: Background_music.mp3",
        "intro_source": "Google Drive: opening.mp4",
        "outro_source": "Google Drive: outro.mp4",
        "voiceover": False,
        "gameweek": gameweek,
        "season": season,
        "sections": list(REPORTS),
    }
    (root / "shorts_manifest.json").write_text(
        json.dumps(info, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"[XG-DEFCON] 9:16 animated Short ready: {measured_duration:.1f}s, music only, 3 reports.")


if __name__ == "__main__":
    render()
