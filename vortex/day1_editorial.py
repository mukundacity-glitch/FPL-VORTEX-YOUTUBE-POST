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


def _player_script(p: dict[str, Any], ctx: dict[str, Any], idx: int, *, bench: bool, next_gw: int) -> str:
    name = str(ctx.get('full_name') or p.get('name') or '').strip()
    if not name:
        raise ValueError('A reviewed player has no verified spoken identity')
    state = str(p.get('review_state') or 'UNKNOWN').upper()
    s = ctx.get('stats') or {}
    points, minutes = _integer(s.get('total_points')), _integer(s.get('minutes'))
    played = state == 'FINAL' and minutes is not None and minutes > 0
    provisional = state in ('LIVE', 'PARTIAL') and minutes is not None and minutes > 0
    reason = _return(p, ctx) if played else ''
    fx = _fixture(p, next_gw)
    xpts, xmins = _model(p)
    official_status = str(ctx.get('status') or '').lower()
    lines: list[str] = []
    if played and points is not None:
        starts = (
            f'{name} finished on {points} points.',
            f'For {name}, the return was {points} points.',
            f'{name} came away with {points} points.',
            f'{name}: {points} points from the recorded match.',
        )
        lines.append(starts[idx % len(starts)])
        if reason:
            lines.append(('That included ' if idx % 2 else 'The difference was ') + reason + '.')
        elif minutes is not None and minutes < 65:
            lines.append(f'Only {minutes} minutes were recorded; the role matters more than this score.')
    elif provisional:
        lines.append(f'{name} has a provisional return; the match or points are not final yet.')
    elif state == 'FINAL' and minutes == 0:
        lines.append(f'{name} did not feature in the completed match.')
    else:
        lines.append(f"For {name}, the result is not verified yet. Don't count a missing score as a blank.")
    if official_status and official_status != 'a':
        lines.append('An official availability flag is active; check the latest team news first.')
    elif played and minutes is not None and minutes < 65:
        lines.append('Short playing time could make the next start risky, even with a good fixture.')
    elif xmins is not None and xmins < 65:
        lines.append(f'The VORTEX minutes estimate is {round(xmins)}, so the selection risk needs attention.')
    elif bench:
        lines.append('For the bench, dependable cover matters more than one surprise return.')
    else:
        lines.append('Recorded minutes help, but they cannot make the next start certain.')
    if fx:
        lines.append(f'Next is {fx}.')
    else:
        lines.append('There is no verified next fixture to use in this comparison.')
    if xpts is not None and idx % 3 == 1:
        lines.append(f'VORTEX estimates {xpts:.1f} expected points, not a guaranteed return.')
    elif bench:
        lines.append('If the first eleven is uncertain, that bench reliability becomes crucial.')
    elif official_status and official_status != 'a':
        lines.append('That is a reason to wait for an update, not chase the previous points.')
    else:
        lines.append('Compare this role against the alternatives before spending a move.')
    return ' '.join(lines)


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
    for i, p in enumerate(roster):
        segment = index[f"player_{p['id']}"]
        segment['text'] = _player_script(p, context[int(p['id'])], i, bench=i >= len(starters), next_gw=next_gw)
        segment['editorial_source'] = ['official review picks', 'official live player statistics', 'official bootstrap', 'official fixtures']
        if p.get('model_projection'):
            segment['editorial_source'].append('VORTEX projected next-GW model, estimate only')
    opener = f'Gameweek {review_gw}: before we look at the next set of decisions, separate what happened from what the result suggests.'
    if provisional:
        opener += " Some matches or scores are still provisional, so they won't be treated as final."
    opener += " The useful questions are about minutes, availability and whether the squad has enough cover. Let's go through the actual selections first."
    index['headline']['text'] = opener
    if 'bench_intro' in index:
        index['bench_intro']['text'] = "The starting eleven is only half the decision. Let's look at the players available as cover, and whether the bench gives us enough room to wait for team news."
    if 'metrics_intro' in index:
        index['metrics_intro']['text'] = 'Now step away from the individual scores. What do the captaincy, the bench and the available players tell us about the next decision?'
    if 'review_close' in index:
        index['review_close']['text'] = ("That brings the review together. The players and points are from the latest completed selection, not a confirmed future squad. "
                                      "Any transfer decision still needs an updated bank, selling prices, free transfers and final availability information.")
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
        {'id':'editorial_squad_context', 'text':note + " This is why reviewing the squad's structure is more useful than reacting to the biggest score on the bench."},
        {'id':'editorial_minutes', 'text':"A player returning points is good news; it doesn't tell us how likely the next start is. Look at actual minutes, how the role has changed and the alternatives available. If that evidence is incomplete, waiting for the deadline information is a valid decision."},
    ]
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
        candidate_text = (f"Among available, model-covered alternatives, {lead['name']} is worth comparing. "
                          f"The current FPL price is {lead['price']:.1f} million, with a VORTEX estimate of {lead['xpts']:.1f} expected points and roughly {round(lead['xmins'])} minutes. "
                          "Those are model estimates, not official predictions or assurances of selection. ")
        if comparison:
            candidate_text += (f"The model has {comparison[1]['name']} at {comparison[0]:.1f} expected points in the most recently confirmed squad. "
                               "That difference gives us a reason to investigate, not permission to ignore transfer costs.")
        else:
            candidate_text += 'There is no verified player-for-player model comparison here, so the right move is still conditional.'
        insert.append({'id':'editorial_comparison','text':candidate_text,
                       'editorial_source':['current official FPL bootstrap','dated VORTEX xPts/xMinutes model']})
    insert.extend([
        {'id':'editorial_routes','text':("There are three sensible routes. If there are enough likely starters, keeping a free transfer can protect flexibility. "
                                         "If one regular starter looks unavailable, a single move may solve the bigger problem. "
                                         "A points hit needs a stronger case: it should improve the expected line-up over more than one week after its cost. None of that can be priced precisely from last week's picks alone.")},
        {'id':'editorial_tradeoff','text':("Think about the players you're leaving behind as well as the ones you might buy. "
                                           "The best headline fixture isn't automatically the best transfer if it leaves the bench exposed. "
                                           "Ownership and rising prices are useful context, but not evidence of a return. And a forecast only helps if the underlying minutes and availability assumptions are plausible.")},
        {'id':'editorial_verdict','text':("So the verdict is conditional: check the verified squad, then decide what actually needs fixing. "
                                          "Prioritise reliable minutes and a playable starting eleven. Compare future fixtures rather than buying last week's points. "
                                          "Where the team is already functional, there's nothing wrong with waiting. "
                                          "Expected points are forecasts, not guaranteed returns. Thanks for watching FPL VORTEX, and good luck for the next Gameweek.")},
    ])
    # Review close is followed by extra editorial beats on the same review
    # scoreboard, never inserted into the 15-player animation sequence.
    scripts.extend(insert)
    validate_narration(scripts, player_ids=ids, max_words=1700)
    words = sum(len(WORD.findall(seg.get('text',''))) for seg in scripts)
    return scripts, {'target_seconds':target_seconds,'draft_words':words,
                     'review_gw':review_gw,'next_gw':next_gw,
                     'current_transfer_state_verified':False,
                     'source':'official review snapshot plus attributed VORTEX estimates',
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


def review_voice_profile(mood: str) -> dict[str, str]:
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