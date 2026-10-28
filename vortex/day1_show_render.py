"""Deterministic, word-timed 4K rendering for the Day 1 decision show."""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import math
import re
import subprocess
from html import escape
from pathlib import Path

from .day1_show import COLORS, _json, _plain, build_show, production_brief
from .day1_short import _concat_quote, _validate_results_video


def _run(command):
    try:
        return subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f'{command[0]} failed: {(exc.stderr or exc.stdout or "unknown failure")[-4000:]}') from exc


def _phrase_span(words, phrase, after=-1):
    tokens = _plain(phrase).split()
    # Names can span multiple Edge word-boundary records.
    flat = []
    for word in words:
        for token in _plain(word['text']).split():
            flat.append((token, float(word['start']), float(word['duration'])))
    for i in range(len(flat) - len(tokens) + 1):
        if flat[i][1] >= after and [x[0] for x in flat[i:i + len(tokens)]] == tokens:
            last = flat[i + len(tokens) - 1]
            return flat[i][1], last[1] + last[2]
    raise RuntimeError(f'No spoken word boundary for {phrase!r}')


def word_time(words, phrase, after=-1):
    return _phrase_span(words, phrase, after)[0]


def fit_word_timing(section, words):
    if not words or any(float(w['duration']) <= 0 or float(w['start']) < 0 for w in words):
        raise RuntimeError(f'Missing or invalid Ryan word timings: {section["id"]}')
    speech_end = max(float(w['start']) + float(w['duration']) for w in words)
    tempo = speech_end / (float(section['duration']) - .4)
    if not .78 <= tempo <= 1.22:
        raise RuntimeError(f'Natural speech fit is outside the allowed tempo range for {section["id"]}: {tempo:.3f}')
    fitted = [dict(w, start=section['start'] + float(w['start']) / tempo,
                   duration=float(w['duration']) / tempo, section_id=section['id']) for w in words]
    if any(w['start'] + w['duration'] > section['end'] for w in fitted):
        raise RuntimeError('Word boundary extends beyond its narration section')
    return tempo, fitted


def build_visual_timeline(show, words):
    beats, highlights = [], []
    by_id = {p['id']: p for p in show['package']['players']}
    for section in show['sections']:
        section_words = [w for w in words if w['section_id'] == section['id']]
        count = math.ceil(section['duration'] / 5)
        step = section['duration'] / count
        for i in range(count):
            phrase = section['phrases'][i % len(section['phrases'])]
            player_id, verdict = section['player_id'], section['verdict']
            if section['id'] == 'plan':
                d = show['decisions'][i % 3]
                player_id, verdict = d['player']['id'], d['verdict']
                phrase = {'text': verdict}
            beats.append({'start': section['start'] + step * i,
                          'end': section['start'] + step * (i + 1),
                          'phrase': phrase['text'], 'player_id': player_id,
                          'verdict': verdict, 'section': section['id'],
                          'variant': i % 3, 'transition': .4})
        for phrase in section['phrases']:
            at = word_time(section_words, phrase['anchor'], section['start'])
            highlights.append({'at': at, 'word': phrase['anchor'].upper(),
                               'phrase': phrase['text'], 'player_id': section['player_id'],
                               'section': section['id'], 'duration': .38})
        # Player names also receive a cue on their exact spoken word boundary.
        subjects = [d['player'] for d in show['decisions']]
        alt = show['decisions'][0].get('alternative')
        if alt:
            subjects.append(alt)
        for p in subjects:
            try:
                at = word_time(section_words, p['name'], section['start'])
            except RuntimeError:
                continue
            highlights.append({'at': at, 'word': p['name'].upper(), 'phrase': p['name'].upper(),
                               'player_id': p['id'], 'section': section['id'], 'duration': .38})
    for beat in beats:
        if not 3 <= beat['end'] - beat['start'] <= 6:
            raise RuntimeError('Visual change must occur every three to six seconds')
        if beat['player_id'] not in by_id or len(beat['phrase'].split()) > 5:
            raise RuntimeError('Invalid player or text budget on a visual beat')
    show['beats'] = beats
    show['highlights'] = sorted(highlights, key=lambda h: h['at'])
    show['words'] = words
    hook_words = [w for w in words if w['section_id'] == 'hook']
    show['impact_at'] = word_time(hook_words, 'captain')
    # Shorts end on a spoken sentence, without cutting an analysis mid-claim.
    for short, section in zip(show['shorts'], show['sections'][2:5]):
        section_words = [w for w in words if w['section_id'] == section['id']]
        cursor, ends = section['start'] - .01, []
        for sentence in re.split(r'(?<=[.!?])\s+', section['text']):
            anchor = ' '.join(_plain(sentence).split()[-3:])
            try:
                at, spoken_end = _phrase_span(section_words, anchor, cursor)
                following = next((w['start'] for w in section_words if w['start'] >= spoken_end), section['end'])
                clean_end = spoken_end + min(.2, max(0, following - spoken_end - .02))
                cursor = spoken_end
                if section['start'] + 15 <= clean_end <= section['start'] + 35:
                    ends.append(clean_end)
            except (RuntimeError, StopIteration):
                continue
        if not ends:
            raise RuntimeError(f'No clean sentence boundary for Short: {section["id"]}')
        short['end'] = min(ends, key=lambda t: abs(t - section['start'] - 28))
    return show


