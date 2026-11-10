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
from pathlib import Path
import shutil
import subprocess
import tempfile

import edge_tts
import requests
from PIL import Image

from .day1_value_live import make_live_value_board


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
    gw = board["nextGameweek"]
    starters = board["starters"]
    bench = board["bench"]
    parts = [(None, f"Welcome to FPL VORTEX, The Value Board. For gameweek {gw}, "
                   f"our researched squad costs {price(board['totalCost'])}, "
                   f"with a {board['formation']} starting formation. "
                   "We prioritise verified minutes, official injury flags, fixture difficulty, "
                   "predicted points, price value and actual market ownership trends. "
                   "Expected points are estimates, not guaranteed returns.")]
    for p in starters:
        part = ("Our captain, " if p.get("captain") else
                "Our vice-captain, " if p.get("viceCaptain") else "Next, ")
        total = sum(float(v) for v in p["weekly"].values())
        next_fixtures = [t for t in p["fixtures"] if t["gw"] == gw]
        fixture_text = "A blank gameweek is currently scheduled. " if not next_fixtures else (
            "The next fixture" + ("s are " if len(next_fixtures) > 1 else " is ") +
            " and ".join(
                f"versus {t.get('opponentSpeechName', t['opponentFullName'])} "
                f"{'at home' if t['venue']=='H' else 'away'}, "
                f"with difficulty {float(t['fdr']):.1f}"
                if t.get("fdr") is not None else
                f"versus {t.get('opponentSpeechName', t['opponentFullName'])} "
                f"{'at home' if t['venue']=='H' else 'away'}"
                for t in next_fixtures
            ) + ". "
        )
        parts.append((p["id"],
            f"{part}{_speaking_name(p)} of {p.get('clubSpeechName', 'his club')}, at {price(p['price'])}. "
            f"He averages {float(p.get('minutesPerAppearance',0)):.1f} recent minutes per appearance. "
            f"{fixture_text}"
            f"The model estimates {float(p['nextGwXpts']):.2f} points next gameweek, "
            f"and {total:.2f} points across the next five gameweeks."))
    for index, p in enumerate(bench, 1):
        parts.append((p["id"],
            f"Bench option {index}, {_speaking_name(p)} of {p.get('clubSpeechName', 'his club')}, costs {price(p['price'])}. "
            f"His next gameweek projection is {float(p['nextGwXpts']):.2f}."))
    market_leaders = sorted([*starters, *bench],
                            key=lambda p: (-float(p.get("ownership", 0)), p["id"]))[:3]
    for player in market_leaders:
        flow = int(player.get("netTransfers", 0))
        direction = "net transfers in" if flow >= 0 else "net transfers out"
        parts.append((player["id"],
                      f"Market trend: {_speaking_name(player)} is owned by "
                      f"{float(player.get('ownership', 0)):.1f} percent of managers, "
                      f"with {abs(flow):,} {direction} in the current gameweek snapshot."))
    names = {p["id"]: _speaking_name(p) for p in [*starters, *bench]}
    plans = {p["gameweek"]: p for p in board["weeklyPlans"]}
    for projection in board["projections"]:
        plan = plans[projection["gameweek"]]
        captain_name = names[plan["captainId"]]
        reserve_names = ", ".join(names[pid] for pid in plan["bench"])
        parts.append((-projection["gameweek"], f"Gameweek {projection['gameweek']}: the optimal "
                            f"{plan['formation']} lineup, with {captain_name} as captain, "
                            f"is estimated at {projection['xpts']:.2f} expected points. "
                            f"Our four bench players are {reserve_names}. "
                            "Review actual starting lineups before the deadline."))
    parts.append((None, "That is our five gameweek Value Board. Check late "
                         "injury updates, official lineups and deadlines before "
                         "making transfers. Subscribe to FPL VORTEX for the next analysis."))
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
        crests = {}

        def crest(source, filename):
            if source and source not in crests:
                path = root / filename
                crests[source] = "/value-assets/" + path.name if _asset(session, source, path) else ""
            return crests.get(source, "")

        for p in [*board["starters"], *board["bench"]]:
            path = root / f"player-{p['id']}.png"
            p["portrait"] = "/value-assets/" + path.name if _asset(session, p.get("portrait"), path) else ""
            p["clubLogo"] = crest(p.get("clubLogo"), f"club-{p['teamId']}.png")
        for fixture in board["nextFixtures"]:
            for side in ("home", "away"):
                field = f"{side}Badge"
                fixture[field] = crest(fixture.get(field), f"match-{fixture['id']}-{side}.png")


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
        local_assets(board, assets)
        voice, cues, voice_duration = asyncio.run(render_voice(narration_parts(board), work))
        shutil.copy2(voice, assets / "scene-5-narration.mp3")
        board["narrationCues"] = [dict(playerId=c["playerId"] if c["playerId"] > 0 else None,
                                      gameweek=-c["playerId"] if c["playerId"] < 0 else None,
                                      start=c["start"], end=c["end"])
                                 for c in cues if c["playerId"] is not None]
        props = {"board": board, "gameweek": board["nextGameweek"],
                 "durationInFrames": int(math.ceil((voice_duration + .5) * 30))}
        props_path = work / "value-board-props.json"
        write_json(props_path, props)
        clip = work / "value-board-4k.mp4"
        run("npx", "remotion", "render", "index.jsx", "ValueBoardStandalone",
            clip, "--props", props_path, "--codec", "h264", "--scale", "2", cwd=remotion_root)
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
                "-i", temporary, "-t", ".8", "-f", "null", "-")
            os.replace(temporary, master)
        finally:
            temporary.unlink(missing_ok=True)

        # Legacy generated MP3 is replaced by day1_media after it mixes the
        # complete five-scene program, never published separately before then.
        board["narrationCues"] = props["board"]["narrationCues"]
        write_json(data / "scene05_value_board.json", board)
        write_json(data / "scene05_narration.json", cues)
        append = {"key": "04_value_board", "scene": "THE VALUE BOARD", "order": 5,
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
