"""Evidence-led Day 1 decision show; no match-results or fifteen-player roll call.

The immutable notebook supplies one official FPL snapshot. This module selects
three editorial decisions, records their evidence, and owns the show timeline.
Opinions are explicitly early plans, never claims of executed transfers.
"""
from __future__ import annotations

import copy
import base64
import json
import math
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

SHOW_VERSION = 'VORTEX-DECISION-SHOW-1'
BANNED = (
    'recorded one goal', 'returned just two', 'returned just 2',
    'the next fixture run is the next test', 'it is worth considering',
    "it's worth considering", 'finished with', 'delivered through',
    'one quiet week', 'now we need to weigh it', 'welcome back',
    'no performance to judge',
)
COLORS = {'BUY': '#62ff88', 'START': '#62ff88', 'HOLD': '#ffd369',
          'MONITOR': '#ffd369', 'WAIT FOR TEAM NEWS': '#ffd369',
          'SELL': '#ff6174', 'BENCH': '#ff6174', 'CAPTAIN': '#6caaff'}
SECTION_TIMES = [('hook', 15), ('story', 30), ('decision_1', 60),
                 ('decision_2', 60), ('decision_3', 60), ('plan', 45), ('cta', 20)]


def _json(path, payload):
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')


def _plain(value):
    return re.sub(r'[^\w]+', ' ', str(value).casefold()).strip()


def _spoken_number(value):
    value = int(value)
    return f'minus {abs(value)}' if value < 0 else str(value)


def package_snapshot(ns):
    """Freeze squad, actual multipliers, news and schedule from the same fetch."""
    snapshot = ns['GW_REVIEW']
    gw = int(snapshot['gw'])
    status = str(snapshot.get('status') or ns.get('GW_REVIEW_STATUS') or '').upper()
    if status != 'FINAL':
        raise RuntimeError('The decision show requires final official review points; wait for FPL finalisation')
    boot = snapshot['bootstrap']
    next_gw = int(ns.get('NEXT_GW') or next(
        (e['id'] for e in boot['events'] if e.get('is_next')), gw + 1))
    if not 1 <= next_gw <= 38 or next_gw <= gw:
        raise RuntimeError('No upcoming Gameweek is verified for the decision show')
    teams = {int(t['id']): t for t in boot['teams']}
    elements = {int(p['id']): p for p in boot['elements']}
    live = {int(p['id']): p['stats'] for p in snapshot['live']['elements']}
    players = []
    for pick in sorted(snapshot['picks']['picks'], key=lambda p: int(p['position'])):
        pid = int(pick['element'])
        p, stats = elements[pid], live.get(pid)
        if stats is None:
            raise RuntimeError(f'Official review stats missing for squad player {pid}')
        team = teams[int(p['team'])]
        badge = ns.get('team_meta_by_id', {}).get(int(p['team']), {}).get('badge', '')
        fixtures = []
        for f in sorted(snapshot['fixtures'], key=lambda f: (int(f.get('event') or 99), f.get('kickoff_time') or '')):
            if int(f.get('event') or 0) < next_gw or int(p['team']) not in (f['team_h'], f['team_a']):
                continue
            home = int(p['team']) == int(f['team_h'])
            opp = teams[int(f['team_a'] if home else f['team_h'])]
            fixtures.append({'gw': int(f['event']), 'opp': opp['short_name'],
                             'opp_name': opp['name'], 'ha': 'H' if home else 'A',
                             'team_code': opp['code'], 'kickoff_time': f.get('kickoff_time')})
        players.append({
            'id': pid, 'name': p['web_name'], 'team': team['short_name'],
            'team_name': team['name'], 'team_code': team['code'],
            'badge': badge,
            'pos': {1: 'GK', 2: 'DEF', 3: 'MID', 4: 'FWD'}[int(p['element_type'])],
            'photo': ns['resolve_player_photo'](p),
            'points': int(stats['total_points']), 'minutes': int(stats['minutes']),
            'bench': int(pick['position']) > 11, 'squad_position': int(pick['position']),
            'captain': bool(pick['is_captain']), 'vice': bool(pick['is_vice_captain']),
            'multiplier': int(pick['multiplier']), 'status': str(p.get('status') or 'u'),
            'news': str(p.get('news') or ''), 'news_added': p.get('news_added'),
            'season_total_points': int(p.get('total_points') or 0),
            'season_starts': int(p['starts']) if p.get('starts') is not None else None,
            'season_minutes': int(p.get('minutes') or 0),
            'season_goals': int(p.get('goals_scored') or 0),
            'season_assists': int(p.get('assists') or 0),
            'season_xg': float(p.get('expected_goals') or 0),
            'season_xa': float(p.get('expected_assists') or 0),
            'price': float(p['now_cost']) / 10, 'ownership': float(p.get('selected_by_percent') or 0),
            'fixtures': fixtures[:5], 'next_fixture': fixtures[0] if fixtures else {},
        })
    history = snapshot['picks']['entry_history']
    gross = int(history['points'])
    calculated = sum(p['points'] * p['multiplier'] for p in players)
    if gross != calculated:
        raise RuntimeError(f'Official squad points do not reconcile: {gross} vs {calculated}')
    event = next(e for e in boot['events'] if int(e['id']) == gw)
    package = {'gw': gw, 'preview_gw': next_gw, 'status': status,
               'verified_at': datetime.now(timezone.utc).isoformat(),
               'players': players, 'metrics': {
                   'gw_points': gross - int(history.get('event_transfers_cost') or 0),
                   'gross_points': gross, 'transfer_cost': int(history.get('event_transfers_cost') or 0),
                   'average_points': event.get('average_entry_score'),
                   'overall_rank': history.get('overall_rank'),
               }}
    return package


