"""Day 1 owns two sections. No transfer solver or standalone prediction slides."""
from __future__ import annotations

import argparse
import ast
import asyncio
import base64
import inspect
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests

from day1 import fpl_data
from day1.media import assemble, render, speak_roundup, compact_roundup, EditorialLimitError
from day1.roundup import Wording, build_roundup, upcoming
from vortex.fixture_forecast import forecast_rows, input_root, records

PACKAGE = Path(__file__).parent


async def stage(name, namespace):
    path = PACKAGE / name
    print(f"Day 1: {name}", flush=True)
    code = compile(path.read_text(), str(path), "exec", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
    result = eval(code, namespace)
    if inspect.isawaitable(result):
        await result


def logo_uri(path):
    # Preserve the approved asset's alpha trim and padding.
    from io import BytesIO
    from PIL import Image
    image = Image.open(path).convert("RGBA")
    bbox = image.getchannel("A").getbbox()
    if bbox:
        left, top, right, bottom = bbox
        pad = max(8, int(max(right-left, bottom-top) * .025))
        image = image.crop((max(0,left-pad), max(0,top-pad), min(image.width,right+pad), min(image.height,bottom+pad)))
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


class Assets:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()

    def image(self, url):
        import hashlib
        path = self.root / (hashlib.sha256(url.encode()).hexdigest() + ".asset")
        if path.is_file():
            content = path.read_bytes()
        else:
            try:
                r = self.session.get(url, timeout=15)
                r.raise_for_status()
                if not r.headers.get("Content-Type", "").startswith("image/"):
                    return ""
                content = r.content
                path.write_bytes(content)
            except requests.RequestException:
                return ""
        mime = "image/png" if content.startswith(b"\x89PNG") else "image/webp" if content[8:12] == b"WEBP" else "image/jpeg"
        return f"data:{mime};base64," + base64.b64encode(content).decode()

    def badge(self, team):
        return self.image(f"https://resources.premierleague.com/premierleague/badges/100/t{team['code']}.png") if team.get("code") else ""

    def player(self, player):
        code = str(player.get("photo") or "").split(".")[0]
        if not code.isdigit():
            return ""
        return self.image(f"https://resources.premierleague.com/premierleague/photos/players/250x250/p{code}.png")


def model_tables(snapshot, rows, next_gw):
    """Only map canonical WC/FH numbers to the approved review presentation schema."""
    slots, individual = [], []
    for team in snapshot["bootstrap"]["teams"]:
        p = {"id": -team["id"], "team": team["id"], "element_type": 3}
        attack = upcoming(p, snapshot, rows, next_gw, 6)
        defence = upcoming(dict(p, element_type=2), snapshot, rows, next_gw, 6)
        slot = {"team_short": team["short_name"], "team_id": team["id"], "fixtures": [], "attack_fdr": [], "defence_fdr": []}
        for aa, dd in zip(attack, defence):
            slot["fixtures"].append(" / ".join(f"{f['opponent']} ({f['venue']})" for f in aa["fixtures"]) or "BLANK")
            for key, source in (("attack_fdr", aa), ("defence_fdr", dd)):
                slot[key].append(" + ".join(f"{f['fdr']:.2f}" if f["fdr"] is not None else "—" for f in source["fixtures"]) or "—")
            for a, d in zip(aa["fixtures"], dd["fixtures"]):
                individual.append({"fixture_id": a["fixture_id"], "gw": aa["gw"], "team": team["short_name"], "team_id": team["id"], "attack_fdr_model": a["fdr"], "defence_fdr_model": d["fdr"]})
        slot["fdr"] = slot["attack_fdr"]
        slots.append(slot)
    frame = pd.DataFrame(individual, columns=["fixture_id", "gw", "team", "team_id", "attack_fdr_model", "defence_fdr_model"])
    return pd.DataFrame(slots), frame


def fdr_class(value):
    values = [float(n) for n in re.findall(r"[1-5](?:\.\d+)?", str(value)) if 1 <= float(n) <= 5]
    return f"fdr-{max(1,min(5,math.floor(sum(values)/len(values)+.5)))}" if values else "fdr-none"


def paths(output, work):
    output, work = Path(output).resolve(), Path(work).resolve()
    if output == work or output in work.parents or work in output.parents:
        raise ValueError("Output and temporary work directories must be separate")
    folders = {"OUTPUT_ROOT": output, "MP4_DIR": output / "MP4", "MP3_DIR": output / "MP3", "SLIDE_DIR": output / "SLIDE", "DATA_DIR": output / "DATA", "HTML_WORK_DIR": work / "html", "AUDIO_WORK_DIR": work / "audio", "VIDEO_WORK_DIR": work / "video"}
    for folder in folders.values():
        folder.mkdir(parents=True, exist_ok=True)
    return folders


async def prepare_review(data, forecasts, namespace, assets):
    namespace.update(data=data, _fpl_module=fpl_data, players=data["players"], teams=data["teams"], fixtures=data["fixtures"], NEXT_GW=data["next_gw"])
    await stage("review_snapshot.py", namespace)
    snapshot = namespace["GW_REVIEW"]
    # JSON timestamps are kept lossless and shared by both sections.
    snapshot["fixtures"] = records(data["fixtures"])
    (namespace["DATA_DIR"] / "official_review_snapshot.json").write_text(json.dumps(snapshot, ensure_ascii=False))
    fdr, individual = model_tables(snapshot, forecasts, data["next_gw"])
    namespace.update(fdr_table=fdr, model_fixture_fdr_df=individual,
        goalkeeper_fixture_fdr_df=individual[["gw", "team", "defence_fdr_model"]].rename(columns={"defence_fdr_model": "goalkeeper_fdr_model"}),
        team_meta_by_short={t["short_name"]: {"name": t["name"], "badge": assets.badge(t)} for t in snapshot["bootstrap"]["teams"]},
        fdr_class=fdr_class, format_fdr_value=lambda x: str(x) if x is not None else "—",
        resolve_player_photo=assets.player, HTML_PATH=namespace["HTML_WORK_DIR"] / "gw_review_scene_4k.html", PNG_PATH=namespace["SLIDE_DIR"] / "gw_review_scene_4k.png")
    # Retrospective three-week context uses official event-live, not an xPts engine.
    history = fpl_data.fetch_recent_player_match_snapshot(data["events"], lookback_gws=3)
    if not history.empty:
        codes = {p["id"]: p["code"] for p in snapshot["bootstrap"]["elements"]}
        history["player_code"] = history["player_id"].map(codes)
        history["gameweek"] = history["event"]
    namespace["phase10_player_gw_all"] = history
    # CS on review cards is the same fixture-level forecast used in the intro.
    namespace["fixture_projection_df"] = pd.DataFrame([{ "gw": r["gameweek"], "home_id": r["home_team_id"], "away_id": r["away_team_id"], "home_cs": r["home_clean_sheet_probability"] * 100, "away_cs": r["away_clean_sheet_probability"] * 100} for r in forecasts], columns=["gw","home_id","away_id","home_cs","away_cs"])
    await stage("spoken_names.py", namespace)
    await stage("review_pitch.py", namespace)
    await stage("review_narration.py", namespace)
    await stage("review_cards.py", namespace)
    await stage("review_animation.py", namespace)
    manifest = namespace["manifest"]
    if manifest["duration"] > 240:
        raise RuntimeError(f"Squad review exceeds four minutes: {manifest['duration']:.1f}s")
    # The closing message belongs to the review's last narration beat, not a third MP4.
    html_path = Path(manifest["html"])
    end = max(s["t0"] for s in namespace["pkg"]["segments"] if s["id"] == "review_close")
    html = html_path.read_text()
    closing = ('<div id="day1-outro" style="position:absolute;inset:0;z-index:200;display:none;align-items:center;justify-content:center;text-align:center;background:linear-gradient(145deg,#020713ed,#07182bf2,#020711ed);font:1000 112px Arial;color:white"><div>THANKS FOR WATCHING<br><span style="color:#ffd447">FPL VORTEX</span><div style="font-size:48px;color:#35e6ff;margin-top:40px">SUBSCRIBE · SEE YOU NEXT TIME</div></div></div>')
    html = html.replace("</body>", closing + f'<script>const reviewSeek=window.__seek;window.__seek=function(t){{const value=reviewSeek(t);document.getElementById("day1-outro").style.display=t>={end:.6f}?"flex":"none";return value;}};</script></body>')
    html_path.write_text(html)
    manifest["motion_windows"].append({"start": end, "end": end + .6})
    return snapshot, manifest


async def main_async(args):
    folders = paths(args.output, args.work)
    now = datetime.now(timezone.utc)
    logo_path = Path(args.logo)
    logo = ""
    if logo_path.is_file():
        logo = '<img class="logo vortex-logo" src="' + logo_uri(logo_path) + '" alt="FPL Vortex">'
    ns = dict(folders, __name__="__day1__", PROJECT_ROOT=Path(args.output).parent, FPL_TEAM_ID=args.team_id, TEAM_ID=args.team_id, ENTRY_ID=args.team_id, VIDEO_WIDTH=args.width, VIDEO_HEIGHT=args.height, VIDEO_FPS=args.fps, SLIDE_SELECTION={"00_intro": True, "gw_review": True}, _vx_re=re, _vx_math=math, np=np, pd=pd)
    # Fresh immutable endpoint cache every run, even in a reused Colab kernel.
    fpl_data._VX_RUN_JSON_CACHE.clear()
    data = fpl_data.fetch_fpl_data()
    season = now.year if now.month >= 7 else now.year - 1
    pl_path = logo_path.with_name("pl.png")
    pl_mark = ('<div class="plLogoCrop"><img class="plLogoOriginal" src="' + logo_uri(pl_path) + '" alt="Premier League"></div>') if pl_path.is_file() else '<div class="plLogoFallback">PL</div>'
    pl_html = '<div class="plBug"><div class="plBugPanel">' + pl_mark + '<div class="plCopy"><div class="plWordmark">Premier League</div><div class="plSeason">' + f'<span>{season}</span><span>/</span><span>{season+1}</span>' + '</div></div></div></div>'
    ns.update(EPL_SEASON=season, vortex_logo_html=logo or '<div class="logo-fallback">FPL <span>VORTEX</span></div>', PL_BUG_HTML=pl_html, PL_BUG_CSS=(PACKAGE / "pl_lockup.css").read_text(), VX_FOOTER_UPDATED_DATE=now.astimezone(ZoneInfo("America/New_York")).strftime("%d %b %Y"))
    await stage("production_helpers.py", ns)
    forecasts = forecast_rows(data["bootstrap"], data["fixtures"], now=now)
    (folders["DATA_DIR"] / "canonical_fixture_forecast.json").write_text(json.dumps(forecasts, indent=2))
    assets = Assets(Path(args.work) / "assets")
    snapshot, review = await prepare_review(data, forecasts, ns, assets)
    wording = Wording(input_root() / "day1_narration_history.json")
    intro = build_roundup(snapshot, forecasts, int(data["next_gw"]), wording, ns["vx_narration_player"])
    try:
        audio = await speak_roundup(intro, ns, folders["AUDIO_WORK_DIR"] / "intro_segments")
    except EditorialLimitError:
        intro = compact_roundup(intro)
        audio = await speak_roundup(intro, ns, folders["AUDIO_WORK_DIR"] / "intro_segments")
    for b in intro["beats"]:
        if b.get("match"):
            for side in ("home", "away"):
                b["match"][side]["badge"] = assets.badge(b["match"][side])
        for mention in ([b] if b.get("card") else b.get("mentions", [])):
            mention["card"]["portrait"] = assets.player(next(p for p in snapshot["bootstrap"]["elements"] if p["id"] == mention["player_id"]))
            for slot in mention["card"]["fixtures"]:
                for fixture in slot["fixtures"]:
                    fixture["badge"] = assets.badge(fixture)
    intro.update(season=f"{ns['EPL_SEASON']}/{str(ns['EPL_SEASON']+1)[-2:]}", updated=now.astimezone(ZoneInfo("America/New_York")).strftime("%d %b %Y"))
    intro_html = folders["HTML_WORK_DIR"] / "intro.html"
    intro_html.write_text((PACKAGE / "intro.html").read_text().replace("__LOGO__", logo).replace("__DATA__", json.dumps(intro, ensure_ascii=False).replace("</", "<\\/")))
    (folders["DATA_DIR"] / "intro_roundup.json").write_text(json.dumps(intro, indent=2, ensure_ascii=False))
    # Timing must include every word-caption change, card reveal and entrance.
    intro_windows = [(b["t0"], b["t0"] + .65) for b in intro["beats"]]
    intro_windows += [(b["t0"] + b.get("name_time", 0), b["t0"] + b.get("name_time", 0) + .5) for b in intro["beats"] if b.get("card")]
    intro_windows += [(b["t0"] + m["name_time"], b["t0"] + m["name_time"] + .5) for b in intro["beats"] for m in b.get("mentions", [])]
    intro_windows += [(b["t0"]+w["start"], b["t0"]+w["start"]+.05) for b in intro["beats"] for i,w in enumerate(b["words"]) if i%13 == 0]
    sections = []
    for key, html, sound, seconds, windows in (("00_intro", intro_html, audio, intro["duration"], intro_windows), ("gw_review", review["html"], review["audio"], review["duration"], [(w["start"], w["end"]) for w in review["motion_windows"]])):
        result = await render(html, sound, folders["MP4_DIR"] / f"{key}.mp4", seconds, args.width, args.height, args.fps, windows, folders["SLIDE_DIR"] / f"{key}.png")
        sections.append(dict(result, key=key, scene="Intro & match roundup" if key == "00_intro" else "My Gameweek review & outro"))
    final_name = f"FPL_VORTEX_GW{data['next_gw']}_COMBINED_{args.height}P_{args.fps}FPS"
    qa = assemble(sections, folders["MP4_DIR"] / (final_name + ".mp4"), folders["MP3_DIR"] / (final_name + ".mp3"), args.assets, folders["DATA_DIR"] / "final_video_qa.json", (args.width, args.height), args.fps, snapshot["gw"])
    wording.save()
    print(f"Day 1 complete: two sections, {qa['duration']:.1f}s", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--team-id", type=int, default=145784)
    parser.add_argument("--output", default="/content/drive/MyDrive/FPL_VORTEX/FIRST VIDEO")
    parser.add_argument("--work", default="/content/FPL_VORTEX_FIRST_DAY_WORK")
    parser.add_argument("--assets", default="/content/drive/MyDrive/FPL_VORTEX/Assets")
    parser.add_argument("--logo", default="/content/drive/MyDrive/elements/logo.png")
    parser.add_argument("--width", type=int, default=3840)
    parser.add_argument("--height", type=int, default=2160)
    parser.add_argument("--fps", type=int, default=24)
    args = parser.parse_args()
    if args.team_id <= 0 or args.width / args.height != 16 / 9 or min(args.width, args.height, args.fps) <= 0:
        parser.error("Invalid entry ID or video dimensions")
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
