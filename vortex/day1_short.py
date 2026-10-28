"""Short Day 1 production: results opening followed by the existing squad review."""
from pathlib import Path
import asyncio, json, subprocess, tempfile
from html import escape
from PIL import Image, ImageDraw, ImageFont
from .day1_results import build_results


def patch_cell(cell):
    if 'SLIDE_01_INTRO = True' in cell:
        for name in ('SLIDE_03_FDR','SLIDE_04_PROJECTED_GOALS','SLIDE_05_CLEAN_SHEETS','SLIDE_06_OUTRO'):
            cell = cell.replace(name+' = True', name+' = False')
    for label in ('# CELL 14A —', '# CELL 14B —', '# CELL 14C —', '# CELL 19 —', '# CELL 20 —'):
        if label in cell:
            return "print('Day 1: removed legacy extra scene/agenda stage')"
    if '# CELL 15 —' in cell:
        anchor = 'for seg in segments:\n    await make_segment(seg)'
        if cell.count(anchor) != 1:
            raise RuntimeError('Review narration insertion point changed')
        cell = cell.replace(anchor, 'from vortex.day1_short import shorten_review\nshorten_review(segments)\n' + anchor)
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


def run(*args):
    subprocess.run(list(map(str,args)),check=True,stdout=subprocess.DEVNULL)


def duration(path):
    return float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',str(path)],text=True).strip())


def frame(path, gw, rows, current, player, photos, caption=""):
    im=Image.new('RGB',(1920,1080),'#031326'); d=ImageDraw.Draw(im)
    def font(n): return ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',n)
    d.rectangle((0,0,1920,10),fill='#23d9ff')
    d.text((65,35),'FPL VORTEX',font=font(45),fill='#ffdc66')
    d.text((65,105),f'GAMEWEEK {gw} | RESULTS REVIEW',font=font(44),fill='white')
    d.text((65,170),'OFFICIAL FPL SNAPSHOT • FINAL SCORES ONLY',font=font(19),fill='#86d9ee')
    count=max(1,len(rows)); h=min(122,690/count)
    for i,r in enumerate(rows):
        if i>current: continue
        y=225+i*h; color='#ffdc66' if i==current else '#2389af'
        d.rounded_rectangle((60,y,1270,y+h-10),12,fill='#09253d',outline=color,width=3)
        d.text((85,y+18),r['home'],font=font(22),fill='white')
        score=f"{r['score'][0]} – {r['score'][1]}" if r['final'] else 'PENDING'
        d.text((625,y+15),score,font=font(27),fill=color)
        d.text((835,y+18),r['away'],font=font(22),fill='white')
    if player:
        d.rounded_rectangle((1320,240,1850,895),22,fill='#0b2d48',outline='#ffdc66',width=4)
        photo=photos.get(int(player['id']))
        if photo:
            img=Image.open(photo).convert('RGBA');img.thumbnail((460,410));im.paste(img,(1350,265),img)
        d.text((1345,705),player['web_name'],font=font(29),fill='#ffdc66')
        import textwrap
        for line_no, line in enumerate(textwrap.wrap(caption, 42)[:5]):
            d.text((1345,760+line_no*24),line,font=font(18),fill='white')
    d.text((60,1010),'@FPLVORTEX  |  @FPLVORTEXM',font=font(24),fill='#a0d9e7')
    d.text((60,960),'AVAILABILITY FLAGS ARE CURRENT AT THE SNAPSHOT TIME',font=font(18),fill='#a0d9e7')
    im.save(path)


async def render_results(ns):
    import edge_tts, requests
    gw, rows, segments=plan(ns['GW_REVIEW'])
    work=Path(ns['VIDEO_WORK_DIR'])/'short_results';work.mkdir(parents=True,exist_ok=True)
    output=Path(ns['MP4_DIR'])/'00_intro.mp4'
    photos={}
    for s in segments:
        p=s['player']
        if not p or int(p['id']) in photos:continue
        path=work/f"player_{p['id']}.png"
        try:
            from wc_fh.player_images import official_photo_urls
            urls=official_photo_urls(p)
        except ImportError:
            urls=[f"https://resources.premierleague.com/premierleague25/photos/players/250x250/{p['code']}.png"]
        for url in urls:
            try:
                response=requests.get(url,timeout=10);response.raise_for_status();path.write_bytes(response.content)
                Image.open(path).verify();photos[int(p['id'])]=path;break
            except Exception:continue
    total=0;clips=[]
    for i,s in enumerate(segments):
        audio=work/f'{i:03}.mp3'
        await edge_tts.Communicate(s['text'],'en-GB-RyanNeural',rate='+0%',pitch='+0Hz').save(str(audio))
        seconds=duration(audio)+0.12;total+=seconds
        if total>200:raise RuntimeError('Results narration exceeds 200 seconds; shorten the script, never speed Ryan up')
        image=work/f'{i:03}.png';frame(image,gw,rows,s['row'],s['player'],photos,s['text'])
        clip=work/f'{i:03}.mp4'
        run('ffmpeg','-y','-loglevel','error','-loop','1','-i',image,'-i',audio,'-t',str(seconds),'-vf','scale=3840:2160,format=yuv420p','-r','24','-c:v','libx264','-preset','ultrafast','-crf','20','-c:a','aac','-b:a','192k',clip)
        clips.append(clip)
    listing=work/'concat.txt';listing.write_text(''.join(f"file '{p}'\n" for p in clips))
    run('ffmpeg','-y','-loglevel','error','-f','concat','-safe','0','-i',listing,'-c','copy','-movflags','+faststart',output)
    preview=Path(ns['SLIDE_DIR'])/'intro_scene_4k.png';frame(preview,gw,rows,len(rows)-1,None,photos)
    (Path(ns['DATA_DIR'])/'day1_results_script.json').write_text(json.dumps({'gw':gw,'rate':'+0%','duration':duration(output),'segments':segments},indent=2))


def shorten_review(segments):
    """Keep every player and their factual first sentence; omit repetitive advice."""
    for segment in segments:
        if segment.get('player_id'):
            text = str(segment['text'])
            first = text.split('. ', 1)[0].rstrip('.') + '.'
            name = segment.get('spoken_name') or segment.get('name')
            if name and name.casefold() not in first.casefold():
                raise RuntimeError('Concise narration lost player identity')
            segment['text'] = first
