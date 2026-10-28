"""Short Day 1 production: results opening followed by the existing squad review."""
from pathlib import Path
import json, math, subprocess
from fractions import Fraction
from html import escape
from .day1_results import build_results


def patch_cell(cell):
    if '# CELL 14 — SELF-CONTAINED' in cell:
        before = cell[:cell.index('# PRESENTATION COMPATIBILITY BRIDGE')]
        branding = cell[cell.index('def vx_apply_pl_lockup'):cell.index('print("✅ Presentation bridge:')]
        review = cell[cell.index('if not globals().get("GW_REVIEW_AVAILABLE", False):'):]
        empty = 'import re as _vx_re\nimport pandas as pd\nfdr_table = pd.DataFrame(columns=["team_short"])\ndef format_fdr_value(value): return "—"\ndef fdr_class(value): return "fdr-grey"\n'
        return before + empty + branding + review
    if '# CELL 7A —' in cell:
        return cell[cell.index('# FPL VORTEX — SHARED PRODUCTION HELPERS'):]
    if '# CELL 9 —' in cell:
        return cell[cell.index('# Bootstrap + fixtures come ONLY'):]
    if any(label in cell for label in ('# CELL 5 —', '# CELL 6 —', '# CELL 7 —', '# CELL 8 —', '# CELL 12 —', '# CELL 13 —', '# CELL 13A —', '# CELL 13B —', '# CELL 13C —', '# CELL 13D —', '# CELL 13E —', '# CELL 13F —')):
        return "print('Day 1: forecast stage removed from retrospective review')"
    if 'SLIDE_01_INTRO = True' in cell:
        for name in ('SLIDE_03_FDR','SLIDE_04_PROJECTED_GOALS','SLIDE_05_CLEAN_SHEETS','SLIDE_06_OUTRO'):
            cell = cell.replace(name+' = True', name+' = False')
    for label in ('# CELL 14A —', '# CELL 14B —', '# CELL 14C —', '# CELL 19 —', '# CELL 20 —'):
        if label in cell:
            return "print('Day 1: removed legacy extra scene/agenda stage')"
    if '# CELL 15 —' in cell:
        neutral = 'profile = {"rate": "+0%", "pitch": "+0Hz", "volume": "+0%"}'
        if cell.count(neutral) != 1:
            raise RuntimeError('Review voice profile insertion point changed')
        cell = cell.replace(neutral, 'profile = vx_tts_profile(mood)', 1)
        cell = cell.replace('spoken = vx_narration_player(player)', 'spoken = _vx_narration_spoken_player_name(player.get("name") or player.get("web_name") or vx_narration_player(player))', 1)
        cell = cell.replace('print("✅ Review Ryan profile: +0% rate / +0Hz pitch / +0% volume")', 'print("✅ Review Ryan: original MOODS profiles active; full squad script preserved")')
    if '# CELL 16 —' in cell:
        anchor = 'for p in pkg["players"]:'
        replacement = 'from vortex.day1_short import raw_card_fixtures\ndef _pc_fixture_pack(team_short, position, player_id):\n    return raw_card_fixtures(globals(), player_id)\n\n' + anchor
        if cell.count(anchor) != 1:
            raise RuntimeError('Original hero-card data insertion point changed')
        cell = cell.replace(anchor, replacement, 1)
    if '# CELL 18 —' in cell:
        return 'from vortex.day1_short import render_results\nawait render_results(globals())'
    return cell


def warning(player):
    name = player.get('web_name', '')
    status = player.get('status')
    if status == 's':
        return f"I would wait on {name}: he is currently flagged as suspended."
    if status in {'i','d','u'}:
        return f"I would check the latest team news before buying {name}; he has an availability flag."
    cards = int(player.get('yellow_cards') or 0)
    if cards > 4:
        return f"{name} has {cards} league yellow cards. I would check his disciplinary status before buying; the count alone does not confirm a ban."
    return ''


