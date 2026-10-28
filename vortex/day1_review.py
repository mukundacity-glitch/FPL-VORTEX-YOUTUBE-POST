"""Pitch-led review editorial layer over one reconciled, final FPL snapshot.

No network calls, projected points, inferred injuries, or invented event stats.
The legacy decision builder remains available for old archives and regressions.
"""
from __future__ import annotations

import copy
import math
from .day1_show import BANNED, build_show, _spoken_number

VERSION = 'VORTEX-PITCH-REVIEW-2'
SCENES = [('opening', 18), ('highlights', 32), ('top', 50), ('worst', 45),
          ('summary', 30), ('pitch', 30), ('reviews', 145), ('bench', 30), ('closing', 20)]
EVENTS = {'goals': 'goals_scored', 'assists': 'assists', 'clean_sheets': 'clean_sheets',
          'saves': 'saves', 'bonus': 'bonus'}


def enrich_review_package(ns, package):
    """Read league spotlights/results from the SAME fetch as the creator's picks."""
    result = copy.deepcopy(package)
    snapshot = ns['GW_REVIEW']
    boot, gw = snapshot['bootstrap'], int(package['gw'])
    teams = {int(t['id']): t for t in boot['teams']}
    live = {int(p['id']): p['stats'] for p in snapshot['live']['elements']}
    own = {p['id']: p for p in result['players']}
    league = []
    for element in boot['elements']:
        pid = int(element['id'])
        stats = live.get(pid, {})
        if stats.get('total_points') is None or stats.get('minutes') is None:
            continue
        team = teams[int(element['team'])]
        fixtures = []
        for f in sorted(snapshot['fixtures'], key=lambda f: (int(f.get('event') or 99), f.get('kickoff_time') or '')):
            if int(f.get('event') or 0) < package['preview_gw'] or team['id'] not in (f['team_h'], f['team_a']):
                continue
            home = team['id'] == f['team_h']
            opp = teams[int(f['team_a'] if home else f['team_h'])]
            fixtures.append({'gw': f['event'], 'opp': opp['short_name'], 'ha': 'H' if home else 'A',
                             'difficulty': f.get('team_h_difficulty' if home else 'team_a_difficulty')})
        p = copy.deepcopy(own.get(pid, {}))
        p.update({'id': pid, 'name': element['web_name'], 'team': team['short_name'],
                  'team_name': team['name'], 'team_code': team['code'],
                  'pos': {1: 'GK', 2: 'DEF', 3: 'MID', 4: 'FWD'}[int(element['element_type'])],
                  'points': int(stats['total_points']), 'minutes': int(stats['minutes']),
                  'status': str(element.get('status') or 'u'), 'news': str(element.get('news') or ''),
                  'price': float(element['now_cost']) / 10 if element.get('now_cost') is not None else None,
                  'ownership': float(element['selected_by_percent']) if element.get('selected_by_percent') else None,
                  'fixtures': fixtures[:5], 'next_fixture': fixtures[0] if fixtures else {}})
        p.update({key: stats.get(source) for key, source in EVENTS.items()})
        if pid in own:
            own[pid].update({key: stats.get(source) for key, source in EVENTS.items()})
        league.append(p)
    eligible = [p for p in league if p['minutes'] > 0]
    top = sorted(eligible, key=lambda p: (-p['points'], -p['minutes'], p['id']))[:3]
    # Price is explicit selection context, NOT a claim about ownership/expectation.
    worst = sorted((p for p in eligible if p['id'] not in {x['id'] for x in top}),
                   key=lambda p: (p['points'], -(p.get('price') or 0), p['id']))[:3]
    for p in top + worst:
        if not p.get('photo'):
            p['photo'] = ns['resolve_player_photo'](next(e for e in boot['elements'] if int(e['id']) == p['id']))
        p['badge'] = ns.get('team_meta_by_id', {}).get(int(next(e for e in boot['elements'] if int(e['id']) == p['id'])['team']), {}).get('badge', '')
    result['league_players'] = list({p['id']: p for p in top + worst}.values())
    result['top_ids'], result['worst_ids'] = [p['id'] for p in top], [p['id'] for p in worst]
    result['performer_scope'] = 'Completed Gameweek · official league snapshot'
    matches = []
    for f in snapshot['fixtures']:
        if int(f.get('event') or 0) != gw or not f.get('finished') or f.get('team_h_score') is None or f.get('team_a_score') is None:
            continue
        home, away = teams[int(f['team_h'])], teams[int(f['team_a'])]
        featured = [p for p in top + worst if p['team_code'] in (home['code'], away['code'])]
        if not featured:
            continue
        assist_stats = next((s for s in f.get('stats', []) if s.get('identifier') == 'assists'), None)
        assists = sum(int(x['value']) for side in ('h', 'a') for x in assist_stats.get(side, [])) if assist_stats is not None else None
        matches.append({'id': f.get('id', len(matches)), 'home': home['short_name'], 'away': away['short_name'],
                        'home_score': f['team_h_score'], 'away_score': f['team_a_score'],
                        'goals': f['team_h_score'] + f['team_a_score'], 'assists': assists,
                        'clean_sheets': int(f['team_h_score'] == 0) + int(f['team_a_score'] == 0),
                        'player_ids': [p['id'] for p in featured],
                        'story': ' · '.join(f'{p["name"]} {p["points"]} pts' for p in featured[:2])})
    result['matches'] = matches[:6]
    return result


