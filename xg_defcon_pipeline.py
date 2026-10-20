from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

NOTEBOOK_ID = "1s_K8Cvdck5JrpoljjgQnWOtBXq49n9kR"
NOTEBOOK_EXECUTABLE_SHA256 = "c26ab9d7cd406200962e4d01613b01e9530c43a4c31e5f4614649d80f7441318"
LOGO_ID = "17RWQXfSOrrCpMt9JbXz6z1J94JSaPQ2Z"
REPORTS = ("xG", "DEFCON", "GAME_STATE")


def required_env(name: str) -> str:
    value = (os.environ.get(name) or "").strip()
    if not value:
        raise RuntimeError(f"Required GitHub secret is missing: {name}")
    return value


def run_command(command: list[str], *, env: dict[str, str] | None = None) -> None:
    subprocess.run(command, check=True, env=env)


def root_path() -> Path:
    value = (os.environ.get("XG_DEFCON_ROOT") or "").strip()
    if not value:
        raise RuntimeError("XG_DEFCON_ROOT must point to isolated runner storage")
    path = Path(value).resolve()
    if path == Path("/") or path == Path.home().resolve():
        raise RuntimeError(f"Unsafe output location: {path}")
    return path


def verified_notebook(path: Path) -> dict[str, Any]:
    # Outputs and execution metadata change whenever Colab saves; pin executable code instead.
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        cells = document["cells"]
        if not isinstance(cells, list) or len(cells) != 12:
            raise ValueError("Expected the reviewed 12-cell notebook")
        executable_cells = (3, 5, 7, 9)
        sources: list[str] = []
        for index in executable_cells:
            cell = cells[index]
            if cell.get("cell_type") != "code":
                raise ValueError(f"Cell {index} is not executable code")
            source = cell.get("source")
            if not isinstance(source, (list, str)):
                raise ValueError(f"Cell {index} source has an invalid type")
            sources.append("".join(source) if isinstance(source, list) else source)
        digest = hashlib.sha256("".join(sources).encode("utf-8")).hexdigest()
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Google Drive notebook cannot be validated: {error}") from error
    if digest != NOTEBOOK_EXECUTABLE_SHA256:
        raise RuntimeError(
            "Google Drive notebook executable cells changed; refusing unreviewed code. "
            f"Expected SHA256={NOTEBOOK_EXECUTABLE_SHA256}; received SHA256={digest}. "
            "Review the notebook code and update this pin only after verification."
        )
    return document


