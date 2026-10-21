from __future__ import annotations


def _once(source: str, old: str, new: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"Availability notebook contract: expected one match, found {count}: {old[:90]}")
    return source.replace(old, new, 1)


def patch_availability_source(cell_index: int, source: str, *, narration: bool = True) -> str:
    if not narration and cell_index in {30, 32}:
        return source
    if cell_index == 5:
        return source + (
            "\nfrom day3.player_availability import install_availability\n"
            "install_availability(globals())\n"
        )
    if cell_index == 10:
        return source + (
            "\nfrom day3.availability_visuals import install_availability_presentation\n"
            "install_availability_presentation(globals())\n"
        )
    if cell_index == 18:
        old = '''def _vx_phase10_availability(row):
    chance = pd.to_numeric(pd.Series([row.get("chance_of_playing_next_round", np.nan)]), errors="coerce").iloc[0]
    if np.isfinite(chance):
        return float(np.clip(chance / 100.0, 0.0, 1.0))
    status = str(row.get("status", "a")).lower().strip()
    return {"a": 1.0, "d": 0.75, "i": 0.0, "s": 0.0, "u": 0.0}.get(status, 0.75)'''
        new = '''def _vx_phase10_availability(row):
    return DAY3_AVAILABILITY.probability(row["player_id"])'''
        source = _once(source, old, new)
        marker = "    # Refresh the DEFCON baseline after any explicit role/minutes override."
        source = _once(source, marker, '''    if avail <= 0.0:
        start_probability = appearance_probability = sixty_probability = expected_minutes = 0.0
        penalty_role_score = defcon_probability = 0.0
        defcon_probability_override_active = False

''' + marker)
        marker = '_vx_phase10_perf_mark("player_features_built")'
        source = _once(source, marker, '''DAY3_AVAILABILITY.bind_model(
    phase10_player_features, _role, players, CURRENT_SEASON,
)
phase10_player_features = DAY3_AVAILABILITY.annotate(phase10_player_features)
DAY3_AVAILABILITY.save_audit(Path(DATA_DIR))
''' + marker)
    elif cell_index == 19:
        source = _once(source,
            '_h["decision_available"] = ~_h["availability_status"].str.lower().eq("u")',
            '_h["decision_available"] = _h["player_id"].map(DAY3_AVAILABILITY.eligible)')
    elif cell_index == 23:
        source = _once(source, '        <div class="pc-card-grid"></div>',
            '        ${window.vxAvailabilityBadge ? window.vxAvailabilityBadge(p?.id) : ""}\n'
            '        <div class="pc-card-grid"></div>')
    elif cell_index == 24:
        marker = '_d3_def_features = _d3_def_attach_context(_d3_def_features, globals().get("phase11_elite_eo_raw"))'
        source = _once(source, marker, marker + '\n_d3_def_features = DAY3_AVAILABILITY.annotate(_d3_def_features)')
        source = _once(source,
            '''    ["cumulative_dc", "dc_per90", "minutes_per_appearance", "player_name"],
    ascending=[False, False, False, True],''',
            '''    ["recommendation_eligible", "cumulative_dc", "dc_per90", "minutes_per_appearance", "player_name"],
    ascending=[False, False, False, False, True],''')
        marker = '    "rank", "player_id", "player_name", "team_name", "position", "fdr_next5", "next_fixtures",'
        source = _once(source, marker, marker + '\n    "recommendation_eligible", "official_status_label", "official_status_news",')
        source = _once(source,
            '''    "ranking": "Cumulative DC descending, then DC/90 descending; minimum minutes applied before rounding.",''',
            '''    "ranking": "Current availability and secure starting evidence first; cumulative DC then DC/90. Flagged fallback rows are historical watchlist entries, not recommendations.",''')
        source = _once(source, '<strong>TOP 20 DEFCON PLAYERS</strong>',
            '<strong>DEFCON · CURRENT TARGETS FIRST</strong>')
        source = _once(source, '        eligible["minimum_fixture_minutes"].ge(80.0)',
            '        eligible["player_id"].map(DAY3_AVAILABILITY.eligible)\n'
            '        & eligible["minimum_fixture_minutes"].ge(80.0)')
        source = _once(source, '    effective_ownership=_d3_bench_eo_map,',
            '    effective_ownership=_d3_bench_eo_map,\n'
            '    eligible_hold_ids=DAY3_AVAILABILITY.eligible_ids(),')
        source = _once(source, '        "availability": 100.0 * _d3_number(m.get("availability_probability")),',
            '        "availability": 100.0 * DAY3_AVAILABILITY.probability(pid),\n'
            '        "player_status": dict(DAY3_AVAILABILITY.state(pid)),')
        source = _once(source, 'def _d3_desk_short_reason(r):',
            'def _d3_desk_short_reason(r):\n'
            '    if not DAY3_AVAILABILITY.state(r["player_id"])["health_clear"]:\n'
            '        return DAY3_AVAILABILITY.state(r["player_id"])["label"]')
        if narration:
            source = _patch_desk_availability_narration(source)
        source = _once(source, 'subtitle=f"GW{int(NEXT_GW)} • BUY TARGETS • PATIENT HOLDS • SELL CANDIDATES"',
            'subtitle=f"GW{int(NEXT_GW)} • BUY ACTIVITY • QUALIFIED HOLDS • SELL ACTIVITY"')
    elif cell_index == 30:
        return _patch_plan_availability_narration(source)
    elif cell_index == 32:
        return _patch_defcon_availability_narration(source)
    return source