def _fixture(player, preview_gw):
    f = player.get('next_fixture') or {}
    if int(f.get('gw') or 0) != preview_gw:
        return f'no confirmed fixture in Gameweek {preview_gw}'
    return f'{f.get("opp_name") or f["opp"]} {"at home" if f.get("ha") == "H" else "away"}'


def select_decisions(package):
    players, gw = package['players'], int(package['preview_gw'])
    if len(players) != 15 or len({p['id'] for p in players}) != 15:
        raise RuntimeError('The decision show requires fifteen unique verified squad players')
    if sum(bool(p.get('captain')) for p in players) > 1:
        raise RuntimeError('Multiple captain selections in the verified snapshot')
    captain = next((p for p in players if p.get('captain')), None)
    if captain is None:
        raise RuntimeError('Verified captain selection is missing')
    alternatives = [p for p in players if p['id'] != captain['id'] and p['pos'] in ('MID', 'FWD')
                    and p.get('status') == 'a' and int(p.get('next_fixture', {}).get('gw') or 0) == gw]
    alternative = max(alternatives, key=lambda p: (p.get('season_total_points', 0), p.get('season_minutes', 0))) if alternatives else None
    first = {'player': captain, 'verdict': 'HOLD' if captain.get('status') == 'a' else 'WAIT FOR TEAM NEWS',
             'angle': 'ownership_and_captaincy', 'alternative': alternative}
    bench = [p for p in players if p.get('bench') and p.get('multiplier', 0) == 0
             and p['pos'] != 'GK' and p.get('status') == 'a' and p.get('minutes', 0) >= 60
             and int(p.get('next_fixture', {}).get('gw') or 0) == gw]
    comparisons = [(b, s) for b in bench for s in players if not s.get('bench')
                   and s['pos'] == b['pos'] and s['id'] != captain['id']]
    if comparisons:
        b, s = max(comparisons, key=lambda pair: (pair[0]['points'] - pair[1]['points'], pair[1].get('status') != 'a'))
        # This is explicitly a conditional opinion, not a new projected-xPts model.
        second = {'player': b, 'replacement': s, 'verdict': 'START', 'angle': 'lineup_choice',
                  'bench_regret': b['points'] > s['points']}
    else:
        p = min((p for p in players if not p.get('bench') and p['pos'] != 'GK' and p['id'] != captain['id']), key=lambda p: p['points'])
        second = {'player': p, 'verdict': 'MONITOR', 'angle': 'lineup_choice', 'bench_regret': False}
    used = {captain['id'], second['player']['id']}
    flagged = [p for p in players if p['id'] not in used and p['pos'] != 'GK'
               and p.get('status') != 'a' and p.get('news')]
    if flagged:
        p = max(flagged, key=lambda p: (p.get('status') in ('i', 's', 'u'), p.get('price', 0)))
        third = {'player': p, 'verdict': 'WAIT FOR TEAM NEWS', 'angle': 'availability'}
    else:
        p = min((p for p in players if p['id'] not in used and not p.get('bench') and p['pos'] != 'GK'), key=lambda p: p['points'])
        third = {'player': p, 'verdict': 'MONITOR', 'angle': 'transfer_priority'}
    return [first, second, third]


