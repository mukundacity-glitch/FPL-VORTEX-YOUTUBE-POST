"""Day 1 Scene 2. Official retrospective data, original Hero Card, measured speech.

The production entry point is called by Cell 17. The CLI renders the identical
section for approval without running account uploads or other Day 1 chapters.
"""
from __future__ import annotations

import argparse
import ast
import asyncio
import base64
from datetime import datetime, timezone
from html import escape
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import time
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from .day1_brief import build_brief, build_intro_agenda, caption_cues, render_brief
from .day1_editorial import word_timed_vtt

ROOT = Path(__file__).resolve().parents[1]
API = 'https://fantasy.premierleague.com/api'
EASTERN = ZoneInfo('America/New_York')
VERSION = 'DAY1-SCENE2-HERO-1'


def fetch_json(path):
    """Fetch a new official response, retaining the endpoint and retrieval time."""
    for attempt in range(3):
        try:
            req = Request(API + path, headers={'User-Agent': 'FPL-VORTEX-Scene2', 'Cache-Control': 'no-cache'})
            with urlopen(req, timeout=30) as response:
                data = json.load(response)
            return data, dict(source=API + path, retrievedAt=datetime.now(timezone.utc).isoformat())
        except Exception:
            if attempt == 2:
                raise
            time.sleep(attempt + 1)


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def field(value, meta, gw, status='FINAL', methodology=None):
    stamp = datetime.fromisoformat(meta['retrievedAt'])
    age = (datetime.now(timezone.utc) - stamp).total_seconds()
    return dict(value=value, source=meta['source'], retrievedAt=meta['retrievedAt'], gameweek=gw,
                freshnessStatus='fresh' if -60 <= age <= 3600 else 'stale', dataStatus=status,
                confidence='official' if methodology is None else 'derived', methodologyVersion=methodology)


def display(value, decimals=None):
    if value is None:
        return 'N/A'
    if isinstance(value, float):
        return f'{value:.{decimals if decimals is not None else 1}f}'
    return str(value)


def completed_gameweek(boot, fixtures):
    eligible = []
    for event in boot.get('events', []):
        rows = [f for f in fixtures if f.get('event') == event['id']]
        if event.get('finished') and event.get('data_checked') and rows and all(
                f.get('finished') and f.get('team_h_score') is not None and f.get('team_a_score') is not None for f in rows):
            eligible.append(event['id'])
    if not eligible:
        raise ValueError('No fully completed, data-checked Gameweek. Final review rendering is blocked.')
    return max(eligible)


def select_players(boot, live):
    """Select distinct editorial stories, rather than five rows from the points sort."""
    identities = {p['id']: p for p in boot['elements']}
    candidates = [dict(id=row['id'], **row['stats']) for row in live['elements']
                  if row['id'] in identities and number(row['stats'].get('minutes')) and
                  number(row['stats'].get('total_points')) is not None]
    chosen = []

    def pick(label, rows, key):
        available = [p for p in rows if p['id'] not in {x['id'] for x in chosen}]
        if available:
            chosen.append(dict(max(available, key=key), story=label))

    pick('GAMEWEEK STANDOUT', candidates, lambda p: (p['total_points'], p['minutes']))
    attackers = [p for p in candidates if p.get('goals_scored', 0) + p.get('assists', 0) > 0]
    pick('SECOND MAJOR PERFORMER', attackers, lambda p: (p.get('goals_scored', 0) + p.get('assists', 0), p['total_points']))
    premiums = [p for p in candidates if number(identities[p['id']].get('now_cost')) is not None and
                identities[p['id']]['now_cost'] >= 90 and p['total_points'] <= 4]
    pick('PREMIUM UNDER SCRUTINY', premiums, lambda p: (identities[p['id']]['now_cost'], p['minutes']))
    differentials = [p for p in candidates if number(identities[p['id']].get('selected_by_percent')) is not None and
                     float(identities[p['id']]['selected_by_percent']) < 10 and p['total_points'] >= 7]
    pick('SURPRISE RETURN', differentials, lambda p: p['total_points'])
    decisions = [p for p in candidates if identities[p['id']].get('status') not in ('a', None) or
                 (p['minutes'] < 60 and float(identities[p['id']].get('selected_by_percent') or 0) >= 10)]
    pick('IMPORTANT MINUTES / AVAILABILITY CHECK', decisions,
         lambda p: float(identities[p['id']].get('selected_by_percent') or 0))
    return chosen


def sum_verified(rows, key):
    values = [number(row.get(key)) for row in rows]
    if not rows or any(value is None for value in values):
        return None
    total = sum(values)
    return int(total) if all(float(v).is_integer() for v in values) else round(total, 3)


