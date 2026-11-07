"""Day 1 Scene 2. Official retrospective data, original Hero Card, measured speech.

The production entry point is called by Cell 17. The CLI renders the identical
section for approval without running account uploads or other Day 1 chapters.
"""
from __future__ import annotations

import argparse
import ast
import asyncio
import base64
from concurrent.futures import ThreadPoolExecutor
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
    own_strength = 'defence' if identity['element_type'] in (1, 2) else 'attack'
    other_strength = 'attack' if own_strength == 'defence' else 'defence'
    for fixture in upcoming:
        home = fixture['team_h'] == identity['team']
        opponent = teams[fixture['team_a'] if home else fixture['team_h']]
        own_rating = number(team.get(f'strength_{own_strength}_{"home" if home else "away"}'))
        other_rating = number(opponent.get(f'strength_{other_strength}_{"away" if home else "home"}'))
        strength_edge = (own_rating - other_rating) / 200 if own_rating is not None and other_rating is not None else 0
        outlook.append(dict(strengthEdge=strength_edge, gw=fixture['event'], opponent=opponent['short_name'],
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


def collect_review(projections=()):
    boot, boot_meta = fetch_json('/bootstrap-static/')
    fixtures, fixture_meta = fetch_json('/fixtures/')
    gw = completed_gameweek(boot, fixtures)
    next_event = next((e for e in boot['events'] if e.get('is_next')), None)
    if not next_event:
        raise ValueError('No verified upcoming FPL Gameweek.')
    next_gw = next_event['id']
    model = {row['player_id']: row for row in projections if row['gameweek'] == next_gw}
    live, live_meta = fetch_json(f'/event/{gw}/live/')
    stats = {row['id']: row['stats'] for row in live['elements']}
    leaders = {}
    for direction in ('in', 'out'):
        key = f'transfers_{direction}_event'
        leaders[direction] = sorted(
            (p for p in boot['elements'] if p['id'] in stats and p.get(key, 0) > 0),
            key=lambda p: -p[key])[:12]
    pool = {p['id']: p for rows in leaders.values() for p in rows}
    with ThreadPoolExecutor(max_workers=6) as executor:
        summaries = dict(zip(pool, executor.map(lambda pid: fetch_json(f'/element-summary/{pid}/'), pool)))
    candidates = {}
    for pid, identity in pool.items():
        summary, summary_meta = summaries[pid]
        player = build_player(identity, stats[pid], summary,
            dict(bootstrap=boot_meta, fixtures=fixture_meta, live=live_meta, summary=summary_meta),
            boot, fixtures, gw, next_gw, '')
        projection = model.get(pid, {})
        xpts = number(projection.get('gameweek_expected_points'))
        source = 'VORTEX Phase 10' if xpts is not None else 'FPL ep_next'
        if xpts is None:
            xpts = number(identity.get('ep_next'))
        if re.match(r'^[A-Z]\.', player['name']):
            player['name'] = identity['first_name'].split()[0] + ' ' + identity['second_name'].split()[-1]
        player['market'] = dict(
            incoming=identity['transfers_in_event'], outgoing=identity['transfers_out_event'],
            ownership=float(identity['selected_by_percent']), price=identity['now_cost'] / 10,
            form=number(identity.get('form')), xpts=xpts, projectionSource=source,
            expectedMinutes=number(projection.get('expected_minutes')),
            source=boot_meta, modelSnapshot=projection.get('modelSnapshot'))
        candidates[pid] = player
    players, ranking = market_shortlist(leaders, candidates, next_gw)
    leader = candidates[leaders['in'][0]['id']]
    skipped = None
    if all(p['id'] != leader['id'] for p in players):
        fixture = next((f for f in leader['fixtures'] if f['gw'] == next_gw), None)
        if fixture and fixture['fdr'] in (4, 5):
            skipped = f'Many managers are bringing in {leader["name"]}. The {fixture["opponentName"]} fixture rates {fixture["fdr"]} for difficulty, so the alternatives deserve a closer look.'

    review_fixtures = [f for f in fixtures if f.get('event') == gw]
    scoreboard = dict(completed=field(len(review_fixtures), fixture_meta, gw),
                      goals=field(sum(f['team_h_score'] + f['team_a_score'] for f in review_fixtures), fixture_meta, gw),
                      topPoints=field(max(row['stats']['total_points'] for row in live['elements']), live_meta, gw))
    snapshot = dict(gw=gw, status='FINAL', bootstrap=boot, fixtures=fixtures, live=live,
                    provenance=dict(bootstrap=boot_meta, fixtures=fixture_meta, live=live_meta))
    return dict(version=VERSION, gameweek=gw, nextGameweek=next_gw, status='FINAL', players=players,
                overview=scoreboard, skippedBuyLeader=skipped, sourceMetadata=dict(bootstrap=boot_meta, fixtures=fixture_meta, live=live_meta),
                brief=build_brief(snapshot, next_gw=next_gw),
                selectionMethod='Top 12 by each transfer direction, then ranked by decision evidence', marketRanking=ranking)


def market_shortlist(leaders, candidates, next_gw):
    """Rank each transfer direction independently, with availability a hard buy filter."""
    selected, ranking = [], {}
    for direction, rows in leaders.items():
        scored = []
        for rank, identity in enumerate(rows, 1):
            player = candidates[identity['id']]
            m = player['market']
            f = {key: item['value'] for key, item in player['fields'].items()}
            fixture = next((row for row in player['fixtures'] if row['gw'] == next_gw), None)
            fdr = number(fixture['fdr']) if fixture else None
            starts = f['recent_starts'] or 0
            form = m['form'] or 0
            xpts = m['xpts']
            net = m['incoming'] - m['outgoing']
            flagged = f['status'] != 'a'
            if m['ownership'] < 5 or not fixture or fdr is None or xpts is None:
                continue
            if direction == 'in' and (flagged or starts < 3 or net <= 0):
                continue
            if direction == 'out' and net >= 0:
                continue
            if direction == 'out' and not flagged and (starts < 3 or f['recent_minutes'] is None):
                continue
            projected_minutes = m['expectedMinutes']
            role = min(starts, 5) / 5 if projected_minutes is None else min(projected_minutes, 90) / 90
            involvement = min(3, (f['recent_xg'] or 0) + (f['recent_xa'] or 0))
            relevance = min(m['ownership'], 50) / 25 + .35 * math.log1p(abs(net) / 1000)
            form_weight = 0 if m['projectionSource'] == 'FPL ep_next' and xpts == form else .6
            strength_edge = max(-1, min(1, fixture['strengthEdge']))
            if direction == 'in':
                score = xpts + form_weight * form + 3 * role + (5 - fdr) + involvement + relevance + xpts / m['price'] + .5 * strength_edge
            else:
                score = (8 if f['status'] in ('i', 's', 'u') else 4 if flagged else 0)
                score += (7 - xpts) + form_weight * (7 - form) + 2 * (1 - role) + fdr + relevance
                score += m['price'] / 5 - .4 * involvement - .5 * strength_edge
            m.update(rank=rank, net=net, direction=direction, nextFixture=fixture, score=round(score, 3))
            scored.append(player)
        ordered = sorted(scored, key=lambda p: (-p['market']['score'], p['market']['rank']))
        ranking[direction] = [dict(name=p['name'], **p['market']) for p in ordered]
        for player in ordered:
            if player in selected:
                continue
            m = player['market']
            status = player['fields']['status']['value']
            if direction == 'in':
                verdict = 'BUY' if m['xpts'] >= 4 and m['nextFixture']['fdr'] <= 3 else 'MONITOR'
            elif status in ('i', 's', 'u'):
                verdict = 'SELL'
            elif status != 'a':
                verdict = 'MONITOR'
            else:
                verdict = 'HOLD' if m['xpts'] >= 4 or m['nextFixture']['fdr'] <= 2 else 'SELL'
            player.update(story=f'PLAYER {direction.upper()}', verdict=verdict,
                          reason=market_reason(player, verdict))
            selected.append(player)
            if sum(p['story'] == f'PLAYER {direction.upper()}' for p in selected) == 2:
                break
    if len(selected) != 4:
        raise ValueError('Insufficient verified evidence for two players in and two players out.')
    return selected, ranking


LINEUP_LINES = (
    'Check the lineup before making the move.',
    'Wait for confirmation that he starts.',
    'Keep an eye on the final team update.',
    'His minutes will become clearer before the deadline.',
    'Make the decision once his fitness is confirmed.',
)


def market_reason(player, verdict):
    status = player['fields']['status']['value']
    if verdict == 'BUY':
        return 'Consider bringing him in. Recent starts and the fixture support the move.'
    if verdict == 'SELL' and status in ('i', 's', 'u'):
        return 'Move him out if you need a reliable starter in that squad place.'
    if verdict == 'SELL':
        return 'Look for a replacement with a better projection and fixture.'
    if verdict == 'HOLD':
        return 'Keep him if his role and fixture still work for your squad.'
    return 'Wait for lineup confirmation before using a transfer.'


def decision_label(player):
    status = player['fields']['status']['value']
    return {
        'i': 'Injury concern',
        's': 'Suspension',
        'u': 'Unavailable',
        'd': 'Fitness concern',
    }.get(status, {
        'BUY': 'Strong opportunity',
        'SELL': 'Replacement worth considering',
        'HOLD': 'Worth keeping',
        'MONITOR': 'Minutes concern',
    }[player['verdict']])


def player_script(player, index):
    market = player['market']
    fields = {key: item['value'] for key, item in player['fields'].items()}
    fixture = market['nextFixture']
    name, verdict = player['name'], player['verdict']
    venue = 'at home' if fixture['venue'] == 'H' else 'away'
    opponent = fixture['opponentName'].replace("Nott'm", 'Nottingham')
    points = (f'The next Gameweek projection is {market["xpts"]:.1f} expected points. '
              f'He faces {opponent} {venue}, with a fixture difficulty rating of {fixture["fdr"]}.')
    starts = fields['recent_starts']
    evidence = f'He started {starts} of the last five completed Gameweeks.' if starts is not None else ''
    if fields['recent_xg'] is not None and fields['recent_xa'] is not None:
        involvement = fields['recent_xg'] + fields['recent_xa']
        evidence += f' His expected goal involvement over that spell was {involvement:.2f}.'
    news = (fields['news'] or '').rstrip('.')
    status = fields['status']
    if status in ('i', 's', 'u'):
        lead = f'{name} is {dict(i="injured", s="suspended", u="unavailable")[status]}.'
        if news:
            lead += f' {news.replace(" - ", ". ")}.'
        decision = 'Move him out if you still have him and need a starter. Holding is reasonable if your bench can cover him.'
        cue = 'move him out'
    elif verdict == 'MONITOR':
        lead = f'{name} needs a closer look. '
        lead += f'{news.replace(" - ", ". ")}.' if news else 'His starting role is uncertain.'
        decision = 'Keeping him is reasonable if he is fit and likely to start. ' + LINEUP_LINES[4 if news else 1]
        cue = 'keeping him'
    elif verdict == 'BUY':
        popularity = ('Many managers are bringing him into their teams.' if index == 0
                      else 'Managers are turning to him ahead of the deadline.')
        lead = f'{name} has a strong fixture opportunity. {popularity}'
        decision = 'Consider bringing him in. ' + LINEUP_LINES[0 if index == 0 else 2]
        cue = 'consider bringing'
    else:
        lead = f'Look at {name}’s minutes and next opponent.'
        decision = market_reason(player, verdict)
        cue = 'look for a replacement' if verdict == 'SELL' else 'keep him'
    return ' '.join(part for part in (lead, points, evidence if status == 'a' else '', decision) if part), cue


def scripts_for(review):
    gw = review['gameweek']
    totals = review['overview']
    segments = [
        dict(id='chapter', kind='chapter', minimum=3,
             text=f'Gameweek {gw} is complete. Let’s focus on the moves that can improve your squad.'),
        dict(id='overview', kind='overview', minimum=0,
             text=f'We had {totals["goals"]["value"]} goals across {totals["completed"]["value"]} fixtures. '
                  'Popular moves give us a shortlist. Minutes, fitness, and fixtures tell us whether they make sense.'),
    ]
    if review.get('skippedBuyLeader'):
        segments[-1]['text'] += ' ' + review['skippedBuyLeader']
    for index, player in enumerate(review['players']):
        player['decisionLabel'] = decision_label(player)
        script, cue = player_script(player, index)
        segments.append(dict(id=f'player_{player["id"]}', kind='player', player_id=player['id'],
                             minimum=0, verdict=player['verdict'], decisionCue=cue, text=script))
    review['takeaways'] = [
        dict(heading='REPLACEMENT TARGETS', explanation='Look for recent starts and a fixture you can target.', implication='Compare expected points within your budget.'),
        dict(heading='AVAILABILITY FIRST', explanation='Check whether the player can fill a place in your eleven.', implication='Use your bench cover and the return timeline to decide.'),
        dict(heading='MINUTES RISK', explanation='A doubtful player can still be worth keeping.', implication='Reassess when you have clearer fitness and lineup information.')]
    segments.append(dict(id='takeaways', kind='takeaways', minimum=0,
                         text='Compare the replacement’s expected points and fixture with what you already have. Check your bench cover before moving out a flagged player.'))
    segments.append(dict(id='next', kind='next', minimum=0,
                         text='Next, let’s look at the fixtures and find where your squad can gain an edge.'))
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
    settings = {}
    for node in ast.parse((ROOT / '1_final_day1.py').read_text()).body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id in ('VOICE', 'MOODS'):
            settings[node.targets[0].id] = ast.literal_eval(node.value)
    offset = 0.0
    paths = []
    for index, segment in enumerate(segments):
        audio = bytearray()
        words = []
        mood = {'chapter': 'intro', 'overview': 'key_stat', 'next': 'outro'}.get(segment['kind'], 'analysis')
        if segment.get('verdict') == 'MONITOR':
            mood = 'warning'
        async for chunk in edge_tts.Communicate(segment['text'], settings['VOICE'],
                                                 **settings['MOODS'][mood], boundary='WordBoundary').stream():
            if chunk['type'] == 'audio':
                audio.extend(chunk['data'])
            elif chunk['type'] == 'WordBoundary':
                words.append(dict(text=chunk['text'], start=chunk['offset'] / 1e7, duration=chunk['duration'] / 1e7))
        path = output / f'speech-{index}.mp3'
        path.write_bytes(audio)
        duration = float(probe(path)['format']['duration'])
        duration = max(duration, segment['minimum'])
        wav = output / f'speech-{index}.wav'
        subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', str(path), '-af', 'apad', '-t', str(duration),
                        '-ar', '48000', '-ac', '1', str(wav)], check=True)
        paths.append(wav)
        segment.update(t0=round(offset, 6), t1=round(offset + duration, 6), words=words,
                       captions=[dict(start=offset + c['start'], end=offset + c['end'], text=c['text']) for c in caption_cues(words)])
        cues = {}
        for key, phrase in dict(xpts='expected points', fdr='difficulty rating', verdict=segment.get('decisionCue', '')).items():
            if not phrase:
                continue
            needles = [phrase.lower().split()]
            if key in ('points', 'goals', 'assists', 'minutes'):
                needles.append([phrase.lower().rstrip('s')])
            tokens = [re.sub(r'[^\w]', '', w['text']).lower() for w in words]
            match = next((i for i in range(len(tokens)) if any(tokens[i:i + len(needle)] == needle for needle in needles)), None)
            if match is not None:
                cues[key] = offset + words[match]['start']
        if segment['kind'] == 'player' and not {'xpts', 'verdict'} <= cues.keys():
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


