"""Adapt shared fixture values to the existing Day 2 scene data contracts."""
from __future__ import annotations

import ast

from vortex.fixture_forecast import fixture_values


def position_name(value):
    return {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}.get(value, str(value))


def rating(rows, fixture, team, position):
    return fixture_values(rows, fixture, team, position_name(position))["fdr"]


def fixture_map(fixtures, teams, rows, weeks):
    result = {}
    # The existing card has one slot. Keep the first scheduled match there;
    # the complete fixture list remains available to horizon calculations.
    for fixture in sorted(fixtures, key=lambda f: (f.get("kickoff_time") or "", int(f["id"]))):
        gw = fixture.get("event")
        if gw not in weeks or fixture.get("finished"):
            continue
        for home in (True, False):
            team = int(fixture["team_h" if home else "team_a"])
            opponent = int(fixture["team_a" if home else "team_h"])
            values = fixture_values(rows, fixture["id"], team)
            result.setdefault(team, {}).setdefault(gw, {
                "fixture_id": int(fixture["id"]), "team_id": team,
                "opp": teams[opponent]["short_name"], "opp_full": teams[opponent]["name"],
                "ha": "H" if home else "A", "kickoff": fixture.get("kickoff_time"), **values,
            })
    return result


def replace_once(source, before, after):
    if source.count(before) != 1:
        raise ValueError(f"Day 2 fixture contract changed: {before[:90]}")
    return source.replace(before, after, 1)


def patch_data_source(source):
    source = replace_once(source,
        '_s2_fixtures = requests.get(f"{API_BASE}/fixtures/", headers=HEADERS, timeout=12).json()',
        '_s2_fixtures = requests.get(f"{API_BASE}/fixtures/", headers=HEADERS, timeout=12).json()\n'
        'from vortex.fixture_forecast import forecast_rows as _vx_forecast_rows\n'
        'from day2.fixture_forecast import fixture_map as _vx_fixture_map, rating as _vx_rating\n'
        '_vx_fixture_rows = _vx_forecast_rows(bootstrap, _s2_fixtures)')
    start = source.index('_s2_fixture_map = {}\n')
    stop = source.index('# Fail closed when the live feed is unavailable;', start)
    source = source[:start] + '_s2_fixture_map = _vx_fixture_map(_s2_fixtures, _s2_teams, _vx_fixture_rows, _s2_context_gws)\n\n' + source[stop:]
    source = replace_once(source, 'next_fdr = _s2_int(next_fixture.get("fdr"), 3)',
        'next_fdr = _vx_rating(_vx_fixture_rows, next_fixture["fixture_id"], team_id, pos_id)')
    source = replace_once(source, '_fdr = _s3_int(_fixture.get("fdr"), 3)',
        '_fdr = _vx_rating(_vx_fixture_rows, _fixture["fixture_id"], _team_id, _pos_id)')
    source = replace_once(source, '"fdr": int(_fx.get("team_h_difficulty") or 3)',
        '"fixture_id": int(_fx["id"]), "fdr": _vx_rating(_vx_fixture_rows, _fx["id"], _th, "MID")')
    source = replace_once(source, '"fdr": int(_fx.get("team_a_difficulty") or 3)',
        '"fixture_id": int(_fx["id"]), "fdr": _vx_rating(_vx_fixture_rows, _fx["id"], _ta, "MID")')
    # Historic fixtures cannot enter a future model lookup.
    source = replace_once(source, 'if _gw not in _s5_horizon_gws:',
        'if _gw not in _s5_horizon_gws or _fx.get("finished"):')
    tree = ast.parse(source)
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_s5_fixture_score_for_player')
    lines = source.splitlines(keepends=True)
    lines[function.lineno - 1:function.end_lineno] = ['''def _s5_fixture_score_for_player(row):
    team_id = int(row["team_id"])
    scores, labels = [], []
    for fx in _s5_fixture_rows.get(team_id, []):
        opp = _s5_team_by_id[int(fx["opp"])]
        value = _vx_rating(_vx_fixture_rows, fx["fixture_id"], team_id, row.get("pos"))
        scores.append(_s5_clamp((6.0 - value) / 5.0 * 100.0))
        labels.append(f"GW{fx['gw']} {opp.get('short_name') or opp['name']} {fx['ha']}")
    return (sum(scores) / len(scores) if scores else 0.0), scores, labels
''']
    source = ''.join(lines)
    source = replace_once(source, '"fdr": int(_fx["fdr"]),',
        '"fdr": _vx_rating(_vx_fixture_rows, _fx["fixture_id"], _team_id, _r.get("pos")),')
    source = replace_once(source, 'str(int(x["fdr"]))', 'format(float(x["fdr"]), ".2f")')
    return source


def patch_notebook(payload):
    cells = [c for c in payload["cells"] if c.get("cell_type") == "code"]
    if len(cells) != 21:
        raise ValueError("Day 2 fixture patch expects the existing 21 cells")
    source = ''.join(cells[4]["source"])
    cells[4]["source"] = patch_data_source(source).splitlines(keepends=True)
    source = ''.join(cells[7]["source"])
    anchor = '    fdr = max(1, min(5, int(round(_s2_num(player.get("fixture_fdr"), 3)))))'
    if source.count(anchor) != 2:
        raise ValueError("Day 2 FDR display contract changed")
    # CSS classes keep their existing integer buckets; only displayed numbers
    # retain the shared model's continuous value.
    source = source.replace(anchor, anchor + '\n    fdr_value = float(player["fixture_fdr"])')
    source = source.replace('>FDR {fdr}</b>', '>FDR {fdr_value:.2f}</b>')
    source = source.replace('fdr{fdr}">{fdr}</div>', 'fdr{fdr}">{fdr_value:.2f}</div>')
    cells[7]["source"] = source.splitlines(keepends=True)
    source = ''.join(cells[13]["source"])
    source = replace_once(source, '{int(_fx.get("fdr") or 3)}</strong>', '{float(_fx["fdr"]):.2f}</strong>')
    cells[13]["source"] = source.splitlines(keepends=True)
