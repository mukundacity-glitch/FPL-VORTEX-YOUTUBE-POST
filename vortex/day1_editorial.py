"""Evidence-led Day 1 review speech, measured pacing and word-timed captions.

No player/club/fixture/price, manager, or gameweek is baked into the template.
The previous completed GW squad is not proof of an editable pre-deadline squad.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import datetime
import math
import os
import re
from typing import Any


BANNED_STOCK = (
    'elite upside', 'tactical blueprint', 'midfield matrix',
    'ultimate asset', 'optimal long-term play', 'must-buy',
)
STAGE_DIRECTION = re.compile(r'\[(?:\d{1,2}:\d{2}|visual|narration|scene|pause|cut|camera)[^\]]*\]', re.I)
PLACEHOLDER = re.compile(r'\[(?:PLAYER|PRICE|RISK|STAT|OUTGOING|TEAM|FIXTURE)[^\]]*\]|\{\{[^{}]+\}\}', re.I)
WORD = re.compile(r"\b[\w’'-]+\b", re.UNICODE)


def _num(v: Any) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    try:
        n = float(v)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None


def _integer(v: Any) -> int | None:
    n = _num(v)
    return int(n) if n is not None else None


def _phrase_join(parts: list[str]) -> str:
    if not parts:
        return ''
    if len(parts) == 1:
        return parts[0]
    return ', '.join(parts[:-1]) + ' and ' + parts[-1]


def _fixture(p: dict[str, Any], next_gw: int) -> str:
    fx = p.get('next_fixture') or {}
    if _integer(fx.get('gw')) != next_gw or not fx.get('opp_name'):
        return ''
    return str(fx['opp_name']) + (' at home' if fx.get('is_home') is True else ' away' if fx.get('is_home') is False else '')


def _return(p: dict[str, Any], c: dict[str, Any]) -> str:
    s = c.get('stats') or {}
    facts: list[str] = []
    for key, singular, plural in (
        ('goals_scored', 'a goal', 'goals'),
        ('assists', 'an assist', 'assists'),
    ):
        n = _integer(s.get(key))
        if n is not None and n > 0:
            facts.append(singular if n == 1 else f'{n} {plural}')
    if p.get('pos') in {'GK', 'DEF'} and _num(s.get('clean_sheets')) and _num(s['clean_sheets']) > 0:
        facts.append('a clean sheet')
    if p.get('pos') == 'GK' and (_num(s.get('saves')) or 0) >= 3:
        facts.append(f"{_integer(s['saves'])} saves")
    dc = (c.get('point_breakdown') or {}).get('defensive_contribution')
    if _num(dc) and _num(dc) > 0:
        facts.append('awarded defensive-contribution points')
    return _phrase_join(facts[:2])


def _model(p: dict[str, Any]) -> tuple[float | None, float | None]:
    m = p.get('model_projection') or {}
    xpts = _num(m.get('next_gw_xpts'))
    xmins = _num(m.get('expected_minutes_next_gw'))
    return (xpts if xpts is not None and xpts > 0 else None,
            xmins if xmins is not None and 0 < xmins <= 90 else None)


class _Variety:
    """Choose the least-used wording so no stock sentence is spoken more than twice.

    Options that embed a player's name or number are naturally unique; the
    counter matters for the shared, name-free sentences. Selection is
    deterministic (rotated by ``seed``), so a rerun with the same data is stable.
    """

    def __init__(self) -> None:
        self.used: Counter[str] = Counter()

    def __call__(self, options: list[str], seed: int = 0) -> str:
        options = [o for o in options if o]
        best = min(range(len(options)),
                   key=lambda i: (self.used[options[i]], (i - seed) % len(options)))
        self.used[options[best]] += 1
        return options[best]


def _fixture_run(ctx: dict[str, Any]) -> str:
    """easy / mixed / demanding from three verified official FDR values, else ''."""
    runs = ctx.get('next_three') or []
    values = [_num(r.get('fdr')) for r in runs[:3]]
    if len(values) != 3 or any(v is None for v in values):
        return ''
    average = sum(values) / 3
    return 'encouraging' if average <= 2.5 else 'demanding' if average >= 3.5 else 'mixed'


def _player_script(p: dict[str, Any], ctx: dict[str, Any], idx: int, *, bench: bool,
                   next_gw: int, pick: _Variety | None = None) -> str:
    pick = pick or _Variety()
    name = str(ctx.get('full_name') or p.get('name') or '').strip()
    if not name:
        raise ValueError('A reviewed player has no verified spoken identity')
    state = str(p.get('review_state') or 'UNKNOWN').upper()
    s = ctx.get('stats') or {}
    points, minutes = _integer(s.get('total_points')), _integer(s.get('minutes'))
    played = state == 'FINAL' and minutes is not None and minutes > 0
    live = state in ('LIVE', 'PARTIAL') and minutes is not None and minutes > 0
    reason = _return(p, ctx) if played else ''
    fx = _fixture(p, next_gw)
    xpts, xmins = _model(p)
    official_status = str(ctx.get('status') or '').lower()
    lines: list[str] = []
    pts_word = 'point' if points == 1 else 'points'
    if played and points is not None:
        lines.append(pick([
            f'{name} finished on {points} {pts_word}.',
            f'For {name}, the return was {points} {pts_word}.',
            f'{name} came away with {points} {pts_word}.',
            f'{name}: {points} {pts_word} from the recorded match.',
            f'{name} ended the week on {points} {pts_word}.',
            f'The week brought {name} {points} {pts_word}.',
            f'{name} collected {points} {pts_word}.',
            f'That left {name} with {points} {pts_word}.',
        ], idx))
        if reason:
            lines.append(pick([
                f'That included {reason}.', f'The difference was {reason}.',
                f'The points came from {reason}.', f'Most of it came from {reason}.',
            ], idx))
        elif minutes is not None and minutes < 65:
            lines.append(pick([
                f'Only {minutes} minutes were recorded; the role matters more than this score.',
                f'With {minutes} minutes on the pitch, the score says little about the role.',
                f'{minutes} minutes is a small sample, so read the score carefully.',
            ], idx))
        bonus = _integer(s.get('bonus'))
        if bonus and bonus > 0:
            lines.append(pick(
                ['A bonus point helped.', 'One bonus point added to it.',
                 'There was a bonus point on top.', 'A single bonus point was part of it.',
                 'Bonus supplied one more point.'] if bonus == 1 else
                [f'Bonus added {bonus} points on top.', f'{bonus} bonus points helped.',
                 f'There were {bonus} bonus points on top.'], idx))
    elif live:
        got = f'{points} {pts_word} so far' if points is not None else 'a return so far'
        lines.append(pick([
            f'{name} has {got}, with the match still to finish.',
            f'{name} is on {got}; the match is still going.',
            f'For {name}, it is {got} and the match is not over.',
        ], idx))
    elif state == 'FINAL' and minutes == 0:
        lines.append(pick([
            f'{name} did not feature in the completed match.',
            f'{name} stayed out of the completed match.',
            f'There were no minutes for {name} in the completed match.',
        ], idx))
    else:
        lines.append(f"For {name}, the result is not verified yet. Don't count a missing score as a blank.")

    recent = ctx.get('last_three') or {}
    total3 = _integer(recent.get('total_points')) if recent.get('complete') else None
    role: str = ''
    if official_status and official_status != 'a':
        role = pick([
            'An official availability flag is active; check the latest team news first.',
            'The official status is flagged, so team news comes first.',
            'There is an official availability flag here; confirm the latest update before relying on the role.',
            'Availability is flagged officially, which makes the next team news important.',
        ], idx)
    elif played and minutes is not None and minutes < 65:
        role = pick([
            'Short playing time could make the next start risky, even with a good fixture.',
            'A short appearance makes the next selection harder to trust.',
            'Limited minutes leave the next start in question.',
            'Check the team sheet before counting on a repeat of this role.',
            'The minutes were limited, which keeps the role uncertain.',
            'A short shift is a reason for caution, whatever the fixture.',
        ], idx)
    elif xmins is not None and xmins < 65:
        role = pick([
            f'The Vortex minutes estimate is {round(xmins)}, so the selection risk needs attention.',
            f'Vortex expects around {round(xmins)} minutes, which keeps selection in doubt.',
            f'A {round(xmins)}-minute estimate from Vortex makes the role the main question.',
        ], idx)
    elif bench:
        role = pick([
            'For the bench, dependable minutes are more useful than one surprise return.',
            'A reserve is only useful cover if the starting place behind him is secure.',
            'Bench depth is the protection here, provided the role is genuinely secure.',
            'Cover from the bench matters most in the week an absence appears.',
            'A bench place earns its value through likely minutes, not one good score.',
            'The question for a reserve is how quickly he would be needed.',
        ], idx)
    elif idx % 2 == 0 or total3 is None:
        role = pick([
            'Recorded minutes are encouraging; they do not guarantee another start.',
            'The next decision still depends on team selection, not just the last score.',
            'There is some playing-time evidence, but the role could still change.',
            'A good return matters less if the next ninety minutes are uncertain.',
            'Starting security is the useful question heading into the next fixture.',
            'A full appearance is evidence, not a promise of the next one.',
            'The next team sheet will tell us more than the previous points.',
            'Selection, more than the last score, drives the next decision.',
            'A run of starts matters more than any single match.',
            'The role is the thing to protect, and the score is only part of it.',
        ], idx)
    if role:
        lines.append(role)
    if total3 is not None and (idx % 2 == 1 or not role):
        pw3 = 'point' if total3 == 1 else 'points'
        lines.append(pick([
            f'Across the last three Gameweeks, that makes {total3} {pw3}.',
            f'The last three Gameweeks add up to {total3} {pw3}.',
            f'That is {total3} {pw3} over three Gameweeks.',
            f'Over the last three Gameweeks, the total is {total3} {pw3}.',
            f'The three-week return stands at {total3} {pw3}.',
            f'The three-week total is {total3} {pw3}.',
        ], idx))

    if fx:
        lines.append(pick([
            f'Next is {fx}.', f'They face {fx} next.', f'The next fixture is {fx}.',
            f'Coming up, {fx}.', f'The schedule sends them {fx}.',
        ], idx))
        run = _fixture_run(ctx)
        if run and idx % 3 != 1:
            lines.append(pick([
                f'The run of three fixtures looks {run}.',
                f'After that, the fixture run looks {run}.',
                f'The three-match outlook is {run}.',
                f'Looking a little further, the schedule reads as {run}.',
                f'Beyond that fixture, the next three games look {run}.',
                f'The upcoming three-game stretch looks {run} on paper.',
                f'On paper, the next three fixtures are {run}.',
                f'The short-term schedule is {run}, according to the official ratings.',
            ], idx))
    else:
        lines.append(pick([
            'There is no verified next fixture to plan around.',
            'The next opponent is unconfirmed in the available data.',
            'The schedule is not verified, so leave that comparison open.',
            'We cannot use a fixture that is missing from the current snapshot.',
            'Without a confirmed next fixture, the selection risk comes first.',
        ], idx))
    price, owned = _num(ctx.get('current_price')), _num(p.get('ownership'))
    if idx % 3 == 2 and price and price > 0 and owned is not None and owned > 0:
        lines.append(pick([
            f'{name} costs {price:.1f} million and is owned by {owned:.1f} percent of managers.',
            f'{owned:.1f} percent of managers own {name}, who costs {price:.1f} million.',
            f'At {price:.1f} million, {name} sits in {owned:.1f} percent of squads.',
            f'{name} is priced at {price:.1f} million, with {owned:.1f} percent ownership.',
        ], idx))
    if xpts is not None and idx % 3 == 1:
        lines.append(pick([
            f'Vortex estimates {xpts:.1f} expected points, not a guaranteed result.',
            f'The Vortex forecast is {xpts:.1f} points, with uncertainty.',
            f'At {xpts:.1f} projected points, the model only suggests a possibility.',
            f'Vortex has {xpts:.1f} expected points; the actual return can differ.',
            f'That {xpts:.1f}-point forecast depends on the minutes assumption.',
        ], idx))
    return ' '.join(lines)


_NUMBER_WORDS = {2: 'Two', 3: 'Three', 4: 'Four', 5: 'Five', 6: 'Six'}


def _squad_data_note(roster: list[dict[str, Any]], context: dict[int, dict[str, Any]]) -> str:
    """Squad-level facts from verified fields only; each sentence is omitted when its data is missing."""
    parts: list[str] = []
    owned = [(float(o), str(context[int(p['id'])].get('full_name') or p.get('name') or ''))
             for p in roster if (o := _num(p.get('ownership'))) is not None and o > 0]
    if len(owned) >= 10:
        hi, lo = max(owned), min(owned)
        if hi[1] and lo[1] and hi[1] != lo[1] and hi[0] - lo[0] >= 5:
            parts.append(f'{hi[1]} is the most widely owned player here at {hi[0]:.1f} percent, '
                         f'while {lo[1]} is the sharpest differential at {lo[0]:.1f} percent.')
    clubs = Counter(str(context[int(p['id'])].get('club') or '') for p in roster)
    clubs.pop('', None)
    if clubs:
        club, count = max(clubs.items(), key=lambda kv: (kv[1], kv[0]))
        if count >= 2 and count in _NUMBER_WORDS:
            parts.append(f'{_NUMBER_WORDS[count]} of the fifteen come from {club}, '
                         'so one result can move several returns at once.')
    priced = [(float(c), str(context[int(p['id'])].get('full_name') or ''))
              for p in roster if (c := _num(context[int(p['id'])].get('current_price'))) is not None and c > 0]
    if priced and max(priced)[1]:
        top = max(priced)
        parts.append(f'The most expensive pick is {top[1]} at {top[0]:.1f} million, so that place carries the most weight.')
    return ' '.join(parts)


def _candidate_data(official_players: list[dict[str, Any]], model_rows: dict[int, Any], roster: list[dict[str, Any]]) -> list[dict[str, Any]]:
    owned = {int(p['id']) for p in roster}
    counts = Counter(int(p['team_id']) for p in roster if p.get('team_id') is not None)
    ranked: list[dict[str, Any]] = []
    for p in official_players:
        pid = _integer(p.get('id'))
        club = _integer(p.get('team'))
        if pid is None or pid in owned or club is None or counts[club] >= 3 or str(p.get('status')) != 'a':
            continue
        projection = model_rows.get(pid)
        if projection is None:
            continue
        if hasattr(projection, 'to_dict'):
            projection = projection.to_dict()
        if not isinstance(projection, dict):
            continue
        xp, mins = _num(projection.get('next_gw_xpts')), _num(projection.get('expected_minutes_next_gw'))
        cost = _num(p.get('now_cost'))
        if xp is None or xp <= 0 or mins is None or mins < 60 or cost is None or cost <= 0:
            continue
        if not p.get('web_name') or p.get('element_type') not in (1, 2, 3, 4):
            continue
        ranked.append(dict(id=pid, name=str(p['web_name']), club_id=club, position=p['element_type'],
                           price=cost / 10, xpts=xp, xmins=mins))
    return sorted(ranked, key=lambda x: (-x['xpts'], -x['xmins'], x['price'], x['id']))



def _compact_player_script(p: dict[str, Any], ctx: dict[str, Any], *, next_gw: int) -> str:
    """One evidence-backed beat per player for the shorter Day 1 cut."""
    name = str(ctx.get('full_name') or p.get('name') or '').strip()
    if not name:
        raise ValueError('A reviewed player has no verified spoken identity')
    state = str(p.get('review_state') or 'UNKNOWN').upper()
    stats = ctx.get('stats') or {}
    points = _integer(stats.get('total_points'))
    minutes = _integer(stats.get('minutes'))
    unit = 'point' if points == 1 else 'points'
    if state == 'FINAL' and minutes is not None and minutes > 0 and points is not None:
        first = f'{name} returned {points} {unit} in the completed Gameweek.'
    elif state in ('LIVE', 'PARTIAL') and minutes is not None and minutes > 0 and points is not None:
        first = f'{name} is on {points} {unit} so far; the result is not final.'
    elif state == 'FINAL' and minutes == 0:
        first = f'{name} did not play in the completed match.'
    else:
        first = f'{name} has no verified final return yet.'
    flagged = str(ctx.get('status') or '').lower() not in ('', 'a')
    next_fixture = _fixture(p, next_gw)
    if flagged:
        second = f'Team news is flagged for {name}; check availability before a move.'
    elif next_fixture:
        second = f'For {name}, next is {next_fixture}.'
    else:
        second = f'The next fixture for {name} is not verified.'
    return first + ' ' + second


def build_editorial_review(
    original: list[dict[str, Any]], starters: list[dict[str, Any]],
    bench: list[dict[str, Any]], context: dict[int, dict[str, Any]], *,
    review_gw: int, next_gw: int, review_status: str,
    official_players: list[dict[str, Any]] | None = None,
    model_rows: dict[int, Any] | None = None,
    target_seconds: int = 480,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Generate the complete review afresh from this run's evidence only.

    Most recent review picks are explicitly NOT a verified current transfer state.
    No free-transfer, bank or hit arithmetic is manufactured.
    """
    if not (1 <= review_gw < next_gw <= 38):
        raise ValueError('Review and upcoming Gameweeks are inconsistent')
    compact = os.environ.get('VORTEX_DAY1_COMPACT', '').strip() == '1'
    if compact:
        target_seconds = 240
    if not 240 <= target_seconds <= 900:
        raise ValueError('Review duration target outside supported bounds')
    roster = starters + bench
    ids = [int(p['id']) for p in roster]
    if len(roster) != 15 or len(set(ids)) != 15 or set(ids) != set(context):
        raise ValueError('Only a verified fifteen-player review can be narrated as a squad review')
    scripts = deepcopy(original)
    index = {s['id']: s for s in scripts}
    expected = [s for s in scripts if s.get('player_id') is not None]
    if [int(s['player_id']) for s in expected] != ids:
        raise ValueError('Narration/visual player ordering differs from the verified review')
    provisional = review_status.upper() not in ('FINAL', 'COMPLETE')
    pick = _Variety()
    for i, p in enumerate(roster):
        segment = index[f"player_{p['id']}"]
        segment['text'] = (
            _compact_player_script(p, context[int(p['id'])], next_gw=next_gw)
            if compact else
            _player_script(p, context[int(p['id'])], i, bench=i >= len(starters),
                           next_gw=next_gw, pick=pick)
        )
        segment['editorial_source'] = ['official review picks', 'official live player statistics', 'official bootstrap', 'official fixtures']
        if p.get('model_projection'):
            segment['editorial_source'].append('Vortex projected next-GW model, estimate only')
    # Reuse the verified formation/points line the review already built, when present.
    lead = str(index['headline'].get('text') or '').strip()
    if not re.match(r"(?i)(?:let's review )?gameweek \d+", lead):
        lead = ''
    opener = ((lead + ' The points count, but our next decision needs a closer look. ') if lead else
              f'Gameweek {review_gw}: the points count, but our next decision needs a closer look. ')
    opener += 'Minutes, availability and bench cover matter more than a single result.'
    if compact:
        opener = f'Gameweek {review_gw} review: the next decision comes down to minutes, team news and value.'
    index['headline']['text'] = opener
    if 'bench_intro' in index:
        index['bench_intro']['text'] = 'Now the bench. Can these players really cover an absence?'
    if 'metrics_intro' in index:
        index['metrics_intro']['text'] = 'Beyond the points, what did captaincy and bench cover actually tell us?'
    if 'review_close' in index:
        index['review_close']['text'] = (
            'These are review picks, not a verified future squad. '
            'A personal transfer still needs current bank, selling prices, free transfers and availability.'
            + (' One match was still unfinished when this was recorded, so a few returns may still move.'
               if provisional else '')
        )
    # Review-specific narration has a dedicated full-data-board phase after the
    # player card sequence; these scenes never claim a current live editable XI.
    frame = [p for p in starters if context[int(p['id'])].get('status') not in ('', 'a')]
    short_minutes = [p for p in starters if _integer((context[int(p['id'])].get('stats') or {}).get('minutes')) is not None
                     and _integer((context[int(p['id'])].get('stats') or {}).get('minutes')) < 65
                     and str(p.get('review_state')) == 'FINAL']
    note = ''
    if frame:
        note = f"There {'is' if len(frame) == 1 else 'are'} {len(frame)} officially flagged starter{'s' if len(frame) != 1 else ''} in the latest selection. That is the first place to check the team news."
    elif short_minutes:
        note = f"There {'is' if len(short_minutes) == 1 else 'are'} {len(short_minutes)} starter{'s' if len(short_minutes) != 1 else ''} with fewer than sixty-five recorded minutes. Watch the role before making a change."
    else:
        note = 'There is no verified reason here to panic about the starting eleven just because of one quiet result. Start with the actual availability and likely minutes.'
    insert = [
        {'id':'editorial_squad_context',
         'text':note + ' The squad structure matters more than a surprising bench return.'},
    ]
    squad_data = _squad_data_note(roster, context)
    if squad_data:
        insert.append({'id':'editorial_squad_data','text':squad_data,
                       'editorial_source':['official ownership','official prices','official team data']})
    # One prospective comparison is sufficient for an evidence-led discussion.
    # It is intentionally NOT a personalized transfer: the current bank/selling
    # prices and next-GW editable squad are not verified by historical picks.
    cands = _candidate_data(official_players or [], model_rows or {}, roster)
    if cands:
        lead = cands[0]
        eligible_owned = [p for p in roster if p['pos'] == {1:'GK', 2:'DEF', 3:'MID', 4:'FWD'}[lead['position']]]
        comparison = None
        for p in eligible_owned:
            xp, _ = _model(p)
            if xp is not None and (comparison is None or xp < comparison[0]):
                comparison = (xp, p)
        candidate_text = (
            f"For a model-backed alternative, {lead['name']} is worth comparing at {lead['price']:.1f} million. "
            f"Vortex estimates {lead['xpts']:.1f} points and roughly {round(lead['xmins'])} minutes. "
            'These are estimates, not assurances of selection. '
        )
        if comparison:
            candidate_text += (
                f"The last confirmed squad has {comparison[1]['name']} at {comparison[0]:.1f} "
                'projected points. Check affordability and likely minutes before deciding.'
            )
        else:
            candidate_text += 'Without a verified direct comparison, waiting remains an option.'
        insert.append({'id':'editorial_comparison','text':candidate_text,
                       'editorial_source':['current official FPL bootstrap','dated Vortex xPts/xMinutes model']})
    insert.extend([
        {'id':'editorial_defence','text':(
            'For defenders, check likely starts, clean-sheet chances, attacking involvement '
            'and verified defensive contributions. Defensive action totals are not awarded '
            'FPL points. Rotation can still spoil a good fixture.')},
        {'id':'editorial_routes','text':(
            'There are three routes. Hold a transfer if you can field eleven reliable starters. '
            'Use one move to repair a real weakness. A hit needs to improve several '
            'upcoming lineups enough to justify its cost.')},
        {'id':'editorial_tradeoff','text':(
            'A friendly fixture alone is not enough if the move weakens your bench. '
            'Compare minutes and genuine alternatives. Price changes and ownership '
            'do not guarantee returns.')},
        {'id':'editorial_verdict','text':(
            'The verdict depends on current team news and your actual squad. '
            'Protect reliable starters. If the team works, waiting can be sensible. '
            'Expected points are forecasts, not guaranteed returns. '
            'Thanks for watching FPL Vortex; see you next Gameweek.')},
    ])
    # Review close is followed by extra editorial beats on the same review
    # scoreboard, never inserted into the 15-player animation sequence.
    if compact:
        short_text = {
            'editorial_defence': 'For defenders, check likely starts and clean-sheet chances.',
            'editorial_routes': 'Hold when your eleven is reliable. Spend a transfer to fix a real risk. Only take a hit when its benefit justifies the cost.',
            'editorial_tradeoff': 'One kind fixture is not enough. Compare minutes, bench cover and price before moving.',
            'editorial_verdict': 'Hold if the squad is healthy; act if verified team news exposes a weakness. Expected points are forecasts, not guaranteed returns. Thanks for watching FPL Vortex.',
        }
        if 'bench_intro' in index:
            index['bench_intro']['text'] = 'The bench matters when starters are unavailable.'
        if 'metrics_intro' in index:
            index['metrics_intro']['text'] = 'Now the captaincy and squad cover.'
        if 'review_close' in index:
            index['review_close']['text'] = (
                'These are review picks, not a confirmed next-Gameweek team.'
                + (' Some matches are unfinished; returns can change.' if provisional else '')
            )
        for beat in insert:
            key = beat['id']
            if key in short_text:
                beat['text'] = short_text[key]
            elif key == 'editorial_squad_context':
                beat['text'] = note
            elif key == 'editorial_squad_data':
                beat['text'] = squad_data.split('. ')[0].rstrip('.') + '.' if squad_data else 'Verify the squad data before making a move.'
            elif key == 'editorial_comparison' and cands:
                candidate = cands[0]
                beat['text'] = (
                    f"Model comparison: {candidate['name']} at {candidate['price']:.1f} million, "
                    f"forecast {candidate['xpts']:.1f} points. Verify minutes and affordability."
                )
    scripts.extend(insert)
    validate_narration(scripts, player_ids=ids, max_words=1700)
    words = sum(len(WORD.findall(seg.get('text',''))) for seg in scripts)
    return scripts, {'target_seconds':target_seconds,'draft_words':words,
                     'review_gw':review_gw,'next_gw':next_gw,
                     'current_transfer_state_verified':False,
                     'source':'official review snapshot plus attributed Vortex estimates',
                     'candidate_comparison':bool(cands)}