def prepare() -> None:
    root = root_path()
    source = root / "source"
    output = root / "output"
    source.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    client_id = required_env("GOOGLE_OAUTH_CLIENT_ID")
    client_secret = required_env("GOOGLE_OAUTH_CLIENT_SECRET")
    refresh_token = required_env("GOOGLE_OAUTH_REFRESH_TOKEN")
    if not client_id.endswith(".apps.googleusercontent.com"):
        raise RuntimeError("Invalid Google OAuth client ID")
    body = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }).encode("utf-8")
    request = urllib.request.Request(
        "https://oauth2.googleapis.com/token", data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST"
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        token_response = json.loads(response.read().decode("utf-8"))
    token = {
        "access_token": token_response["access_token"],
        "token_type": token_response.get("token_type", "Bearer"),
        "refresh_token": refresh_token,
        "expiry": (datetime.now(timezone.utc) + timedelta(
            seconds=max(60, int(token_response.get("expires_in", 3600)) - 60)
        )).isoformat().replace("+00:00", "Z"),
    }
    config = source / "rclone.conf"
    config.write_text("\n".join([
        "[xg-defcon-drive]", "type = drive",
        f"client_id = {client_id}", f"client_secret = {client_secret}",
        "scope = drive", "token = " + json.dumps(token, separators=(",", ":")),
        "", "[xg-defcon-assets]", "type = drive",
        f"client_id = {client_id}", f"client_secret = {client_secret}",
        "scope = drive", "token = " + json.dumps(token, separators=(",", ":")),
        "root_folder_id = 1h3Loznr5RnsMyh-kUd-zMxEgOf98uFSt", "",
    ]), encoding="utf-8")
    config.chmod(0o600)
    environment = dict(os.environ, RCLONE_CONFIG=str(config))
    notebook = source / "notebook.ipynb"
    run_command([
        "rclone", "backend", "copyid", "xg-defcon-drive:", NOTEBOOK_ID, str(notebook)
    ], env=environment)
    verified_notebook(notebook)
    print("[XG-DEFCON] Notebook executable SHA256 verified; Colab outputs excluded.")
    logo = source / "brand-logo.png"
    run_command([
        "rclone", "backend", "copyid", "xg-defcon-drive:", LOGO_ID, str(logo)
    ], env=environment)
    if not logo.is_file() or logo.stat().st_size < 100:
        raise RuntimeError("Branded logo could not be restored from Google Drive")
    for asset_name in ("gamestate_match_cache", "fpl_event_data"):
        remote = f"xg-defcon-drive:FPL_xG_Mix/_assets/{asset_name}"
        local = output / "_assets" / asset_name
        check = subprocess.run([
            "rclone", "lsf", remote, "--max-depth", "1"
        ], env=environment, capture_output=True, text=True)
        if check.returncode == 0:
            local.mkdir(parents=True, exist_ok=True)
            run_command(["rclone", "copy", remote, str(local), "--transfers", "4"], env=environment)
        else:
            print(f"[XG-DEFCON] Optional archive is unavailable: {asset_name}")
    music_remote = "xg-defcon-assets:Background_music.mp3"
    music_check = subprocess.run([
        "rclone", "lsf", music_remote
    ], env=environment, capture_output=True, text=True)
    if music_check.returncode == 0:
        run_command([
            "rclone", "copyto", music_remote, str(source / "background.mp3")
        ], env=environment)
    # Load the established FPL VORTEX assets, without modifying any Google Drive files.
    media_files = {
        "opening.mp4": "1KlxpGOUrC-2-rNMZINuZWbfL05nQj0U-",
        "outro.mp4": "1M4w9Adk1H9xsVLQHCIcf6HdUn4XOqPmg",
        "background.mp3": "1Vmwc1Qlvx1Vi1DHJ3BEOzbqG8oOUusXW",
    }
    for filename, file_id in media_files.items():
        destination = source / filename
        run_command(
            ["rclone", "backend", "copyid", "xg-defcon-drive:", file_id, str(destination)],
            env=environment,
        )
        if not destination.is_file() or destination.stat().st_size < 1000:
            raise RuntimeError(f"Required Google Drive media is missing: {filename}")
    config.unlink(missing_ok=True)
    print("[XG-DEFCON] Pinned notebook, logo, intro/outro and licensed music assets restored.")


def read_report_metadata(root: Path) -> dict[str, Any]:
    output = root / "output"
    metas: dict[str, dict[str, Any]] = {}
    from PIL import Image
    for report in REPORTS:
        folder = output / report
        image_path = folder / "1.png"
        caption_path = folder / "1.txt"
        metadata_path = folder / "1.metadata.json"
        for required in (image_path, caption_path, metadata_path):
            if not required.is_file() or required.stat().st_size == 0:
                raise RuntimeError(f"Missing complete, fresh {report} deliverable: {required}")
        with Image.open(image_path) as picture:
            picture.verify()
        with Image.open(image_path) as picture:
            if picture.width < 1920 or picture.height < 1080:
                raise RuntimeError(f"{report} report is too small for a public YouTube video")
        meta = json.loads(metadata_path.read_text(encoding="utf-8"))
        if int(meta.get("team_count", -1)) != 20:
            raise RuntimeError(f"{report} is missing a complete 20-team report")
        # The official FPL API can flag a fully completed gameweek as provisional.
        # Publish only with visible provisional disclosure; other fixture checks remain mandatory.
        if not isinstance(meta.get("provisional"), bool):
            raise RuntimeError(f"{report} is missing its official provisional-data indicator")
        if int(meta.get("gameweek", 0)) < 1:
            raise RuntimeError(f"{report} has no completed gameweek")
        if not caption_path.read_text(encoding="utf-8").strip():
            raise RuntimeError(f"{report} matching caption is empty")
        metas[report] = meta
    values = {(entry["gameweek"], entry["season"]) for entry in metas.values()}
    if len(values) != 1:
        raise RuntimeError("The three reports refer to different gameweeks/seasons")
    if not metas["xG"].get("source_cutoff_verified"):
        raise RuntimeError("xG source cutoff is not verified against FPL")
    game_state = metas["GAME_STATE"]
    if int(game_state.get("verified_fixture_count", -1)) != int(game_state.get("fixture_count", -2)):
        raise RuntimeError("GAME_STATE does not validate every finished fixture")
    return metas


def execute_notebook() -> None:
    root = root_path()
    notebook = root / "source" / "notebook.ipynb"
    document = verified_notebook(notebook)
    cells = document.get("cells")
    if not isinstance(cells, list) or len(cells) < 10:
        raise RuntimeError("Notebook cell structure is invalid")
    for index in (3, 5, 7, 9):
        if cells[index].get("cell_type") != "code":
            raise RuntimeError(f"Expected notebook code cell {index}")
    output = root / "output"
    output.mkdir(parents=True, exist_ok=True)
    namespace: dict[str, Any] = {"__name__": "__main__"}
    previous_directory = Path.cwd()
    previous_argv = sys.argv
    try:
        os.chdir(output)
        sys.argv = ["xg-defcon-notebook"]
        for index in (3, 5, 7, 9):
            source = cells[index].get("source") or []
            code = "".join(source) if isinstance(source, list) else str(source)
            if index == 3:
                exec(compile(code, f"notebook:cell-{index}", "exec"), namespace)
                namespace["DEFAULT_LOGO"] = str(root / "source" / "brand-logo.png")
            else:
                exec(compile(code, f"notebook:cell-{index}", "exec"), namespace)
    finally:
        sys.argv = previous_argv
        os.chdir(previous_directory)
    metas = read_report_metadata(root)
    print(f"[XG-DEFCON] All three official reports validated for GW{metas['xG']['gameweek']}.")


def render_video() -> None:
    from PIL import Image, ImageDraw, ImageFont
    root = root_path()
    metas = read_report_metadata(root)
    frames = root / "frames"
    frames.mkdir(parents=True, exist_ok=True)
    season = str(metas["xG"]["season"])
    gameweek = int(metas["xG"]["gameweek"])
    try:
        title_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 42)
        subtitle_font = ImageFont.truetype("DejaVuSans.ttf", 26)
    except OSError:
        title_font = ImageFont.load_default()
        subtitle_font = ImageFont.load_default()
    segments = [
        ("xG", "EXPECTED GOALS: CLUB BY CLUB"),
        ("DEFCON", "DEFCON: DEFENSIVE CONTRIBUTIONS"),
        ("GAME_STATE", "GAME STATE: TIME WINNING / DRAWING / LOSING"),
    ]
    duration_per_frame = 9
    manifest_lines = ["ffconcat version 1.0"]
    frame_files: list[Path] = []
    for section, heading in segments:
        with Image.open(root / "output" / section / "1.png") as picture:
            image = picture.convert("RGB")
        resized_height = max(1, round(image.height * 1810 / image.width))
        image = image.resize((1810, resized_height), Image.Resampling.LANCZOS)
        usable_height = 820
        for index, part in enumerate(("TOP", "MIDDLE", "BOTTOM")):
            canvas = Image.new("RGB", (1920, 1080), "#09172F")
            draw = ImageDraw.Draw(canvas)
            draw.text((55, 27), f"FPL VORTEX   |   {heading}", fill="#FFFFFF", font=title_font)
            draw.text((56, 87), f"PREMIER LEAGUE {season}   •   GW1–GW{gameweek}   •   {part} TEAMS",
                      fill="#C5D9F3", font=subtitle_font)
            scroll = int(max(0, resized_height - usable_height) * index / 2)
            portion = image.crop((0, scroll, image.width, min(image.height, scroll + usable_height)))
            canvas.paste(portion, (55, 140))
            draw.line((55, 990, 1865, 990), fill="#2C9B9A", width=3)
            draw.text((55, 1012), f"{section}  |  20 Premier League clubs  |  Official FPL data / validated sources",
                      fill="#C5D9F3", font=subtitle_font)
            frame_path = frames / f"{section.lower()}-{index}.png"
            canvas.save(frame_path, optimize=True)
            frame_files.append(frame_path)
            manifest_lines.extend([f"file '{frame_path.as_posix()}'", f"duration {duration_per_frame}"])
    manifest_lines.append(f"file '{frame_files[-1].as_posix()}'")
    playlist = frames / "video.ffconcat"
    playlist.write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")
    video_path = root / "FPL_VORTEX_XG_DEFCON_GAME_STATE.mp4"
    command = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "concat", "-safe", "0", "-i", str(playlist),
    ]
    music = root / "source" / "background.mp3"
    if music.is_file() and music.stat().st_size > 100:
        command += ["-stream_loop", "-1", "-i", str(music),
                    "-filter_complex", "[1:a]volume=0.11[a]",
                    "-map", "0:v:0", "-map", "[a]"]
    else:
        command += ["-f", "lavfi", "-i",
                    "anullsrc=channel_layout=stereo:sample_rate=48000",
                    "-map", "0:v:0", "-map", "1:a:0"]
    command += [
        "-shortest", "-t", str(len(frame_files) * duration_per_frame),
        "-vf", "fps=24", "-c:v", "libx264", "-preset", "medium",
        "-crf", "19", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
        str(video_path),
    ]
    run_command(command)
    if not video_path.is_file() or video_path.stat().st_size < 100_000:
        raise RuntimeError("Video rendering failed or produced an incomplete MP4")
    run_command(["ffprobe", "-v", "error", "-show_entries",
                 "format=duration", "-of", "default=noprint_wrappers=1", str(video_path)])
    print(f"[XG-DEFCON] Rendered verified video: {video_path}")