def original_photo_urls(identity):
    tree = ast.parse((ROOT / '1_final_day1.py').read_text())
    value = next(ast.literal_eval(n.value) for n in ast.walk(tree) if isinstance(n, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == '_VX_DAY1_WC_FH_IMAGE_SOURCE' for t in n.targets))
    image_tree = ast.parse(value)
    names = {'_row', '_player_code', 'official_photo_urls'}
    nodes = [n for n in image_tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    constants = {n.targets[0].id: ast.literal_eval(n.value) for n in image_tree.body if isinstance(n, ast.Assign)
                 and isinstance(n.targets[0], ast.Name) and n.targets[0].id in {'PL_PHOTO_BASE_CURRENT', 'PL_PHOTO_BASE_LEGACY'}}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), 'original-photo-chain', 'exec'), constants)
    return constants['official_photo_urls'](identity)


def build_player(identity, stats, summary, meta, boot, fixtures, gw, next_gw, story):
    teams = {t['id']: t for t in boot['teams']}
    positions = {p['id']: p['singular_name_short'] for p in boot['element_types']}
    team = teams[identity['team']]
    history = [h for h in summary.get('history', []) if h.get('round', 99) <= gw]
    review = [h for h in history if h.get('round') == gw]
    recent = [h for h in history if gw - 4 <= h.get('round', 0) <= gw]
    # A DGW has multiple rows. Never mistake the last row for the entire GW.
    for key in ('total_points', 'minutes', 'goals_scored', 'assists'):
        aggregate = sum_verified(review, key)
        if aggregate is not None and aggregate != stats.get(key):
            raise ValueError(f'Live/summary mismatch for player {identity["id"]}, {key}')
    values = {key: field(stats.get(key), meta['live'], gw) for key in
              ('total_points', 'minutes', 'goals_scored', 'assists', 'clean_sheets', 'bonus', 'saves',
               'yellow_cards', 'red_cards', 'own_goals', 'penalties_saved', 'penalties_missed', 'starts')}
    for key in ('expected_goals', 'expected_assists'):
        values[key] = field(sum_verified(review, key), meta['summary'], gw)
    for key in ('status', 'news', 'chance_of_playing_next_round', 'now_cost', 'selected_by_percent'):
        values[key] = field(identity.get(key), meta['bootstrap'], next_gw, 'CURRENT FPL SNAPSHOT')
    values['recent_minutes'] = field(sum_verified(recent, 'minutes'), meta['summary'], gw,
                                    methodology='Sum of official rows in last five GW, v1')
    values['recent_starts'] = field(sum_verified(recent, 'starts'), meta['summary'], gw,
                                   methodology='Sum of official starts in last five GW, v1')
    values['recent_xg'] = field(sum_verified(recent, 'expected_goals'), meta['summary'], gw,
                              methodology='Sum of official expected goals in last five GW, v1')
    values['recent_xa'] = field(sum_verified(recent, 'expected_assists'), meta['summary'], gw,
                              methodology='Sum of official expected assists in last five GW, v1')
    upcoming = sorted([f for f in fixtures if f.get('event') and f['event'] >= next_gw and
                       identity['team'] in (f.get('team_h'), f.get('team_a'))],
                      key=lambda f: (f['event'], f.get('kickoff_time') or ''))[:5]
    outlook = []
    for fixture in upcoming:
        home = fixture['team_h'] == identity['team']
        opponent = teams[fixture['team_a'] if home else fixture['team_h']]
        outlook.append(dict(gw=fixture['event'], opponent=opponent['short_name'],
                            opponentName=opponent['name'], venue='H' if home else 'A',
                            fdr=fixture.get('team_h_difficulty' if home else 'team_a_difficulty'),
                            source=meta['fixtures'], status='Official overall FDR, 1–5; not a probability',
                            badge=f'https://resources.premierleague.com/premierleague/badges/t{opponent["code"]}.png'))
    starts = values['recent_starts']['value']
    available = identity.get('status') == 'a'
    verdict = 'HOLD' if available and starts is not None and starts >= 4 and outlook else 'MONITOR'
    minutes_assessment = dict(label='Likely starter' if available and starts is not None and starts >= 4 else 'Starting place uncertain',
                              confidence='medium' if available and starts is not None and starts >= 4 else 'low',
                              dataStatus='EDITORIAL ESTIMATE', source=[meta['bootstrap'], meta['summary']],
                              methodologyVersion='Recent five-GW starts plus FPL status v1',
                              limitation='No manager-confirmed lineup. Expected minutes unavailable.')
    reason = ('Recent starts support holding for existing owners. Recheck team news before the deadline.'
              if verdict == 'HOLD' else 'Resolve the availability or starting-minutes uncertainty before a transfer.')
    if not available:
        reason = 'Check the latest official FPL flag and club update before committing a transfer.'
    season_minutes = number(identity.get('minutes'))
    per90 = lambda key: round(float(identity[key]) * 90 / season_minutes, 2) if number(identity.get(key)) is not None and season_minutes else None
    rows = [('ball', 'xG PER 90', per90('expected_goals')), ('boot', 'xA PER 90', per90('expected_assists')),
            ('target', 'GOALS PER 90', per90('goals_scored')), ('assist', 'ASSISTS PER 90', per90('assists')),
            ('shield', 'CLEAN SHEETS', identity.get('clean_sheets')), ('star', 'POINTS PER MATCH', number(identity.get('points_per_game')))]
    season_deadlines = [e['deadline_time'] for e in boot['events'] if e.get('deadline_time')]
    first = datetime.fromisoformat(min(season_deadlines).replace('Z', '+00:00'))
    year = first.year if first.month >= 7 else first.year - 1
    season = f'{year}/{str(year + 1)[-2:]}'
    card = dict(id=identity['id'], name=identity['web_name'], full_name=identity['first_name'] + ' ' + identity['second_name'],
                first_name=identity['first_name'], surname=identity['second_name'], club=team['name'],
                position=positions[identity['element_type']], position_label=positions[identity['element_type']],
                club_badge=f'https://resources.premierleague.com/premierleague/badges/t{team["code"]}.png',
                player_image=f'https://resources.premierleague.com/premierleague/photos/players/250x250/p{identity["code"]}.png',
                price=f'£{identity["now_cost"] / 10:.1f}m' if identity.get('now_cost') is not None else 'N/A',
                ownership=f'{identity["selected_by_percent"]}%' if identity.get('selected_by_percent') is not None else 'N/A',
                season_label=season,
                display_stats=[dict(icon=i, label=l, value=display(v, 2)) for i, l, v in rows],
                fixtures=[dict(gw=f['gw'], opponent=f['opponent'], venue=f['venue'], fdr_value=f['fdr'],
                               fixdiff=f['fdr'], badge=f['badge']) for f in outlook])
    return dict(id=identity['id'], name=identity['web_name'], club=team['name'], position=positions[identity['element_type']],
                story=story, fields=values, fixtures=outlook, card=card, verdict=verdict, reason=reason,
                photoSources=original_photo_urls(identity), cardSource=meta['bootstrap'], minutesAssessment=minutes_assessment,
                verdictStatus='FPL VORTEX editorial judgement; conditional',
                limitations=['Shots, big chances and tactical role are not verified by these endpoints.',
                             'Expected minutes unavailable. Official status a is not a club-confirmed fitness statement.',
                             'FDR is the official overall rating. Split attack/defence model unavailable.'])


