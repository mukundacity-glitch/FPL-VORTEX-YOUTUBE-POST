from __future__ import annotations

import ast
import textwrap


def replace_once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise RuntimeError(f"Live-evidence notebook contract changed: {old[:90]}")
    return source.replace(old, new, 1)


def replace_function(source: str, name: str, replacement: str) -> str:
    tree = ast.parse(source)
    matches = [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one {name}, found {len(matches)}")
    node = matches[0]
    lines = source.splitlines(keepends=True)
    prefix = " " * node.col_offset
    lines[node.lineno - 1:node.end_lineno] = [textwrap.indent(textwrap.dedent(replacement).strip(), prefix) + "\n"]
    return "".join(lines)


def patch_evidence_pipeline(cell_index: int, source: str) -> str:
    if cell_index == 5:
        source = replace_once(source, 'EXPECTED_REVIEW_GW = int(NEXT_GW) - 1 if int(NEXT_GW) > 1 else None',
                              'EXPECTED_REVIEW_GW = max(data.get("review_ready_gws") or [], default=None)')
        source = replace_once(source, 'data = fetch_fpl_data()', 'data = fetch_fpl_data()\n' + textwrap.dedent('''

            from day3.live_evidence import capture_evidence, freeze_official_module, save_snapshot
            DAY3_EVIDENCE = capture_evidence(data)
            freeze_official_module(_fpl_module, DAY3_EVIDENCE)
            save_snapshot(DAY3_EVIDENCE, Path(DATA_DIR))
            print(f"Verified live cutoff: {DAY3_EVIDENCE['cutoff']}; GW{DAY3_EVIDENCE['next_gw']}; no cached fallback")
        '''))
        source = replace_once(source, 'data_snapshot_timestamp = datetime.now(timezone.utc).isoformat()',
                              'data_snapshot_timestamp = DAY3_EVIDENCE["cutoff"]')
    if cell_index == 6:
        source += '\nif failed_retained or failed_missing:\n    raise RuntimeError("Current-season source refresh failed; stale files may not feed narration")\n'
    if cell_index == 18:
        source = replace_once(source, 'PHASE10_VERSION = "VORTEX-V2.7-PLAYER-XPTS-CUMULATIVE-DEFCON-70"',
                              'PHASE10_VERSION = "VORTEX-V3-LIVE-ROLE-VERIFIED-DEFCON"')
        source = replace_function(source, "_vx_phase10_defcon_forecast", '''
            def _vx_phase10_defcon_forecast(rate90, position, minutes_pmf, probability_override=None):
                from day3.live_evidence import dc_forecast
                return dc_forecast(rate90, position, minutes_pmf, probability_override)
        ''')
        source = replace_function(source, "_vx_phase10_availability", '''
            def _vx_phase10_availability(row):
                player_id = int(row["player_id"])
                value = DAY3_EVIDENCE["players"][player_id]["availability"]
                if value is None:
                    raise RuntimeError(f"Player {player_id}: conflicting or unconfirmed availability; cannot assign expected minutes")
                return float(value)
        ''')
        source = replace_function(source, "_vx_phase10_load_defcon_history", '''
            def _vx_phase10_load_defcon_history():
                global PHASE10_DEFCON_EVIDENCE_SOURCE, PHASE10_DEFCON_SOURCES_BY_GW
                frames = [_vx_phase10_parse_defcon_event(DAY3_EVIDENCE["_event_payloads"][int(gameweek)], int(gameweek))
                          for gameweek in _phase10_review_gws]
                PHASE10_DEFCON_EVIDENCE_SOURCE = "FPL_API_LIVE_LOCKED"
                PHASE10_DEFCON_SOURCES_BY_GW = {int(gameweek): "FPL_API_LIVE_LOCKED" for gameweek in _phase10_review_gws}
                return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=_PHASE10_DEFCON_EVENT_COLUMNS)
        ''')
        first = source.index('    if _PHASE10_DRAFT_FAST:', source.index('def _vx_phase10_player_features(row):'))
        last = source.index('    short_rest_profile =', first)
        source = source[:first] + textwrap.indent(textwrap.dedent('''
            from day3.live_evidence import live_role
            role = live_role(DAY3_EVIDENCE, pid)
            start_rate, appearance_rate, p60_rate = role["start"], role["app"], role["p60"]
            minute_mean, role_n = role["mean"], int(role["sample"])
            minute_sd = float(np.std(DAY3_EVIDENCE["players"][pid]["recent_minutes"])) if role_n else 0.0
            rg = pd.DataFrame()
        ''').strip() + '\n\n', '    ') + source[last:]
        marker = '    _ov_ts = pd.to_datetime(_active_ov["source_timestamp"], utc=True, errors="coerce")'
        source = replace_once(source, marker, marker + '\n    if (_ov_ts < pd.Timestamp(DAY3_EVIDENCE["cutoff"]) - pd.Timedelta(hours=6)).any():\n        raise RuntimeError("Active player override is older than the live evidence window")')
        source = replace_once(source, 'phase10_player_fixture_expected_points = pd.DataFrame(_phase10_fixture_rows, columns=PHASE10_FIXTURE_FIELDS)',
                              'phase10_player_fixture_expected_points = pd.DataFrame(_phase10_fixture_rows, columns=PHASE10_FIXTURE_FIELDS)\n'
                              'from day3.live_evidence import audit_fixture_rows\n'
                              'audit_fixture_rows(phase10_player_fixture_expected_points, DAY3_EVIDENCE)')
    if cell_index == 24:
        # Patches run after shortlist removal, which canonicalizes Python formatting.
        first = source.index('_d3_next_fixture_counts = globals().get(')
        last = source.index("_d3_def_features['previous_defcon']", first)
        source = source[:first] + textwrap.dedent('''
            from day3.evidence_narration import validated_fixture_forecasts, forecast_text
            _d3_next_fixture_counts = validated_fixture_forecasts(
                _d3_def_features, phase10_player_fixture_expected_points, DAY3_EVIDENCE)
            _d3_def_features = _d3_def_features.merge(_d3_next_fixture_counts, on="player_id", how="left", validate="one_to_one")
        ''').strip() + '\n' + source[last:]
        source = source.replace("for _col in ('previous_defcon', 'xdefcon', 'secure_players', 'dc_for', 'completed_matches'):",
                                "for _col in ('previous_defcon', 'secure_players', 'dc_for', 'completed_matches'):")
        source = source.replace("xdefcon=('xdefcon', 'sum')", "xdefcon=('xdefcon', lambda values: values.sum(min_count=len(values)))")
        source = replace_once(source, "_d3_def_features.groupby('team_id', as_index=False)",
                              "_d3_def_features.loc[_d3_def_features['defcon_total_minutes'].gt(0)].groupby('team_id', as_index=False)")
        source = replace_once(source, "out['eo_percent'] = overall.fillna(0.0).clip(lower=0.0)",
                              "out['eo_percent'] = overall.clip(lower=0.0)\n    if out['eo_percent'].isna().any():\n        raise RuntimeError('Official ownership is missing; do not display a fabricated zero')")
        source = source.replace("out['eo_snapshot_timestamp'] = pd.Timestamp.now(tz='UTC')",
                                "out['eo_snapshot_timestamp'] = pd.Timestamp(DAY3_EVIDENCE['cutoff'])")
        source = replace_once(source, "if not DAY3_DEFCON_PLAYERS['xdefcon'].iloc[:_D3_DEFCON_PLAYER_COUNT].notna().all():",
                              "if not DAY3_DEFCON_PLAYERS['projection_status'].iloc[:_D3_DEFCON_PLAYER_COUNT].notna().all():")
        source = replace_function(source, "_d3_def_next3_fdr", '''
            def _d3_def_next3_fdr(team_id, position, limit=3):
                from day3.evidence_narration import next_fixture_packs
                packs = next_fixture_packs(DAY3_EVIDENCE, fixture_fdr_model_only, int(team_id), str(position), int(limit))
                for pack in packs:
                    if pack["fdr_value"] is not None:
                        pack["band"] = str(vx_phase4_fdr_colour_band(pack["fdr_value"])).lower()
                return packs
        ''')
        source = replace_once(source, "'gw': int(NEXT_GW) + slot", "'gw': int(pack['gw'])")
        source = source.replace("SEASON DC RANK · SMALL = DC/GAME · ARROW vs GW", "DC VOLUME ONLY · SMALL = DC/GAME · vs GW")
        source = source.replace(" · GREEN TOP 5 · RED BOTTOM 3", " · NOT A BUY/SELL RANK")
        source = source.replace("<span>EO%</span>", "<span>OWN%</span>")
        # Replace optional forecast formatting inside f-strings without changing the design.
        class OptionalForecast(ast.NodeTransformer):
            def visit_FormattedValue(self, node: ast.FormattedValue) -> ast.AST:
                if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name) and node.value.func.id == "float":
                    if len(node.value.args) == 1 and isinstance(node.value.args[0], ast.Subscript):
                        subscript = node.value.args[0]
                        if isinstance(subscript.slice, ast.Constant) and subscript.slice.value == "xdefcon":
                            node.value = ast.Call(func=ast.Name(id="forecast_text", ctx=ast.Load()), args=[subscript], keywords=[])
                            node.format_spec = None
                return self.generic_visit(node)
        tree = OptionalForecast().visit(ast.parse(source))
        ast.fix_missing_locations(tree)
        source = ast.unparse(tree) + '\n'
    if cell_index == 32:
        source = replace_function(source, "_d3_defcon_narration", '''
            def _d3_defcon_narration():
                from day3.evidence_narration import defcon_narration
                return defcon_narration(globals())
        ''')
        source = source.replace("int(_defcon_manifest.get('previous_gw', -1)) != int(NEXT_GW) - 1",
                                "int(_defcon_manifest.get('previous_gw', -1)) != max(DAY3_EVIDENCE['history_gameweeks'], default=0)")
        source = replace_function(source, "_d3_defcon_player_line", '''
            def _d3_defcon_player_line(_idx):
                from day3.evidence_narration import player_analysis
                return player_analysis(DAY3_EVIDENCE, int(_d3_defcon_player_row(_idx)["player_id"]), int(_idx) + 1)[1]
        ''')
        source = replace_function(source, "_d3_defcon_team_line", '''
            def _d3_defcon_team_line(_idx):
                from day3.evidence_narration import team_analysis
                return team_analysis(DAY3_EVIDENCE, int(_d3_defcon_team_row(_idx)["team_id"]), int(_idx) + 1, "high")[1]
        ''')
        source = replace_function(source, "_number", '''
            def _number(value, fallback=None):
                from day3.live_evidence import number
                return number(value, "projected-goals narration statistic", minimum=-1000000)
        ''')
        source = replace_function(source, "_d3_elite1000_spoken_count", '''
            def _d3_elite1000_spoken_count(_value):
                from day3.live_evidence import number
                return f"{int(round(number(_value, 'official transfer count'))):,}"
        ''')
        class VerifiedNarrationNumbers(ast.NodeTransformer):
            def visit_Call(self, node: ast.Call) -> ast.AST:
                self.generic_visit(node)
                if isinstance(node.func, ast.Name) and node.func.id == "float" and len(node.args) == 1:
                    argument = node.args[0]
                    if isinstance(argument, ast.BoolOp) and isinstance(argument.op, ast.Or):
                        if isinstance(argument.values[-1], ast.Constant) and argument.values[-1].value == 0:
                            argument = argument.values[0]
                    if isinstance(argument, ast.Call) and isinstance(argument.func, ast.Attribute) and argument.func.attr == "get":
                        if len(argument.args) == 2 and isinstance(argument.args[1], ast.Constant) and argument.args[1].value == 0:
                            argument.args = argument.args[:1]
                        node = ast.Call(func=ast.Name(id="verified_narration_number", ctx=ast.Load()),
                                        args=[argument, ast.Constant("narration source statistic")],
                                        keywords=[ast.keyword(arg="minimum", value=ast.Constant(-1000000))])
                return node
        tree = VerifiedNarrationNumbers().visit(ast.parse(source))
        ast.fix_missing_locations(tree)
        source = 'from day3.live_evidence import number as verified_narration_number\n' + ast.unparse(tree) + '\n'
        source += '\nfrom day3.evidence_narration import write_script_manifest\nwrite_script_manifest(globals())\n'
    return source