def publish_public() -> None:
    from google.auth.transport.requests import Request as GoogleRequest
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    root = root_path()
    metas = read_report_metadata(root)
    video_path = root / "FPL_VORTEX_XG_DEFCON_GAME_STATE.mp4"
    if not video_path.is_file() or video_path.stat().st_size < 100_000:
        raise RuntimeError("Cannot publish an absent or incomplete video")
    client_id = os.environ.get("YOUTUBE_OAUTH_CLIENT_ID") or required_env("GOOGLE_OAUTH_CLIENT_ID")
    client_secret = os.environ.get("YOUTUBE_OAUTH_CLIENT_SECRET") or required_env("GOOGLE_OAUTH_CLIENT_SECRET")
    credentials = Credentials(
        token=None,
        refresh_token=required_env("YOUTUBE_OAUTH_REFRESH_TOKEN"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=["https://www.googleapis.com/auth/youtube.upload",
                "https://www.googleapis.com/auth/youtube.readonly"],
    )
    credentials.refresh(GoogleRequest())
    youtube = build("youtube", "v3", credentials=credentials, cache_discovery=False)
    channel_response = youtube.channels().list(part="id", mine=True).execute()
    channels = channel_response.get("items") or []
    expected_channel = required_env("YOUTUBE_CHANNEL_ID")
    if len(channels) != 1 or channels[0].get("id") != expected_channel:
        raise RuntimeError("Authenticated YouTube channel does not match configured channel")
    gameweek = int(metas["xG"]["gameweek"])
    season = str(metas["xG"]["season"])
    # Only the validated 9:16 Shorts renderer is permitted to publish.
    manifest_path = root / "shorts_manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError("Missing verified Shorts manifest; refusing legacy landscape publishing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        manifest.get("format") != "youtube_shorts"
        or manifest.get("orientation") != "9:16"
        or manifest.get("width") != 1080
        or manifest.get("height") != 1920
        or not (10 <= float(manifest.get("duration_seconds", 0)) < 59)
        or manifest.get("voiceover") is not False
        or int(manifest.get("gameweek", 0)) != gameweek
        or str(manifest.get("season")) != season
    ):
        raise RuntimeError("Shorts render manifest does not pass publishing requirements")
    title = f"FPL GW{gameweek}: xG vs DEFCON & Game State | All 20 PL Clubs #Shorts"
    if len(title) > 100:
        raise RuntimeError("YouTube title exceeds 100 characters")
    provisional = any(bool(meta.get("provisional")) for meta in metas.values())
    descriptions = [
        f"FPL VORTEX | Premier League {season} through completed GW{gameweek}.",
        *(
            ["DATA STATUS: Official FPL figures are currently provisional and may be revised."]
            if provisional else []
        ),
        "Which Premier League clubs lead in xG, DEFCON and time spent winning?",
        "Animated 9:16 Shorts analysis of all 20 clubs using validated FPL and match data.",
        "",
    ]
    for report_name in REPORTS:
        caption_path = root / "output" / report_name / "1.txt"
        caption_lines = [
            line.strip() for line in caption_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        descriptions.append(f"{report_name}:")
        descriptions.extend(caption_lines[1:4])
        descriptions.append("")
    descriptions += [
        "Sources: Official FPL stats and verified FotMob game-state timelines.",
        "Descriptive statistics are not predictions.",
        "Music, intro and outro: FPL VORTEX Google Drive media assets.",
        "No voiceover. Rendered specifically for YouTube Shorts.",
        "",
        f"#Shorts #FPL #FPLGW{gameweek} #FantasyPremierLeague #PremierLeague #xG #DEFCON #FPLVORTEX",
    ]
    body = {
        "snippet": {
            "title": title,
            "description": "\n".join(descriptions),
            "tags": ["YouTube Shorts", "FPL", f"FPL GW{gameweek}", "Fantasy Premier League",
                     "Premier League", "Expected Goals", "xG", "DEFCON", "Defensive Contributions",
                     "Game State", "FPL VORTEX"],
            "categoryId": "17",
            "defaultLanguage": "en",
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        },
    }
    request = youtube.videos().insert(
        part="snippet,status", body=body, notifySubscribers=False,
        media_body=MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True, chunksize=8 * 1024 * 1024),
    )
    response = None
    while response is None:
        progress, response = request.next_chunk()
        if progress:
            print(f"[XG-DEFCON] YouTube upload: {progress.progress() * 100:.1f}%")
    video_id = (response or {}).get("id")
    if not video_id:
        raise RuntimeError("YouTube upload completed without returning a video ID")
    verified = youtube.videos().list(part="status,snippet", id=video_id).execute()
    items = verified.get("items") or []
    if len(items) != 1:
        raise RuntimeError(f"Uploaded video {video_id} could not be independently verified")
    privacy = (items[0].get("status") or {}).get("privacyStatus")
    owner = (items[0].get("snippet") or {}).get("channelId")
    if privacy != "public" or owner != expected_channel:
        raise RuntimeError(
            f"YouTube upload failed public/channel verification: video={video_id}, privacy={privacy}"
        )
    report = {"video_id": video_id, "privacy_status": privacy, "channel_id": owner,
              "gameweek": gameweek, "season": season,
              "watch_url": f"https://www.youtube.com/watch?v={video_id}"}
    (root / "public_upload.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"[XG-DEFCON] PUBLIC upload verified: {report['watch_url']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Independent manually-dispatched xG/DEFCON/Game State YouTube pipeline")
    parser.add_argument("command", choices=["prepare", "execute", "render", "publish"])
    arguments = parser.parse_args()
    if arguments.command == "prepare":
        prepare()
    elif arguments.command == "execute":
        execute_notebook()
    elif arguments.command == "render":
        render_video()
    elif arguments.command == "publish":
        publish_public()


if __name__ == "__main__":
    main()