def collect_review():
    boot, boot_meta = fetch_json('/bootstrap-static/')
    fixtures, fixture_meta = fetch_json('/fixtures/')
    gw = completed_gameweek(boot, fixtures)
    next_event = next((e for e in boot['events'] if e.get('is_next')), None)
    if not next_event:
        raise ValueError('No verified upcoming FPL Gameweek. No future fixture recommendation will be invented.')
    next_gw = next_event['id']
    live, live_meta = fetch_json(f'/event/{gw}/live/')
    selected = select_players(boot, live)
    players = []
    for selected_player in selected:
        pid = selected_player['id']
        identity = next(p for p in boot['elements'] if p['id'] == pid)
        summary, summary_meta = fetch_json(f'/element-summary/{pid}/')
        players.append(build_player(identity, selected_player, summary,
            dict(bootstrap=boot_meta, fixtures=fixture_meta, live=live_meta, summary=summary_meta),
            boot, fixtures, gw, next_gw, selected_player['story']))
    if len(players) < 3:
        raise ValueError('Fewer than three distinct verified player stories. Review generation requires editorial review.')
    review_fixtures = [f for f in fixtures if f.get('event') == gw]
    scoreboard = dict(completed=field(len(review_fixtures), fixture_meta, gw),
                      goals=field(sum(f['team_h_score'] + f['team_a_score'] for f in review_fixtures), fixture_meta, gw),
                      topPoints=field(max(row['stats']['total_points'] for row in live['elements']), live_meta, gw))
    snapshot = dict(gw=gw, status='FINAL', bootstrap=boot, fixtures=fixtures, live=live,
                    provenance=dict(bootstrap=boot_meta, fixtures=fixture_meta, live=live_meta))
    return dict(version=VERSION, gameweek=gw, nextGameweek=next_gw, status='FINAL', players=players,
                overview=scoreboard, sourceMetadata=dict(bootstrap=boot_meta, fixtures=fixture_meta, live=live_meta),
                brief=build_brief(snapshot, next_gw=next_gw),
                selectionMethod='Distinct standout, contribution, premium, low-ownership and minutes/availability stories v1')