def _font_css():
    assets = Path(__file__).resolve().parents[1] / 'day2' / 'assets'
    styles = []
    for name, file in [('Inter', 'Inter.ttf'), ('Barlow', 'BarlowCondensed-SemiBold.ttf')]:
        data = base64.b64encode((assets / file).read_bytes()).decode()
        styles.append(f"@font-face{{font-family:{name};src:url(data:font/ttf;base64,{data}) format('truetype')}}")
    return ''.join(styles)


def show_html(show):
    # JSON is script-safe; names/news never become interpolated executable HTML.
    compact = dict(show)
    compact['package'] = {'players': show['package']['players']}
    data = json.dumps(compact, ensure_ascii=False).replace('</', '<\\/')
    css = r'''
    *{box-sizing:border-box}html,body{margin:0;background:#07101b;overflow:hidden}body{font-family:Inter,Arial,sans-serif;color:#fff}
    #stage{position:absolute;width:1920px;height:1080px;transform-origin:top left;overflow:hidden;background:radial-gradient(ellipse at 88% 48%,#123559 0,transparent 52%),linear-gradient(120deg,#060e18,#0d1827 60%,#081426)}
    #stage:before{content:"";position:absolute;inset:0;background-image:linear-gradient(#ffffff02 1px,transparent 1px),linear-gradient(90deg,#ffffff02 1px,transparent 1px);background-size:80px 80px}
    header{position:absolute;left:112px;right:112px;top:57px;display:flex;align-items:center;justify-content:space-between;z-index:5}#brand{display:flex;gap:18px;align-items:center;font-weight:900;letter-spacing:5px;font-size:24px}#brand svg{width:43px;height:47px}.gw{font-size:20px;letter-spacing:4px;color:#9aaec5;font-weight:700}
    .scene{position:absolute;inset:0;--accent:#ffd369}.kicker{position:absolute;left:120px;top:226px;font-size:20px;letter-spacing:5px;color:#91a7c0;text-transform:uppercase}.rule{position:absolute;left:120px;top:270px;height:5px;width:72px;background:var(--accent);border-radius:3px}.headline{position:absolute;left:113px;top:305px;width:980px;font-family:Barlow,Arial,sans-serif;font-size:158px;line-height:.98;letter-spacing:-2px;text-transform:uppercase;font-weight:600;overflow-wrap:normal;text-wrap:balance}.headline em{font-style:normal;color:var(--accent)}
    .lede{position:absolute;left:120px;top:733px;max-width:900px;font-size:27px;line-height:1.45;color:#91a6be}.decisionDots{position:absolute;left:120px;top:901px;display:flex;gap:12px}.decisionDots span{width:58px;height:6px;border-radius:5px;background:#253245}.decisionDots span.on{background:var(--accent)}
    .hero{position:absolute;left:1210px;top:171px;width:610px;height:790px;border:2px solid #3bcbf3;border-radius:30px;background:radial-gradient(ellipse at 0 20%,#00bcff88,transparent 58%),linear-gradient(122deg,#008cdd,#09276c 58%,#030a33);box-shadow:0 18px 80px #0009,inset 0 0 28px #32c5ff25;overflow:hidden;transform-origin:center center}
    .portrait{position:absolute;left:-54px;bottom:231px;width:377px;height:480px;object-fit:contain;object-position:center bottom;filter:drop-shadow(7px 10px 12px #0006)}.name{position:absolute;left:274px;right:20px;top:27px;font-family:Barlow;font-size:57px;line-height:1.04;font-weight:600;text-wrap:balance}.blueRule{position:absolute;left:275px;right:27px;top:162px;height:3px;background:#08bffe;box-shadow:0 0 8px #02b9ff}.club{position:absolute;left:280px;top:190px;width:275px;display:flex;gap:14px;align-items:center}.crest{height:61px;width:61px;object-fit:contain}.club span{font-size:23px;font-weight:750}.position{position:absolute;left:280px;top:289px;font-size:22px;color:#4ce6ff;font-weight:850;letter-spacing:2px}.pill{position:absolute;left:279px;right:25px;top:343px;padding:13px 10px;border:1px solid var(--accent);color:var(--accent);border-radius:10px;text-align:center;font-size:22px;line-height:1.3;font-weight:850;background:#030c27b5}.pill.long{font-size:19px}
    .fixtures{position:absolute;left:14px;right:14px;top:480px;display:grid;grid-template-columns:1fr;gap:7px}.fixture{height:105px;border-radius:10px;background:#041337cf;border:1px solid #44cfff66;display:flex;flex-direction:row;align-items:center;justify-content:center;gap:30px}.fixture b{font-size:46px}.fixture small{font-size:30px;color:#93c2df}.fixture.empty{opacity:.25}
    .evidence{position:absolute;left:15px;right:15px;bottom:15px;height:158px;border-radius:19px;background:#f3f7fb;display:flex;align-items:center;gap:23px;padding:25px;color:#111b35}.icon{flex:0 0 78px;height:78px;border-radius:18px;display:grid;place-items:center;background:var(--accent);color:#07101b;font-size:42px;font-weight:900}.evidence small{display:block;font-size:17px;color:#6a768b;letter-spacing:1px;font-weight:750;text-transform:uppercase}.evidence strong{font-family:Barlow;font-size:56px;line-height:1.1;display:block;max-width:390px}.evidence strong.long{font-size:37px}
    #caption{position:absolute;left:120px;right:120px;bottom:30px;text-align:center;font-size:28px;letter-spacing:.2px;font-weight:600;z-index:10;color:#cbd6e4}#caption span{padding:3px 5px;border-radius:5px}#caption span.active{background:#ffd369;color:#06101a}
    #wordFlash{position:absolute;left:120px;top:832px;font-size:20px;font-weight:800;letter-spacing:3px;color:#ffd369;z-index:11}#progress{position:absolute;left:0;bottom:0;height:4px;background:#3abafa;z-index:20}
    body.vertical #stage{width:1080px;height:1920px}body.vertical header{left:75px;right:75px;top:60px}body.vertical #brand{font-size:24px}body.vertical .gw{font-size:20px}body.vertical .kicker{left:75px;top:176px}body.vertical .rule{left:75px;top:220px}body.vertical .headline{left:70px;top:260px;width:940px;font-size:120px;line-height:1;max-height:260px}body.vertical .hero{left:235px;top:620px;transform:scale(1.12);transform-origin:top center}body.vertical .lede{display:none}body.vertical .decisionDots{left:75px;top:553px}body.vertical #wordFlash{left:75px;top:1580px;font-size:27px}body.vertical #caption{left:65px;right:65px;bottom:140px;font-size:46px;line-height:1.35}
    '''
    script = r'''
    const show=SHOW, players=Object.fromEntries(show.package.players.map(p=>[p.id,p]));
    const colors=COLORS, layers=[document.getElementById('a'),document.getElementById('b')];
    function el(tag,cls,text){const x=document.createElement(tag);if(cls)x.className=cls;if(text!==undefined)x.textContent=text;return x;}
    function evidence(beat,p){if(beat.section==='hook')return ['C','Captain points',String(show.accuracy.captain_points)];if(beat.section==='story')return ['✓','Points counted',String(p.points)];if(beat.section==='decision_1'&&beat.variant===0)return ['↗','Season starts',String(p.season_starts??'—')];if(beat.section==='decision_2'&&beat.variant===1)return ['↗',p.bench?'Unused bench':'GW points',String(p.points)];if(beat.section==='decision_3')return ['!','Official update',p.status==='a'?'Available':'Team news needed'];const f=p.next_fixture||{};return ['↗','Next fixture',f.opp?`${f.opp} · ${f.ha}`:'Not confirmed'];}
    function paint(root,beat){root.replaceChildren();const p=players[beat.player_id];let accent=colors[beat.verdict]||'#ffd369';if(beat.section==='hook'&&show.accuracy.captain_points<=4)accent='#ff6174';root.style.setProperty('--accent',accent);
      const labels={hook:'The captain call',story:'What actually counted',decision_1:'Decision 01',decision_2:'Decision 02',decision_3:'Decision 03',plan:'My early plan',cta:'Your decision'};
      root.append(el('div','kicker',labels[beat.section]));root.append(el('div','rule'));
      const headline=el('div','headline');headline.textContent=beat.phrase;root.append(headline);
      const dots=el('div','decisionDots');for(let i=0;i<3;i++){const dot=el('span',beat.section===`decision_${i+1}`?'on':'');dots.append(dot)}root.append(dots);
      const card=el('div','hero');const photo=el('img','portrait');photo.src=p.photo||'';photo.alt=p.name;card.append(photo);const name=el('div','name',p.name);if(p.name.length>15)name.style.fontSize='43px';card.append(name,el('div','blueRule'));
      const club=el('div','club');if(p.badge){const badge=el('img','crest');badge.src=p.badge;club.append(badge)}club.append(el('span','',p.team_name||p.team));card.append(club,el('div','position',p.pos));card.append(el('div','pill'+(beat.verdict.length>12?' long':''),beat.verdict));
      const fixtures=el('div','fixtures');const list=p.fixtures||[];const f=list[beat.variant%Math.max(1,list.length)];const tile=el('div','fixture'+(!f?' empty':''));tile.append(el('b','',f?`${f.opp} · ${f.ha}`:'—'),el('small','',f?`GW${f.gw}`:'—'));fixtures.append(tile);card.append(fixtures);
      const e=evidence(beat,p),panel=el('div','evidence');panel.append(el('div','icon',e[0]));const copy=el('div','');copy.append(el('small','',e[1]),el('strong',e[2].length>14?'long':'',e[2]));panel.append(copy);card.append(panel);root.append(card);
    }
    let lastA=-1,lastB=-1;window.seek=(time)=>{const t=Math.max(0,Math.min(show.duration-.001,time));let index=show.beats.findIndex(b=>t>=b.start&&t<b.end);if(index<0)index=show.beats.length-1;const beat=show.beats[index],prior=show.beats[Math.max(0,index-1)];if(lastA!==index-1){paint(layers[0],prior);lastA=index-1}if(lastB!==index){paint(layers[1],beat);lastB=index}
      const x=index===0?1:Math.min(1,(t-beat.start)/.4),ease=x*x*(3-2*x);layers[0].style.opacity=String(1-ease);layers[1].style.opacity=String(ease);
      const words=show.words||[];let wi=words.findIndex(w=>t>=w.start&&t<w.start+w.duration);const caption=document.getElementById('caption');caption.replaceChildren();if(wi>=0){const start=Math.floor(wi/5)*5;for(let k=start;k<Math.min(words.length,start+5);k++)caption.append(el('span',k===wi?'active':'',words[k].text));}
      const h=(show.highlights||[]).find(h=>t>=h.at&&t<h.at+h.duration);document.getElementById('wordFlash').textContent=h?h.word:'';document.getElementById('wordFlash').style.opacity=h?'1':'0';document.getElementById('progress').style.width=`${t/show.duration*100}%`;
    };
    window.setFormat=(w,h,vertical=false)=>{document.body.classList.toggle('vertical',vertical);document.getElementById('stage').style.transform=`scale(${w/(vertical?1080:1920)},${h/(vertical?1920:1080)})`;};setFormat(1920,1080);seek(0);
    '''.replace('SHOW', data).replace('COLORS', json.dumps(COLORS))
    logo = str(show.get('brand_logo') or '')
    brand_mark = ('<img alt="" style="width:62px;height:62px;object-fit:contain" src="' + escape(logo, quote=True) + '">') if logo.startswith('data:image/') else ''
    return ('<!doctype html><html><head><meta charset="utf-8"><style>' + _font_css() + css +
            '</style></head><body><div id="stage"><header><div id="brand">' +
            brand_mark + 'FPL VORTEX</div><div class="gw">GW' + str(show['preview_gw']) +
            '</div></header><div id="a" class="scene"></div><div id="b" class="scene"></div>'
            '<div id="wordFlash"></div><div id="caption"></div><div id="progress"></div></div><script>' + script + '</script></body></html>')


