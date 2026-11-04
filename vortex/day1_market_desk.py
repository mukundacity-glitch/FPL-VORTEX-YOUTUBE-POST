"""Post-review market watchlist, using the existing Day 3 selection policy.

Event transfer counts describe manager activity, not a legal personal transfer.
The review's fifteen-player scoring timeline remains a separate contract.
"""
from __future__ import annotations
import math


def _number(value):
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None


def build_market_desk(bootstrap):
    import pandas as pd
    from day3.transfer_desk import select_transfer_desk
    players = bootstrap.get('elements') or []
    if not players:
        raise ValueError('Market desk requires the current official player snapshot')
    frame = pd.DataFrame(players)
    groups = select_transfer_desk(
        frame, total_managers=bootstrap.get('total_players'), count=1,
        recent_performance={int(p['id']): {'form': p.get('form')} for p in players},
    )
    # A popular unavailable player can be shown as a sell, never as a buy.
    eligible = [p for p in players if p.get('status') == 'a'
                and (_number(p.get('minutes')) or 0) > 0
                and _number(p.get('transfers_in_event')) is not None
                and _number(p.get('transfers_out_event')) is not None
                and float(p['transfers_in_event']) > float(p['transfers_out_event'])]
    eligible.sort(key=lambda p: (-float(p['transfers_in_event']),
                                -(float(p['transfers_in_event'])-float(p['transfers_out_event'])), int(p['id'])))
    buy_id = int(eligible[0]['id']) if eligible else None
    groups['BUY'] = [{'player_id': buy_id}] if buy_id else []
    groups['HOLD'] = [r for r in groups['HOLD'] if int(r['player_id']) != buy_id
                      and next(p for p in players if int(p['id']) == int(r['player_id'])).get('status') == 'a']
    by_id = {int(p['id']): p for p in players}
    result = []
    for action in ('BUY', 'HOLD', 'SELL'):
        if not groups[action]:
            result.append(dict(segment_id=f'market_{action.lower()}_empty', action=action,
                element=None, text=f'{action.title()} watchlist: no player clears the evidence checks in this snapshot. Leave that slot open.'))
            continue
        row = groups[action][0]
        p = by_id[int(row['player_id'])]
        name = str(p['web_name'])
        incoming, outgoing = int(p['transfers_in_event']), int(p['transfers_out_event'])
        if action == 'BUY':
            reason = f'{incoming:,} transfers in against {outgoing:,} out in the current event. Official status is available. Compare the fixtures and likely minutes before buying.'
        elif action == 'SELL':
            reason = f'{outgoing:,} transfers out against {incoming:,} in. That selling pressure is a reason to check the role and team news, not an automatic instruction to copy the crowd.'
        else:
            reason = f"Ownership is {p['selected_by_percent']} percent despite recent form of {p['form']} points per match. Most estimated owners have held. One quiet run alone is not a reason to sell."
        if p.get('status') != 'a':
            reason += ' This player has an availability flag; check the official update.'
        result.append(dict(segment_id=f'market_{action.lower()}', action=action,
            element=p, text=f'{action.title()} watchlist: {name}. {reason}'))
    return result


def insert_market_segments(segments, desk):
    """Place the desk directly after the retrospective closing beat."""
    cut = next(i for i, s in enumerate(segments) if s['id'] == 'review_close') + 1
    additions = [dict(id='market_intro', text=(
        "Now the next Gameweek: buy, hold and sell watchlists. These are current-event market trends, "
        "not rolling transfer momentum or a personalized move. Check your budget and free transfers first."))]
    additions.extend(dict(id=r['segment_id'], text=r['text']) for r in desk)
    return segments[:cut] + additions + segments[cut:]


def market_card(record, teams, fixtures, photo_resolver=None):
    p = record['element']
    if p is None:
        return None
    team = teams[int(p['team'])]
    code = str(p.get('code') or '')
    pos = {1:'GK', 2:'DEF', 3:'MID', 4:'FWD'}[int(p['element_type'])]
    def number(key, decimals=0):
        n = _number(p.get(key))
        return f'{n:,.{decimals}f}' if n is not None else '—'
    labels = [('transfers_in_event','TRANSFERS IN','people',0),
              ('transfers_out_event','TRANSFERS OUT','people',0),
              ('form','RECENT FORM','star',1), ('minutes','SEASON MINUTES','clock',0),
              ('total_points','SEASON POINTS','star',0), ('points_per_game','POINTS PER MATCH','star',1)]
    return dict(id=int(p['id']), name=p['web_name'], first_name=p.get('first_name',''),
        surname=p.get('second_name') or p['web_name'], position=pos,
        club=team['name'], club_short=team['short_name'],
        club_badge=f"https://resources.premierleague.com/premierleague/badges/100/t{team['code']}.png",
        player_image=(photo_resolver(p) if photo_resolver else
            f'https://resources.premierleague.com/premierleague/photos/players/250x250/p{code}.png' if code else ''),
        price=f"£{float(p['now_cost'])/10:.1f}m", ownership=f"{p['selected_by_percent']}%",
        verdict_sub=f"{record['action']} WATCHLIST • EVENT MARKET",
        display_stats=[dict(label=label, icon=icon, value=number(key, decimals)) for key,label,icon,decimals in labels],
        fixtures=fixtures(team['short_name'],pos,int(p['id'])))