def player_script(player, gw, index):
    f = {key: item['value'] for key, item in player['fields'].items()}
    index = ['GAMEWEEK STANDOUT', 'SECOND MAJOR PERFORMER', 'PREMIUM UNDER SCRUTINY', 'SURPRISE RETURN', 'IMPORTANT MINUTES / AVAILABILITY CHECK'].index(player['story'])
    introductions = [f'The Gameweek standout is {player["name"]}.',
                     f'Another major contribution came from {player["name"]}.',
                     f'The premium decision is {player["name"]}.',
                     f'For a lower-owned return, look at {player["name"]}.',
                     f'The decision to check carefully is {player["name"]}.']
    opening = introductions[min(index, 4)]
    unit = lambda value, singular: f'{value} {singular}' + ('' if value == 1 else 's')
    result = f'{unit(f["total_points"], "point")}, {unit(f["goals_scored"], "goal")} and {unit(f["assists"], "assist")}, across {f["minutes"]} minutes.'
    xg, xa = f['expected_goals'], f['expected_assists']
    underlying = (f'Expected goals were {xg:.2f}, and expected assists {xa:.2f}.' if xg is not None and xa is not None
                  else 'The underlying numbers are incomplete, so they cannot settle the transfer decision.')
    recent_xg = f['recent_xg']
    recent_xa = f['recent_xa']
    interpretations = [
        f"The return includes {unit(f['clean_sheets'], 'clean sheet')} and {f['bonus']} bonus points. Repeated starts are the stronger evidence for holding than assuming another goal.",
        ('The goal and assist returns outpaced the expected attacking involvement this week. Treat that as a reason to check the longer sample, not chase the score.' if xg is not None and xa is not None and f['goals_scored'] + f['assists'] > xg + xa + .5 else 'The attacking return adds evidence, but the next opponent and repeated minutes still decide the transfer.'),
        (f"Across the last five Gameweeks, expected goals total {recent_xg:.2f}. That wider opportunity matters more than reacting to a single blank." if recent_xg is not None else 'A single low return cannot establish a decline. The longer underlying sample is unavailable.'),
        (f"Current ownership is {f['selected_by_percent']} percent. With {f['recent_starts']} starts in the last five Gameweeks, minutes deserve checking before the low ownership." if f['recent_starts'] is not None else 'Low ownership does not establish a secure starting role. Recent starts are unavailable.'),
        (f"The last five Gameweeks total {f['recent_minutes']} minutes. An attractive opponent does not remove uncertainty over the next start." if f['recent_minutes'] is not None else 'Recent minutes are unavailable. Check the next starting role before acting on the fixture.')]
    minutes = (f'The last five Gameweeks contain {f["recent_starts"]} starts.' if f['recent_starts'] is not None
               else 'Recent starting evidence is incomplete.')
    if index == 3:
        minutes = ''
    availability = '' if f['status'] == 'a' else 'Check the current FPL availability flag.'
    next_fixture = player['fixtures'][0] if player['fixtures'] else None
    fixture = (f'Next is {next_fixture["opponentName"]}, {"at home" if next_fixture["venue"] == "H" else "away"}.'
               if next_fixture else 'The next fixture is not verified.')
    verdict = ('Hold for existing owners, subject to final team news.' if player['verdict'] == 'HOLD'
               else 'Monitor. Resolve the minutes or fitness question before making the move.')
    return ' '.join(part for part in (opening, result, underlying, interpretations[min(index, 4)], minutes, availability, fixture, verdict) if part)


def scripts_for(review):
    gw = review['gameweek']
    o = review['overview']
    segments = [dict(id='chapter', kind='chapter', text='Gameweek review. The real story.', minimum=5),
                dict(id='overview', kind='overview', minimum=10,
                     text=f'Gameweek {gw} is complete. {o["completed"]["value"]} fixtures produced {o["goals"]["value"]} goals. '
                          f'The highest individual FPL return was {o["topPoints"]["value"]} points. Now, which performances should change the next decision?')]
    for index, player in enumerate(review['players']):
        segments.append(dict(id=f'player_{player["id"]}', kind='player', player_id=player['id'], minimum=0,
                             text=player_script(player, gw, index)))
    players = review['players']
    minutes_case = min(players, key=lambda p: p['fields']['minutes']['value'])
    minutes_played = minutes_case['fields']['minutes']['value']
    chance_cases = [p for p in players if all(p['fields'][key]['value'] is not None for key in ('expected_goals', 'expected_assists'))]

    def attacking_gap(player):
        values = player['fields']
        return (values['goals_scored']['value'] + values['assists']['value']
                - values['expected_goals']['value'] - values['expected_assists']['value'])

    chance_case = max(chance_cases, key=attacking_gap, default=None)
    chance_explanation = 'The underlying sample is incomplete for these players.'
    chance_voice = 'Use verified chance data to put returns in context.'
    if chance_case:
        values = chance_case['fields']
        returns = values['goals_scored']['value'] + values['assists']['value']
        xgi = values['expected_goals']['value'] + values['expected_assists']['value']
        chance_explanation = f'{chance_case["name"]} recorded {returns} attacking returns against {xgi:.2f} expected goal involvements.'
        chance_voice = (f'{chance_case["name"]} returned more than his expected involvement this week.'
                        if attacking_gap(chance_case) > 0 else f'{chance_case["name"]} shows why chances and returns need separate readings.')
    fixture_case = next((p for p in players if p['verdict'] == 'HOLD' and p['fixtures']), None)
    fixture_explanation = 'Check each verified upcoming opponent and venue before making a move.'
    fixture_voice = 'Check the fixture alongside the starting evidence.'
    if fixture_case:
        fixture = fixture_case['fixtures'][0]
        venue = 'at home' if fixture['venue'] == 'H' else 'away'
        fixture_explanation = f'{fixture_case["name"]} faces {fixture["opponentName"]} {venue}. Official overall FDR {display(fixture["fdr"])}.'
        fixture_voice = f'For {fixture_case["name"]}, {fixture["opponentName"]} {venue} is the next fixture to assess.'
    review['takeaways'] = [
        dict(heading='MINUTES AND ROLE', explanation=f'{minutes_case["name"]} played {minutes_played} minutes in Gameweek {gw}.',
             implication='Check repeated starts before backing the fixture.'),
        dict(heading='UNDERLYING PERFORMANCE', explanation=chance_explanation,
             implication='Keep a single return in the context of the longer sample.'),
        dict(heading='NEXT-FIXTURE OPPORTUNITY', explanation=fixture_explanation,
             implication='Combine the fixture with availability and starting evidence.')]
    segments.append(dict(id='takeaways', kind='takeaways', minimum=12,
        text=f'Three lessons. {minutes_case["name"]} shows why the starting role matters. {chance_voice} {fixture_voice} Check all three before using a transfer.'))
    segments.append(dict(id='next', kind='next', minimum=4,
                         text='Next, players and fixtures. Who deserves your attention now?'))
    return segments