async def synthesize_show(show, work, tts):
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    words, files = [], []
    for section in show['sections']:
        desired_wpm = len(section['text'].split()) * 60 / (section['duration'] - .4)
        rate = max(-15, min(12, round((desired_wpm / 155 - 1) * 100)))
        profile = {'rate': f'{rate:+d}%', 'pitch': '-2Hz', 'volume': '+0%'}
        payload, boundaries = await tts(section['text'], profile)
        raw = work / f'{section["id"]}.mp3'
        raw.write_bytes(payload)
        tempo, fitted = fit_word_timing(section, boundaries)
        # Slow/fast transport output outside the fit gate must not silently
        # become minutes of padding or a rushed voice.
        wav = work / f'{section["id"]}.wav'
        _run(['ffmpeg', '-y', '-v', 'error', '-i', str(raw), '-af',
              f'atempo={tempo:.9f},apad=whole_dur={section["duration"]},atrim=duration={section["duration"]}',
              '-ar', '48000', '-ac', '2', '-c:a', 'pcm_s16le', str(wav)])
        section['tts_profile'] = profile
        section['audio_tempo'] = tempo
        files.append(wav)
        words.extend(fitted)
        print(f'Ryan section ready: {section["id"]} ({section["duration"]}s; measured word timings)', flush=True)
    listing = work / 'narration.ffconcat'
    listing.write_text(''.join(f"file '{_concat_quote(p)}'\n" for p in files))
    audio = work / 'day1_show.mp3'
    _run(['ffmpeg', '-y', '-v', 'error', '-f', 'concat', '-safe', '0', '-i', str(listing),
          '-c:a', 'libmp3lame', '-b:a', '192k', '-ar', '48000', str(audio)])
    build_visual_timeline(show, words)
    return audio