def plan(snapshot):
    boot = snapshot['bootstrap']; gw = int(snapshot['gw'])
    rows = build_results(boot, snapshot['fixtures'], gw)
    if not rows: raise RuntimeError('No official review fixtures')
    players = {int(p['id']): p for p in boot['elements']}
    segments = [{'text': f"Welcome back to FPL Vortex. I am reviewing Gameweek {gw}, then taking you through my squad.", 'row': -1, 'player': None}]
    warned = set()
    for index, row in enumerate(rows):
        if row['final']:
            a,b = row['score']; text = f"{row['home']} {a}, {row['away']} {b}."
        else:
            text = f"{row['home']} against {row['away']} is not confirmed as a final result in this snapshot."
        segments.append({'text':text, 'row':index, 'player':None})
        merged = {}
        for event in row['returns']:
            merged.setdefault(event['id'], []).append(event)
        for pid, events in merged.items():
            p = players[pid]; facts=[]
            for e in events:
                label = 'goal' if e['kind']=='goals_scored' else 'assist'
                facts.append(f"{e['count']} {label}{'s' if e['count'] != 1 else ''}")
            text = p['web_name']+' recorded '+' and '.join(facts)+'.'
            if pid not in warned:
                text += ' '+warning(p); warned.add(pid)
            segments.append({'text':text.strip(), 'row':index, 'player':p})
    for pick in snapshot['picks']['picks']:
        pid=int(pick['element']); p=players.get(pid)
        if p and pid not in warned and warning(p):
            segments.append({'text':warning(p), 'row':len(rows)-1,'player':p}); warned.add(pid)
    segments.append({'text':"Now I will review my own Gameweek squad.",'row':len(rows)-1,'player':None})
    return gw, rows, segments


def results_assets(ns, segments):
    """Use the original Cell 16 card-data builder and Cell 15A card runtime."""
    boot=ns['GW_REVIEW']['bootstrap']
    teams={int(t['id']):t for t in boot['teams']}
    live={int(p['id']):p.get('stats',{}) for p in ns['GW_REVIEW']['live']['elements']}
    records=[]
    for p in {int(s['player']['id']):s['player'] for s in segments if s['player']}.values():
        t=teams[int(p['team'])]; stats=live.get(int(p['id']),{})
        record={'id':p['id'],'name':p['web_name'],'full_name':p['web_name'],
                'first_name':p.get('first_name',''),'second_name':p.get('second_name',''),
                'team':t['short_name'],'team_name':t['name'],'team_code':t['code'],
                'pos':{1:'GK',2:'DEF',3:'MID',4:'FWD'}[int(p['element_type'])],
                'photo':ns['resolve_player_photo'](p),'price':float(p.get('now_cost',0))/10,
                'ownership':float(p.get('selected_by_percent',0)), 'review_state':'FINAL',
                'fixture':{},'bench':False,'captain':False,'vice':False,'multiplier':1}
        for dst,src in {'total_points':'total_points','form':'form','xg':'expected_goals','xa':'expected_assists','xgi':'expected_goal_involvements','minutes':'minutes','starts':'starts','goals':'goals_scored','assists':'assists','clean_sheets':'clean_sheets','goals_conceded':'goals_conceded','saves':'saves','bonus':'bonus'}.items():
            record['season_'+dst]=float(p.get(src,0) or 0)
        for dst,src in {'points':'total_points','minutes':'minutes','bonus':'bonus','bps':'bps'}.items():record[dst]=stats.get(src,0)
        records.append(record)
    source=Path(__file__).resolve().parents[1].joinpath('1_final_day1.py').read_text()
    start=source.index('for p in pkg["players"]:')
    end=source.index('# IMPORTANT: pkg["players"]',start)
    local=dict(ns);local['pkg']={'players':records,'gw':ns['REVIEW_GW']}
    exec(compile(source[start:end],'original-hero-card-data','exec'),local)
    return {int(p['id']):p['card'] for p in records}