def original_card_literals(source=None):
    """Extract the authoritative literal strings without executing notebook cells."""
    tree = ast.parse(source or (ROOT / '1_final_day1.py').read_text())
    found = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id in ('PLAYER_CARD_CSS', 'PLAYER_CARD_JS'):
                found[node.targets[0].id] = ast.literal_eval(node.value)
    if len(found) != 2:
        raise ValueError('The original Hero Card CSS and runtime are required')
    return found


def render_scene(review, segments, logo_html):
    cards = build_intro_agenda(['00_intro', 'gw_review'], next_gw=review['nextGameweek'],
        review_gw=review['gameweek'], review_status='FINAL',
        review_segments=[dict(id=x) for x in ('headline', 'editorial_squad_context', 'editorial_routes', 'editorial_verdict')],
        brief=review['brief'])
    base = render_brief(review['brief'], logo_html=logo_html, cards=cards)
    original = original_card_literals()
    css = (ROOT / 'vortex/day1_scene2.css').read_text().replace('__INTER_FONT__', base64.b64encode((ROOT / 'day2/assets/Inter.ttf').read_bytes()).decode())
    runtime = (ROOT / 'vortex/day1_scene2.js').read_text()
    payload = json.dumps(dict(review={k: v for k, v in review.items() if k != 'brief'}, segments=segments, cardCss=original['PLAYER_CARD_CSS']), ensure_ascii=False).replace('<', '\\u003c')
    head = base[:base.index('<main>')]
    broadcast = re.search(r'<section class="broadcast".*?</section>', base, flags=re.S).group(0)
    base = head + '<main>' + broadcast + '</main><div class="captions"><span></span></div></body></html>'
    content = '<div id="scene2" aria-label="Gameweek Review"><div id="scene2-content"></div></div>'
    base = base.replace('</head>', '<style>' + css + '</style></head>')
    base = base.replace('</body>', content + original['PLAYER_CARD_JS'] + '<script>const SCENE2=' + payload + ';\n' + runtime + '</script></body>')
    return base


def probe(path):
    return json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)]))


def local_asset(url, cache, *, required=True):
    """Embed authentic ID-based media. A missing photo fails the production gate."""
    path = cache / hashlib.sha256(url.encode()).hexdigest()
    if not path.exists():
        try:
            with urlopen(Request(url, headers={'User-Agent': 'FPL-VORTEX'}), timeout=25) as response:
                data = response.read()
                mime = response.headers.get_content_type()
            if not mime.startswith('image/'):
                raise ValueError('Image endpoint returned non-image content')
            path.write_text(json.dumps(dict(mime=mime, data=base64.b64encode(data).decode())))
        except Exception:
            if required:
                raise RuntimeError(f'Authentic player/club asset unavailable at {url}')
            return ''
    asset = json.loads(path.read_text())
    return 'data:' + asset['mime'] + ';base64,' + asset['data']