def build_show(package):
    package = copy.deepcopy(package)
    if package.get('status') != 'FINAL':
        raise RuntimeError('A final official snapshot is required; provisional points are not a final story')
    gw = int(package['gw'])
    preview = int(package.get('preview_gw') or gw + 1)
    package['preview_gw'] = preview
    if not 1 <= gw < preview <= 38:
        raise RuntimeError('Invalid review/upcoming Gameweek pair')
    decisions = select_decisions(package)
    d1, d2, d3 = decisions
    c, b, injury = (d['player'] for d in decisions)
    n, bn, jn = c['name'], b['name'], injury['name']
    effective = next((p for p in package['players'] if p.get('multiplier', 0) > 1), c)
    captain_points = effective['points'] * effective['multiplier']
    if effective['id'] != c['id']:
        consequence = f'{n} did not supply my captain score. The armband passed to {effective["name"]} for {_spoken_number(captain_points)} points.'
    elif captain_points <= 4:
        consequence = f'I gave {n} the armband. {_spoken_number(captain_points).capitalize()} points from my captain.'
    else:
        consequence = f'{n} gave me {_spoken_number(captain_points)} captain points. Now I have to decide whether to trust that armband again.'
    replacement = d2.get('replacement')
    regret = d2.get('bench_regret', False)
    bench_story = (f'{bn} scored {b["points"]} on my unused bench.' if regret
                   else f'My next starting-eleven choice is {bn}.')
    hook = (f'{consequence} {bench_story} But would changing everything fix my team, or make it worse? '
            f'By the end, I will give you three decisions for Gameweek {preview}.')
    points = int(package['metrics']['gw_points'])
    average = package['metrics'].get('average_points')
    score = f'I ended Gameweek {gw} on {points} points.'
    if average is not None:
        score += f' The overall average was {int(average)}.'
    correct_hero = max((p for p in package['players'] if not p.get('bench')), key=lambda p: p['points'])
    story = (f'{score} That is the score I have to work from. '
             f'{correct_hero["name"]} was already in my starting eleven, so those {correct_hero["points"]} points counted. '
             'I am separating the decision I made before the deadline from the result I saw afterwards. '
             'The useful question is what I change now. I have an ownership call, a place in defence, and a transfer I will not rush.')
    if d1['verdict'] == 'HOLD':
        reaction = 'hurt' if captain_points <= 4 else 'helped'
        starts = (f'He has {int(c["season_starts"])} starts in the season data. That matters more to my ownership call than a single score. '
                  if c.get('season_starts') is not None else
                  'I would judge his place in my team using the next fixture and the latest availability update. ')
        one = (f'First decision: {n}. My verdict is hold. That captain score {reaction}, but selling him and changing my captain are separate calls. '
               + starts +
               f'His next fixture is {_fixture(c, preview)}. That is the matchup I need to judge, rather than letting last week decide everything. '
               'I would keep the player and reopen the armband decision. Keeping him does not mean I have to captain him again. '
               'What would change my mind? New availability news, a genuine change in his role, or a better use of that place in my team. '
               'A bad score does not, by itself, tell me that his role has changed. ')
    else:
        one = (f'First decision: {n}. My verdict is wait for team news. I would separate the frustration of the captain score from his actual availability. '
               f'The latest official update says: {c.get("news") or "availability is uncertain"}. '
               'That is a reason to pause, rather than pretend I know the next team sheet. I need a clear update before trusting the armband. '
               'If he is fit, I can assess ownership and captaincy separately. If he is ruled out, the decision changes. ')
    alt = d1.get('alternative')
    if alt:
        one += (f'{alt["name"]} is in my captain shortlist, with {_fixture(alt, preview)} next. '
                'That is a candidate, not a confirmed captain. My ownership verdict stays separate from the armband.')
    else:
        one += ('I will compare the available attackers in my own squad before locking a captain. '
                'There is no need to manufacture a favourite without a confirmed fixture and availability.')
    if replacement:
        reason = (f'{replacement["name"]} played {replacement["minutes"]} minutes and has an availability flag in the latest update.'
                  if replacement.get('status') != 'a' else
                  f'{bn} has a confirmed next fixture and played {b["minutes"]} minutes in the reviewed match.')
        regret_line = 'It stings, but those points do not buy him a place automatically.' if regret else 'Last week does not decide this place automatically.'
        two = (f'Second decision: start {bn}? My early verdict is start, ahead of {replacement["name"]}, if the current information holds. '
               f'{reason} {bn} faces {_fixture(b, preview)}. '
               f'{bench_story} {regret_line} '
               'The reason for this lean is the next team selection, not a promise that the same return happens again. '
               'I am not turning a bench haul into a prediction. A defender can be the right pick next week and still blank. '
               'If the team news changes, I revisit the swap. If it does not, I would rather make one deliberate change than reshuffle the whole defence. '
               f'This is a same-position swap, so I keep a legal formation. That is the plan: {bn} starts, with the final check before the deadline.')
    else:
        two = (f'Second decision: {bn}. My verdict is monitor. I would keep this as a starting-eleven question before making it a transfer. '
               f'His next schedule shows {_fixture(b, preview)}. That is where the decision begins. '
               'I would check who else in my squad can take that place, and whether the formation still works. '
               'A low score alone is not evidence that his next start is unsafe. Equally, last week is not a reason to ignore a better matchup. '
               'For now, I keep the decision open rather than announce a change I cannot support. '
               'I want one clear reason to start him and one clear reason to choose the alternative. '
               'If neither side has enough evidence, waiting is a real decision. I will settle the place using the final team news and the confirmed schedule.')
    if d3['angle'] == 'availability':
        three = (f'Third decision: {jn}. My verdict is wait for team news. The latest official update says: {injury["news"]}. '
                 'That is the limit of what I know. I will not give you a recovery date that has not been confirmed. '
                 f'The schedule lists {_fixture(injury, preview)}, but a fixture on the calendar is not a promise that he starts. '
                 'If I own him, I first check whether my bench can cover the uncertainty. If I am looking to buy him, I would wait for the press conference. '
                 'Selling now and buying now are different decisions, with different costs. I would check my selling price and the cost of the replacement before calling that a move. '
                 'A confirmed absence would move this up my priority list. A clear fitness update would let me reassess. Until then, I keep the transfer open. '
                 'The deadline is the checkpoint, rather than the moment the first rumour appears.')
    else:
        three = (f'Third decision: {jn}. My verdict is monitor, with no transfer locked in. '
                 f'The next fixture is {_fixture(injury, preview)}. I want that decision to earn a transfer rather than take one by default. '
                 'Before selling, I need to know who comes in, whether that player is available, and whether I can actually afford the move. '
                 'I do not have all of that verified here. So this is an honest watchlist call, rather than a transfer announcement. '
                 'The useful comparison is the next few starts, not simply the points each player scored last time. '
                 'If the evidence supports a change before the deadline, I can act. If it does not, keeping the transfer available gives me a choice. '
                 'I would prefer a clear reason for one move to a chain of moves made because the last Gameweek was frustrating.')
    plan = (f'So here is my early Gameweek {preview} plan. {n}: {d1["verdict"].lower()}. '
            f'{bn}: {d2["verdict"].lower()}, with the lineup decision checked before the deadline. '
            f'{jn}: {d3["verdict"].lower()}. '
            'These are my current calls, not transfers I have already made. The captain gets one final comparison against the available alternatives. '
            'I am keeping the ownership decision separate from that armband. For the team sheet, I check availability first, then the confirmed opponent, then the formation. '
            'If new information changes one of those calls, I change that call. I do not have to tear up everything else. '
            'That is how I want to leave this Gameweek: with three decisions I can explain, rather than a longer list of regrets.')
    question = (f'Would you start {bn} ahead of {replacement["name"]}?' if replacement else
                f'Would you start {bn} in Gameweek {preview}?')
    cta = (f'{question} That is the one call I want you to make. '
           'Tell me your choice and one reason in the comments. I will read the reasoning, not just the names. '
           'And subscribe to FPL Vortex if you want the next decision show before you set your team.')
    texts = [hook, story, one, two, three, plan, cta]
    labels = ['The captain problem', 'What actually counted', f'{n}: ownership or armband?',
              f'{bn}: my lineup choice', f'{jn}: the transfer decision', f'My GW{preview} plan', question]
    people = [c, correct_hero, c, b, injury, c, b]
    verdicts = ['CAPTAIN', 'HOLD', d1['verdict'], d2['verdict'], d3['verdict'], 'HOLD', 'MONITOR']
    phrases = [
        [('CAPTAIN FAIL' if captain_points <= 4 else 'TRUST HIM AGAIN?', 'captain'), ('THREE DECISIONS', 'three')],
        [(f'{points} POINTS', 'points'), ('THOSE POINTS COUNTED', 'counted'), ('WHAT CHANGES NOW?', 'change')],
        [(d1['verdict'], d1['verdict'].split()[0]), ('OWNERSHIP OR ARMBAND?', 'armband'), ('MY CAPTAIN SHORTLIST', 'captain')],
        [(f'START {bn.upper()}' if replacement else 'MONITOR', 'start' if replacement else 'monitor'), ('NO POINTS CHASING', 'points' if replacement else 'score'), ('CHECK THE TEAM NEWS', 'news')],
        [(d3['verdict'], 'wait' if d3['angle'] == 'availability' else 'monitor'), ('NO MOVE LOCKED', 'transfer'), ('DEADLINE CHECK', 'deadline')],
        [(d1['verdict'], d1['verdict'].split()[0]), (d2['verdict'], d2['verdict'].split()[0]), (d3['verdict'], d3['verdict'].split()[0])],
        [('YOUR CALL', 'choice'), ('ONE REASON', 'reason'), ('SET YOUR TEAM', 'team')],
    ]
    sections = []
    cursor = 0
    for index, ((key, length), text) in enumerate(zip(SECTION_TIMES, texts)):
        sections.append({'id': key, 'title': labels[index], 'start': cursor, 'end': cursor + length,
                         'duration': length, 'text': text, 'player_id': people[index]['id'],
                         'verdict': verdicts[index], 'phrases': [{'text': p, 'anchor': a} for p, a in phrases[index]],
                         'direction': 'Single blue portrait card; charcoal stage; one evidence panel; 0.4s dissolve; key word pulses on its spoken word boundary.'})
        cursor += length
    titles = [f'FPL GW{preview}: Sell {n} or Keep the Faith?',
              f'{n} Captain {"Pain" if captain_points <= 4 else "Call"}: My FPL GW{preview} Plan',
              f'FPL GW{preview}: Three Decisions After GW{gw}',
              f'Would You Start {bn}? My FPL GW{preview} Plan',
              f'FPL GW{preview}: Fix the Team or Trust It?']
    # Long verified player names must never break the title constraint.
    fallbacks = [f'FPL GW{preview}: Sell or Hold My Captain?', f'My Captain Call for FPL GW{preview}',
                 f'FPL GW{preview}: Three Decisions After GW{gw}', f'My Starting XI Choice for FPL GW{preview}',
                 f'FPL GW{preview}: Fix the Team or Trust It?']
    titles = [t if len(t) < 60 else fallbacks[i] for i, t in enumerate(titles)]
    thumbnails = ['SELL OR HOLD?', 'CAPTAIN PAIN' if captain_points <= 4 else 'TRUST HIM AGAIN?', 'MY NEXT MOVE']
    show = {'version': SHOW_VERSION, 'review_gw': gw, 'preview_gw': preview,
            'concept': f'Trust the squad or react to GW{gw}? Three early decisions for GW{preview}.',
            'central_conflict': f'Keep {n}, or let the captain outcome force a change?',
            'duration': cursor, 'title_options': titles, 'thumbnail_text_options': thumbnails,
            'decisions': decisions, 'sections': sections, 'question': question,
            'poll': {'question': question, 'options': [f'Start {bn}', f'Keep {replacement["name"]}' if replacement else f'Bench {bn}', 'Wait for team news']},
            'pinned_comment': question + ' Give me one reason for your choice.',
            'shorts': [{'title': f'{d["player"]["name"]}: {d["verdict"].title()}',
                        'start': sections[i + 2]['start'], 'end': sections[i + 2]['start'] + 30,
                        'player_id': d['player']['id'], 'verdict': d['verdict']} for i, d in enumerate(decisions)],
            'accuracy': {'source': 'One final official FPL snapshot', 'verified_at': package.get('verified_at'),
                         'captain_id': c['id'], 'effective_captain_id': effective['id'], 'captain_points': captain_points,
                         'gw_points': points, 'actual_bench_regret_id': b['id'] if regret else None,
                         'executed_transfers_claimed': False, 'fixture_difficulty_invented': False,
                         'injury_return_dates_invented': False, 'opinions_are_provisional': True},
            'analytics_review': {
                'status': 'manual_review_after_publication',
                'metrics': ['impressions click-through rate', 'first 30 seconds retention', 'retention at each decision', 'average percentage viewed'],
                'action': 'Compare with recent similar uploads. Diagnose the first major drop. Test up to three distinct title/thumbnail combinations in desktop Studio when eligible; use watch time as the test outcome, not CTR alone.',
                'source': 'https://support.google.com/youtube/answer/16391400?hl=en',
                'eligibility': 'Studio advanced features required. Private videos and Shorts are not eligible. Publish manually only after review; the workflow never starts a test or changes visibility.'},
            'b_roll': ['Captain portrait and doubled score', 'Actual previous XI, with no imagined bench points',
                       'One blue player hero at a time', 'Next verified opponents with home/away icons',
                       'Green/amber/red verdict fills', 'Single availability evidence panel', 'One audience question'],
            'sound': {'music': 'Continuous quiet bed under narration; no intro sting ahead of hook.',
                      'impacts': 'One soft impact at the first spoken captain reveal.', 'pause_after_hook': .35},
            'package': package}
    validate_show(show)
    return show