def normalize_player(p, decisions):
    p = copy.deepcopy(p)
    p['position'] = p.get('pos', p.get('position', 'MID'))
    p['isCaptain'], p['isViceCaptain'], p['isBench'] = bool(p.get('captain')), bool(p.get('vice')), bool(p.get('bench'))
    p['availability'] = p.get('status') or 'u'
    p['status_reason'] = p.get('news') or ''
    decision = next((d for d in decisions if d['player']['id'] == p['id']), None)
    if p['availability'] != 'a' and p['status_reason']:
        verdict = 'WAIT FOR TEAM NEWS'
    elif p.get('minutes') is None:
        verdict = 'MONITOR'
    elif decision:
        verdict = decision['verdict']
    elif p['minutes'] < 60:
        verdict = 'MONITOR'
    else:
        verdict = 'HOLD'
    p['verdict'] = verdict
    goals, assists, cs, saves = (p.get(k) for k in ('goals', 'assists', 'clean_sheets', 'saves'))
    if p['availability'] != 'a' and p['status_reason']:
        action = 'injury'
    elif p['isBench'] and p.get('multiplier', 0) == 0 and (p.get('points') or 0) >= 6:
        action = 'bench-haul'
    elif p['isCaptain']:
        action = 'captain'
    elif goals and goals > 0:
        action = 'goal'
    elif assists and assists > 0:
        action = 'assist'
    elif p['position'] == 'GK' and saves and saves > 0:
        action = 'saves'
    elif cs and cs > 0:
        action = 'clean-sheet'
    else:
        action = 'blank' if p.get('points') is not None and p['points'] <= 2 else 'points'
    p['action'] = action
    events = []
    for key, label in [('goals', 'goal'), ('assists', 'assist'), ('clean_sheets', 'clean sheet'), ('saves', 'save'), ('bonus', 'bonus')]:
        value = p.get(key)
        if value is not None and value > 0:
            events.append(f'{value} {label}' + ('s' if value != 1 and label != 'bonus' else ''))
    p['event_summary'] = ', '.join(events[:2]) if events else ('Blank' if action == 'blank' else 'Data pending')
    p['analysis'] = {
        'START': 'An early starting option; confirm availability and the fixture before the deadline.',
        'HOLD': 'Keep the place for now. Check the role and next opponent before making a transfer.',
        'MONITOR': 'Review the minutes and role before using a transfer here.',
        'WAIT FOR TEAM NEWS': 'Wait for a confirmed update; a flag is not a return date.',
    }.get(verdict, 'Review the next fixture and team news before acting.')
    return p