def validate_narration(segments: list[dict[str, Any]], *, player_ids: list[int], max_words: int = 1700) -> None:
    spoken = [str(s.get('text') or '').strip() for s in segments]
    if not spoken or any(not line for line in spoken):
        raise ValueError('Empty narration segment')
    all_text = ' '.join(spoken)
    if STAGE_DIRECTION.search(all_text) or PLACEHOLDER.search(all_text):
        raise ValueError('Stage direction or unresolved placeholder in spoken text')
    if any(stock in all_text.lower() for stock in BANNED_STOCK):
        raise ValueError('Repetitive hype phrase in narration')
    if re.search(r'\b(?:nailed|must[ -]buy|must[ -]sell)\b',all_text,re.I) or re.search(r'\bguaranteed\b', re.sub(r'\bnot (?:a )?guaranteed\b', '', all_text, flags=re.I), re.I):
        raise ValueError('Unsupported certainty in narration')
    actual = [int(s['player_id']) for s in segments if s.get('player_id') is not None]
    if actual != player_ids:
        raise ValueError('Player narration and visual sequencing drifted')
    if len(spoken) != len(set(x.lower() for x in spoken)):
        raise ValueError('Duplicate narration segments')
    if len(WORD.findall(all_text)) > max_words:
        raise ValueError('Narration exceeds review editorial limit')
    # Avoid mechanical repeated openings without banning natural transitions.
    starts = [' '.join(WORD.findall(text.lower())[:5]) for text in spoken]
    if max(Counter(starts).values()) > 3:
        raise ValueError('Too many identical sentence openings')
    sentences = [re.sub(r'\s+', ' ', part.lower().strip())
                 for text in spoken for part in re.split(r'(?<=[.!?])\s+', text)
                 if len(WORD.findall(part)) >= 7]
    if sentences and max(Counter(sentences).values()) > 3:
        raise ValueError('Excessive repeated sentences across player segments')