def validate_show(show):
    text = ' '.join(s['text'] for s in show['sections'])
    for phrase in BANNED:
        if phrase in text.casefold():
            raise RuntimeError(f'Forbidden narration phrase: {phrase}')
    if len(show['decisions']) != 3 or len({d['player']['id'] for d in show['decisions']}) != 3:
        raise RuntimeError('The show must contain exactly three distinct player decisions')
    if not 240 <= show['duration'] <= 360:
        raise RuntimeError('Decision show must be four to six minutes')
    for s in show['sections']:
        for p in s['phrases']:
            if len(p['text'].split()) > 5:
                raise RuntimeError(f'Graphic exceeds five words: {p["text"]}')
            if _plain(p['anchor']) not in _plain(s['text']):
                raise RuntimeError(f'Unspoken visual anchor: {p["anchor"]} in {s["id"]}')
    if len(show['title_options']) != 5 or any(len(t) >= 60 for t in show['title_options']):
        raise RuntimeError('Five titles under 60 characters are required')
    if any(len(t.split()) > 4 for t in show['thumbnail_text_options']):
        raise RuntimeError('Thumbnail text exceeds four words')


def prepare_show(ns):
    package = package_snapshot(ns)
    show = build_show(package)
    logo = Path('/content/drive/MyDrive/elements/logo.png')
    if logo.is_file():
        show['brand_logo'] = 'data:image/png;base64,' + base64.b64encode(logo.read_bytes()).decode()
    ns['DAY1_SHOW'] = show
    ns['GW_REVIEW_PACKAGE'] = package
    root = Path(ns['DATA_DIR'])
    _json(root / 'gw_review_package.json', package)
    _json(root / 'day1_show.json', show)
    print(f'Premium decision show: GW{package["gw"]} → GW{package["preview_gw"]}; three decisions; no results roll call')
    return show


