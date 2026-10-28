"""Verified FPL match-event data for Day 1's results board."""
from __future__ import annotations


def build_results(bootstrap, fixtures, gameweek):
    teams = {int(t['id']): t for t in bootstrap['teams']}
    players = {int(p['id']): p for p in bootstrap['elements']}
    rows = []
    matches = sorted((f for f in fixtures if f.get('event') == gameweek),
                     key=lambda f: (f.get('kickoff_time') or '', f['id']))
    for fixture in matches:
        home, away = teams[int(fixture['team_h'])], teams[int(fixture['team_a'])]
        final = bool(fixture.get('finished')) and fixture.get('team_h_score') is not None and fixture.get('team_a_score') is not None
        returns = []
        for stat in fixture.get('stats', []):
            kind = stat.get('identifier')
            if kind not in {'goals_scored', 'assists'}:
                continue
            for side in ('h', 'a'):
                for item in stat.get(side) or []:
                    player = players.get(int(item.get('element') or 0))
                    count = int(item.get('value') or 0)
                    if player and count > 0:
                        returns.append({'id': int(player['id']), 'name': player['web_name'],
                                        'code': player.get('code'), 'team': int(player['team']),
                                        'kind': kind, 'count': count})
        rows.append({'id': int(fixture['id']), 'home': home['name'], 'away': away['name'],
                     'home_code': home.get('code'), 'away_code': away.get('code'),
                     'score': [int(fixture['team_h_score']), int(fixture['team_a_score'])] if final else None,
                     'final': final, 'kickoff': fixture.get('kickoff_time'),
                     'returns': returns if final else []})
    return rows