def sample_times(show, start=0, end=None):
    end = show['duration'] if end is None else end
    times = {float(start), end - 1 / 24}
    for beat in show['beats']:
        if start <= beat['start'] < end:
            times.update(beat['start'] + i / 12 for i in range(6) if beat['start'] + i / 12 < end)
        if start < beat['end'] < end:
            times.add(beat['end'] - 1 / 24)
    for event in show.get('highlights', []):
        for t in (event['at'], event['at'] + event['duration']):
            if start <= t < end:
                times.add(t)
    # Full word captions are drawn by libass on the 24fps frame clock. Browser
    # captures are needed only for visual transitions and major keyword cues.
    return sorted(t for t in times if start <= t < end)


def caption_ass(show, start=0, end=None, vertical=False):
    end = show['duration'] if end is None else end
    width, height, size, y = (1080, 1920, 46, 1740) if vertical else (1920, 1080, 30, 1030)
    def ts(t):
        cs = max(0, round(t * 100))
        return f'{cs//360000}:{cs//6000%60:02}:{cs//100%60:02}.{cs%100:02}'
    lines = ['[Script Info]', 'ScriptType: v4.00+', f'PlayResX: {width}', f'PlayResY: {height}',
             'WrapStyle: 2', '[V4+ Styles]',
             'Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding',
             f'Style: Caption,Inter,{size},&H00FFFFFF,&H0069D3FF,&H00100806,&H80100806,-1,0,0,0,100,100,0,0,1,1.5,1,5,50,50,20,1',
             '[Events]', 'Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text']
    words = show.get('words', [])
    section_words = {}
    local_index = {}
    for word in words:
        group = section_words.setdefault(word['section_id'], [])
        local_index[id(word)] = len(group)
        group.append(word)
    for i, word in enumerate(words):
        if not start <= word['start'] < end:
            continue
        until = min(end, words[i + 1]['start'] if i + 1 < len(words) else word['start'] + word['duration'])
        local = local_index[id(word)]
        group = section_words[word['section_id']][local//5*5:local//5*5+5]
        text = []
        for other in group:
            clean = str(other['text']).replace('\\', '/').replace('{', '(').replace('}', ')').replace('\n', ' ')
            text.append(('{\\c&H0069D3FF&}' if other is word else '{\\c&H00FFFFFF&}') + clean)
        line = '{\\an5\\pos(' + f'{width//2},{y}' + ')}' + ' '.join(text)
        lines.append(f'Dialogue: 0,{ts(word["start"]-start)},{ts(until-start)},Caption,,0,0,0,,{line}')
    return '\n'.join(lines) + '\n'


def encode_frames(frames, audio, output, duration, fps=24, audio_start=0, captions=None, audio_duration=None):
    # Manifests and ASS files stay in scratch work, outside the output contract.
    listing = Path(frames[0][1]).parent / 'frames.ffconcat'
    held = []
    for item in frames:
        if held and item[0] - held[-1][0] > .2:
            held.append((item[0] - 1 / fps, held[-1][1]))
        held.append(item)
    frames = held
    rows = ['ffconcat version 1.0']
    for i, (t, path) in enumerate(frames):
        until = frames[i + 1][0] if i + 1 < len(frames) else duration
        rows += [f"file '{_concat_quote(path)}'", f'duration {max(.00001, until - t):.9f}']
    rows += [f"file '{_concat_quote(frames[-1][1])}'"]
    listing.write_text('\n'.join(rows) + '\n')
    vf = f'framerate=fps={fps}:scene=100,fps={fps}:round=near,format=yuv420p'
    if captions:
        fonts = Path(__file__).resolve().parents[1] / 'day2/assets'
        vf += f",subtitles=filename='{Path(captions)}':fontsdir='{fonts}'"
    audio_length = duration if audio_duration is None else audio_duration
    _run(['ffmpeg', '-y', '-v', 'error', '-f', 'concat', '-safe', '0', '-i', str(listing),
          '-ss', f'{audio_start:.9f}', '-i', str(audio), '-map', '0:v:0', '-map', '1:a:0',
          '-vf', vf, '-fps_mode', 'cfr',
          '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18', '-threads', '2',
          '-af', f'aresample=48000:async=1:first_pts=0,atrim=duration={audio_length:.9f},apad', '-c:a', 'aac', '-b:a', '192k',
          '-ar', '48000', '-ac', '2', '-t', f'{duration:.9f}', '-movflags', '+faststart', str(output)])
    _validate_results_video(output, fps, duration)


async def capture_show(show, work, audio, output, width=3840, height=2160, start=0, end=None, vertical=False):
    from .day1_remotion import capture_show as capture_remotion
    return await capture_remotion(show, work, audio, output, width, height, start, end, vertical)


def _vtt(words):
    def stamp(t):
        ms = round(t * 1000)
        return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02}.{ms%1000:03}'
    lines = ['WEBVTT', '']
    for i in range(0, len(words), 5):
        chunk = words[i:i + 5]
        lines += [f'{stamp(chunk[0]["start"])} --> {stamp(chunk[-1]["start"]+chunk[-1]["duration"])}',
                  ' '.join(w['text'] for w in chunk), '']
    return '\n'.join(lines)