def production_brief(show):
    def stamp(t):
        return f'{int(t)//60}:{int(t)%60:02}'
    rows = ['# FPL VORTEX — Decision Show', '',
            '## A. Concept and central conflict', '', show['concept'], '', show['central_conflict'], '',
            '## B. Five title options', '']
    rows += [f'{i}. {t}' for i, t in enumerate(show['title_options'], 1)]
    rows += ['', '## C. Thumbnail text', ''] + [f'- {t}' for t in show['thumbnail_text_options']]
    rows += ['', '## D–E. Narration, timing and visual directions', '',
             'Target duration: 4:50. The hook is the first audible content. Ryan speaks with measured phrasing; short pauses stay inside the section timing.', '']
    for s in show['sections']:
        rows += [f'### {stamp(s["start"])}–{stamp(s["end"])} — {s["title"]}', '',
                 s['text'], '', '**On screen:** ' + ' → '.join(f'`{p["text"]}`' for p in s['phrases']), '',
                 '**Visual:** ' + s['direction'], '']
    rows += ['## F. B-roll / graphics', ''] + [f'- {x}' for x in show['b_roll']]
    rows += ['', 'Keep the attached blue-card identity: portrait, club badge, fixture tiles and white evidence panel. Reveal only the current fact; no dense season-stat wall.', '',
             '## G. Three Shorts', '', 'The workflow exports three vertical clips. Each uses the relevant decision opening and ends at a sentence boundary within its section. The cuts below are planned; each run finalises the boundaries from Ryan’s actual spoken timing.', '']
    for s in show['shorts']:
        rows += [f'- **{s["title"]}** — {stamp(s["start"])}–{stamp(s["end"])}. Portrait-led vertical reframe; big verdict; source narration retained.']
    rows += ['', '## H. Community poll', '', show['poll']['question'], ''] + [f'- {o}' for o in show['poll']['options']]
    rows += ['', '## I. Pinned-comment question', '', show['pinned_comment'], '', '## J. Final accuracy check', '',
             f'- Source: final official GW{show["review_gw"]} snapshot, captured {show["accuracy"].get("verified_at") or "in the completed workflow"}.',
             f'- Verified total: {show["accuracy"]["gw_points"]}; effective captain contribution: {show["accuracy"]["captain_points"]}.',
             '- Starting/bench status uses actual picks and multipliers. No imagined bench haul or assumed autosub.',
             '- Fixtures and availability come from the same snapshot. No invented FDR, xPts, penalties, fitness clearance or recovery date.',
             '- HOLD / START / WAIT are editorial opinions and early plans. No transfer or captain change is described as already executed.',
             '- The first sentence creates tension; three decisions replace the fifteen-player roll call.',
             '- Editorial overlays contain at most five words; stats are shown one at a time; transitions last 0.4s.',
             '- Private upload policy remains in place. Review the final team news and full video before manually publishing.', '',
             '## Learning loop', '',
             'After publication, compare CTR and first-30-second retention with recent similar videos. Note the first major drop and which decision caused it. Change the next opening using that evidence. In eligible desktop YouTube Studio, test up to three meaningfully different title/thumbnail combinations and assess watch time as well as clicks. Private videos and Shorts cannot run that test.', '',
             '[YouTube: A/B test titles and thumbnails](https://support.google.com/youtube/answer/16391400?hl=en)', '',
             '## Sound', '', show['sound']['music'], show['sound']['impacts'], '']
    return '\n'.join(rows)