def player_script(p, index=0, spotlight=False):
    name = p['name']
    points = _spoken_number(p['points']) if p.get('points') is not None else 'points data pending'
    verdict = p['verdict']
    if verdict == 'WAIT FOR TEAM NEWS':
        # Only repeat supplied news; never infer a body part, cause, or return date.
        reason = ' '.join(p['status_reason'].split()[:10])
        return f'{name}: {reason}. That uncertainty affects my team selection. I want a confirmed update before I rely on this place. My verdict: wait for team news.'
    prefixes = [f'{name} gave me {points} points.', f'For {name}, the score was {points}.', f'Next, {name}: {points} points.']
    fact = prefixes[index % len(prefixes)]
    if spotlight:
        fact = f'{name} scored {points} points.'
    if p['action'] == 'captain':
        multiplier = p.get('multiplier', 0)
        counted = p['points'] * multiplier
        detail = f'The official multiplier made that {_spoken_number(counted)} in my total. I separate the ownership call from the armband.'
    elif p['action'] == 'bench-haul':
        detail = 'Those points stayed on the unused bench. That makes selection worth revisiting, with minutes and the next opponent checked first.'
    elif p.get('minutes') is not None and p['minutes'] < 60:
        detail = f'{p["minutes"]} minutes puts the role under scrutiny. I need more confidence in the playing time before depending on this spot.'
    elif p.get('goals'):
        detail = 'The goal helped the score, but I will judge the next selection on the role and fixture rather than assume another haul.'
    elif p.get('assists'):
        detail = 'The assist mattered this week. For the next decision, I want that attacking involvement supported by reliable minutes in the same role.'
    elif p.get('clean_sheets'):
        detail = 'The clean sheet helped. I want to keep that defensive route to points, while checking the next opponent before committing to the lineup.'
    else:
        detail = [
            'The minutes matter to this call. Before I change the lineup, I will compare the next opponent and the alternatives already in my squad.',
            'This place needs a clear plan. I want to check the upcoming fixture and the role before I use a transfer to change it.',
            'My next selection starts with availability and the fixture. This score is useful context, but I still need a reason for the next move.',
        ][index % 3]
    end = {'START': 'Early verdict: start if the checks hold.', 'HOLD': 'My verdict is hold.',
           'MONITOR': 'My verdict is monitor.', 'SELL': 'My early verdict is sell.'}.get(verdict, 'Wait for news.')
    return f'{fact} {detail} {end}'


