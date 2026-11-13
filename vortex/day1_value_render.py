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
    # Full official names; abbreviations such as BHA never enter spoken text.
    name = player.get("fullName") or player.get("name")
    return name.strip()


def narration_parts(board):
    def price(value):
        return f"{float(value):.1f} million pounds"

    starters = board["starters"]
    bench = board["bench"]
    players = {p["id"]: p for p in [*starters, *bench]}
    captain = next(p for p in starters if p["captain"])
    vice = next(p for p in starters if p["viceCaptain"])
    first_sub = next(p for p in bench if p["position"] != "GK")
    budget = min((p for p in starters if p["position"] != "GK"),
                 key=lambda p: (p["price"], -p["nextGwXpts"], p["id"]))
    formation = " ".join(board["formation"].split("-"))
    parts = [(None, f"The Value Board comes in at {price(board['totalCost'])}, with "
                   f"{price(board['bank'])} left from the model squad budget. "
                   f"I'd set up in a {formation}. The full squad and bench order are on the board."),
             (budget["id"], f"{_speaking_name(budget)} is the cheapest outfield starter here, at "
                            f"{price(budget['price'])}. That keeps more of the budget available for "
                            "the positions where I'd back a player to start and contribute most weeks. "
                            "For a cheaper pick, I want to see how often the planner actually starts them."),
             (captain["id"], f"I'd captain {_speaking_name(captain)}. The model gives this pick "
                             "the strongest points projection in the starting eleven. If the team "
                             "update puts those minutes in doubt, I'd revisit the armband."),
             (vice["id"], f"{_speaking_name(vice)} is my vice-captain. If the captain doesn't play "
                          "at all, the vice gets double points provided they play."),
             (first_sub["id"], f"First outfield substitute is {_speaking_name(first_sub)}. "
                               "Bench order matters, and an automatic change still has to leave a legal formation.")]
    plans = board["weeklyPlans"]
    projections = {p["gameweek"]: p["xpts"] for p in board["projections"]}
    first = plans[0]
    biggest = max(plans[1:], key=lambda plan: (
        len(set(first["starters"]) - set(plan["starters"])),
        plan["captainId"] != first["captainId"],
        plan["formation"] != first["formation"],
        -plan["gameweek"],
    ), default=first)
    for plan in plans:
        gw = plan["gameweek"]
        if plan is first:
            line = f"Gameweek {gw} is the starting point. Watch how the lineup changes across the run."
        elif plan is biggest:
            swaps = len(set(first["starters"]) - set(plan["starters"]))
            new_captain = plan["captainId"] != first["captainId"]
            if swaps:
                line = (f"Gameweek {gw} has the biggest change, with {swaps} "
                        f"starting {'spot' if swaps == 1 else 'spots'} changing from the opening lineup.")
            else:
                line = f"The starting eleven holds in Gameweek {gw}."
            if swaps == 0 and not new_captain:
                line += " I’d keep the same captain if the team news stays clear."
            if new_captain:
                line += f" The armband switches to {_speaking_name(players[plan['captainId']])}."
            line += " That’s the week I’d check again before locking the plan."
        else:
            previous = projections[gw - 1]
            projected = projections[gw]
            if projected > previous:
                line = f"The team projection rises in Gameweek {gw}."
            elif projected < previous:
                line = f"Gameweek {gw} looks a little tougher for this squad."
            else:
                line = f"The projected team return holds steady in Gameweek {gw}."
        parts.append((-gw, line))
    parts.append((None, "My call is to roll if the current squad has cover. I'd use a free transfer "
                        "if the team update rules out a starter and the replacement fits your squad and budget."))
    parts.append((None, f"Which spot in your squad would you use a transfer on this week? Tell me the "
                        "position you're weighing up in the comments. I'll be back with the next "
                        f"Fantasy Premier League Vortex update before the Gameweek {board['nextGameweek']} deadline."))
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
    with requests.Session() as session:
        for p in [*board["starters"], *board["bench"]]:
            for field, prefix in (("portrait", "player"), ("clubLogo", "club")):
                path = root / f"{prefix}-{p['id']}.png"
                if _asset(session, p.get(field), path):
                    p[field] = "/value-assets/" + path.name
                else:
                    p[field] = ""


def _check_previous_program(qa, review, board):
    expected = ["00_intro", "gw_review", "02_fdr", "03_projected_goals"]
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
        if before_seconds + voice_duration + .55 > DAY1_MAX_EXPORT_SECONDS:
            raise RuntimeError(
                f"Day 1 narration and first four scenes exceed the {DAY1_MAX_EXPORT_SECONDS:.0f}s export limit"
            )
        local_assets(board, assets)
        shutil.copy2(voice, assets / "scene-5-narration.mp3")
        board["narrationCues"] = [dict(playerId=c["playerId"] if c["playerId"] > 0 else None,
                                      gameweek=-c["playerId"] if c["playerId"] < 0 else None,
                                      start=c["start"], end=c["end"])
                                 for c in cues if c["playerId"] is not None]
        props = {"board": board, "gameweek": board["nextGameweek"],
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