def review_voice_profile(mood: str, variation: int = 0) -> dict[str, str]:
    # Edge Ryan supports rate, pitch and volume; not arbitrary SSML acting.
    # Subtle changes between segments, not an exaggerated presenter voice.
    profiles = {
        'intro': ('+1%', '-2Hz'),
        'analysis': ('-3%', '-2Hz'),
        'key_stat': ('-1%', '-2Hz'),
        'warning': ('-5%', '-2Hz'),
        'outro': ('+0%', '-2Hz'),
    }
    rate,pitch = profiles.get(mood,profiles['analysis'])
    if variation and mood == 'analysis':
        # Small, repeatable changes so consecutive players do not share one
        # flat delivery. Stays within Edge's supported rate/pitch controls.
        r = int(rate.rstrip('%')) + (0, 2, -1, 3, -2)[variation % 5]
        h = int(pitch.removesuffix('Hz')) + (0, 1, -1)[variation % 3]
        rate, pitch = f'{r:+d}%', f'{h:+d}Hz'
    return {'rate':rate,'pitch':pitch,'volume':'+0%'}


def measured_audio_report(segments: list[dict[str, Any]], duration: float, *, target_seconds: int = 480) -> dict[str, Any]:
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('Measured narration duration must be positive')
    words = sum(len(WORD.findall(str(s.get('text') or ''))) for s in segments)
    return {'target_seconds':target_seconds,'audio_seconds':round(duration,3),
            'delta_seconds':round(duration-target_seconds,3),
            'spoken_words':words,'measured_wpm':round(60*words/duration,1),
            'within_target':abs(duration-target_seconds)<=60}


