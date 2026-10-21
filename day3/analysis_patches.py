"""Connect evidence validation to the existing notebook without editing Drive."""
from __future__ import annotations

from day3.defcon_analysis import patch_narration


def once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise RuntimeError(f"Live-analysis notebook contract changed: {old[:90]}")
    return source.replace(old, new, 1)


def patch_analysis_source(cell_index: int, source: str) -> str:
    if cell_index == 18:
        marker = 'PHASE10_DEFCON_THRESHOLDS = dict(PHASE10_FPL_RULES["defcon_thresholds"])'
        source = once(source, marker, '''_live_scoring = DAY3_AVAILABILITY.research["scoring"]
_live_points = set(_live_scoring["points_by_position"].values())
if len(_live_points) != 1:
    raise RuntimeError("Position-specific DC points changed; scoring-model review required")
PHASE10_FPL_RULES["defcon_thresholds"] = dict(_live_scoring["thresholds"])
PHASE10_FPL_RULES["defcon_points"] = float(next(iter(_live_points)))
PHASE10_FPL_RULES["defcon_max_points_per_match"] = PHASE10_FPL_RULES["defcon_points"]
''' + marker)
        marker = '    if not rg.empty:\n        rg = rg.sort_values("match_date", kind="stable").tail(PHASE10_MAX_ROLE_OBSERVATIONS)'
        source = once(source, marker,
            '    rg = DAY3_AVAILABILITY.model_roles(rg, pid, pcode, CURRENT_SEASON)\n' + marker)
        source += '''
phase10_player_fixture_expected_points = DAY3_AVAILABILITY.validate_projections(phase10_player_fixture_expected_points)
phase10_player_features = DAY3_AVAILABILITY.annotate(phase10_player_features)
DAY3_AVAILABILITY.save_audit(Path(DATA_DIR))
'''
    elif cell_index == 24:
        source = 'from day3.defcon_analysis import annotate_players, annotate_teams, forecast_text, rank_profiles\n' + source
        marker = '_d3_def_features = DAY3_AVAILABILITY.annotate(_d3_def_features)'
        source = once(source, marker,
            '_d3_def_features = annotate_players(_d3_def_features, DAY3_AVAILABILITY, SLIDE_PLAYER_FIXTURE_XPTS)')
        source = once(source,
            '_d3_def_features["defcon_eligible"].fillna(False).astype(bool)\n    & _d3_def_features["minutes_per_appearance"].ge(PHASE10_DEFCON_MIN_AVG_MINUTES)',
            '(_d3_def_features["defcon_eligible"].fillna(False).astype(bool)\n    & _d3_def_features["minutes_per_appearance"].ge(PHASE10_DEFCON_MIN_AVG_MINUTES))\n    | _d3_def_features["recommendation_eligible"]')
        source = once(source, '_d3_def_cards = _d3_def_features.loc[', '_d3_def_cards = rank_profiles(_d3_def_features.loc[')
        source = once(source,
            '].sort_values(\n    ["recommendation_eligible", "cumulative_dc", "dc_per90", "minutes_per_appearance", "player_name"],\n    ascending=[False, False, False, False, True],\n).reset_index(drop=True)',
            '].copy())')
        source = once(source, 'DAY3_DEFCON_TARGETS = _d3_def_cards.head(5).copy()',
            'DAY3_DEFCON_TARGETS = _d3_def_cards.head(5).copy()\n'
            'DAY3_DEFCON_RECOMMENDATIONS = DAY3_DEFCON_TARGETS.loc[DAY3_DEFCON_TARGETS.recommendation_eligible].copy()')
        marker = '_d3_team_defcon = _d3_defcon_rank_current_teams(_d3_team_defcon)'
        source = once(source, marker, marker + '\n_d3_team_defcon = annotate_teams(_d3_team_defcon, _d3_def_features, DAY3_AVAILABILITY)')
        marker = '    "recommendation_eligible", "official_status_label", "official_status_news",'
        source = once(source, marker, marker + '\n    "projection_verified", "positional_threshold", "recommendation_score", "historical_rank",')
        source = source.replace('{float(row["xdefcon"]):.1f}', '{forecast_text(row)}')
        source = source.replace('DEFCON · CURRENT TARGETS FIRST', 'DEFCON · TARGETS & WATCHLIST')
        source = source.replace('≥{PHASE10_DEFCON_MIN_AVG_MINUTES:g} MIN/APP', 'LIVE TARGETS + SEASON WATCHLIST')
        source = source.replace('"minimum_average_minutes": float(PHASE10_DEFCON_MIN_AVG_MINUTES)',
                                '"historical_minimum_average_minutes": float(PHASE10_DEFCON_MIN_AVG_MINUTES)')
        source = source.replace('GREEN TOP 5 · RED BOTTOM 3', 'SEASON WORKLOAD · NOT PICK QUALITY')
        for field, model_field in (("has_projection", "xpts"), ("has_horizon", "next_5_xpts"),
                                   ("has_minutes", "xmins"), ("has_start_probability", "start_probability")):
            old = f'"{field}": bool(pd.notna(m.get("{model_field}"))),'
            source = once(source, old, f'"{field}": bool(DAY3_AVAILABILITY.state(pid).get("projection_verified") and pd.notna(m.get("{model_field}"))),')
        marker = '        "has_projection": bool(DAY3_AVAILABILITY.state(pid).get("projection_verified")'
        source = once(source, marker, '        "projection_verified": bool(DAY3_AVAILABILITY.state(pid).get("projection_verified")),\n' + marker)
        source = once(source,
            "f'<span>{r[\"xpts\"]:.1f} xPTS • {r[\"xmins\"]:.0f} xMINS</span>'",
            "f'<span>{forecast_text(r, \"xpts\")} xPTS • {forecast_text(r, \"xmins\", digits=0)} xMINS</span>'")
    elif cell_index == 32:
        source = patch_narration(source)
    return source