def build_review(package):
    # Reuse established finalisation, captain, legal swap and metadata checks.
    show = build_show(package)
    decisions = show['decisions']
    players = [normalize_player(p, decisions) for p in package['players']]
    league = [normalize_player(p, []) for p in package.get('league_players', [])]
    by_id = {p['id']: p for p in league + players}
    scope = package.get('performer_scope') or 'Verified supplied squad · league data pending'
    top_ids = package.get('top_ids') or [p['id'] for p in sorted(players, key=lambda p: (-p['points'], p['id']))[:3]]
    worst_ids = package.get('worst_ids') or [p['id'] for p in sorted(players, key=lambda p: (p['points'], p['id'])) if p['id'] not in top_ids][:3]
    top, worst = [by_id[i] for i in top_ids[:3]], [by_id[i] for i in worst_ids[:3]]
    if len(top) < 3 or len(worst) < 3:
        raise RuntimeError('Three verified top performers and three disappointments are required')
    starters = sorted((p for p in players if not p['isBench']), key=lambda p: p['squad_position'])
    bench = sorted((p for p in players if p['isBench']), key=lambda p: p['squad_position'])
    counts = {pos: sum(p['position'] == pos for p in starters) for pos in ('GK', 'DEF', 'MID', 'FWD')}
    if len(starters) != 11 or len(bench) != 4 or counts['GK'] != 1 or not (3 <= counts['DEF'] <= 5 and 2 <= counts['MID'] <= 5 and 1 <= counts['FWD'] <= 3):
        raise RuntimeError('Expected a legal verified starting eleven and four bench players')
    captain = by_id[show['accuracy']['effective_captain_id']]
    hero = max((p for p in players if p.get('multiplier', 0) > 0), key=lambda p: p['points'])
    regret = next((p for p in players if p['id'] == show['accuracy']['actual_bench_regret_id']), None)
    points, average = package['metrics']['gw_points'], package['metrics'].get('average_points')
    sections, scenes, cursor = [], [], 0

    def section(key, scene, title, text, p, length, action=None):
        nonlocal cursor
        sections.append({'id': key, 'scene': scene, 'title': title, 'start': cursor, 'end': round(cursor + length, 9),
                         'duration': length, 'text': text, 'player_id': p['id'], 'verdict': p['verdict'],
                         'action': action or p['action'], 'phrases': [{'text': p['verdict'], 'anchor': p['name']}],
                         'direction': 'Keep pitch context; select player, grow reference hero from pitch location; event-driven SVG motion.'})
        cursor = round(cursor + length, 9)

    for scene, length in SCENES:
        begin = cursor
        if scene == 'opening':
            tension = (f'{regret["name"]} had {regret["points"]} on my unused bench.' if regret else f'{hero["name"]} was my strongest counted return.')
            text = f'My captain contribution: {_spoken_number(show["accuracy"]["captain_points"])} points. {tension} My team scored {points}, but the score alone does not settle the next selection. Today I am reviewing the decisions behind the points, starting with the biggest returns.'
            section('opening', scene, 'The Gameweek turning point', text, captain, length)
        elif scene == 'highlights':
            text = ('Before my own team, here are the returns that shape this review. ' +
                    ' '.join(f'{p["name"]} scored {_spoken_number(p["points"])}.' for p in top) +
                    ' I am looking for routes to points we can trust again, rather than reading every match result. '
                    'A goal can transform one week; reliable minutes and the next opponent decide whether that changes my team. '
                    'The score ticker shows the verified results behind these stories.' if package.get('matches') else
                    'Before my own team, three returns stand out in the supplied data. ' +
                    ' '.join(f'{p["name"]} scored {_spoken_number(p["points"])} points.' for p in top) +
                    ' The complete league results are still pending, so these are the verified squad highlights. '
                    'I am looking at routes to points and selection decisions. A strong score matters, but it does not automatically promise the same outcome next time. '
                    'Let us look more closely at those three performances.')
            section('highlights', scene, 'Gameweek in thirty seconds', text, top[0], length)
        elif scene in ('top', 'worst'):
            if scene == 'top':
                section('top_radar', scene, 'Three returns to investigate',
                        'Three form alerts. The points get attention; the role decides my verdict.', top[0], 5)
            for i, p in enumerate(top if scene == 'top' else worst):
                p = copy.deepcopy(p)
                if scene == 'worst' and p['verdict'] == 'HOLD':
                    p['verdict'] = 'MONITOR' if p['minutes'] < 60 else 'HOLD'
                text = player_script(p, i, spotlight=True)
                section(f'{scene}_{i+1}', scene, ('Form alert: ' if scene == 'top' else 'Decision check: ') + p['name'], text, p, 15)
        elif scene == 'summary':
            comparison = f'against an average of {average}' if average is not None else 'with the average still pending'
            pain = f'{regret["name"]} was my bench regret.' if regret else 'The unused bench did not produce a verified better same-position swap.'
            text = (f'My total was {points}, {comparison}. {hero["name"]} was my best counted return, so that selection deserves credit. '
                    f'{pain} Then there is the captaincy: {_spoken_number(show["accuracy"]["captain_points"])} points counted. '
                    'I can be honest about the frustration without changing every part of the team. The next lineup needs a better reason than simply reacting to the score.')
            section('summary', scene, 'My Gameweek story', text, hero, length)
        elif scene == 'pitch':
            lines = [(pos, [p for p in starters if p['position'] == pos]) for pos in ('GK', 'DEF', 'MID', 'FWD')]
            text = ('Here is the verified starting eleven, with the bench kept separate. ' +
                    ' '.join(f'{", ".join(p["name"] for p in line)} {dict(GK="in goal", DEF="in defence", MID="in midfield", FWD="up front")[pos]}.' for pos, line in lines if line) +
                    ' The armband follows the actual captain selection. Any official substitute contribution is already included through its multiplier. '
                    'Now I will go through every starting player, keeping their position on the pitch in view.')
            section('pitch', scene, 'The full squad reveal', text, captain, length)
        elif scene == 'reviews':
            for i, p in enumerate(starters):
                section(f'review_{p["id"]}', scene, p['name'], player_script(p, i), p, length / 11)
        elif scene == 'bench':
            for i, p in enumerate(bench):
                if p['verdict'] == 'WAIT FOR TEAM NEWS':
                    text = f'{p["name"]}: the supplied update flags availability. I will not assume a return date. Wait for team news.'
                elif p.get('multiplier', 0) > 0:
                    text = f'{p["name"]}: {p["points"]} points, and the official multiplier says that contribution counted. This is not an unused bench regret. Hold.'
                elif regret and p['id'] == regret['id']:
                    text = f'{p["name"]}: {p["points"]} points unused. Bench regret, clearly. My early plan is start, if the next fixture and team news support it.'
                else:
                    text = f'{p["name"]}: {p["points"]} points on the unused bench. I will check the role before relying on this cover. {p["verdict"].capitalize()}.'
                section(f'bench_{p["id"]}', scene, p['name'], text, p, length / 4)
        else:
            d1, d2, d3 = decisions
            text = (f'My early plan: {d2["verdict"].lower()} for {d2["player"]["name"]}, subject to the final checks. '
                    f'{d1["player"]["name"]} is a {d1["verdict"].lower()}, with the armband assessed separately. '
                    f'For {d3["player"]["name"]}, {d3["verdict"].lower()}. '
                    f'{show["question"]}')
            section('closing', scene, 'Your next Gameweek plan', text, by_id[d2['player']['id']], length)
        cursor = begin + length
        sections[-1]['end'] = cursor
        sections[-1]['duration'] = cursor - sections[-1]['start']
        scenes.append({'id': scene, 'start': begin, 'end': cursor, 'duration': length})
    show.update({'version': VERSION, 'sections': sections, 'scenes': scenes, 'duration': cursor,
                 'players': list(by_id.values()), 'top_ids': top_ids[:3], 'worst_ids': worst_ids[:3],
                 'performer_scope': scope, 'matches': package.get('matches', []),
                 'formation': [sum(p['position'] == pos for p in starters) for pos in ('DEF', 'MID', 'FWD')],
                 'concept': f'GW{package["gw"]} review: the whole squad, every decision on the pitch.',
                 'shorts': [{'title': s['title'], 'start': s['start'], 'end': s['end'],
                             'section_id': s['id'], 'player_id': s['player_id'], 'verdict': s['verdict']}
                            for s in [next(s for s in sections if s['scene'] == name and s['id'] != 'top_radar') for name in ('top', 'worst', 'summary')]],
                 'b_roll': ['Animated stadium pitch', 'Reference hero card and sequential stat chips',
                            'Eleven sequential player entrances', 'All fifteen players reviewed', 'Bench and availability watch'],
                 'sound': {'music': 'Quiet electronic bed; speech-driven sidechain ducking.',
                           'impacts': 'Sparse event cues: captain, haul and tactical movements.'}})
    validate_review(show)
    return show


