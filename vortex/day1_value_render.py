"""Build, narrate and append genuine Scene 05 to the freshly rendered Day 1 master.

The first four scenes are NOT regenerated or removed by the data layer: their
actual completed program clip is carried through the splice. Never silently
reuse previous-episode video assets. Output may be published only after QA.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import re
from pathlib import Path
import shutil
import subprocess
import tempfile

import edge_tts
import requests
from PIL import Image

from .day1_value_live import make_live_value_board
from .day1_final_scenes import SCENE_KEYS
from .youtube_studio_package import DAY1_MAX_EXPORT_SECONDS


def run(*args, cwd=None):
    process = subprocess.run([str(x) for x in args], capture_output=True, text=True, cwd=cwd)
    if process.returncode:
        raise RuntimeError(f"{args[0]} failed: {process.stderr[-3500:]}")
    return process.stdout


def probe(path):
    return json.loads(run("ffprobe", "-v", "error", "-show_format",
                          "-show_streams", "-of", "json", path))


def duration(path):
    value = float(probe(path).get("format", {}).get("duration") or 0)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"Invalid media duration: {path}")
    return value


def video_size(path):
    tracks = [s for s in probe(path)["streams"] if s.get("codec_type") == "video"]
    if len(tracks) != 1:
        raise ValueError(f"Expected one video track: {path}")
    return int(tracks[0]["width"]), int(tracks[0]["height"])


def write_json(path, payload):
    tmp = path.with_name("." + path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _speaking_name(player):
    return re.sub(r"^[A-Za-z]\.\s*", "", player["name"].strip())


SCENE_LIMIT_SECONDS = 120


def narration_parts(board, *, compact=False):
    def price(value):
        return f"{float(value):.1f} million pounds"

    starters = board["starters"]
    players = [*starters, *board["bench"]]
    captain = next(p for p in starters if p["captain"])
    gameweek = board["nextGameweek"]
    parts = [(None, f"Here’s the recommended Gameweek {gameweek} squad, at {price(board['totalCost'])}.")]
    changes = board.get("selectionChanges", {})
    removed, added = changes.get("omitted", []), changes.get("added", [])
    if removed and added and board.get("preferredCost", 0) and board["preferredCost"] > board["budget"]:
        parts.append((None, "To stay within budget, "
                            f"the model adds {' and '.join(added)} and leaves out {' and '.join(removed)}."))
    for position in ("GK", "DEF", "MID", "FWD"):
        picks = [p for p in players if p["position"] == position]
        for index, player in enumerate(picks):
            name = _speaking_name(player)
            stats = player.get("heroStats", {})
            points = player["nextGwXpts"]
            if position == "GK":
                if index == 0:
                    line = f"{name} starts in goal, projected at {points:.1f} points."
                else:
                    line = f"{name} is the playing reserve at {price(player['price'])}."
            elif position == "DEF":
                actions = stats.get("defensiveActions90")
                hits, games = stats.get("defconHits"), stats.get("defconAppearances")
                if hits is not None and games and not compact:
                    patterns = (
                        "{name} reached the mark in {hits} of {games} tracked appearances.",
                        "For {name}, it was {hits} from {games}.",
                        "{name} qualified {hits} times across {games} appearances.",
                        "{name} hit ten actions in {hits} of {games}.",
                        "{name} earned those points in {hits} of {games} tracked appearances.",
                    )
                    line = patterns[index].format(name=name, hits=hits, games=games)
                elif actions is not None:
                    line = f"{name} averages {actions:.1f} defensive actions per ninety."
                else:
                    line = f"{name} projects at {points:.1f} points."
                if index == 0:
                    line = "Defenders earn two points for ten defensive actions in a match. " + line
            elif player["id"] == captain["id"]:
                line = f"{name} takes the armband, at {points:.1f} projected points."
            else:
                keys = ("xa90", "xg90") if position == "MID" else ("xg90", "goals90")
                key = keys[index % 2]
                amount = stats.get(key)
                wording = {"xa90": "expected assists", "xg90": "expected goals", "goals90": "goals"}
                line = (f"{name} averages {amount:.2f} {wording[key]} per ninety."
                        if amount is not None and not compact else f"{name} projects at {points:.1f}.")
            parts.append((player["id"], line))
    parts.append((None, "See you in the next video, where I will analyze transfer options "
                        f"before the Gameweek {gameweek} deadline."))
    return parts


async def render_voice(parts, work):
    pieces, times, elapsed = [], [], 0.0
    for index, (player_id, text) in enumerate(parts):
        target = work / f"voice-{index:02d}.mp3"
        voice = edge_tts.Communicate(text, voice="en-GB-RyanNeural", rate="+0%")
        await voice.save(str(target))
        seconds = duration(target)
        pieces.append(target)
        times.append({"playerId": player_id, "start": round(elapsed, 3),
                      "end": round(elapsed + seconds, 3), "text": text})
        elapsed += seconds
    playlist = work / "voices.txt"
    playlist.write_text("".join("file '" + p.as_posix().replace("'", "'\\''") + "'\n" for p in pieces))
    audio = work / "scene-5-narration.mp3"
    run("ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "concat", "-safe", "0", "-i", playlist, "-ar", "48000",
        "-c:a", "libmp3lame", "-q:a", "3", audio)
    total = duration(audio)
    if abs(total-elapsed) > max(0.4, 0.02 * elapsed):
        raise RuntimeError("Ryan narration concat timing drift exceeds safe tolerance")
    return audio, times, total


def _asset(session, source, destination):
    if not source:
        return None
    try:
        r = session.get(source, timeout=12)
        r.raise_for_status()
        if len(r.content) > 3_000_000 or not r.content:
            return None
        from io import BytesIO
        with Image.open(BytesIO(r.content)) as raw:
            pic = raw.convert("RGBA")
            if pic.width < 24 or pic.height < 24:
                return None
            pic = pic.crop(pic.getbbox())
            pic.thumbnail((512, 512), Image.Resampling.LANCZOS)
            pic.save(destination, format="PNG")
        return destination
    except (requests.RequestException, OSError, ValueError):
        return None


def local_assets(board, root):
    if root.name != "value-assets" or root.parent.name != "public":
        raise ValueError("Refusing to clean assets outside the Scene 05 public cache")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    original = Path(os.environ.get("DAY1_LOGO_FILE", "/content/drive/MyDrive/elements/logo.png"))
    if not original.is_file():
        raise FileNotFoundError(f"Approved original FPL VORTEX logo missing: {original}")
    with Image.open(original) as img:
        img.convert("RGBA").save(root / "original-logo.png", format="PNG")
    league = original.with_name("pl.png")
    if not league.is_file():
        league = next(Path("/content/drive/MyDrive").rglob("pl.png"), league)
    if league.is_file():
        with Image.open(league) as img:
            rgba = img.convert("RGBA")
            if rgba.getchannel("A").getextrema()[0] < 255:
                alpha = rgba.getchannel("A")
                rgba = Image.new("RGBA", rgba.size, "white")
                rgba.putalpha(alpha)
            rgba.crop(rgba.getbbox()).save(root / "league-logo.png")
        board["leagueLogo"] = "value-assets/league-logo.png"

    with requests.Session() as session:
        for player in [*board["starters"], *board["bench"]]:
            portrait = root / f"player-{player['id']}.png"
            code = player.get("photoCode")
            base = "https://resources.premierleague.com"
            sources = [
                f"{base}/premierleague25/photos/players/500x500/{code}.png",
                f"{base}/premierleague25/photos/players/250x250/{code}.png",
                f"{base}/premierleague/photos/players/250x250/p{code}.png",
                f"{base}/premierleague/photos/players/110x140/p{code}.png",
            ] if code else []
            if player.get("portrait"):
                sources.append(player["portrait"])
            player["portrait"] = ("/value-assets/" + portrait.name if
                any(_asset(session, source, portrait) for source in sources) else "")
            crest = root / f"club-{player['teamId']}.png"
            player["clubLogo"] = ("/value-assets/" + crest.name if
                crest.is_file() or _asset(session, player.get("clubLogo"), crest) else "")


def _check_previous_program(qa, review, board):
    expected = list(SCENE_KEYS[:-1])
    if qa.get("passed") is not True or qa.get("scene_keys") != expected:
        raise RuntimeError(f"Expected four verified original scenes before Scene 05, found {qa.get('scene_keys')}")
    actual_review_gw = int(review.get("gw") or 0)
    if actual_review_gw + 1 != board["nextGameweek"]:
        raise RuntimeError("Live FPL Scene 05 gameweek differs from original program review")
    if str(review.get("status") or "").upper() not in {"FINAL", "COMPLETE"}:
        raise RuntimeError("Five-scene premium build requires finalized review")
    if qa.get("external_media_integration", {}).get("applied"):
        raise RuntimeError("Scene 05 must be inserted before external background music integration")


def integrate(output_root, *, remotion_root):
    root = Path(output_root)
    data = root / "DATA"
    mp4_dir = root / "MP4"
    mp3_dir = root / "MP3"
    qa_file = data / "final_video_qa.json"
    qa = json.loads(qa_file.read_text())
    review = json.loads((data / "gw_review_package.json").read_text())
    board = make_live_value_board()
    _check_previous_program(qa, review, board)
    originals = sorted(mp4_dir.glob("*COMBINED*.mp4"))
    audios = sorted(mp3_dir.glob("*COMBINED*.mp3"))
    if len(originals) != 1 or len(audios) != 1:
        raise RuntimeError("Missing or ambiguous current-run four-scene combined master")
    master = originals[0]
    if video_size(master) != (3840, 2160):
        raise RuntimeError("Canonical first-four-scene program is not true 3840x2160")
    before_seconds = duration(master)
    with tempfile.TemporaryDirectory(prefix="vortex-scene5-") as staging:
        work = Path(staging)
        public = remotion_root / "public"
        assets = public / "value-assets"
        parts = narration_parts(board)
        if any(not line.strip() or re.search(r"\(xxx\)|\[MISSING DATA:", line, re.I)
               for _, line in parts):
            raise RuntimeError("Unresolved or empty Scene 05 narration")
        voice, cues, voice_duration = asyncio.run(render_voice(parts, work))
        scene_limit = min(SCENE_LIMIT_SECONDS, DAY1_MAX_EXPORT_SECONDS - before_seconds)
        if voice_duration + .55 >= scene_limit:
            voice, cues, voice_duration = asyncio.run(render_voice(narration_parts(board, compact=True), work))
        if voice_duration + .55 >= scene_limit:
            raise RuntimeError(
                f"Scene 05 exceeds its {scene_limit:.1f}s remaining export allowance"
            )
        local_assets(board, assets)
        shutil.copy2(voice, assets / "scene-5-narration.mp3")
        board["narrationCues"] = [dict(playerId=c["playerId"], start=c["start"], end=c["end"])
                                 for c in cues if c["playerId"] is not None]
        props = {"board": board,
                 "durationInFrames": int(math.ceil((voice_duration + .5) * 30))}
        props_path = work / "value-board-props.json"
        write_json(props_path, props)
        clip_1080 = work / "value-board-1080.mp4"
        run("npx", "remotion", "render", "index.jsx", "ValueBoardStandalone",
            clip_1080, "--props", props_path, "--codec", "h264", cwd=remotion_root)
        clip = work / "value-board-4k.mp4"
        run("ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", clip_1080, "-vf", "scale=3840:2160:flags=lanczos,setsar=1",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
            "-ar", "48000", "-movflags", "+faststart", clip)
        if video_size(clip) != (3840, 2160):
            raise RuntimeError("Scene 05 video dimensions invalid")
        scene_duration = duration(clip)
        run("ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", "1",
            "-i", clip, "-frames:v", "1", root / "SLIDE" / "scene05_value_board.png")
        temporary = mp4_dir / (".five-scene-" + master.name)
        try:
            run("ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-i", master, "-i", clip, "-filter_complex",
                "[0:v]fps=30,scale=3840:2160,setsar=1,format=yuv420p[v0];"
                "[1:v]fps=30,scale=3840:2160,setsar=1,format=yuv420p[v1];"
                "[0:a]aresample=48000,aformat=channel_layouts=stereo[a0];"
                "[1:a]aresample=48000,aformat=channel_layouts=stereo[a1];"
                "[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]",
                "-map", "[v]", "-map", "[a]", "-c:v", "libx264",
                "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                "-movflags", "+faststart", temporary)
            measured = duration(temporary)
            if video_size(temporary) != (3840, 2160):
                raise RuntimeError("Combined five-scene master is not 4K")
            if abs(measured - (before_seconds + scene_duration)) > .5:
                raise RuntimeError("Five-scene duration mismatch")
            # Perform video+audio decoding, not simply a file existence check.
            run("ffmpeg", "-hide_banner", "-loglevel", "error", "-sseof", "-1",
                "-i", temporary, "-t", "0.8", "-f", "null", "-")
            os.replace(temporary, master)
        finally:
            temporary.unlink(missing_ok=True)

        # Legacy generated MP3 is replaced by day1_media after it mixes the
        # complete five-scene program, never published separately before then.
        board["narrationCues"] = props["board"]["narrationCues"]
        write_json(data / "scene05_value_board.json", board)
        write_json(data / "scene05_narration.json", cues)
        append = {"key": "04_value_board", "scene": "THE VALUE BOARD",
                  "duration": scene_duration, "start_seconds": before_seconds}
        qa.setdefault("sections", []).append(append)
        qa["scene_keys"].append("04_value_board")
        qa.setdefault("scene_order", []).append("THE VALUE BOARD")
        qa["scene_count"] = len(qa["scene_keys"])
        qa["expected_duration"] = measured
        qa["final_duration"] = measured
        qa["duration_delta"] = 0.0
        qa["scene05_verified"] = {
            "source": board["dataOrigin"], "market_snapshot_utc": board["marketSnapshotUTC"],
            "gw": board["nextGameweek"], "squad": 15, "start_xi": 11,
            "bench": 4, "budget": board["totalCost"],
            "video_seconds": scene_duration, "narration_seconds": voice_duration,
            "generation_method": board["method"],
            "frame_size": [3840, 2160],
            "sha256": hashlib.sha256(master.read_bytes()).hexdigest(),
        }
        write_json(qa_file, qa)
        print(f"[SCENE 05] PASS: GW{board['nextGameweek']}, £{board['totalCost']:.1f}m, 15 players, {measured:.2f}s combined")
        return qa["scene05_verified"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", default="/content/drive/MyDrive/FPL_VORTEX/FIRST VIDEO")
    parser.add_argument("--remotion-root", default="tools/day1-broadcast")
    args = parser.parse_args()
    integrate(args.output_root, remotion_root=Path(args.remotion_root).resolve())


if __name__ == "__main__":
    main()
