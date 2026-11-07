"""Render an inspectable MP4 of the existing programme opening; never upload to YouTube."""
from __future__ import annotations

import ast
import asyncio
import base64
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import time
import unicodedata
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from vortex.day1_brief import build_brief, build_intro_agenda, build_timeline, caption_cues, render_brief
from vortex.day1_agenda import spoken_intro_agenda
from vortex.day1_editorial import word_timed_vtt

API = "https://fantasy.premierleague.com/api"


def fetch(path):
    for attempt in range(3):
        try:
            request = Request(API + path, headers={"Cache-Control":"no-cache", "User-Agent":"FPL-VORTEX-Preview"})
            with urlopen(request, timeout=30) as response:
                return json.load(response), datetime.now(timezone.utc).isoformat()
        except Exception:
            if attempt == 2:
                raise
            time.sleep(1)


async def main():
    import edge_tts
    from playwright.async_api import async_playwright

    output = Path(sys.argv[1] if len(sys.argv)>1 else "brief-preview").resolve()
    output.mkdir(parents=True, exist_ok=True)
    source = (ROOT/"1_final_day1.py").read_text()
    tree = ast.parse(source)
    team_id = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign)
                   and any(isinstance(t,ast.Name) and t.id=="FPL_TEAM_ID" for t in n.targets))
    boot, boot_at = fetch("/bootstrap-static/")
    fixtures, fixtures_at = fetch("/fixtures/")
    next_gw = next(e["id"] for e in boot["events"] if e.get("is_next"))
    current = next((e for e in boot["events"] if e.get("is_current")), None)
    completed = [e for e in boot["events"] if e.get("finished") and e["id"] < next_gw]
    if current and current["id"] < next_gw and any(f.get("event")==current["id"] and f.get("started") for f in fixtures):
        gw = current["id"]
    elif completed:
        gw = max(e["id"] for e in completed)
    else:
        raise RuntimeError("No official review Gameweek; no sample data will be substituted")
    event = next(e for e in boot["events"] if e["id"]==gw)
    status = "FINAL" if event.get("finished") and event.get("data_checked") else "LIVE/PARTIAL"
    snapshot = dict(gw=gw,status=status,bootstrap=boot,fixtures=fixtures,provenance={
        "bootstrap":{"source":API+"/bootstrap-static/","retrievedAt":boot_at},
        "fixtures":{"source":API+"/fixtures/","retrievedAt":fixtures_at}})
    for key,path,label in (
        ("history",f"/entry/{team_id}/history/","Official FPL presenter history"),
        ("picks",f"/entry/{team_id}/event/{gw}/picks/","Official FPL presenter picks"),
        ("live",f"/event/{gw}/live/",API+f"/event/{gw}/live/")):
        try:
            snapshot[key],stamp = fetch(path)
            snapshot["provenance"][key] = dict(source=label,retrievedAt=stamp)
        except Exception:
            snapshot[key] = {}
    try:
        brief = build_brief(snapshot,next_gw=next_gw)
    except ValueError as exc:
        # Propagating live points can disagree. Do not put a guessed score on screen.
        print("Presenter reconciliation unavailable:",type(exc).__name__)
        snapshot["picks"]={}; snapshot["history"]={}
        brief = build_brief(snapshot,next_gw=next_gw)
    segments = [{"id":x} for x in ("headline","editorial_squad_context","editorial_routes","editorial_verdict")]
    cards = build_intro_agenda(["00_intro","gw_review"],next_gw=next_gw,review_gw=gw,
        review_status=status,review_segments=segments,brief=brief)
    expression = next(v for n in ast.walk(tree) if isinstance(n,ast.Assign) and isinstance(n.value,ast.Dict)
        for k,v in zip(n.value.keys,n.value.values) if isinstance(k,ast.Constant) and k.value=="00_intro"
        and any(isinstance(x,ast.Name) and x.id=="VX_INTRO_AGENDA_SPOKEN" for x in ast.walk(v)))
    script = eval(compile(ast.Expression(expression),"production-intro","eval"),
        {"NEXT_GW":next_gw,"VX_INTRO_AGENDA_SPOKEN":spoken_intro_agenda(cards)})
    functions = [n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in {"vx_norm_text","vx_phrase_span"}]
    namespace = dict(re=re,unicodedata=unicodedata)
    exec(compile(ast.Module(body=functions,type_ignores=[]),"production-sync","exec"),namespace)

    audio = bytearray(); words=[]
    async for chunk in edge_tts.Communicate(script,"en-GB-RyanNeural",rate="+0%",pitch="-4Hz",boundary="WordBoundary").stream():
        if chunk["type"]=="audio": audio.extend(chunk["data"])
        if chunk["type"]=="WordBoundary": words.append(dict(text=chunk["text"],start=chunk["offset"]/1e7,duration=chunk["duration"]/1e7))
    audio_path = output/"opening.mp3";audio_path.write_bytes(audio)
    duration = float(subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(audio_path)]))
    if duration < 35:
        padded=output/"opening-padded.mp3"
        subprocess.run(["ffmpeg","-y","-v","error","-i",str(audio_path),"-af","apad","-t","38",str(padded)],check=True)
        padded.replace(audio_path);duration=38.0
    timeline = build_timeline(words,duration=duration,phrase_span=namespace["vx_phrase_span"],cards=cards)
    logo_file = ROOT/"tools/preview_assets/vortex-lion-reference.jpg"
    logo = '<img alt="FPL VORTEX lion from the supplied master slide" src="data:image/jpeg;base64,'+base64.b64encode(logo_file.read_bytes()).decode()+'">'
    # The approval file covers the opening only. Production supplies its actual review URI.
    page_html = render_brief(brief,logo_html=logo,cards=cards,timeline=timeline)
    page_html = page_html.replace("</body>","<script>window.__setBriefTimeline("+json.dumps(timeline)+","+json.dumps(caption_cues(words))+");</script></body>")
    html_path=output/"opening.html";html_path.write_text(page_html)
    frames=output/"frames";frames.mkdir(exist_ok=True)
    fps=24;total=math.ceil(duration*fps)
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True,args=["--no-sandbox"])
        page=await browser.new_page(viewport={"width":1920,"height":1080})
        await page.goto(html_path.as_uri(),wait_until="load")
        await page.wait_for_function("window.__ready===true")
        await page.evaluate("document.fonts.ready")
        await page.add_style_tag(content="*,*:before,*:after{transition:none!important;animation:none!important}html,body{margin:0;width:100vw;height:100vh;overflow:hidden}")
        for i in range(total):
            await page.evaluate("t=>window.__seek(t)",i/fps)
            await page.screenshot(path=str(frames/f"frame_{i:06d}.jpg"),type="jpeg",quality=92)
            if i in (0, int(timeline["cards"][0]*fps)+24, total-1):
                await page.screenshot(path=str(output/f"preview-{i}.png"))
            if i%120==0:print(f"Rendered {i}/{total} frames",flush=True)
        await browser.close()
    target=output/"FPL_VORTEX_Day1_Season_PL_Opening.mp4"
    subprocess.run(["ffmpeg","-y","-v","error","-framerate",str(fps),"-i",str(frames/"frame_%06d.jpg"),
        "-i",str(audio_path),"-c:v","libx264","-preset","fast","-crf","19","-pix_fmt","yuv420p",
        "-c:a","aac","-b:a","192k","-t",str(total/fps),"-movflags","+faststart",str(target)],check=True)
    (output/"opening.vtt").write_text(word_timed_vtt([dict(t0=0,t1=duration,text=script,words=words)]))
    (output/"render-report.json").write_text(json.dumps(dict(duration=duration,frames=total,fps=fps,
        resolution=[1920,1080],timeline=timeline,openingPreviewOnly=True,sources=brief),indent=2))
    print("MP4 preview ready:",target.name,flush=True)


if __name__=="__main__":asyncio.run(main())