async def render_show(ns):
    import shutil
    show = ns['DAY1_SHOW']
    work = Path(ns['VIDEO_WORK_DIR']) / 'decision_show'
    audio = await synthesize_show(show, work, ns['vx_edge_tts_stream'])
    output = Path(ns['MP4_DIR']) / '00_intro.mp4'
    frames = await capture_show(show, work / 'landscape', audio, output,
                                int(ns.get('VIDEO_WIDTH', 3840)), int(ns.get('VIDEO_HEIGHT', 2160)))
    shutil.copy2(audio, Path(ns['MP3_DIR']) / 'day1_show.mp3')
    shutil.copy2(frames[0][1], Path(ns['SLIDE_DIR']) / 'intro_scene_4k.png')
    shutil.copy2(work / 'landscape/remotion-qa.json', Path(ns['DATA_DIR']) / 'day1_remotion_qa.json')
    _json(Path(ns['DATA_DIR']) / 'day1_show.json', show)
    (Path(ns['DATA_DIR']) / 'day1_show.vtt').write_text(_vtt(show['words']), encoding='utf-8')
    # The brief is a separate workflow artifact, never a text file inside DATA.
    (work / 'FPL_VORTEX_Production_Brief.md').write_text(production_brief(show), encoding='utf-8')
    print('Premium decision show: 4K/24fps video and exact word-timing QA PASS')


async def render_shorts(output_root):
    root = Path(output_root)
    show = json.loads((root / 'DATA/day1_show.json').read_text())
    qa = json.loads((root / 'DATA/final_video_qa.json').read_text())
    # Use the finished, music-mixed audio. Time zero is the spoken hook.
    audio = Path(qa['final_file'])
    work = Path('/content/FPL_VORTEX_FIRST_DAY_WORK/video/decision_show/shorts')
    for i, short in enumerate(show['shorts'], 1):
        output = root / 'MP4' / f'day1_short_{i}.mp4'
        await capture_show(show, work / str(i), audio, output, 1080, 1920,
                           short['start'], short['end'], vertical=True)
        short['file'] = str(output)
    _json(root / 'DATA/day1_show.json', show)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--shorts', action='store_true')
    parser.add_argument('--output-root', type=Path, default=Path('/content/drive/MyDrive/FPL_VORTEX/FIRST VIDEO'))
    args = parser.parse_args()
    if args.shorts:
        asyncio.run(render_shorts(args.output_root))


if __name__ == '__main__':
    main()