def validate_review(show):
    text = ' '.join(s['text'] for s in show['sections'])
    if any(phrase in text.casefold() for phrase in BANNED):
        raise RuntimeError('Forbidden review narration phrase')
    if not 700 <= len(text.split()) <= 950:
        raise RuntimeError(f'Review narration needs 700–950 words; got {len(text.split())}')
    if not 300 <= show['duration'] <= 420:
        raise RuntimeError('Review must run five to seven minutes')
    if len([s for s in show['sections'] if s['scene'] == 'reviews']) != 11 or len([s for s in show['sections'] if s['scene'] == 'bench']) != 4:
        raise RuntimeError('Every verified squad player needs an individual review')
    if any(not math.isfinite(s['duration']) or s['duration'] <= 0 for s in show['sections']):
        raise RuntimeError('Invalid review timing')
    if any(a['end'] != b['start'] for a, b in zip(show['sections'], show['sections'][1:])):
        raise RuntimeError('Review sections must be contiguous')


def build_review_timeline(show, words):
    from .day1_show_render import word_time
    show['words'] = words
    show['beats'], show['highlights'] = [], []
    for s in show['sections']:
        count = max(1, math.ceil(s['duration'] / 5))
        for i in range(count):
            show['beats'].append({'start': s['start'] + s['duration'] * i / count,
                                  'end': s['start'] + s['duration'] * (i + 1) / count,
                                  'section': s['id'], 'player_id': s['player_id'], 'verdict': s['verdict'],
                                  'phrase': s['verdict'], 'variant': i % 3, 'transition': .4})
    show['impact_at'] = word_time([w for w in words if w['section_id'] == 'opening'], 'captain')
    # Sparse cues only. Never run a sound effect at every sentence or stat chip.
    show['sound_cues'] = [{'at': show['impact_at'], 'kind': 'impact'}]
    for s in show['sections']:
        if s['scene'] == 'top' and s['action'] in ('goal', 'bench-haul'):
            show['sound_cues'].append({'at': s['start'] + .8, 'kind': 'crowd'})
        if s['scene'] == 'reviews' and s['action'] in ('goal', 'assist', 'saves', 'captain'):
            show['sound_cues'].append({'at': s['start'] + .1, 'kind': 'whoosh'})
    return show
