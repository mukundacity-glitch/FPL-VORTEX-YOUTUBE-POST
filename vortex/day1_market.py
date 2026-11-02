"""Day 1 market-led transfer selector. Never infer equal windows from cumulative FPL totals.

A BUY or SELL requires consecutive equal-length windows, owners-at-start,
configurable thresholds, a separately verified CURRENT editable squad, and
official prices and availability. Unsupported details produce WATCH/HOLD.
"""
from __future__ import annotations
from datetime import datetime
import math


def _ts(value):
    try:
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return dt if dt.tzinfo else None
    except (TypeError, ValueError):
        return None


def _number(value):
    if isinstance(value, bool):
        return None
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError):
        return None


def _watch(reason):
    return {'verdict': 'WATCH', 'action': 'HOLD', 'alternatives': [],
            'updated_at': None, 'reason': reason,
            'market_provenance': 'INSUFFICIENT DATA'}


def choose_market_transfer(payload):
    """Market ranking first; no-hit legal/affordable feasibility second.

    Historical windows each require start, end, source and players mapping:
    {player_id: {in: int, out: int, owners_at_start: int}}.
    Current squad: 15 verified picks with selling_value, bank, free_transfers.
    Pool: official price, position, club_id, availability and name.
    """
    if not isinstance(payload, dict):
        return _watch('Two comparable market windows and current squad are missing')
    th = payload.get('thresholds') or {}
    thresholds = ('min_owners', 'min_activity', 'min_demand', 'min_momentum')
    if any(_number(th.get(k)) is None or float(th[k]) < 0 for k in thresholds):
        return _watch('Documented market thresholds are missing')
    th = {k: float(th[k]) for k in thresholds}
    if th['min_owners'] < 1 or th['min_activity'] < 1:
        return _watch('Market owner/activity safeguards must be positive')
    windows = payload.get('windows')
    if not isinstance(windows, list) or len(windows) != 2:
        return _watch('Exactly two comparable market windows required')
    older, recent = windows
    try:
        a, b = _ts(older.get('start')), _ts(older.get('end'))
        c, d = _ts(recent.get('start')), _ts(recent.get('end'))
    except AttributeError:
        return _watch('Historical market window structure is invalid')
    if not all((a, b, c, d)) or not (a < b == c < d) or b-a != d-c:
        return _watch('Unequal, overlapping or nonconsecutive market windows')
    if not older.get('source') or older.get('source') != recent.get('source'):
        return _watch('Market windows must come from the same data source')
    if any(w.get('measure') != 'window_delta' for w in windows):
        return _watch('Explicit window-delta inputs required; cumulative FPL event totals are invalid')
    if not isinstance(older.get('players'), dict) or not isinstance(recent.get('players'), dict):
        return _watch('Per-player transfer and ownership windows are missing')
    signals = []
    for raw_id, first in older['players'].items():
        second = recent['players'].get(str(raw_id), recent['players'].get(raw_id))
        if not isinstance(first, dict) or not isinstance(second, dict):
            continue
        rows = []
        for entry in (first, second):
            values = [_number(entry.get(k)) for k in ('in', 'out', 'owners_at_start')]
            if any(v is None or v < 0 or v != int(v) for v in values):
                break
            inn, out, owners = (int(v) for v in values)
            if owners <= 0 or owners < th['min_owners'] or inn+out < th['min_activity']:
                break
            rows.append((inn, out, owners))
        if len(rows) != 2:
            continue
        try:
            player_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if player_id <= 0:
            continue
        n0, n1 = rows[0][0]-rows[0][1], rows[1][0]-rows[1][1]
        d0, d1 = n0/rows[0][2], n1/rows[1][2]
        mom = d1-d0
        verdict = 'WATCH'
        if n0 > 0 and n1 > 0 and d1 >= th['min_demand'] and mom >= th['min_momentum'] and mom > 0:
            verdict = 'BUY'
        elif n0 < 0 and n1 < 0 and d1 <= -th['min_demand'] and mom <= -th['min_momentum'] and mom < 0:
            verdict = 'SELL'
        signals.append({'id': player_id, 'verdict': verdict, 'demand': d1,
                        'momentum': mom, 'net_older': n0, 'net_recent': n1})
    squad = payload.get('current_squad') or {}
    picks = squad.get('picks')
    if not isinstance(picks, list) or len(picks) != 15:
        return _watch('Verified current 15-player squad is missing')
    owned = {p.get('id'): p for p in picks if isinstance(p, dict)}
    if len(owned) != 15 or any(not isinstance(k, int) or k <= 0 for k in owned):
        return _watch('Current squad has duplicate or invalid IDs')
    if not _ts(squad.get('verified_at')) or not squad.get('source'):
        return _watch('Current editable squad source/timestamp is unverified')
    if _ts(squad['verified_at']) < d:
        return _watch('Current squad snapshot predates market observation window')
    if not _ts(payload.get('pool_verified_at')) or not payload.get('pool_source'):
        return _watch('Official candidate price and availability source/timestamp missing')
    if _ts(payload['pool_verified_at']) < d:
        return _watch('Candidate price and availability snapshot is stale')
    bank, ft = _number(squad.get('bank')), _number(squad.get('free_transfers'))
    if bank is None or bank < 0 or ft is None or ft < 0 or ft != int(ft):
        return _watch('Current bank or free-transfer allowance is unverified')
    if not isinstance(payload.get('pool'), list):
        return _watch('Verified current candidate pool is missing')
    pool = {p.get('id'): p for p in payload['pool'] if isinstance(p, dict)}
    sells = sorted((p for p in signals if p['verdict'] == 'SELL' and p['id'] in owned),
                   key=lambda p: (p['demand'], p['momentum'], p['id']))
    buys = sorted((p for p in signals if p['verdict'] == 'BUY' and p['id'] not in owned),
                  key=lambda p: (-p['demand'], -p['momentum'], p['id']))
    options = []
    for old in sells:
        departing = owned[old['id']]
        selling = _number(departing.get('selling_value'))
        if selling is None or not departing.get('name'):
            continue
        for incoming in buys:
            target = pool.get(incoming['id'])
            if not target:
                continue
            price = _number(target.get('price'))
            club = target.get('club_id')
            if (not target.get('name') or target.get('position') != departing.get('position')
                    or price is None or price > selling+bank
                    or not isinstance(club, int) or target.get('available') is not True):
                continue
            if sum(1 for p in picks if p.get('club_id') == club and p.get('id') != old['id']) >= 3:
                continue
            if ft < 1:  # Never justify a points hit from transfer activity alone.
                continue
            options.append({'outgoing': old['id'], 'outgoing_name': departing['name'],
                            'incoming': incoming['id'], 'name': target['name'],
                            'demand': incoming['demand'], 'momentum': incoming['momentum'],
                            'price': price, 'selling_value': selling})
    if not options:
        return {'verdict': 'HOLD', 'action': 'HOLD', 'alternatives': [],
                'reason': 'No verified legal, affordable one-transfer market-led replacement.',
                'updated_at': recent['end'], 'market_provenance': recent['source']}
    return {'verdict': 'BUY', 'action': 'BUY', 'option': options[0],
            'alternatives': options[:3], 'updated_at': recent['end'],
            'market_provenance': recent['source'],
            'reason': 'Sustained selling pressure out; strengthening buying momentum in; legal without a hit.'}