def _patch_desk_availability_narration(source: str) -> str:
    source = _once(source, '    evidence = record.get("recent_performance") or {}',
        '''    if role in {"BUY", "HOLD"} and not DAY3_AVAILABILITY.eligible(record["player_id"]):
        return (
            f"{identity}. This is transfer-market activity, not an active recommendation. "
            + DAY3_AVAILABILITY.caution(record["player_id"])
            + f" His next fixture is {fixture}."
        )
    evidence = record.get("recent_performance") or {}''')
    source = _once(source,
        '    return f"{leads[role][index]} {performance} {outlook} {decision}"',
        '''    status_note = ""
    if not DAY3_AVAILABILITY.state(record["player_id"])["health_clear"]:
        status_note = DAY3_AVAILABILITY.caution(record["player_id"]) + " "
    return f"{leads[role][index]} {status_note}{performance} {outlook} {decision}"''')
    return source


def _patch_plan_availability_narration(source: str) -> str:
    for signature in (
        "    def _d3_plan_player_text(p, bench=False):",
        "    def _d3_transfer_plan_player_text(p, bench=False, first_goalkeeper=False):",
    ):
        source = _once(source, signature, signature + '''
        if not DAY3_AVAILABILITY.eligible(p["id"]):
            return str(vx_narration_player(int(p["id"]))) + ". " + DAY3_AVAILABILITY.caution(p["id"])
''')
    source = _once(source,
        '            segment["text"] = re.sub(r"\\bmodel\\b", "analysis", segment["text"], flags=re.I)',
        '''            segment["text"] = re.sub(r"\\bmodel\\b", "analysis", segment["text"], flags=re.I)
            _player_id = segment.get("player_id")
            if _player_id is not None and not DAY3_AVAILABILITY.eligible(_player_id):
                segment["text"] = (
                    str(vx_narration_player(int(_player_id))) + ". "
                    + DAY3_AVAILABILITY.caution(_player_id)
                )''')
    return source


def _patch_defcon_availability_narration(source: str) -> str:
    source = _once(source,
        '        opening = "For the next Gameweek, these are the five defensive contribution players I\'m focusing on."',
        '        opening = "For the next Gameweek, these are the five defensive contribution profiles. Current availability and starting prospects decide which are active targets; flagged profiles are watchlist only."')
    marker = "        def _team_name(row):"
    source = _once(source, marker, '''        for _index, _player in enumerate(player_rows):
            _player_id = int(_player["player_id"])
            if not DAY3_AVAILABILITY.eligible(_player_id):
                _cue = individual[_index][0]
                individual[_index] = (
                    _cue,
                    _cue + " on the historical watchlist, but he is not an active target. "
                    + DAY3_AVAILABILITY.caution(_player_id),
                )

''' + marker)
    return source