def results_html(ns,gw,rows,cards):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    tiles=[]
    for i,r in enumerate(rows):
        stamp=datetime.fromisoformat(r['kickoff'].replace('Z','+00:00')).astimezone(ZoneInfo('Europe/London')).strftime('%a %d %b • %H:%M %Z') if r.get('kickoff') else 'KICKOFF TBC'
        def crest(code):
            meta=next((v for v in ns['team_meta_by_id'].values() if int(v.get('code',0))==int(code)),{})
            return meta.get('badge') or f'https://resources.premierleague.com/premierleague/badges/100/t{code}.png'
        score=' – '.join(map(str,r['score'])) if r['final'] else 'PENDING'
        tiles.append(f'<article class="match" id="match-{i}"><div class="kick">{escape(stamp)}</div><div class="line"><img src="{escape(crest(r["home_code"]))}"><b>{escape(r["home"])}</b><strong>{score}</strong><b>{escape(r["away"])}</b><img src="{escape(crest(r["away_code"]))}"></div><small>{"FT" if r["final"] else "NOT FINAL"}</small></article>')
    css='''<style>
    *{box-sizing:border-box}body{margin:0;background:#020916;color:white;font-family:Arial,sans-serif;overflow:hidden}#stage{width:3840px;height:2160px;position:relative;overflow:hidden;background:radial-gradient(ellipse at 94% 66%,#176fb8aa,transparent 46%),repeating-linear-gradient(132deg,transparent 0 280px,#0f77c72e 282px 286px,transparent 290px 540px),linear-gradient(130deg,#020a1b,#073b70 48%,#020c21)}
    #stage:before{content:"";position:absolute;inset:-50px;border:36px solid #9ee7ff;transform:skew(-17deg);box-shadow:inset 0 0 90px #2ebdff,0 0 90px #2ebdff;pointer-events:none}header{position:absolute;top:35px;left:70px;right:70px;height:145px;display:flex;align-items:center;justify-content:space-between;border-bottom:4px solid #76dfff}header img{max-height:140px;max-width:420px;object-fit:contain}.brand{font-weight:900;font-size:55px;color:#ffe071}.pl{font-size:43px;font-weight:900;text-align:right}h1{position:absolute;top:170px;margin:0;width:100%;text-align:center;font-size:158px;font-style:italic;letter-spacing:-4px;text-shadow:4px 8px 12px #000}h1 em{color:#ffe36a;font-style:normal}.sub{position:absolute;top:355px;width:100%;text-align:center;font-size:48px;font-weight:bold;letter-spacing:6px;color:#75eaff}#board{position:absolute;left:200px;top:505px;width:3440px;display:grid;grid-template-columns:1fr 1fr;gap:27px;transform-origin:left center}.match{height:270px;border:4px solid #7ce4ff;border-radius:24px;background:linear-gradient(110deg,#021024f5,#063c6fe0,#020d20f5);box-shadow:0 0 18px #20b4ff;opacity:.75;position:relative}.match.active{border-color:#ffdc65;box-shadow:0 0 38px #ffd34b;opacity:1}.match.seen{opacity:1}.kick{text-align:center;font-size:29px;letter-spacing:1px;margin:12px}.line{display:grid;grid-template-columns:140px 1fr 300px 1fr 140px;align-items:center;gap:16px;padding:0 22px}.line img{height:140px;width:135px;object-fit:contain}.line b{font-size:37px;text-transform:uppercase;text-align:center}.line strong{text-align:center;background:linear-gradient(#0962b7,#071c50);font-size:84px;border-radius:15px;border:2px solid #36a1ff}.match small{position:absolute;bottom:7px;left:48%;font-size:26px;background:#03070c;border:1px solid #decf89;padding:2px 9px}#hero{position:absolute;left:2420px;top:430px;width:1360px;height:1810px;z-index:10;display:none;transform-origin:right top}footer{position:absolute;bottom:25px;width:100%;font-size:39px;font-weight:bold;letter-spacing:4px;text-align:center;border-top:3px solid #97e5ff;padding:28px;background:#031322c9;color:#e1f5ff}#caption{position:absolute;bottom:147px;left:150px;width:1990px;font-size:39px;line-height:1.22;background:#031225de;border-radius:14px;padding:18px 26px;display:none}
    </style>'''
    data=json.dumps(cards,ensure_ascii=False).replace('</','<\\/')
    js='''<script>const cards=CARDS;window.showFrame=(row,pid,progress,caption)=>{document.querySelectorAll('.match').forEach((el,i)=>{el.classList.toggle('active',i===row);el.classList.toggle('seen',i<=row)});const hero=document.querySelector('#hero');document.querySelector('#board').style.transform=pid?'translateX(-100px) scale(.59)':'none';hero.style.display=pid?'block':'none';if(pid){if(hero.dataset.pid!==String(pid)){VXPlayerCard.mount(hero,cards[String(pid)]);hero.dataset.pid=pid;}hero.style.opacity=String(progress);hero.style.transform=`translateY(${50*(1-progress)}px) scale(${.88*(.94+.06*progress)})`;}const c=document.querySelector('#caption');c.style.display=pid?'block':'none';c.textContent=caption||'';};showFrame(-1,null,1,'');</script>'''.replace('CARDS',data)
    return '<!doctype html><html><head><meta charset="utf-8">'+css+'<style>'+str(ns.get('PL_BUG_CSS',''))+'.plBug{top:35px;right:70px}</style>'+ns['PLAYER_CARD_CSS']+'</head><body><div id="stage"><header><div>'+str(ns['vortex_logo_html'])+'</div><span class="brand">FPL VORTEX</span><span class="pl">PREMIER LEAGUE<br>RESULTS REVIEW</span></header><h1>GAMEWEEK <em>'+f'{gw:02}'+'</em></h1><div class="sub">FULL-TIME RESULTS • '+str(ns.get('EPL_SEASON',''))+'/'+str(int(ns.get('EPL_SEASON',2026))+1)[-2:]+'</div><main id="board">'+''.join(tiles)+'</main><div id="hero"></div><div id="caption"></div><footer>▶ @FPLVORTEX　 |　𝕏 @FPLVORTEXM　 |　DATA • DECISION • POINT • RANK CLIMB</footer></div>'+ns['PLAYER_CARD_JS']+js+'</body></html>'


