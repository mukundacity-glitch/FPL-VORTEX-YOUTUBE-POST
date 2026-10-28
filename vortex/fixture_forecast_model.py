"""FPL VORTEX canonical Day-3 fixture forecast engine (Phase 1–4).

Read-only extraction of the user's DAY-3 forecasting methodology. The 26
shared Phase-1/Phase-2 functions are syntax-tree identical to DAY-3's source.
FPL-Core match evidence is fetched and verified from its original public GitHub
repository; the consumer does not read DAY-1/2/3 Colab notebooks or Drive.

Requires fresh complete current-season source coverage. If the upstream source
is incomplete, raises an error rather than substituting official FPL FDR.
Publication of this module does not modify the user's DAY-3 notebook.
"""
from pathlib import Path
from datetime import datetime, timezone
import re, math, json, os
import numpy as np
import pandas as pd
import concurrent.futures as futures
import hashlib
import io
from urllib.parse import quote
import requests

def refresh_fpl_core(boot, official_fixtures, input_root, now, client):
    """Mirror the archive's original public repository at a verified commit.

    Preserve the user's archive. Official team, kickoff and score identities
    validate the new current-season CSVs before any model rebuild uses them.
    Missing red-card timing is resolved from the matching ESPN event only.
    """
    year=min(int(e['deadline_time'][:4]) for e in boot['events'])
    complete=[f for f in official_fixtures if f.get('finished')]
    repository = os.environ.get('VORTEX_FPL_CORE_REPOSITORY', 'olbauday/FPL-Core-Insights')
    if repository not in {'olbauday/FPL-Core-Insights', 'lukegiuseppin/fpl'}:
        raise ValueError('Unsupported FPL Core repository')
    ref = os.environ.get('VORTEX_FPL_CORE_REF', 'main')
    if ref != 'main' and not re.fullmatch('[0-9a-f]{40}', ref):
        raise ValueError('Invalid FPL Core commit reference')
    if ref == 'main':
        commit = client.get(f'https://api.github.com/repos/{repository}/commits/main', required=True, timeout=8)
        sha = str(commit.get('sha', ''))
    else:
        sha = ref
    if not re.fullmatch('[0-9a-f]{40}', sha):
        raise RuntimeError('Original FPL Core repository commit could not be verified')
    tree=client.get(f'https://api.github.com/repos/{repository}/git/trees/{sha}?recursive=1',required=True,timeout=8)
    if not re.fullmatch('[0-9a-f]{40}', str(tree.get('sha', ''))) or tree.get('truncated'):
        raise RuntimeError('Original FPL Core repository commit/tree could not be verified')
    files={r['path']:r for r in tree.get('tree',[]) if r.get('type')=='blob'}
    paths=[f'{year-1}-{year}/teams.csv',f'{year}-{year+1}/teams.csv']
    paths += [f'{year-1}-{year}/By Tournament/Premier League/GW{gw}/matches.csv' for gw in range(1,39)]
    paths += [f'{year}-{year+1}/By Tournament/Premier League/GW{gw}/matches.csv' for gw in sorted({int(f['event']) for f in complete})]
    root=Path(input_root)/'fpl_core_live'/sha;root.mkdir(parents=True,exist_ok=True)
    def csv_file(path):
        record=files.get('data/'+path)
        if not record:raise RuntimeError('Original archive lacks '+path)
        target=root/path;url='https://raw.githubusercontent.com/'+repository+'/'+sha+'/data/'+quote(path,safe='/')
        payload=target.read_bytes() if target.exists() else None
        def matches_blob(data):
            return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()==record.get('sha')
        if payload is None or not matches_blob(payload):
            error=None
            for attempt in range(2):
                try:
                    response=requests.get(url,timeout=12);response.raise_for_status();payload=response.content
                    if not matches_blob(payload):raise RuntimeError('Repository blob checksum mismatch: '+path)
                    pd.read_csv(io.BytesIO(payload))
                    target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(payload);break
                except (requests.RequestException,ValueError,RuntimeError) as exc:error=exc
            else:raise RuntimeError('Could not refresh '+path+': '+str(error))
        return path,url,hashlib.sha256(payload).hexdigest()
    with futures.ThreadPoolExecutor(max_workers=6) as executor:
        downloads=list(executor.map(csv_file,paths))
    current=pd.read_csv(root/f'{year}-{year+1}/teams.csv')
    by_code={int(r['code']):_vx_norm_team_name(r['name']) for _,r in current.iterrows()}
    official_names={int(t['id']):_vx_norm_team_name(t['name']) for t in boot['teams']}
    if set(by_code.values())!=set(official_names.values()):raise RuntimeError('Refreshed archive teams differ from official season teams')
    frames=[pd.read_csv(root/p).assign(__path=p) for p in paths if p.startswith(f'{year}-{year+1}/') and p.endswith('/matches.csv')]
    matches=pd.concat(frames,ignore_index=True) if frames else pd.DataFrame()
    matches=matches[matches.finished.astype(str).str.lower().isin(['true','1'])].copy()
    if len(matches)!=len(complete) or matches.match_id.duplicated().any():raise RuntimeError('Refreshed completed fixture coverage is incomplete or duplicated')
    identities={};verified=[]
    for _,match in matches.iterrows():
        hn=by_code.get(int(match.home_team));an=by_code.get(int(match.away_team));kickoff=pd.to_datetime(match.kickoff_time,utc=True)
        candidates=[f for f in complete if official_names[f['team_h']]==hn and official_names[f['team_a']]==an and pd.to_datetime(f['kickoff_time'],utc=True)==kickoff and f['team_h_score']==int(match.home_score) and f['team_a_score']==int(match.away_score)]
        if len(candidates)!=1:raise RuntimeError('Refreshed fixture differs from official identity: '+str(match.match_id))
        identities[str(match.match_id)]=(hn,an,candidates[0]);verified.append(int(candidates[0]['id']))
    if len(set(verified))!=len(complete):raise RuntimeError('Refreshed fixture identity is not one-to-one')
    incidents=[]
    red=matches[(matches.home_red_cards.fillna(0)+matches.away_red_cards.fillna(0))>0]
    def red_timing(item):
        _,match=item;hn,an,official=identities[str(match.match_id)]
        day=str(match.kickoff_time)[:10].replace('-','')
        board_url='https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard?dates='+day+'&limit=1000'
        board=client.get(board_url,required=True,timeout=6);found=[]
        for event in board.get('events',[]):
            if not event.get('status',{}).get('type',{}).get('completed'):continue
            sides={s['homeAway']:s for s in event.get('competitions',[{}])[0].get('competitors',[])}
            if set(sides)!={'home','away'}:continue
            if _vx_norm_team_name(sides['home']['team']['displayName'])!=hn or _vx_norm_team_name(sides['away']['team']['displayName'])!=an:continue
            if pd.Timestamp(event['date'])!=pd.Timestamp(official['kickoff_time']):continue
            if int(sides['home']['score'])!=int(match.home_score) or int(sides['away']['score'])!=int(match.away_score):continue
            found.append(event)
        if len(found)!=1:raise RuntimeError('ESPN red-card fixture identity is not unique: '+str(match.match_id))
        url='https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/summary?event='+str(found[0]['id'])
        detail=client.get(url,required=True,timeout=6);got={'home':[],'away':[]}
        for side in detail.get('rosters',[]):
            homeaway=side.get('homeAway')
            if homeaway not in got or _vx_norm_team_name(side.get('team',{}).get('displayName'))!=(hn if homeaway=='home' else an):continue
            for player in side.get('roster',[]):
                for play in player.get('plays',[]):
                    if not play.get('redCard'):continue
                    clock=str(play.get('clock',{}).get('displayValue',''))
                    timing=re.fullmatch(r"(\d+)(?:\s*['’]\s*\+\s*(\d+)|\s*\+\s*(\d+))?['’]?",clock.strip())
                    if not timing:raise RuntimeError('Red-card minute is unverified: '+clock)
                    got[homeaway].append({'match_id':str(match.match_id),'team_side':'H' if homeaway=='home' else 'A','minute':int(timing.group(1)),
                        'added_time':int(timing.group(2) or timing.group(3) or 0),'card_type':'Red card','source_url':url,'athlete_id':player.get('athlete',{}).get('id')})
        for side,count in [('home',int(match.home_red_cards)),('away',int(match.away_red_cards))]:
            if len(got[side])!=count:raise RuntimeError(f'{match.match_id}: expected {count} {side} red cards, verified {len(got[side])}')
        return got['home']+got['away']
    with futures.ThreadPoolExecutor(max_workers=4) as executor:
        for rows in executor.map(red_timing,red.iterrows()):incidents.extend(rows)
    pl=root/f'{year}-{year+1}/By Tournament/Premier League'
    if incidents:pd.DataFrame(incidents).to_csv(pl/'incidents.csv',index=False)
    report={'repository':'https://github.com/'+repository,'commit':sha,'checked_at':now.isoformat(),
            'official_completed_fixtures':len(complete),'verified_fixture_ids':verified,'verified_red_card_incidents':incidents,
            'files':[{'path':p,'source_url':u,'sha256':h} for p,u,h in downloads]}
    (Path(input_root)/'fpl_core_refresh_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(f'FPL Core refresh: {len(complete)} completed fixtures verified; {len(incidents)} red-card timings verified',flush=True)
    return root

def _vx_norm_team_name(value):
    text = str(value or "").strip().lower()
    for a, b in (("&", "and"), ("-", " "), ("_", " "), (".", ""), ("'", "")):
        text = text.replace(a, b)
    text = " ".join(text.split())
    aliases = {
        "man city": "manchester city",
        "man utd": "manchester united",
        "man united": "manchester united",
        "spurs": "tottenham hotspur",
        "tottenham": "tottenham hotspur",
        "wolves": "wolverhampton wanderers",
        "wolverhampton": "wolverhampton wanderers",
        "west ham": "west ham united",
        "brighton": "brighton and hove albion",
        "newcastle": "newcastle united",
        "nottingham forest": "nottingham forest",
        "nottm forest": "nottingham forest",
        "leeds": "leeds united",
    }
    return aliases.get(text, text)

def _vx_pick_col(frame, aliases, label, required=True):
    lut = {str(c).strip().lower(): c for c in frame.columns}
    for name in aliases:
        if str(name).lower() in lut:
            return lut[str(name).lower()]
    if required:
        raise RuntimeError(f"FPL_CORE adapter: cannot prove column for {label}; tried {aliases}")
    return None

def _vx_read_many_csv(paths):
    frames = []
    for path in sorted(set(Path(x) for x in paths)):
        try:
            f = pd.read_csv(path)
        except Exception as exc:
            raise RuntimeError(f"FPL_CORE adapter cannot read {path}: {type(exc).__name__}: {exc}")
        if not f.empty:
            f = f.copy()
            f["__source_file"] = str(path)
            frames.append(f)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

def _vx_fpl_core_season_dir(start_year):
    return PHASE1_FPL_CORE_ROOT / f"{start_year}-{start_year + 1}"

def _vx_fpl_core_pl_root(start_year):
    return _vx_fpl_core_season_dir(start_year) / "By Tournament" / "Premier League"

def _vx_provider_team_key(value):
    """Canonical key for provider team identifiers such as 39, 39.0 or '39'."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    try:
        num = float(value)
        if np.isfinite(num) and abs(num - round(num)) < 1e-9:
            return str(int(round(num)))
    except Exception:
        pass
    text = str(value).strip()
    return text if text else None

def _vx_fpl_core_season_team_maps(start_year):
    """Read the season-local teams.csv and expose explicit code/id -> club-name maps.

    FPL_CORE match files use provider identifiers that can differ from official
    FPL's current-season `id`. 2025/26 `matches.csv`, for example, stores the
    `code` field (e.g. Wolves=39, Man City=43) in home_team/away_team.
    We therefore prove the key space from the season-local teams table rather
    than treating those numbers as cross-season identities.
    """
    season_dir = _vx_fpl_core_season_dir(start_year)
    candidates = [season_dir / "teams.csv"]
    if not candidates[0].exists():
        # Safe fallback to a season snapshot when the master table is absent.
        candidates.extend(sorted((season_dir / "By Tournament" / "Premier League").rglob("teams.csv")))
        candidates.extend(sorted((season_dir / "By Gameweek").rglob("teams.csv")))
    team_file = next((p for p in candidates if p.exists()), None)
    if team_file is None:
        raise RuntimeError(f"FPL_CORE adapter: no season-local teams.csv for {start_year}-{start_year + 1}")

    tf = pd.read_csv(team_file)
    if tf.empty:
        raise RuntimeError(f"FPL_CORE adapter: empty teams.csv at {team_file}")
    name_col = _vx_pick_col(tf, ("name", "team_name", "fotmob_name"), "season team name")
    code_col = _vx_pick_col(tf, ("code",), "season team code", required=False)
    id_col = _vx_pick_col(tf, ("id", "team_id"), "season team id", required=False)
    if code_col is None and id_col is None:
        raise RuntimeError(f"FPL_CORE adapter: teams.csv has neither code nor id at {team_file}")

    def _build_map(key_col):
        out = {}
        if key_col is None:
            return out
        for _, tr in tf.iterrows():
            k = _vx_provider_team_key(tr.get(key_col))
            nm = str(tr.get(name_col, "")).strip()
            if k is None or not nm:
                continue
            # A single key must never point to two clubs inside the same key space.
            if k in out and _vx_norm_team_name(out[k]) != _vx_norm_team_name(nm):
                raise RuntimeError(
                    f"FPL_CORE adapter: duplicate season team key {k!r} in {key_col}: "
                    f"{out[k]!r} vs {nm!r}"
                )
            out[k] = nm
        return out

    code_map = _build_map(code_col)
    id_map = _build_map(id_col)
    return {"code": code_map, "id": id_map, "source": team_file}

def _vx_resolve_match_team_map(matches, home_col, away_col, start_year):
    """Prove whether match home/away identifiers use season team code or id."""
    maps = _vx_fpl_core_season_team_maps(start_year)
    raw_vals = pd.concat([matches[home_col], matches[away_col]], ignore_index=True)
    keys = {_vx_provider_team_key(v) for v in raw_vals.dropna().tolist()}
    keys.discard(None)
    if not keys:
        raise RuntimeError("FPL_CORE adapter: match file contains no team identifiers")

    coverage = {}
    for label in ("code", "id"):
        m = maps[label]
        coverage[label] = sum(k in m for k in keys) / float(len(keys)) if m else 0.0

    best = max(coverage, key=coverage.get)
    best_cov = float(coverage[best])
    if best_cov < 0.95:
        raise RuntimeError(
            "FPL_CORE adapter: cannot prove match-team identifier space from season teams.csv; "
            f"code_coverage={coverage['code']:.3f}, id_coverage={coverage['id']:.3f}, "
            f"sample_keys={sorted(keys)[:10]}"
        )
    chosen = maps[best]
    unresolved = sorted(k for k in keys if k not in chosen)
    if unresolved:
        raise RuntimeError(
            f"FPL_CORE adapter: unresolved match team identifiers using {best}: {unresolved[:10]}"
        )
    return chosen, best, maps["source"]

def _vx_synthetic_legacy_team_id(name):
    # Stable negative ID for previous-season opponents not present in the
    # current FPL team list. It is used only for opponent adjustment; it never
    # becomes a current-team output row.
    import hashlib
    digest = hashlib.sha1(_vx_norm_team_name(name).encode("utf-8")).hexdigest()[:8]
    return -int(digest, 16)

def _vx_fpl_core_side_from_shot(row, home_name, away_name, team_col=None, side_col=None):
    if side_col is not None:
        v = row.get(side_col)
        if isinstance(v, (bool, np.bool_)):
            return "H" if bool(v) else "A"
        t = str(v).strip().lower()
        if t in {"h", "home", "1", "true"}:
            return "H"
        if t in {"a", "away", "0", "false"}:
            return "A"
    if team_col is not None:
        n = _vx_norm_team_name(row.get(team_col))
        if n == _vx_norm_team_name(home_name):
            return "H"
        if n == _vx_norm_team_name(away_name):
            return "A"
    return None

def _vx_try_build_fpl_core_team_match_raw():
    """Build Phase-1 team-match evidence from canonical FPL_CORE match aggregates.

    The trusted match table already exposes non-penalty xG, set-play xG, total
    xG and big chances. Using those canonical aggregates removes the fragile
    dependency on shot-level situation parsing. Incidents are consulted only
    when a finished match actually contains a red card, because Phase 1 needs
    the duration of the numerical disadvantage for its context weight.

    Cross-season numeric team identifiers are never treated as identities.
    Each season's matches are resolved through that season's teams.csv and are
    then re-keyed to the current official FPL team IDs by normalized club name.
    Relegated historical opponents receive stable negative IDs used only for
    opponent adjustment.
    """
    global PHASE1_PREVIOUS_SEASON_TEAM_NAMES, PHASE1_CONTINUING_CURRENT_TEAM_IDS

    if not PHASE1_FPL_CORE_ROOT.exists():
        return None, None

    current_name_to_id = {}
    for _, tr in teams.iterrows():
        tid = int(tr["id"])
        for nm in (tr.get("name"), tr.get("short_name")):
            if nm is not None and str(nm).strip():
                current_name_to_id[_vx_norm_team_name(nm)] = tid

    def _current_or_legacy_id(name):
        norm = _vx_norm_team_name(name)
        return int(current_name_to_id.get(norm, _vx_synthetic_legacy_team_id(norm)))

    def _as_float(value):
        try:
            out = float(value)
        except Exception:
            return np.nan
        return out if np.isfinite(out) else np.nan

    def _boolish(value):
        if isinstance(value, (bool, np.bool_)):
            return bool(value)
        text = str(value).strip().lower()
        return text in {"1", "true", "yes", "y", "finished", "complete", "completed"}

    def _incident_minute(value, added=None):
        """Return a football minute including stoppage time when separately stored."""
        if value is None or (isinstance(value, float) and np.isnan(value)):
            return np.nan
        if isinstance(value, (int, float, np.integer, np.floating)):
            base = float(value)
        else:
            text = str(value).strip()
            mm = re.match(r"^(\d+)(?:\s*\+\s*(\d+))?", text)
            if not mm:
                return np.nan
            base = float(mm.group(1)) + float(mm.group(2) or 0.0)
        if added is not None and not (isinstance(added, float) and np.isnan(added)):
            try:
                add_v = float(added)
                if np.isfinite(add_v) and add_v > 0 and "+" not in str(value):
                    base += add_v
            except Exception:
                pass
        return base

    all_team_rows = []
    previous_season_team_names = set()
    skipped_red_timing = []

    for start_year in (_start_year - 1, _start_year):
        season_label = f"{start_year}-{str(start_year + 1)[-2:]}"
        pl_root = _vx_fpl_core_pl_root(start_year)
        if not pl_root.exists():
            if start_year == _start_year:
                print(f"ℹ️ Phase 1: no current-season Premier League detail folder at {pl_root}; prior-only mode.")
                continue
            raise RuntimeError(f"FPL_CORE adapter: missing Premier League folder {pl_root}")

        match_files = list(pl_root.rglob("matches.csv"))
        if not match_files:
            if start_year == _start_year:
                print(f"ℹ️ Phase 1: no completed current-season matches under {pl_root}; prior-only mode.")
                continue
            raise RuntimeError(f"FPL_CORE adapter: no matches.csv under {pl_root}")

        matches = _vx_read_many_csv(match_files)
        if matches.empty:
            if start_year == _start_year:
                print(f"ℹ️ Phase 1: current-season match table is empty; prior-only mode.")
                continue
            raise RuntimeError(f"FPL_CORE adapter: previous-season matches.csv files are empty under {pl_root}")

        # Canonical match fields. These are documented FPL_CORE match aggregates
        # and are materially safer than reconstructing the same quantities from
        # shot labels.
        m_id = _vx_pick_col(matches, ("match_id", "id"), "match id")
        m_date = _vx_pick_col(matches, ("kickoff_time", "match_date", "start_time", "date"), "match date")
        m_home = _vx_pick_col(matches, ("home_team", "home_team_name", "home_name"), "home team")
        m_away = _vx_pick_col(matches, ("away_team", "away_team_name", "away_name"), "away team")
        m_npxg_h = _vx_pick_col(matches, ("home_non_penalty_xg", "home_npxg"), "home non-penalty xG")
        m_npxg_a = _vx_pick_col(matches, ("away_non_penalty_xg", "away_npxg"), "away non-penalty xG")
        m_total_h = _vx_pick_col(matches, ("home_expected_goals_xg", "home_xg"), "home total xG")
        m_total_a = _vx_pick_col(matches, ("away_expected_goals_xg", "away_xg"), "away total xG")
        m_set_h = _vx_pick_col(matches, ("home_xg_set_play", "home_set_piece_xg", "home_set_play_xg"), "home set-play xG")
        m_set_a = _vx_pick_col(matches, ("away_xg_set_play", "away_set_piece_xg", "away_set_play_xg"), "away set-play xG")
        m_hbc = _vx_pick_col(matches, ("home_big_chances", "home_big_chance"), "home big chances")
        m_abc = _vx_pick_col(matches, ("away_big_chances", "away_big_chance"), "away big chances")
        m_finished = _vx_pick_col(matches, ("finished", "is_finished", "complete", "completed"), "finished flag", required=False)
        m_red_h = _vx_pick_col(matches, ("home_red_cards", "home_red_card"), "home red-card count", required=False)
        m_red_a = _vx_pick_col(matches, ("away_red_cards", "away_red_card"), "away red-card count", required=False)

        season_team_lookup, season_team_key_space, season_team_source = _vx_resolve_match_team_map(
            matches, m_home, m_away, start_year
        )
        if start_year == _start_year - 1:
            previous_season_team_names.update(
                _vx_norm_team_name(nm) for nm in season_team_lookup.values() if str(nm).strip()
            )
            print(
                f"✅ Phase 1 identity: {season_label} matches use teams.csv `{season_team_key_space}` keys; "
                f"{len(previous_season_team_names)} previous-season PL clubs resolved."
            )

        # A GW directory can be either gameweek-only or cumulative. Sort by the
        # numeric GW encoded in the source path and retain the latest occurrence.
        def _source_gw(path_text):
            mm = re.search(r"(?:^|[/\\])GW(\d+)(?:[/\\]|$)", str(path_text), flags=re.I)
            return int(mm.group(1)) if mm else -1

        matches = matches.copy()
        matches["__match_id_text"] = matches[m_id].astype(str)
        matches["__source_gw"] = matches["__source_file"].map(_source_gw)
        matches = matches.sort_values(["__match_id_text", "__source_gw"]).drop_duplicates(
            subset=["__match_id_text"], keep="last"
        )

        # Read incidents only as a red-card timing source. Current-season
        # incidents may not exist yet; that is harmless when no finished match
        # in the available sample has a red card.
        incident_files = list(pl_root.rglob("incidents.csv"))
        incidents = _vx_read_many_csv(incident_files) if incident_files else pd.DataFrame()
        i_mid = i_min = i_added = i_side = i_card = None
        if not incidents.empty:
            incidents = incidents.drop_duplicates(
                subset=[c for c in incidents.columns if c != "__source_file"]
            ).copy()
            i_mid = _vx_pick_col(incidents, ("match_id",), "incident match id")
            i_min = _vx_pick_col(incidents, ("minute", "incident_minute", "time"), "incident minute")
            i_added = _vx_pick_col(incidents, ("added_time", "stoppage_time"), "incident added time", required=False)
            i_side = _vx_pick_col(incidents, ("team_side", "side", "home_away", "is_home"), "incident team side")
            i_card = _vx_pick_col(
                incidents,
                ("card_type", "card_colour", "card_color", "card", "incident_detail", "detail"),
                "incident card type",
                required=False,
            )
            incidents[i_mid] = incidents[i_mid].astype(str)

        season_rows_before = len(all_team_rows)
        for _, mr in matches.iterrows():
            if m_finished is not None and not _boolish(mr.get(m_finished)):
                continue

            mid = str(mr[m_id])
            home_key = _vx_provider_team_key(mr[m_home])
            away_key = _vx_provider_team_key(mr[m_away])
            if home_key not in season_team_lookup or away_key not in season_team_lookup:
                raise RuntimeError(
                    f"FPL_CORE adapter: unresolved season team key for match_id={mid}: "
                    f"home={home_key!r}, away={away_key!r}, key_space={season_team_key_space}"
                )
            home_name = str(season_team_lookup[home_key])
            away_name = str(season_team_lookup[away_key])
            match_date = pd.to_datetime(mr[m_date], utc=True, errors="coerce")
            if pd.isna(match_date):
                continue

            vals = {
                "hnp": _as_float(mr[m_npxg_h]),
                "anp": _as_float(mr[m_npxg_a]),
                "htot": _as_float(mr[m_total_h]),
                "atot": _as_float(mr[m_total_a]),
                "hset": _as_float(mr[m_set_h]),
                "aset": _as_float(mr[m_set_a]),
                "hbc": _as_float(mr[m_hbc]),
                "abc": _as_float(mr[m_abc]),
            }
            # Missing aggregate statistics mean the fixture is not yet usable as
            # descriptive evidence. Do not turn missing values into zeroes.
            if any(not np.isfinite(v) for v in vals.values()):
                continue
            if any(v < -1e-9 for v in vals.values()):
                raise RuntimeError(f"FPL_CORE adapter: negative descriptive match statistic for match_id={mid}")

            # Total xG and NPxG are the same provider measure; their difference
            # isolates penalty xG. Allow only tiny rounding noise below zero.
            hpen_delta = vals["htot"] - vals["hnp"]
            apen_delta = vals["atot"] - vals["anp"]
            if hpen_delta < -0.03 or apen_delta < -0.03:
                raise RuntimeError(
                    f"FPL_CORE adapter: total xG < NPxG beyond rounding tolerance for match_id={mid}: "
                    f"home_delta={hpen_delta:.3f}, away_delta={apen_delta:.3f}"
                )
            hpen = float(max(0.0, hpen_delta))
            apen = float(max(0.0, apen_delta))

            red_count_h = int(max(0.0, _as_float(mr[m_red_h]))) if m_red_h is not None and np.isfinite(_as_float(mr[m_red_h])) else 0
            red_count_a = int(max(0.0, _as_float(mr[m_red_a]))) if m_red_a is not None and np.isfinite(_as_float(mr[m_red_a])) else 0
            red_h = red_a = 0.0

            if red_count_h or red_count_a:
                # Red-card duration is the only item not recoverable from the
                # aggregate match row. If timing cannot be proven, omit this one
                # distorted match rather than fabricating a minute or failing the
                # entire 380-match season.
                if incidents.empty or i_card is None:
                    skipped_red_timing.append(mid)
                    continue
                inc = incidents.loc[incidents[i_mid].eq(mid)].copy()
                if inc.empty:
                    skipped_red_timing.append(mid)
                    continue
                card_text = (
                    inc[i_card].astype(str).str.lower()
                    .str.replace(r"[_-]+", " ", regex=True)
                    .str.replace(r"\s+", " ", regex=True)
                    .str.strip()
                )
                red_mask = card_text.str.contains(
                    r"\bred\b|\bsecond yellow\b|\b2nd yellow\b|\byellow red\b", regex=True, na=False
                )
                reds = inc.loc[red_mask].copy()
                if len(reds) < red_count_h + red_count_a:
                    skipped_red_timing.append(mid)
                    continue
                reds["__minute"] = [
                    _incident_minute(v, a if i_added is not None else None)
                    for v, a in zip(
                        reds[i_min].tolist(),
                        reds[i_added].tolist() if i_added is not None else [None] * len(reds),
                    )
                ]
                reds["__side"] = reds.apply(
                    lambda r: _vx_fpl_core_side_from_shot(r, home_name, away_name, None, i_side), axis=1
                )
                if reds["__minute"].isna().any() or reds["__side"].isna().any():
                    skipped_red_timing.append(mid)
                    continue
                actual_h = int(reds["__side"].eq("H").sum())
                actual_a = int(reds["__side"].eq("A").sum())
                if actual_h < red_count_h or actual_a < red_count_a:
                    skipped_red_timing.append(mid)
                    continue
                red_h = float(sum(max(0.0, 90.0 - float(x)) for x in reds.loc[reds["__side"].eq("H"), "__minute"]))
                red_a = float(sum(max(0.0, 90.0 - float(x)) for x in reds.loc[reds["__side"].eq("A"), "__minute"]))

            hid = _current_or_legacy_id(home_name)
            aid = _current_or_legacy_id(away_name)
            source_path = Path(str(mr.get("__source_file", "")))
            if source_path.exists():
                source_ts = datetime.fromtimestamp(source_path.stat().st_mtime, tz=timezone.utc).isoformat()
            else:
                source_ts = data_snapshot_timestamp

            common = {
                "season": season_label,
                "match_date": match_date.isoformat(),
                "source_name": "FPL_CORE_CANONICAL_MATCH_AGGREGATES_INCIDENTS",
                "source_timestamp": source_ts,
            }
            all_team_rows.extend([
                {
                    **common,
                    "team_id": hid,
                    "opponent_id": aid,
                    "team_name": home_name,
                    "opponent_name": away_name,
                    "venue": "H",
                    "npxg_for": vals["hnp"],
                    "npxga": vals["anp"],
                    "big_chances_for": vals["hbc"],
                    "big_chances_against": vals["abc"],
                    "set_piece_xg_for": vals["hset"],
                    "set_piece_xg_against": vals["aset"],
                    "penalty_xg_for": hpen,
                    "penalty_xg_against": apen,
                    "red_card_minutes_for": red_h,
                    "red_card_minutes_against": red_a,
                },
                {
                    **common,
                    "team_id": aid,
                    "opponent_id": hid,
                    "team_name": away_name,
                    "opponent_name": home_name,
                    "venue": "A",
                    "npxg_for": vals["anp"],
                    "npxga": vals["hnp"],
                    "big_chances_for": vals["abc"],
                    "big_chances_against": vals["hbc"],
                    "set_piece_xg_for": vals["aset"],
                    "set_piece_xg_against": vals["hset"],
                    "penalty_xg_for": apen,
                    "penalty_xg_against": hpen,
                    "red_card_minutes_for": red_a,
                    "red_card_minutes_against": red_h,
                },
            ])

        n_team_rows = len(all_team_rows) - season_rows_before
        if start_year == _start_year - 1 and n_team_rows < 600:
            # 300 usable matches is a deliberately broad integrity floor; a
            # normal previous PL season should yield close to 760 team-match rows.
            raise RuntimeError(
                f"FPL_CORE adapter: only {n_team_rows // 2} usable previous-season PL matches; "
                "expected at least 300"
            )
        if start_year == _start_year and n_team_rows == 0:
            print("ℹ️ Phase 1: no usable completed current-season aggregate rows yet; prior-only mode.")

    if not all_team_rows:
        raise RuntimeError("FPL_CORE adapter produced no completed-match evidence")

    frame = pd.DataFrame(all_team_rows)
    PHASE1_PREVIOUS_SEASON_TEAM_NAMES = sorted(previous_season_team_names)
    PHASE1_CONTINUING_CURRENT_TEAM_IDS = sorted({
        int(tr["id"])
        for _, tr in teams.iterrows()
        if (
            _vx_norm_team_name(tr.get("name")) in previous_season_team_names
            or _vx_norm_team_name(tr.get("short_name")) in previous_season_team_names
        )
    })
    if len(PHASE1_CONTINUING_CURRENT_TEAM_IDS) < 14:
        raise RuntimeError(
            "FPL_CORE adapter: cross-season roster continuity remains unproven after teams.csv mapping; "
            f"matched_current_clubs={len(PHASE1_CONTINUING_CURRENT_TEAM_IDS)}, "
            f"previous_names={PHASE1_PREVIOUS_SEASON_TEAM_NAMES}"
        )

    if skipped_red_timing:
        print(
            f"ℹ️ Phase 1: omitted {len(set(skipped_red_timing))} red-card-distorted match(es) "
            "whose exact send-off timing could not be proven."
        )

    missing = [c for c in PHASE1_MATCH_FIELDS if c not in frame.columns]
    if missing:
        raise RuntimeError(f"FPL_CORE adapter output missing required fields: {missing}")
    return frame, PHASE1_FPL_CORE_ROOT

def _vx_context_template():
    base = teams[["id", "name", "short_name"]].rename(columns={"id": "team_id"}).copy()
    base["promoted_team"] = pd.NA
    for c in _PHASE1_CONTEXT_NUMERIC_FIELDS:
        base[c] = np.nan
    base["context_complete"] = False
    base["context_source"] = ""
    base["context_source_timestamp"] = ""
    return base

def _vx_context_is_untouched_template(frame):
    """True only for the machine-created blank template; partial edits are preserved."""
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return False
    required = {"team_id", "promoted_team", "context_complete", "context_source", *_PHASE1_CONTEXT_NUMERIC_FIELDS}
    if not required.issubset(frame.columns):
        return False
    complete_text = frame["context_complete"].astype(str).str.strip().str.lower()
    if (~complete_text.isin({"false", "0", "no", "n", "", "nan", "<na>"})).any():
        return False
    if frame["context_source"].fillna("").astype(str).str.strip().ne("").any():
        return False
    # Promoted/not-promoted flags alone are descriptive scaffold metadata.
    # They do not make this a manually calibrated context file. This allows a
    # persisted machine template with only those flags filled to be safely
    # completed from trusted FPL_CORE roster continuity. Any numeric adjustment
    # or provenance below still protects genuine manual work from overwrite.
    promoted_text = frame["promoted_team"].fillna("").astype(str).str.strip().str.lower()
    _allowed_promoted_scaffold = {"", "nan", "<na>", "none", "true", "false", "1", "0", "yes", "no", "y", "n"}
    if (~promoted_text.isin(_allowed_promoted_scaffold)).any():
        return False
    for c in _PHASE1_CONTEXT_NUMERIC_FIELDS:
        if pd.to_numeric(frame[c], errors="coerce").notna().any():
            return False
    return True

def _vx_auto_context_from_match_evidence(match_frame):
    if not isinstance(match_frame, pd.DataFrame) or match_frame.empty:
        return None, "NO_TRUSTED_MATCH_EVIDENCE"
    prev = match_frame.loc[match_frame["season"].astype(str).eq(PREVIOUS_SEASON)].copy()
    if prev.empty:
        return None, f"NO_PREVIOUS_SEASON_EVIDENCE_{PREVIOUS_SEASON}"

    current_ids = set(pd.to_numeric(teams["id"], errors="coerce").dropna().astype(int))

    # Prefer the explicit previous-season normalized club-name set captured by
    # the FPL_CORE adapter. This avoids the cross-season-ID bug that previously
    # classified every current club as unmatched. Fall back to IDs only for a
    # manually supplied raw table that does not carry names.
    explicit_continuing = set(
        int(x) for x in globals().get("PHASE1_CONTINUING_CURRENT_TEAM_IDS", [])
        if pd.notna(x)
    )
    if explicit_continuing:
        prev_ids = explicit_continuing & current_ids
    elif "team_name" in prev.columns:
        prev_names = set(prev["team_name"].dropna().astype(str).map(_vx_norm_team_name))
        prev_ids = set()
        for _, _tr in teams.iterrows():
            if (
                _vx_norm_team_name(_tr.get("name")) in prev_names
                or _vx_norm_team_name(_tr.get("short_name")) in prev_names
            ):
                prev_ids.add(int(_tr["id"]))
    else:
        prev_ids = set(pd.to_numeric(prev["team_id"], errors="coerce").dropna().astype(int)) & current_ids

    # A normal PL rollover retains about 17 clubs. These broad rails catch a
    # broken team-name map rather than accidentally labelling many clubs promoted.
    if len(prev_ids) < 14:
        return None, f"ROSTER_CONTINUITY_UNPROVEN_ONLY_{len(prev_ids)}_CURRENT_TEAMS_MATCHED"
    promoted_ids = current_ids - prev_ids
    if len(promoted_ids) > 6:
        return None, f"ROSTER_CONTINUITY_IMPLAUSIBLE_{len(promoted_ids)}_PROMOTED_IDS"

    ts = datetime.now(timezone.utc).isoformat()
    base = teams[["id", "name", "short_name"]].rename(columns={"id": "team_id"}).copy()
    base["team_id"] = pd.to_numeric(base["team_id"], errors="raise").astype(int)
    base["promoted_team"] = base["team_id"].isin(promoted_ids)
    base["promoted_attack_prior_adjustment"] = np.where(
        base["promoted_team"], PHASE1_AUTO_PROMOTED_ATTACK_ADJUSTMENT, 0.0
    )
    base["promoted_defence_prior_adjustment"] = np.where(
        base["promoted_team"], PHASE1_AUTO_PROMOTED_DEFENCE_ADJUSTMENT, 0.0
    )
    base["promoted_team_uncertainty"] = np.where(
        base["promoted_team"], PHASE1_AUTO_PROMOTED_UNCERTAINTY, 0.0
    )
    for c in (
        "squad_arrivals_attack_delta",
        "squad_arrivals_defence_delta",
        "squad_departures_attack_delta",
        "squad_departures_defence_delta",
        "manager_attack_delta",
        "manager_defence_delta",
        "expected_xi_attack_delta",
        "expected_xi_defence_delta",
    ):
        base[c] = 0.0
    base["context_uncertainty"] = PHASE1_AUTO_BASE_CONTEXT_UNCERTAINTY
    base["context_complete"] = True
    base["context_source"] = "AUTO_BASELINE_FPL_CORE_ROSTER_CONTINUITY_V1"
    base["context_source_timestamp"] = ts
    return base, f"AUTO_BASELINE_READY_PROMOTED_IDS={sorted(promoted_ids)}"

def _vx_phase1_validate_match_frame(frame):
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return False, ["team_match_xg_raw has no approved rows"]
    missing = [c for c in PHASE1_MATCH_FIELDS if c not in frame.columns]
    issues = [f"missing field: {c}" for c in missing]
    if issues:
        return False, issues

    f = frame.copy()
    for c in (
        "team_id", "opponent_id", "npxg_for", "npxga",
        "big_chances_for", "big_chances_against",
        "set_piece_xg_for", "set_piece_xg_against",
        "penalty_xg_for", "penalty_xg_against",
        "red_card_minutes_for", "red_card_minutes_against",
    ):
        f[c] = pd.to_numeric(f[c], errors="coerce")

    if f["team_id"].isna().any() or f["opponent_id"].isna().any():
        issues.append("team_id/opponent_id contains null or non-numeric rows")
    if (~f["venue"].astype(str).str.upper().isin(["H", "A"])).any():
        issues.append("venue must be H or A")
    for c in ("npxg_for", "npxga", "set_piece_xg_for", "set_piece_xg_against", "penalty_xg_for", "penalty_xg_against"):
        if f[c].isna().any() or (f[c] < 0).any():
            issues.append(f"{c} contains missing/negative values")
    for c in ("big_chances_for", "big_chances_against", "red_card_minutes_for", "red_card_minutes_against"):
        if f[c].isna().any() or (f[c] < 0).any():
            issues.append(f"{c} contains missing/negative values")

    return len(issues) == 0, issues

def _vx_bool(value):
    if value is True or value is False:
        return bool(value)
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return False
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n", ""}:
        return False
    raise ValueError(f"Cannot parse boolean value: {value!r}")

def _vx_phase1_validate_context(frame):
    issues = []
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return False, ["team_context_raw is empty"]
    expected_ids = set(pd.to_numeric(teams["id"], errors="coerce").dropna().astype(int))
    got_ids = set(pd.to_numeric(frame["team_id"], errors="coerce").dropna().astype(int))
    if expected_ids != got_ids:
        issues.append(f"context team IDs mismatch: missing={sorted(expected_ids-got_ids)}, extra={sorted(got_ids-expected_ids)}")
    if "context_complete" not in frame.columns:
        issues.append("context_complete field is missing")
    else:
        try:
            complete_flags = frame["context_complete"].map(_vx_bool)
            if not complete_flags.all():
                issues.append("every team must have context_complete=True")
        except Exception as exc:
            issues.append(f"context_complete contains invalid boolean values: {exc}")
    numeric_context = [
        c for c in PHASE1_CONTEXT_FIELDS
        if c.endswith("_delta") or c.endswith("_adjustment") or c.endswith("_uncertainty")
    ]
    for c in numeric_context:
        vals = pd.to_numeric(frame[c], errors="coerce")
        if vals.isna().any():
            issues.append(f"{c} contains missing/non-numeric values")
    if "context_source" in frame.columns:
        if frame["context_source"].fillna("").astype(str).str.strip().eq("").any():
            issues.append("context_source must be non-empty for every team")
    if "context_source_timestamp" in frame.columns:
        parsed_ts = pd.to_datetime(frame["context_source_timestamp"], utc=True, errors="coerce")
        if parsed_ts.isna().any():
            issues.append("context_source_timestamp contains missing/invalid values")
    return len(issues) == 0, issues

def _vx_red_context_weight(row):
    # NPxG from heavily non-11v11 game states is downweighted, never deleted.
    rf = float(row.get("red_card_minutes_for", 0.0) or 0.0)
    ra = float(row.get("red_card_minutes_against", 0.0) or 0.0)
    distorted = min(90.0, abs(rf - ra))
    return float(max(0.35, 1.0 - 0.65 * distorted / 90.0))

def _vx_time_decay_weight(match_date, anchor_ts, half_life_days=90.0):
    d = pd.Timestamp(match_date)
    a = pd.Timestamp(anchor_ts)
    if d.tzinfo is None:
        d = d.tz_localize("UTC")
    else:
        d = d.tz_convert("UTC")
    if a.tzinfo is None:
        a = a.tz_localize("UTC")
    else:
        a = a.tz_convert("UTC")
    age_days = max(0.0, (a - d).total_seconds() / 86400.0)
    # Exact Phase-2 recency contract: w_match = 0.5 ** (days_since_match / 90).
    return float(0.5 ** (age_days / float(half_life_days)))

def _vx_weighted_mean(values, weights):
    v = np.asarray(values, dtype=float)
    w = np.asarray(weights, dtype=float)
    ok = np.isfinite(v) & np.isfinite(w) & (w > 0)
    if not ok.any():
        return np.nan
    return float(np.sum(v[ok] * w[ok]) / np.sum(w[ok]))

def _vx_shrink(raw_strength, n_eff, prior_equiv=4.0):
    if not np.isfinite(raw_strength):
        return 1.0
    n_eff = max(0.0, float(n_eff))
    return float((raw_strength * n_eff + 1.0 * prior_equiv) / (n_eff + prior_equiv))

def _vx_build_prior(match_frame, context_frame):
    f = match_frame.loc[match_frame["season"].astype(str).eq(PREVIOUS_SEASON)].copy()
    if f.empty:
        raise RuntimeError(f"No previous-season rows found for {PREVIOUS_SEASON}")

    f["match_date"] = pd.to_datetime(f["match_date"], utc=True, errors="coerce")
    if f["match_date"].isna().any():
        raise RuntimeError("Previous-season match_date contains invalid rows")

    num_cols = [
        "team_id","opponent_id","npxg_for","npxga","big_chances_for","big_chances_against",
        "set_piece_xg_for","set_piece_xg_against","penalty_xg_for","penalty_xg_against",
        "red_card_minutes_for","red_card_minutes_against"
    ]
    for c in num_cols:
        f[c] = pd.to_numeric(f[c], errors="raise")
    f["team_id"] = f["team_id"].astype(int)
    f["opponent_id"] = f["opponent_id"].astype(int)
    f["venue"] = f["venue"].astype(str).str.upper()
    f["_w"] = f.apply(_vx_red_context_weight, axis=1)

    mu_home = _vx_weighted_mean(f.loc[f["venue"].eq("H"), "npxg_for"], f.loc[f["venue"].eq("H"), "_w"])
    mu_away = _vx_weighted_mean(f.loc[f["venue"].eq("A"), "npxg_for"], f.loc[f["venue"].eq("A"), "_w"])
    if not np.isfinite(mu_home) or not np.isfinite(mu_away) or mu_home <= 0 or mu_away <= 0:
        raise RuntimeError("Cannot estimate previous-season venue NPxG baselines")

    # Penalties are a separate scoring component. NPxG remains the non-penalty
    # process baseline; penalty xG is added back explicitly downstream.
    pen_home = _vx_weighted_mean(f.loc[f["venue"].eq("H"), "penalty_xg_for"], f.loc[f["venue"].eq("H"), "_w"])
    pen_away = _vx_weighted_mean(f.loc[f["venue"].eq("A"), "penalty_xg_for"], f.loc[f["venue"].eq("A"), "_w"])
    pen_for_league = _vx_weighted_mean(f["penalty_xg_for"], f["_w"])
    pen_against_league = _vx_weighted_mean(f["penalty_xg_against"], f["_w"])
    if any((not np.isfinite(x) or x < 0) for x in (pen_home, pen_away, pen_for_league, pen_against_league)):
        raise RuntimeError("Cannot estimate previous-season penalty-xG baselines")

    team_ids = sorted(set(pd.to_numeric(teams["id"], errors="coerce").dropna().astype(int)))
    ah = {t: 1.0 for t in team_ids}
    dh = {t: 1.0 for t in team_ids}
    aa = {t: 1.0 for t in team_ids}
    da = {t: 1.0 for t in team_ids}

    # Fixed-point opponent adjustment. Attack >1 means stronger scoring process.
    # Defence >1 means weaker defence / more concession.
    for _ in range(20):
        new_ah, new_dh, new_aa, new_da = {}, {}, {}, {}
        for t in team_ids:
            h = f.loc[(f["team_id"].eq(t)) & (f["venue"].eq("H"))]
            a = f.loc[(f["team_id"].eq(t)) & (f["venue"].eq("A"))]

            h_att_ratio = h["npxg_for"].to_numpy() / np.maximum(
                0.05, mu_home * np.array([da.get(int(o), 1.0) for o in h["opponent_id"]])
            )
            h_def_ratio = h["npxga"].to_numpy() / np.maximum(
                0.05, mu_away * np.array([aa.get(int(o), 1.0) for o in h["opponent_id"]])
            )
            a_att_ratio = a["npxg_for"].to_numpy() / np.maximum(
                0.05, mu_away * np.array([dh.get(int(o), 1.0) for o in a["opponent_id"]])
            )
            a_def_ratio = a["npxga"].to_numpy() / np.maximum(
                0.05, mu_home * np.array([ah.get(int(o), 1.0) for o in a["opponent_id"]])
            )

            new_ah[t] = _vx_shrink(_vx_weighted_mean(h_att_ratio, h["_w"]), h["_w"].sum(), 4.0)
            new_dh[t] = _vx_shrink(_vx_weighted_mean(h_def_ratio, h["_w"]), h["_w"].sum(), 4.0)
            new_aa[t] = _vx_shrink(_vx_weighted_mean(a_att_ratio, a["_w"]), a["_w"].sum(), 4.0)
            new_da[t] = _vx_shrink(_vx_weighted_mean(a_def_ratio, a["_w"]), a["_w"].sum(), 4.0)

        # Geometric recentering prevents scale drift during iteration.
        def _recenter(d):
            vals = np.array([max(0.20, float(v)) for v in d.values()], dtype=float)
            gm = float(np.exp(np.mean(np.log(vals))))
            return {k: float(max(0.20, min(3.0, v / gm))) for k, v in d.items()}
        ah, dh, aa, da = map(_recenter, (new_ah, new_dh, new_aa, new_da))

    ctx = context_frame.copy()
    ctx["team_id"] = pd.to_numeric(ctx["team_id"], errors="raise").astype(int)
    ctx = ctx.set_index("team_id")

    rows = []
    for t in team_ids:
        team_rows = f.loc[f["team_id"].eq(t)]
        n = float(team_rows["_w"].sum())

        # Major squad, manager and expected-XI changes are applied exactly once
        # to the preseason prior as log-strength deltas.
        c = ctx.loc[t]
        att_delta = (
            float(c["squad_arrivals_attack_delta"])
            + float(c["squad_departures_attack_delta"])
            + float(c["manager_attack_delta"])
            + float(c["expected_xi_attack_delta"])
        )
        def_delta = (
            float(c["squad_arrivals_defence_delta"])
            + float(c["squad_departures_defence_delta"])
            + float(c["manager_defence_delta"])
            + float(c["expected_xi_defence_delta"])
        )

        promoted = _vx_bool(c["promoted_team"])
        promoted_att = float(c["promoted_attack_prior_adjustment"]) if promoted else 0.0
        promoted_def = float(c["promoted_defence_prior_adjustment"]) if promoted else 0.0
        promoted_unc = float(c["promoted_team_uncertainty"]) if promoted else 0.0

        # Temporary promoted adjustment lives ONLY here in the prior.
        ah_t = ah[t] * math.exp(att_delta + promoted_att)
        aa_t = aa[t] * math.exp(att_delta + promoted_att)
        dh_t = dh[t] * math.exp(def_delta + promoted_def)
        da_t = da[t] * math.exp(def_delta + promoted_def)

        overall_att = math.sqrt(max(0.05, ah_t) * max(0.05, aa_t))
        overall_def = math.sqrt(max(0.05, dh_t) * max(0.05, da_t))

        # Known injuries/suspensions enter uncertainty. Their strength impact
        # must be represented explicitly through expected-XI deltas, never by
        # a guessed per-player penalty.
        injury_count = int(
            pd.to_numeric(injuries_raw.get("team_id", pd.Series(dtype=float)), errors="coerce").eq(t).sum()
        )
        suspension_count = int(
            pd.to_numeric(suspensions_raw.get("team_id", pd.Series(dtype=float)), errors="coerce").eq(t).sum()
        )
        availability_unc = min(0.20, 0.025 * injury_count + 0.04 * suspension_count)
        sampling_unc = min(0.35, 1.0 / math.sqrt(max(1.0, n)))
        prior_unc = float(min(
            1.0,
            max(0.02, sampling_unc + float(c["context_uncertainty"]) + promoted_unc + availability_unc)
        ))

        # Penalty opportunity is sparse, so its separate attack/defence signals
        # receive heavy shrinkage and conservative caps. They never contaminate
        # the non-penalty attack/defence strength.
        pen_att_raw = float(_vx_weighted_mean(team_rows["penalty_xg_for"], team_rows["_w"]) / max(0.01, pen_for_league))
        pen_def_raw = float(_vx_weighted_mean(team_rows["penalty_xg_against"], team_rows["_w"]) / max(0.01, pen_against_league))
        pen_att_prior = float(np.clip(_vx_shrink(pen_att_raw, n, 12.0), 0.60, 1.40))
        pen_def_prior = float(np.clip(_vx_shrink(pen_def_raw, n, 12.0), 0.60, 1.40))

        rows.append({
            "team_id": t,
            "prior_attack_overall": overall_att,
            "prior_defence_overall": overall_def,
            "prior_attack_home": ah_t,
            "prior_defence_home": dh_t,
            "prior_attack_away": aa_t,
            "prior_defence_away": da_t,
            "prior_penalty_attack_signal": pen_att_prior,
            "prior_penalty_defence_signal": pen_def_prior,
            "prior_uncertainty": prior_unc,
            "promoted_attack_prior_adjustment": promoted_att,
            "promoted_defence_prior_adjustment": promoted_def,
            "promoted_team_uncertainty": promoted_unc,
            "previous_season_effective_matches": n,
        })

    prior = pd.DataFrame(rows)
    return prior, {
        "league_home_npxg": float(mu_home),
        "league_away_npxg": float(mu_away),
        "league_home_penalty_xg": float(max(0.0, pen_home)),
        "league_away_penalty_xg": float(max(0.0, pen_away)),
    }

def _vx_safe_ratio(value, denom, floor=0.05):
    return float(value) / max(float(floor), float(denom))

def _vx_build_current_signals(match_frame, prior, venue_baselines):
    f = match_frame.loc[match_frame["season"].astype(str).eq(CURRENT_SEASON)].copy()
    team_ids = sorted(set(pd.to_numeric(teams["id"], errors="coerce").dropna().astype(int)))
    p = prior.set_index("team_id")
    anchor = forecast_timestamp or data_snapshot_timestamp or datetime.now(timezone.utc).isoformat()

    if f.empty:
        # Valid preseason state: no current-season matches yet.
        rows = []
        for t in team_ids:
            rows.append({
                "team_id": t,
                "season_attack_signal": 1.0,
                "season_defence_signal": 1.0,
                "season_home_attack_signal": 1.0,
                "season_home_defence_signal": 1.0,
                "season_away_attack_signal": 1.0,
                "season_away_defence_signal": 1.0,
                "season_penalty_attack_signal": 1.0,
                "season_penalty_defence_signal": 1.0,
                "opponent_adjusted_npxg_for": np.nan,
                "opponent_adjusted_npxga": np.nan,
                "recent_form_weight": 0.0,
                "sample_size": 0.0,
                "home_sample_size": 0.0,
                "away_sample_size": 0.0,
                "home_recent_form_weight": 0.0,
                "away_recent_form_weight": 0.0,
            })
        return pd.DataFrame(rows)

    f["match_date"] = pd.to_datetime(f["match_date"], utc=True, errors="coerce")
    if f["match_date"].isna().any():
        raise RuntimeError("Current-season match_date contains invalid rows")
    for c in (
        "team_id","opponent_id","npxg_for","npxga","big_chances_for","big_chances_against",
        "set_piece_xg_for","set_piece_xg_against","penalty_xg_for","penalty_xg_against",
        "red_card_minutes_for","red_card_minutes_against"
    ):
        f[c] = pd.to_numeric(f[c], errors="raise")
    f["team_id"] = f["team_id"].astype(int)
    f["opponent_id"] = f["opponent_id"].astype(int)
    f["venue"] = f["venue"].astype(str).str.upper()
    f["_red_w"] = f.apply(_vx_red_context_weight, axis=1)
    f["_time_w"] = f["match_date"].map(lambda x: _vx_time_decay_weight(x, anchor))
    f["_w"] = f["_red_w"] * f["_time_w"]

    mu_h = float(venue_baselines["league_home_npxg"])
    mu_a = float(venue_baselines["league_away_npxg"])

    # League feature baselines are estimated from the CURRENT raw season only.
    # They normalize unlike units (counts vs xG) before component blending.
    def _league_mean(col):
        val = _vx_weighted_mean(f[col], f["_w"])
        return max(0.05, float(val)) if np.isfinite(val) else 0.05

    bc_for_mu = _league_mean("big_chances_for")
    bc_against_mu = _league_mean("big_chances_against")
    sp_for_mu = _league_mean("set_piece_xg_for")
    sp_against_mu = _league_mean("set_piece_xg_against")
    pen_for_observed = _vx_weighted_mean(f["penalty_xg_for"], f["_w"])
    pen_against_observed = _vx_weighted_mean(f["penalty_xg_against"], f["_w"])
    pen_for_mu = max(0.05, float(pen_for_observed)) if np.isfinite(pen_for_observed) else 0.05
    pen_against_mu = max(0.05, float(pen_against_observed)) if np.isfinite(pen_against_observed) else 0.05
    use_penalty_attack = bool(np.isfinite(pen_for_observed) and pen_for_observed >= 0.03)
    use_penalty_defence = bool(np.isfinite(pen_against_observed) and pen_against_observed >= 0.03)

    def _row_adjusted(row):
        t_opp = int(row["opponent_id"])
        venue = str(row["venue"])
        if venue == "H":
            opp_def = float(p.loc[t_opp, "prior_defence_away"])
            opp_att = float(p.loc[t_opp, "prior_attack_away"])
            mu_for, mu_against = mu_h, mu_a
        else:
            opp_def = float(p.loc[t_opp, "prior_defence_home"])
            opp_att = float(p.loc[t_opp, "prior_attack_home"])
            mu_for, mu_against = mu_a, mu_h
        return pd.Series({
            "_adj_npxg_for": float(row["npxg_for"]) / max(0.20, opp_def),
            "_adj_npxga": float(row["npxga"]) / max(0.20, opp_att),
            "_npxg_att_ratio": _vx_safe_ratio(row["npxg_for"], mu_for * opp_def),
            "_npxg_def_ratio": _vx_safe_ratio(row["npxga"], mu_against * opp_att),
        })

    f = pd.concat([f, f.apply(_row_adjusted, axis=1)], axis=1)

    def _signal_subset(g, team_id):
        if g.empty:
            return {
                "att": 1.0, "def": 1.0, "pen_att": 1.0, "pen_def": 1.0,
                "adj_for": np.nan, "adj_against": np.nan,
                "n_eff": 0.0, "n_matches": 0, "recency_mean": 0.0,
            }
        w = g["_w"]
        n_eff = float(w.sum())
        n_matches = int(len(g))
        recency_mean = float(pd.to_numeric(g["_time_w"], errors="coerce").fillna(0.0).mean())

        # NPxG dominates. Big chances and set-piece xG are secondary process
        # features. Penalties are kept separate, strongly shrunk and capped.
        npxg_att = _vx_weighted_mean(g["_npxg_att_ratio"], w)
        npxg_def = _vx_weighted_mean(g["_npxg_def_ratio"], w)
        bc_att = _vx_safe_ratio(_vx_weighted_mean(g["big_chances_for"], w), bc_for_mu)
        bc_def = _vx_safe_ratio(_vx_weighted_mean(g["big_chances_against"], w), bc_against_mu)
        sp_att = _vx_safe_ratio(_vx_weighted_mean(g["set_piece_xg_for"], w), sp_for_mu)
        sp_def = _vx_safe_ratio(_vx_weighted_mean(g["set_piece_xg_against"], w), sp_against_mu)

        # Penalty opportunity is noisy: shrink 75% toward league average and cap.
        if use_penalty_attack:
            pen_att_raw = _vx_safe_ratio(_vx_weighted_mean(g["penalty_xg_for"], w), pen_for_mu)
            pen_att = float(np.clip(1.0 + 0.25 * (pen_att_raw - 1.0), 0.80, 1.20))
        else:
            pen_att = 1.0
        if use_penalty_defence:
            pen_def_raw = _vx_safe_ratio(_vx_weighted_mean(g["penalty_xg_against"], w), pen_against_mu)
            pen_def = float(np.clip(1.0 + 0.25 * (pen_def_raw - 1.0), 0.80, 1.20))
        else:
            pen_def = 1.0

        def _geom(parts):
            total = 0.0
            for val, weight in parts:
                total += weight * math.log(max(0.20, min(3.0, float(val))))
            return float(math.exp(total))

        # Core team strength is NON-PENALTY process strength. The weights sum
        # to one and penalties remain a separate component.
        attack = _geom(((npxg_att, 0.70), (bc_att, 0.15), (sp_att, 0.15)))
        defence = _geom(((npxg_def, 0.70), (bc_def, 0.15), (sp_def, 0.15)))

        return {
            "att": attack,
            "def": defence,
            "pen_att": pen_att,
            "pen_def": pen_def,
            "adj_for": _vx_weighted_mean(g["_adj_npxg_for"], w),
            "adj_against": _vx_weighted_mean(g["_adj_npxga"], w),
            "n_eff": n_eff,
            "n_matches": n_matches,
            "recency_mean": recency_mean,
        }

    rows = []
    for t in team_ids:
        g = f.loc[f["team_id"].eq(t)]
        gh = g.loc[g["venue"].eq("H")]
        ga = g.loc[g["venue"].eq("A")]
        overall = _signal_subset(g, t)
        home = _signal_subset(gh, t)
        away = _signal_subset(ga, t)

        # Venue-specific signals are estimated with the exact same recency-weighted
        # match evidence, then shrunk toward the overall current-season signal
        # when the venue sample is thin. The PRIOR/CURRENT blend is deliberately
        # NOT done here; Phase 2 owns that update with w = n / (n + 8).
        def _venue_signal(v, o, n_matches):
            venue_share = min(1.0, float(n_matches) / 6.0)
            return float(math.exp(
                venue_share * math.log(max(0.20, v))
                + (1.0 - venue_share) * math.log(max(0.20, o))
            ))

        rows.append({
            "team_id": t,
            "season_attack_signal": overall["att"],
            "season_defence_signal": overall["def"],
            "season_home_attack_signal": _venue_signal(home["att"], overall["att"], home["n_matches"]),
            "season_home_defence_signal": _venue_signal(home["def"], overall["def"], home["n_matches"]),
            "season_away_attack_signal": _venue_signal(away["att"], overall["att"], away["n_matches"]),
            "season_away_defence_signal": _venue_signal(away["def"], overall["def"], away["n_matches"]),
            "season_penalty_attack_signal": float(overall["pen_att"]),
            "season_penalty_defence_signal": float(overall["pen_def"]),
            "opponent_adjusted_npxg_for": overall["adj_for"],
            "opponent_adjusted_npxga": overall["adj_against"],
            "recent_form_weight": overall["recency_mean"],
            "sample_size": overall["n_matches"],
            "home_sample_size": home["n_matches"],
            "away_sample_size": away["n_matches"],
            "home_recent_form_weight": home["recency_mean"],
            "away_recent_form_weight": away["recency_mean"],
            "recency_effective_sample_size": overall["n_eff"],
        })

    return pd.DataFrame(rows)


PHASE1_MATCH_FIELDS = (
    "season",
    "match_date",
    "team_id",
    "opponent_id",
    "venue",
    "npxg_for",
    "npxga",
    "big_chances_for",
    "big_chances_against",
    "set_piece_xg_for",
    "set_piece_xg_against",
    "penalty_xg_for",
    "penalty_xg_against",
    "red_card_minutes_for",
    "red_card_minutes_against",
)
PHASE1_CONTEXT_FIELDS = (
    "team_id",
    "promoted_team",
    "promoted_attack_prior_adjustment",
    "promoted_defence_prior_adjustment",
    "promoted_team_uncertainty",
    "squad_arrivals_attack_delta",
    "squad_arrivals_defence_delta",
    "squad_departures_attack_delta",
    "squad_departures_defence_delta",
    "manager_attack_delta",
    "manager_defence_delta",
    "expected_xi_attack_delta",
    "expected_xi_defence_delta",
    "context_uncertainty",
    "context_complete",
    "context_source",
    "context_source_timestamp",
)
PHASE1_AUTO_PROMOTED_ATTACK_ADJUSTMENT = float(math.log(0.82))
PHASE1_AUTO_PROMOTED_DEFENCE_ADJUSTMENT = float(math.log(1.18))
PHASE1_AUTO_PROMOTED_UNCERTAINTY = 0.30
PHASE1_AUTO_BASE_CONTEXT_UNCERTAINTY = 0.08


def rebuild(boot, official_fixtures, core_root, input_root, now):
    """Reuse the inspected upstream functions, with current-season coverage gates."""
    global teams, PHASE1_FPL_CORE_ROOT, _start_year, CURRENT_SEASON, PREVIOUS_SEASON
    global forecast_timestamp, data_snapshot_timestamp, injuries_raw, suspensions_raw
    global PHASE1_PREVIOUS_SEASON_TEAM_NAMES, PHASE1_CONTINUING_CURRENT_TEAM_IDS
    teams = pd.DataFrame(boot['teams'])
    # Season identity comes from official event deadlines, never the wall-clock year.
    _start_year = min(int(e['deadline_time'][:4]) for e in boot['events'])
    CURRENT_SEASON = f'{_start_year}-{str(_start_year+1)[-2:]}'
    PREVIOUS_SEASON = f'{_start_year-1}-{str(_start_year)[-2:]}'
    forecast_timestamp = data_snapshot_timestamp = now.isoformat()
    PHASE1_FPL_CORE_ROOT = Path(core_root)
    PHASE1_PREVIOUS_SEASON_TEAM_NAMES = []
    PHASE1_CONTINUING_CURRENT_TEAM_IDS = []
    raw, source = _vx_try_build_fpl_core_team_match_raw()
    supplied = Path(input_root)/'team_match_xg_raw.csv'
    if raw is None and supplied.exists():
        raw = pd.read_csv(supplied)
    if raw is None:
        raise RuntimeError('No complete trusted raw match archive or team_match_xg_raw.csv')
    ok, issues = _vx_phase1_validate_match_frame(raw)
    if not ok:
        raise RuntimeError('; '.join(issues))
    current = raw[raw.season.astype(str).eq(CURRENT_SEASON)].copy()
    complete = [f for f in official_fixtures if f.get('finished')]
    coverage = []
    for tid in teams.id.astype(int):
        expected = sum(tid in (f['team_h'],f['team_a']) for f in complete)
        actual = int(current.team_id.eq(tid).sum())
        coverage.append({'team_id':int(tid),'team':str(teams.loc[teams.id.astype(int).eq(tid),'name'].iloc[0]),
                         'raw_matches':actual,'official_completed_matches':expected,'complete':actual==expected})
    report = {'season':CURRENT_SEASON,'checked_at':now.isoformat(),'archive_root':str(PHASE1_FPL_CORE_ROOT),
              'current_season_rows':len(current),'teams':coverage,'missing_fixture_identities':[]}
    report_path = Path(input_root)/'fdr_coverage_report.json'
    report_path.parent.mkdir(parents=True,exist_ok=True)
    # Prove opponent/venue/date identity, rather than just the number of rows.
    for f in complete:
        for home in (True,False):
            tid=f['team_h'] if home else f['team_a'];opp=f['team_a'] if home else f['team_h']
            rows=current[current.team_id.eq(tid)&current.opponent_id.eq(opp)&current.venue.eq('H' if home else 'A')]
            dates=pd.to_datetime(rows.match_date,utc=True,errors='coerce')
            kickoff=pd.Timestamp(f['kickoff_time'])
            count = int(((dates-kickoff).abs().dt.total_seconds()<86400).sum())
            if count != 1:
                report['missing_fixture_identities'].append({'fixture_id':int(f['id']),'team_id':int(tid),
                    'opponent_id':int(opp),'venue':'H' if home else 'A','matching_raw_rows':count})
    report['passed'] = all(t['complete'] for t in coverage) and not report['missing_fixture_identities']
    report_path.write_text(json.dumps(report,indent=2),encoding='utf-8')
    if not report['passed']:
        gaps = [f"{t['team']} {t['raw_matches']}/{t['official_completed_matches']}" for t in coverage if not t['complete']]
        reason = 'Current-season coverage gaps: '+', '.join(gaps) if gaps else 'Current-season fixture identity gaps'
        raise RuntimeError(reason+f"; {len(report['missing_fixture_identities'])} unresolved fixture/team rows. Details: {report_path}")
    if (pd.to_datetime(raw.match_date,utc=True)>pd.Timestamp(now)).any():
        raise RuntimeError('Future match evidence cannot enter a pre-deadline forecast')
    context_path=Path(input_root)/'team_context_raw.csv'
    ctx=pd.read_csv(context_path) if context_path.exists() else None
    if ctx is None or _vx_context_is_untouched_template(ctx):
        ctx, reason=_vx_auto_context_from_match_evidence(raw)
        if ctx is None:raise RuntimeError(reason)
    ok,issues=_vx_phase1_validate_context(ctx)
    if not ok:raise RuntimeError('; '.join(issues))
    flagged=pd.DataFrame(boot['elements'])
    injuries_raw=flagged[flagged.status.isin(['i','d'])].rename(columns={'team':'team_id'})
    suspensions_raw=flagged[flagged.status.eq('s')].rename(columns={'team':'team_id'})
    prior,baselines=_vx_build_prior(raw,ctx)
    signals=_vx_build_current_signals(raw,prior,baselines).set_index('team_id')
    prior=prior.set_index('team_id');strength={}
    names={'attack_home':'season_home_attack_signal','defence_home':'season_home_defence_signal',
           'attack_away':'season_away_attack_signal','defence_away':'season_away_defence_signal',
           'penalty_attack_signal':'season_penalty_attack_signal','penalty_defence_signal':'season_penalty_defence_signal'}
    for tid in teams.id.astype(int):
        n=int(current.team_id.eq(tid).sum());w=vx_phase2_current_weight(n)
        strength[tid]={k:(1-w)*float(prior.loc[tid,'prior_'+k])+w*float(signals.loc[tid,v]) for k,v in names.items()}
    out=[]
    for f in official_fixtures:
        if f.get('finished') or f.get('event') is None:continue
        h,a=f['team_h'],f['team_a'];hs,as_=strength[h],strength[a]
        deltas={h:(0.,0.,0.),a:(0.,0.,0.)}
        # Only explicit sourced, pre-deadline overrides affect strength. Empty template is neutral.
        news_path=Path(input_root)/'team_news_overrides.csv'
        if news_path.exists():
            news=pd.read_csv(news_path)
            for tid,home in ((h,True),(a,False)):
                hit=news[news.fixture_id.eq(f['id'])&news.team_id.eq(tid)]
                if len(hit)>1:raise RuntimeError('Duplicate team-news override')
                if hit.empty or not _vx_bool(hit.iloc[0].get('override_active')):continue
                r=hit.iloc[0]
                if not r.get('source_name') or not r.get('reason') or not _vx_bool(r.get('is_pre_deadline_data')):
                    raise RuntimeError('Active team-news override lacks provenance')
                ts=pd.Timestamp(r.get('source_timestamp'))
                if ts.tzinfo is None or ts>pd.Timestamp(now) or (pd.Timestamp(now)-ts).total_seconds()>21600:
                    raise RuntimeError('Active team-news override stale or from the future')
                # Original Phase 2 semantics: net strength helps attack and reduces weakness.
                net=sum(float(r.get(k,0) or 0) for k in ('manager_change_adjustment','rest_days_adjustment','lineup_confidence_adjustment'))
                att=float(r.get('attack_injury_adjustment',0) or 0)+net
                defend=float(r.get('defence_injury_adjustment',0) or 0)+float(r.get('goalkeeper_adjustment',0) or 0)-net
                pen=float(r.get('penalty_taker_adjustment',0) or 0)
                if any(not np.isfinite(v) or abs(v)>.5 for v in (att,defend,pen)):
                    raise RuntimeError('Invalid team-news strength delta')
                deltas[tid]=(att,defend,pen)
        ha,hd,hp=deltas[h];aa,ad,ap=deltas[a]
        hc=ha+ad;ac=aa+hd
        lh=baselines['league_home_npxg']*hs['attack_home']*as_['defence_away']*math.exp(hc)+baselines['league_home_penalty_xg']*hs['penalty_attack_signal']*as_['penalty_defence_signal']*math.exp(hc+hp)
        la=baselines['league_away_npxg']*as_['attack_away']*hs['defence_home']*math.exp(ac)+baselines['league_away_penalty_xg']*as_['penalty_attack_signal']*hs['penalty_defence_signal']*math.exp(ac+ap)
        out.append({'fixture_id':f['id'],'gameweek':f['event'],'home_team_id':h,'away_team_id':a,
                    'model_lambda_home':lh,'model_lambda_away':la,
                    # Additional provenance fields for the existing weekly schema.
                    # The WC/FH lambda equations above remain unchanged.
                    'model_lambda_home_nonpenalty':baselines['league_home_npxg']*hs['attack_home']*as_['defence_away']*math.exp(hc),
                    'model_lambda_away_nonpenalty':baselines['league_away_npxg']*as_['attack_away']*hs['defence_home']*math.exp(ac),
                    'model_lambda_home_penalty':baselines['league_home_penalty_xg']*hs['penalty_attack_signal']*as_['penalty_defence_signal']*math.exp(hc+hp),
                    'model_lambda_away_penalty':baselines['league_away_penalty_xg']*as_['penalty_attack_signal']*hs['penalty_defence_signal']*math.exp(ac+ap),
                    'league_home_scoring_baseline':baselines['league_home_npxg']+baselines['league_home_penalty_xg'],
                    'league_away_scoring_baseline':baselines['league_away_npxg']+baselines['league_away_penalty_xg'],
                    'league_home_nonpenalty_baseline':baselines['league_home_npxg'],
                    'league_away_nonpenalty_baseline':baselines['league_away_npxg'],
                    'league_home_penalty_baseline':baselines['league_home_penalty_xg'],
                    'league_away_penalty_baseline':baselines['league_away_penalty_xg'],
                    'home_attack_strength':hs['attack_home'],'away_defensive_weakness':as_['defence_away'],
                    'away_attack_strength':as_['attack_away'],'home_defensive_weakness':hs['defence_home'],
                    'home_penalty_attack_signal':hs['penalty_attack_signal'],'away_penalty_defence_signal':as_['penalty_defence_signal'],
                    'away_penalty_attack_signal':as_['penalty_attack_signal'],'home_penalty_defence_signal':hs['penalty_defence_signal'],
                    'context_home_multiplier':math.exp(hc),'context_away_multiplier':math.exp(ac),
                    'context_home_penalty_multiplier':math.exp(hc+hp),'context_away_penalty_multiplier':math.exp(ac+ap),
                    'home_clean_sheet_probability':math.exp(-la),'away_clean_sheet_probability':math.exp(-lh),
                    'data_snapshot_timestamp':now.isoformat(),'source_name':'Day 3 Phase 1–4 equations; current coverage verified'})
    return out

_PHASE1_CONTEXT_NUMERIC_FIELDS = (
    "promoted_attack_prior_adjustment",
    "promoted_defence_prior_adjustment",
    "promoted_team_uncertainty",
    "squad_arrivals_attack_delta",
    "squad_arrivals_defence_delta",
    "squad_departures_attack_delta",
    "squad_departures_defence_delta",
    "manager_attack_delta",
    "manager_defence_delta",
    "expected_xi_attack_delta",
    "expected_xi_defence_delta",
    "context_uncertainty",
)



def vx_phase2_current_weight(n):
    n = int(n)
    if n < 0:
        raise ValueError("completed match count cannot be negative")
    return float(n / (n + 8.0)) if n else 0.0

def _vx_phase2_linear_blend(prior_value, signal_value, n):
    """Exact arithmetic blend required by the Phase-2 contract."""
    p = float(prior_value)
    s = float(signal_value)
    if not np.isfinite(p) or not np.isfinite(s) or p <= 0 or s <= 0:
        raise RuntimeError(f"Invalid strength inputs prior={p}, signal={s}")
    w = vx_phase2_current_weight(n)
    return float((1.0 - w) * p + w * s)


def _vx_phase4_clip_fdr(value):
    value = float(value)
    if not np.isfinite(value):
        raise RuntimeError(f"Non-finite FDR value: {value}")
    return float(min(5.0, max(1.0, value)))


def vx_phase4_attack_fdr(lambda_for):
    """
    Continuous attack difficulty. Lower = easier attacking fixture.
    Formula requested for V1; output boundary-clipped to the defined 1..5 scale.
    """
    lam = float(lambda_for)
    if not np.isfinite(lam) or lam <= 0:
        raise RuntimeError(f"Attack FDR requires finite positive lambda, got {lam}")
    raw = 1.0 + 4.0 * (3.2 - lam) / 2.8
    return _vx_phase4_clip_fdr(raw)


def vx_phase4_defence_fdr(clean_sheet_probability):
    """
    Continuous defensive difficulty. Lower = easier clean-sheet environment.
    """
    p_cs = float(clean_sheet_probability)
    if not np.isfinite(p_cs) or not 0.0 <= p_cs <= 1.0:
        raise RuntimeError(f"Defence FDR requires CS probability in [0,1], got {p_cs}")
    easy_cs = math.exp(-0.4)
    hard_cs = math.exp(-3.2)
    raw = 1.0 + 4.0 * (easy_cs - p_cs) / (easy_cs - hard_cs)
    return _vx_phase4_clip_fdr(raw)


def vx_phase4_fdr_colour_band(fdr_value):
    """Classify the full FDR value; rounding is only for displayed text."""
    value = float(fdr_value)
    if not np.isfinite(value) or not 0.0 <= value <= 5.0:
        raise RuntimeError(f"FDR colour band requires value in [0,5], got {value}")
    if value < 2.5:
        return "Green"
    if value < 3.0:
        return "Blue"
    if value < 4.0:
        return "Grey"
    return "Red"

PHASE4_FDR_STYLE_BY_CLASS = {'fdr-1': {'gradient': ('#9BF3C0', '#35C978'), 'text': '#000000'}, 'fdr-2': {'gradient': ('#8BE3FF', '#399CE6'), 'text': '#000000'}, 'fdr-3': {'gradient': ('#D4DFEC', '#9BAEC3'), 'text': '#000000'}, 'fdr-4': {'gradient': ('#FF6573', '#AE102D'), 'text': '#FFFFFF'}, 'fdr-5': {'gradient': ('#FF6573', '#AE102D'), 'text': '#FFFFFF'}}

CANONICAL_MODEL_VERSION = "VORTEX-V1-PHASE4-POISSON-CS-FDR"

def day3_fdr_style(value):
    """Return DAY-3's precise four-band gradient and text colour contract."""
    band = vx_phase4_fdr_colour_band(value)
    class_name = {"Green":"fdr-1","Blue":"fdr-2","Grey":"fdr-3","Red":"fdr-5"}[band]
    return {"band": band, "class_name": class_name, **PHASE4_FDR_STYLE_BY_CLASS[class_name]}