async def narrate(segments, output):
    import edge_tts
    offset = 0.0
    paths = []
    for index, segment in enumerate(segments):
        audio = bytearray()
        words = []
        async for chunk in edge_tts.Communicate(segment['text'], 'en-GB-RyanNeural', rate='+0%', pitch='-4Hz', boundary='WordBoundary').stream():
            if chunk['type'] == 'audio':
                audio.extend(chunk['data'])
            elif chunk['type'] == 'WordBoundary':
                words.append(dict(text=chunk['text'], start=chunk['offset'] / 1e7, duration=chunk['duration'] / 1e7))
        path = output / f'speech-{index}.mp3'
        path.write_bytes(audio)
        duration = float(probe(path)['format']['duration'])
        duration = max(duration + .25, segment['minimum'])
        wav = output / f'speech-{index}.wav'
        subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', str(path), '-af', 'apad', '-t', str(duration),
                        '-ar', '48000', '-ac', '1', str(wav)], check=True)
        paths.append(wav)
        segment.update(t0=round(offset, 6), t1=round(offset + duration, 6), words=words,
                       captions=[dict(start=offset + c['start'], end=offset + c['end'], text=c['text']) for c in caption_cues(words)])
        cues = {}
        for key, phrase in dict(points='points', goals='goals', assists='assists', minutes='minutes', xg='Expected goals', xa='expected assists', next='Next is', verdict=segment.get('verdict', 'Hold' if 'Hold for' in segment['text'] else 'Monitor')).items():
            needles = [phrase.lower().split()]
            if key in ('points', 'goals', 'assists', 'minutes'):
                needles.append([phrase.lower().rstrip('s')])
            tokens = [re.sub(r'[^\w]', '', w['text']).lower() for w in words]
            match = next((i for i in range(len(tokens)) if any(tokens[i:i + len(needle)] == needle for needle in needles)), None)
            if match is not None:
                cues[key] = offset + words[match]['start']
        if segment['kind'] == 'player' and not {'points', 'goals', 'assists', 'minutes', 'verdict'} <= cues.keys():
            raise ValueError(f'Incomplete measured statistic cues for {segment["id"]}')
        segment['cues'] = cues
        offset += duration
        print(f'Ryan timing ready {index + 1}/{len(segments)}', flush=True)
    concat = output / 'audio-concat.txt'
    concat.write_text('\n'.join("file '" + str(p).replace("'", "'\\''") + "'" for p in paths))
    speech = output / 'dialogue.wav'
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-f', 'concat', '-safe', '0', '-i', str(concat),
                    '-af', 'loudnorm=I=-18:TP=-1.5:LRA=7', '-ar', '48000', str(speech)], check=True)
    return speech, offset


def render_times(segments, fps=30):
    """Full 30fps during motion, exact caption/stat cue boundaries during holds."""
    times = {0.0, round(segments[-1]['t1'] - 1 / fps, 6)}
    for s in segments:
        start, end = s['t0'], s['t1']
        windows = [(start, min(end, start + (5 if s['kind'] == 'chapter' else 3))), (max(start, end - .65), end)]
        for a, b in windows:
            times.update(round(min(b, a + i / fps), 6) for i in range(math.ceil((b - a) * fps)))
        for cue in s['captions']:
            times.update((round(cue['start'], 6), round(cue['end'], 6)))
        verdict = s['cues'].get('verdict')
        if s['kind'] == 'player' and verdict is not None:
            times.update(round(verdict - .15 + i / fps, 6) for i in range(math.ceil(.65 * fps)))
        for cue in s['cues'].values():
            times.update((round(cue, 6), round(cue + 1.4, 6)))
        times.add(round(start + .01, 6))
    return sorted(t for t in times if 0 <= t < segments[-1]['t1'])


def make_original_bed(output, duration, segments, include_music=True):
    """An original quiet sustained pad and short accents. No third-party recording."""
    import array
    import wave
    rate = 48000
    samples = array.array('h')
    accents = [s['t0'] + .15 for s in segments if s['kind'] in ('chapter', 'player', 'next')]
    accents += [s['cues']['verdict'] for s in segments if s['kind'] == 'player' and 'verdict' in s['cues']]
    for i in range(math.ceil(duration * rate)):
        t = i / rate
        envelope = min(1, t / 2, (duration - t) / 2)
        pad = sum(math.sin(2 * math.pi * f * t) for f in (220, 261.6256, 329.6276)) / 3
        accent = sum(math.sin(2 * math.pi * (650 * (t - a) - 500 * (t - a) ** 2)) * math.exp(-25 * (t - a))
                     for a in accents if 0 <= t - a < .22)
        samples.append(int(32767 * (pad * (.006 if include_music else 0) * max(0, envelope) + accent * .008)))
    path = output / 'original-broadcast-bed.wav'
    with wave.open(str(path), 'wb') as handle:
        handle.setnchannels(1); handle.setsampwidth(2); handle.setframerate(rate); handle.writeframes(samples.tobytes())
    return path