def _concat_quote(path):
    return str(Path(path).resolve()).replace("'", "'\\''")


def _validate_results_video(path, fps, expected_duration):
    probe = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_streams', '-of', 'json', str(path)],
        capture_output=True, text=True, check=True,
    )
    streams = json.loads(probe.stdout)['streams']
    video = next((s for s in streams if s.get('codec_type') == 'video'), None)
    audio = next((s for s in streams if s.get('codec_type') == 'audio'), None)
    if video is None or audio is None:
        raise RuntimeError(f'Results video is missing video or narration: {path}')
    rate = float(Fraction(video.get('avg_frame_rate') or '0/1'))
    if abs(rate - fps) > .05:
        raise RuntimeError(f'Results video: {rate:.3f}fps instead of {fps}fps: {path}')
    if video.get('codec_name') != 'h264' or audio.get('codec_name') != 'aac':
        raise RuntimeError(f'Results video requires H.264 video and AAC narration: {path}')
    # A sparse clip can report 24fps while its video ends seconds before its
    # audio. Check both stream lengths, including after the clips are joined.
    for stream in (video, audio):
        duration = float(stream.get('duration') or 0)
        if not math.isfinite(duration) or abs(duration - expected_duration) > 2 / fps:
            raise RuntimeError(
                f'Results {stream["codec_type"]} duration {duration:.3f}s '
                f'instead of {expected_duration:.3f}s: {path}'
            )


def _encode_results_segment(images, audio, clip, seconds, fps):
    # Round up so the frame grid contains all narration plus its existing tail.
    duration = math.ceil(seconds * fps) / fps
    listing = Path(clip).with_suffix('.ffconcat')
    listing.write_text(
        ''.join(
            f"file '{_concat_quote(image)}'\n"
            f"duration {(.08 if index < 3 else max(.08, duration - .24)):.9f}\n"
            for index, image in enumerate(images)
        ) + f"file '{_concat_quote(images[-1])}'\n"
    )
    subprocess.run(
        ['ffmpeg', '-y', '-loglevel', 'error',
         '-f', 'concat', '-safe', '0', '-i', str(listing), '-i', str(audio),
         '-vf', f'fps={fps}:round=near,format=yuv420p',
         '-fps_mode', 'cfr', '-r', str(fps),
         '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '20',
         '-af', 'aresample=48000:async=1:first_pts=0,apad',
         '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2',
         '-t', f'{duration:.9f}', str(clip)],
        check=True,
    )
    _validate_results_video(clip, fps, duration)
    return duration