async def produce(output, *, logo_html=None, opening_frame=None, include_music=True, projections=()):
    from playwright.async_api import async_playwright
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    cache = output / 'asset-cache'
    cache.mkdir(exist_ok=True)
    review = collect_review(projections)
    (output / 'shortlist.json').write_text(json.dumps([{k:v for k,v in p.items() if k != 'card'} for p in review['players']], ensure_ascii=False, indent=2))
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
    model = namespace.get('phase10_player_gameweek_expected_points')
    if model is not None and not model.empty:
        model_file = output / 'scene2-projections.json'
        rows = model[['player_id', 'gameweek', 'gameweek_expected_points', 'expected_minutes']].copy()
        rows['modelSnapshot'] = str(namespace.get('data_snapshot_timestamp') or 'Current production run')
        rows.to_json(model_file, orient='records')
        command.extend(['--projections', str(model_file)])
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
    parser.add_argument('--projections', type=Path)
    parser.add_argument('--logo-html')
    parser.add_argument('--existing-master-music', action='store_true')
    args = parser.parse_args()
    asyncio.run(produce(args.output, opening_frame=args.opening_frame,
                        logo_html=Path(args.logo_html).read_text() if args.logo_html else None,
                        include_music=not args.existing_master_music,
                        projections=json.loads(args.projections.read_text()) if args.projections else ()))


if __name__ == '__main__':
    main()