async def produce(output, *, logo_html=None, opening_frame=None, include_music=True):
    from playwright.async_api import async_playwright
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    cache = output / 'asset-cache'
    cache.mkdir(exist_ok=True)
    review = collect_review()
    for player in review['players']:
        card = player['card']
        portrait = ''
        for url in player['photoSources']:
            portrait = local_asset(url, cache, required=False)
            if portrait:
                break
        if not portrait:
            raise RuntimeError(f'Original official image chain exhausted for player {player["id"]}')
        card['player_image'] = portrait
        card['club_badge'] = local_asset(card['club_badge'], cache)
        for f in card['fixtures']:
            f['badge'] = local_asset(f['badge'], cache)
    if not logo_html:
        logo_path = ROOT / 'tools/preview_assets/vortex-lion-reference.jpg'
        logo_html = '<img alt="FPL VORTEX" src="data:image/jpeg;base64,' + base64.b64encode(logo_path.read_bytes()).decode() + '">'
    segments = scripts_for(review)
    speech, duration = await narrate(segments, output)
    html = render_scene(review, segments, logo_html)
    if opening_frame:
        uri = 'data:image/png;base64,' + base64.b64encode(Path(opening_frame).read_bytes()).decode()
        html = html.replace('</body>', '<img id="opening-match" src="' + uri + '" alt=""><script>window.SCENE2_OPENING_MATCH=true</script></body>')
    page_path = output / 'D1_02_Gameweek_Review.html'
    page_path.write_text(html)
    times = render_times(segments)
    frames = output / 'frames'
    frames.mkdir(exist_ok=True)
    qa = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
        page = await browser.new_page(viewport=dict(width=1920, height=1080), device_scale_factor=1)
        await page.goto(page_path.as_uri(), wait_until='load')
        await page.evaluate('document.fonts.ready')
        await page.wait_for_function('window.__ready===true')
        await page.screenshot(path=str(output / 'first-frame.png'))
        for s in segments:
            await page.evaluate('t=>window.__seek(t)', min(s['t1'] - .7, s['t0'] + 4))
            await page.wait_for_function('window.__scene2AssetsReady()')
            state = await page.evaluate('window.__scene2Audit()')
            qa.append(state)
            await page.screenshot(path=str(output / (s['id'] + '.png')))
        failures = [state for state in qa if state['overlapsBranding'] or state['overflowingText'] or state['missingImage'] or state['cardInternalOverlap']]
        if failures:
            (output / 'qa-results.json').write_text(json.dumps(dict(passed=False, visualChecks=qa), indent=2))
            raise ValueError(f'Scene 2 visual QA failed: {failures}')
        for i, t in enumerate(times):
            await page.evaluate('t=>window.__seek(t)', t)
            await page.screenshot(path=str(frames / f'{i:05d}.jpg'), type='jpeg', quality=94)
            if i % 150 == 0:
                print(f'Captured Scene 2 {i}/{len(times)}', flush=True)
        await browser.close()
    concat = output / 'frames.ffconcat'
    lines = ['ffconcat version 1.0']
    for i, t in enumerate(times):
        end = times[i + 1] if i + 1 < len(times) else duration
        lines.extend([f"file '{frames / f'{i:05d}.jpg'}'", f'duration {end - t:.6f}'])
    lines.append(f"file '{frames / f'{len(times) - 1:05d}.jpg'}'")
    concat.write_text('\n'.join(lines))
    bed = make_original_bed(output, duration, segments, include_music=include_music)
    target = output / 'D1_02_Gameweek_Review.mp4'
    temporary = output / '.scene2-render.mp4'
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-f', 'concat', '-safe', '0', '-i', str(concat),
        '-i', str(speech), '-i', str(bed), '-filter_complex',
        '[1:a]asplit=2[voice][control];[2:a][control]sidechaincompress=threshold=0.02:ratio=3:attack=20:release=300[bed];[voice][bed]amix=inputs=2:normalize=0,alimiter=limit=0.84:level=0[a]',
        '-map', '0:v', '-map', '[a]', '-vf', 'fps=30,scale=out_range=tv,format=yuv420p', '-c:v', 'libx264', '-preset', 'fast', '-crf', '18', '-pix_fmt', 'yuv420p', '-color_range', 'tv',
        '-fps_mode', 'cfr', '-video_track_timescale', '30000', '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-t', str(duration), '-movflags', '+faststart', str(temporary)], check=True)
    media = probe(temporary)
    video = next(s for s in media['streams'] if s['codec_type'] == 'video')
    audio = next(s for s in media['streams'] if s['codec_type'] == 'audio')
    if (video['width'], video['height'], video['r_frame_rate'], video['codec_name'], video['pix_fmt'],
        audio['codec_name'], audio['sample_rate']) != (1920, 1080, '30/1', 'h264', 'yuv420p', 'aac', '48000'):
        raise ValueError(f'Scene 2 export specification failed: {video["width"]}x{video["height"]}, {video["r_frame_rate"]}, {video["codec_name"]}/{video["pix_fmt"]}, {audio["codec_name"]}/{audio["sample_rate"]}')
    subprocess.run(['ffmpeg', '-v', 'error', '-i', str(temporary), '-f', 'null', '-'], check=True)
    levels = subprocess.run(['ffmpeg', '-hide_banner', '-i', str(temporary), '-af', 'volumedetect', '-vn', '-sn', '-dn', '-f', 'null', '-'], capture_output=True, text=True, check=True).stderr
    peak_match = re.search(r'max_volume: ([+-]?[0-9.]+) dB', levels)
    mean_match = re.search(r'mean_volume: ([+-]?[0-9.]+) dB', levels)
    peak = float(peak_match.group(1)) if peak_match else None
    if peak is None or peak > -0.1:
        raise ValueError('Scene 2 audio clipping/measurement gate failed')
    temporary.replace(target)
    (output / 'verified-player-data.json').write_text(json.dumps({k: v for k, v in review.items() if k != 'brief'}, ensure_ascii=False, indent=2))
    (output / 'narration-scripts.json').write_text(json.dumps(segments, ensure_ascii=False, indent=2))
    for segment in segments:
        if segment['kind'] == 'player':
            (output / (segment['id'] + '-script.txt')).write_text(segment['text'])
    (output / 'narration-scripts.txt').write_text('\n\n'.join(s['id'] + '\n' + s['text'] for s in segments))
    vtt_segments = [dict(t0=s['t0'], t1=s['t1'], text=s['text'], words=s['words']) for s in segments]
    (output / 'D1_02_Gameweek_Review.vtt').write_text(word_timed_vtt(vtt_segments))
    report = dict(passed=True, version=VERSION, gameweek=review['gameweek'], duration=float(media['format']['duration']),
        sceneCount=len(segments), playerCount=len(review['players']), visualChecks=qa,
        originalHeroCardSHA256={k: hashlib.sha256(v.encode()).hexdigest() for k, v in original_card_literals().items()},
        video=video, audio=audio, peakVolumeDb=peak, meanVolumeDb=float(mean_match.group(1)) if mean_match else None, dataStatus='FINAL', audioBed='Original synthesized pad and restrained accents, narration-ducked' if include_music else 'Restrained accents; existing Day 1 master supplies its confirmed music',
        limitations=['No press-conference feed, shots or tactical-role provider was available.',
                     'Expected minutes and split model FDR are unavailable. Verdicts remain conditional.'])
    (output / 'qa-results.json').write_text(json.dumps(report, indent=2))
    print('Scene 2 export verified', target, flush=True)
    return dict(path=str(target), report=report, review=review)