def _join_results_segments(clips, output, fps, duration):
    listing = Path(clips[0]).parent / 'concat.txt'
    listing.write_text(''.join(f"file '{_concat_quote(p)}'\n" for p in clips))
    subprocess.run(
        ['ffmpeg', '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0',
         '-i', str(listing), '-c', 'copy', '-movflags', '+faststart', str(output)],
        check=True,
    )
    _validate_results_video(output, fps, duration)


async def render_results(ns):
    from playwright.async_api import async_playwright
    gw,rows,segments=plan(ns['GW_REVIEW'])
    cards=results_assets(ns,segments)
    for s in segments:
        if s['player']:
            p=s['player'];name=ns['vx_narration_player'](p['id'])
            s['text']=s['text'].replace(p['web_name'],name)
    work=Path(ns['VIDEO_WORK_DIR'])/'premium_results';work.mkdir(parents=True,exist_ok=True)
    html=work/'results.html';html.write_text(results_html(ns,gw,rows,cards))
    output=Path(ns['MP4_DIR'])/'00_intro.mp4'; clips=[];total=0
    fps=int(ns.get('VIDEO_FPS',24))
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
        page=await browser.new_page(viewport={'width':3840,'height':2160},device_scale_factor=1)
        await page.goto(html.as_uri(),wait_until='networkidle')
        await page.evaluate('document.fonts.ready')
        for i,s in enumerate(segments):
            mood='intro' if i==0 else 'warning' if 'flag' in s['text'] or 'cards' in s['text'] else 'analysis' if s['player'] else 'key_stat'
            profile=ns['vx_tts_profile'](mood)
            audio=work/f'{i:03}.mp3';payload,words=await ns['vx_edge_tts_stream'](s['text'],profile);audio.write_bytes(payload)
            seconds=ns['vx_media_duration'](audio)+.08
            images=[];pid=int(s['player']['id']) if s['player'] else None
            for k,progress in enumerate((.15,.45,.8,1.0)):
                await page.evaluate('(v)=>showFrame(v.row,v.pid,v.p,v.text)',{'row':s['row'],'pid':pid,'p':progress,'text':s['text']})
                await page.evaluate('()=>{document.querySelectorAll("#hero img").forEach(i=>i.loading="eager")}')
                await page.evaluate('()=>Promise.all(Array.from(document.images).map(i=>i.complete?Promise.resolve():new Promise(r=>{i.onload=r;i.onerror=r;setTimeout(r,4000)})))')
                path=work/f'{i:03}-{k}.png';await page.screenshot(path=str(path));images.append(path)
            clip=work/f'{i:03}.mp4'
            seconds=_encode_results_segment(images,audio,clip,seconds,fps);total+=seconds
            s['tts_mood']=mood;s['tts_profile']=profile;s['duration']=seconds;clips.append(clip)
        await page.evaluate('(v)=>showFrame(v,null,1,"")',len(rows)-1)
        await page.screenshot(path=str(Path(ns['SLIDE_DIR'])/'intro_scene_4k.png'))
        await browser.close()
    _join_results_segments(clips,output,fps,total)
    (Path(ns['DATA_DIR'])/'day1_results_script.json').write_text(json.dumps({'gw':gw,'profiles':ns['MOODS'],'segments':segments},indent=2))


def raw_card_fixtures(ns, player_id):
    snapshot=ns['GW_REVIEW'];boot=snapshot['bootstrap']
    p=next(p for p in boot['elements'] if int(p['id'])==int(player_id))
    teams={int(t['id']):t for t in boot['teams']}
    fixtures=sorted((f for f in snapshot['fixtures'] if int(f.get('event') or 0)>int(snapshot['gw']) and int(p['team']) in (f['team_h'],f['team_a'])),key=lambda f:(int(f['event']),f.get('kickoff_time') or ''))[:6]
    result=[]
    for f in fixtures:
        home=int(p['team'])==int(f['team_h']);opp=teams[int(f['team_a'] if home else f['team_h'])]
        meta=ns.get('team_meta_by_id',{}).get(int(opp['id']),{})
        result.append({'gw':int(f['event']),'opponent':opp['short_name'],'venue':'H' if home else 'A','badge':meta.get('badge',''),'fdr_class':'fdr-none'})
    return result