def _ts(seconds: float) -> str:
    ms = int(round(max(0.,seconds)*1000))
    h,ms=divmod(ms,3600000);m,ms=divmod(ms,60000);s,ms=divmod(ms,1000)
    return f'{h:02d}:{m:02d}:{s:02d}.{ms:03d}'


def word_timed_vtt(segments: list[dict[str, Any]], *, max_words: int = 8, max_seconds: float = 3.8) -> str:
    """Short captions from measured TTS WordBoundary offsets, not guessed text timings."""
    if not 3 <= max_words <= 12:
        raise ValueError('Unsupported subtitle words-per-cue limit')
    cues: list[tuple[float,float,str]] = []
    for seg in segments:
        boundary = seg.get('words') or []
        if not boundary:
            raise ValueError('Caption synchronization requires actual TTS word boundaries')
        t0 = float(seg['t0']); t1 = float(seg['t1'])
        words: list[tuple[float,float,str]] = []
        for w in boundary:
            text = str(w.get('text') or '').strip()
            start = t0+float(w['start'])
            end = min(t1,start+max(0.03,float(w['duration'])))
            if not text or start >= t1 or end <= start:
                continue
            words.append((start,end,text))
        if not words:
            raise ValueError(f"TTS had no captionable words for {seg.get('id')}")
        chunk: list[tuple[float,float,str]] = []
        for word in words:
            if chunk and (len(chunk) >= max_words or word[1]-chunk[0][0] > max_seconds):
                cues.append((chunk[0][0],chunk[-1][1], ' '.join(w[2] for w in chunk)))
                chunk=[]
            chunk.append(word)
        if chunk:
            cues.append((chunk[0][0],chunk[-1][1], ' '.join(w[2] for w in chunk)))
    result=['WEBVTT','']
    prior_end=0.0
    for index,(a,b,t) in enumerate(cues,1):
        a=max(a,prior_end)
        if b <= a:
            continue
        result.extend([str(index),f'{_ts(a)} --> {_ts(b)}',t,''])
        prior_end=b
    if len(result)<6:
        raise ValueError('No valid timed captions produced')
    return '\n'.join(result)