def production_entry(namespace):
    """Cell 17's selected review MP4, keeping the existing master assembly path."""
    output = Path(namespace.get('VIDEO_WORK_DIR', '/content/FPL_VORTEX_FIRST_DAY_WORK/video')) / 'scene2'
    output.mkdir(parents=True, exist_ok=True)
    logo_file = output / 'channel-logo.html'
    logo_file.write_text(str(namespace['vortex_logo_html']))
    # The notebook runner can already have an asyncio loop. A subprocess owns this
    # render so nested event-loop behavior cannot corrupt the notebook session.
    command = [__import__('sys').executable, '-m', 'vortex.day1_scene2', '--output', str(output), '--logo-html', str(logo_file), '--existing-master-music']
    subprocess.run(command, check=True, cwd=ROOT)
    mp4 = output / 'D1_02_Gameweek_Review.mp4'
    destination = Path(namespace.get('MP4_DIR', '/content/FPL_VORTEX_FIRST_DAY_WORK/mp4')) / 'gw_review.mp4'
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.with_name('.scene2-staging.mp4')
    width = int(namespace.get('VIDEO_WIDTH', 3840))
    height = int(namespace.get('VIDEO_HEIGHT', 2160))
    fps = int(namespace.get('VIDEO_FPS', 24))
    if (width, height, fps) == (1920, 1080, 30):
        shutil.copyfile(mp4, staging)
    else:
        subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', str(mp4),
                        '-vf', f'scale={width}:{height}:flags=lanczos,fps={fps}',
                        '-c:v', 'libx264', '-preset', 'fast', '-crf', '18', '-pix_fmt', 'yuv420p',
                        '-c:a', 'aac', '-ar', '48000', '-b:a', '192k', '-movflags', '+faststart', str(staging)], check=True)
    media = probe(staging)
    video = next(stream for stream in media['streams'] if stream['codec_type'] == 'video')
    if (video['width'], video['height']) != (width, height):
        raise ValueError('Scene 2 master-assembly geometry failed')
    staging.replace(destination)
    html_dir = Path(namespace.get('HTML_WORK_DIR', '/content/FPL_VORTEX_FIRST_DAY_WORK/html'))
    html_dir.mkdir(parents=True, exist_ok=True)
    poster = 'data:image/png;base64,' + base64.b64encode((output / 'first-frame.png').read_bytes()).decode()
    # The approved opening's existing handoff receives the new Scene 2 first
    # frame at any canvas size. The opening component and timing are untouched.
    (html_dir / 'gw_review_scene_4k_animated.html').write_text(
        '<html><body style="margin:0;background:#090e1d"><img alt="Gameweek Review" style="width:100vw;height:100vh;object-fit:contain" src="' + poster + '"><script>window.__ready=true;window.__seek=()=>{}</script></body></html>')
    data_dir = Path(namespace['DATA_DIR'])
    for name in ('verified-player-data.json', 'narration-scripts.json', 'qa-results.json', 'D1_02_Gameweek_Review.vtt'):
        shutil.copyfile(output / name, data_dir / ('scene2-' + name))
    return str(destination)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='scene2-output')
    parser.add_argument('--opening-frame')
    parser.add_argument('--logo-html')
    parser.add_argument('--existing-master-music', action='store_true')
    args = parser.parse_args()
    asyncio.run(produce(args.output, opening_frame=args.opening_frame,
                        logo_html=Path(args.logo_html).read_text() if args.logo_html else None,
                        include_music=not args.existing_master_music))


if __name__ == '__main__':
    main()
