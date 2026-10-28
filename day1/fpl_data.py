
from __future__ import annotations

from typing import Any
import copy
import requests
import pandas as pd
import time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

FPL_API_BASE = "https://fantasy.premierleague.com/api"

# Run-wide immutable FPL API snapshot. Cell 2 rewrites/reloads this module once at
# the start of every Run all, so this cache is automatically fresh for each run.
# The first response for each official endpoint is locked and every later caller
# receives a deep copy of that exact payload.
_VX_RUN_JSON_CACHE: dict[str, Any] = {}


def _vx_http_session() -> requests.Session:
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=0.6,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("https://", adapter)
    session.headers.update({
        "User-Agent": "FPL-VORTEX/2.0",
        "Accept": "application/json",
    })
    return session


def _vx_get_json(session: requests.Session, path: str) -> Any:
    # One Run all = one immutable official FPL snapshot per endpoint. The first
    # request is forced fresh; every later request in this runtime reuses it.
    cache_key = str(path)
    if cache_key in _VX_RUN_JSON_CACHE:
        return copy.deepcopy(_VX_RUN_JSON_CACHE[cache_key])

    sep = "&" if "?" in path else "?"
    url = f"{FPL_API_BASE}{path}{sep}_vx={time.time_ns()}"
    response = session.get(
        url,
        timeout=30,
        headers={"Cache-Control": "no-cache, no-store", "Pragma": "no-cache"},
    )
    response.raise_for_status()
    payload = response.json()
    _VX_RUN_JSON_CACHE[cache_key] = copy.deepcopy(payload)
    return copy.deepcopy(payload)


def _vx_sanitize_fixture_rows(rows):
    # Provider-owned difficulty labels are discarded at the ingestion boundary.
    banned_keys = ("team_h_" + "difficulty", "team_a_" + "difficulty")
    clean = []
    for item in rows or []:
        row = dict(item or {})
        for key in banned_keys:
            row.pop(key, None)
        clean.append(row)
    return clean


def _vx_require_columns(frame: pd.DataFrame, required: set[str], label: str) -> None:
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"{label} missing required columns: {missing}")


def fetch_fpl_data() -> dict[str, Any]:
    # ONE canonical bootstrap/fixtures snapshot for the notebook.
    session = _vx_http_session()
    bootstrap = _vx_get_json(session, "/bootstrap-static/")
    fixture_rows = _vx_sanitize_fixture_rows(_vx_get_json(session, "/fixtures/"))

    players = pd.DataFrame(bootstrap["elements"]).copy()
    teams = pd.DataFrame(bootstrap["teams"]).copy()
    events = pd.DataFrame(bootstrap["events"]).copy()
    element_types = pd.DataFrame(bootstrap.get("element_types", [])).copy()
    fixtures = pd.DataFrame(fixture_rows).copy()

    _vx_require_columns(players, {"id", "team", "element_type", "now_cost"}, "players")
    _vx_require_columns(teams, {"id", "name", "short_name"}, "teams")
    _vx_require_columns(
        events,
        {"id", "deadline_time", "is_previous", "is_current", "is_next", "finished", "data_checked"},
        "events",
    )
    _vx_require_columns(
        fixtures,
        {
            "id", "team_h", "team_a", "event", "started", "minutes",
            "finished", "finished_provisional", "team_h_score", "team_a_score",
        },
        "fixtures",
    )

    if players["id"].duplicated().any():
        raise ValueError("Duplicate FPL player IDs found")
    if teams["id"].duplicated().any():
        raise ValueError("Duplicate FPL team IDs found")
    if fixtures["id"].duplicated().any():
        raise ValueError("Duplicate FPL fixture IDs found")

    valid_team_ids = set(teams["id"].astype(int).tolist())
    referenced_team_ids = set(fixtures["team_h"].dropna().astype(int)) | set(fixtures["team_a"].dropna().astype(int))
    unknown = referenced_team_ids - valid_team_ids
    if unknown:
        raise ValueError(f"Fixtures reference unknown teams: {sorted(unknown)}")

    team_name_map = teams.set_index("id")["name"].to_dict()
    team_short_map = teams.set_index("id")["short_name"].to_dict()

    if not element_types.empty and {"id", "singular_name_short"}.issubset(element_types.columns):
        position_map = element_types.set_index("id")["singular_name_short"].to_dict()
    else:
        position_map = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}

    position_map = {
        int(k): ("GK" if str(v).upper() == "GKP" else str(v).upper())
        for k, v in position_map.items()
    }

    players["team_name"] = players["team"].map(team_name_map)
    players["team_short"] = players["team"].map(team_short_map)
    players["price"] = pd.to_numeric(players["now_cost"], errors="coerce") / 10.0
    players["position"] = players["element_type"].map(position_map)

    # ------------------------------------------------------------------
    # ONE CANONICAL OFFICIAL STATUS CONTRACT
    # ------------------------------------------------------------------
    # The live FPL payload can pass through short transition windows where
    # event flags and fixture flags update at different moments. No single flag
    # is accepted as proof of completion. Every completed fixture must satisfy
    # all four pieces of provider evidence already present in /fixtures/:
    #   1) started == True
    #   2) minutes >= 90
    #   3) finished OR finished_provisional
    #   4) both final-score fields are present
    # A review candidate needs a terminal lifecycle signal (finished,
    # data_checked, or is_previous) AND every fixture in that event must
    # satisfy the full fixture contract above. "finished" identifies completed
    # fixtures; it does NOT mean FPL has locked the Gameweek points. In 2026/27,
    # final scoring is locked at 09:00 UK time on the day after its last match.
    def _flag(frame: pd.DataFrame, column: str) -> pd.Series:
        if column not in frame.columns:
            raise ValueError(f"Official FPL payload missing required flag: {column}")
        return frame[column].fillna(False).astype(bool)

    event_finished_signal = _flag(events, "finished")
    event_checked_signal = _flag(events, "data_checked")
    event_previous_signal = _flag(events, "is_previous")
    event_current_signal = _flag(events, "is_current")
    event_next_signal = _flag(events, "is_next")

    fixture_started_signal = _flag(fixtures, "started")
    fixture_finished_signal = _flag(fixtures, "finished")
    fixture_provisional_signal = _flag(fixtures, "finished_provisional")
    fixture_minutes = pd.to_numeric(fixtures["minutes"], errors="coerce").fillna(0.0)
    fixture_minutes_complete = fixture_minutes.ge(90.0)
    fixture_has_score = fixtures["team_h_score"].notna() & fixtures["team_a_score"].notna()
    fixture_status_complete = fixture_finished_signal | fixture_provisional_signal
    fixture_complete = (
        fixture_started_signal
        & fixture_minutes_complete
        & fixture_status_complete
        & fixture_has_score
    )

    # Persist the atomic fixture checks so downstream cells consume the same
    # answer and never reimplement status logic locally.
    fixtures["vx_started"] = fixture_started_signal
    fixtures["vx_minutes_complete"] = fixture_minutes_complete
    fixtures["vx_status_complete"] = fixture_status_complete
    fixtures["vx_score_complete"] = fixture_has_score
    fixtures["vx_completed"] = fixture_complete

    fixture_completion_by_gw: dict[int, bool] = {}
    fixture_counts_by_gw: dict[int, int] = {}
    fixture_state_counts_by_gw: dict[int, dict[str, int]] = {}
    fixture_rows_with_event = fixtures.loc[fixtures["event"].notna()].copy()

    for gw_value, gw_rows in fixture_rows_with_event.groupby("event"):
        gw = int(gw_value)
        idx = gw_rows.index
        fixture_counts_by_gw[gw] = int(len(gw_rows))
        fixture_completion_by_gw[gw] = bool(
            len(gw_rows) > 0 and fixtures.loc[idx, "vx_completed"].all()
        )
        fixture_state_counts_by_gw[gw] = {
            "fixtures": int(len(gw_rows)),
            "started": int(fixtures.loc[idx, "vx_started"].sum()),
            "minutes_90_plus": int(fixtures.loc[idx, "vx_minutes_complete"].sum()),
            "status_complete": int(fixtures.loc[idx, "vx_status_complete"].sum()),
            "scores_present": int(fixtures.loc[idx, "vx_score_complete"].sum()),
            "completed": int(fixtures.loc[idx, "vx_completed"].sum()),
        }

    event_finished_gws = set(events.loc[event_finished_signal, "id"].astype(int).tolist())
    event_data_checked_gws = set(events.loc[event_checked_signal, "id"].astype(int).tolist())
    event_previous_gws = set(events.loc[event_previous_signal, "id"].astype(int).tolist())
    event_current_gws = set(events.loc[event_current_signal, "id"].astype(int).tolist())
    event_terminal_gws = event_finished_gws | event_data_checked_gws | event_previous_gws
    # data_checked is the official FPL score-lock signal. is_previous only
    # identifies the prior event and can change before the 09:00 UK score lock.
    event_scores_locked_gws = event_data_checked_gws
    fixture_finished_gws = {gw for gw, done in fixture_completion_by_gw.items() if done}

    # ------------------------------------------------------------------
    # TRANSITIONAL CURRENT-GW PATH
    # ------------------------------------------------------------------
    # The live FPL API can sit in a legitimate transitional state where the
    # just-completed Gameweek is still flagged is_current=True — finished,
    # data_checked and is_previous all still False — while the following
    # Gameweek has already become is_next=True. event_terminal_gws alone
    # cannot see a GW in this state, even when every one of its fixtures has
    # actually finished.
    #
    # Recognise that state as a second, independently-verified route into
    # review eligibility, gated on:
    #   1) event.is_current is True
    #   2) the event's own official deadline has already passed (so an
    #      upcoming GW mislabelled early can never qualify)
    #   3) the event has at least one fixture on record
    #   4) every fixture belonging to that event satisfies the existing
    #      fixture-evidence contract above (started, 90+ minutes, finished
    #      OR finished_provisional, both scores present)
    # This never widens the fixture-evidence contract itself and never
    # touches the terminal-flag route below — it only adds one more way to
    # reach the same review_ready_gws set once fixture evidence agrees.
    event_deadline_series = pd.to_datetime(events["deadline_time"], errors="coerce", utc=True)
    event_deadline_passed_signal = event_deadline_series.notna() & event_deadline_series.le(
        pd.Timestamp.now(tz="UTC")
    )
    transitional_current_gws = {
        gw for gw in set(
            events.loc[event_current_signal & event_deadline_passed_signal, "id"].astype(int).tolist()
        )
        if fixture_counts_by_gw.get(gw, 0) > 0 and fixture_completion_by_gw.get(gw, False)
    }

    review_eligible_gws = event_terminal_gws | transitional_current_gws

    review_ready_gws = sorted(
        int(gw)
        for gw in review_eligible_gws
        if fixture_completion_by_gw.get(int(gw), False)
    )
    latest_completed_gw = max(review_ready_gws) if review_ready_gws else None
    events["vx_review_ready"] = pd.to_numeric(events["id"], errors="coerce").isin(review_ready_gws)

    # ------------------------------------------------------------------
    # AUTO REVIEW GAMEWEEK — FIRST VERIFIED RESULT, THEN FINAL
    # ------------------------------------------------------------------
    # The forward analysis follows FPL's official is_next pointer. The review
    # follows the official is_current event as soon as ONE fixture has passed
    # the same strict fixture-completion contract used above. Until that first
    # result exists, retain the latest fully completed review. This never uses
    # NEXT_GW - 1, a fixed Gameweek number, or calendar arithmetic.
    current_review_gws_with_results = sorted(
        int(gw)
        for gw in event_current_gws
        if int(
            fixture_state_counts_by_gw.get(int(gw), {}).get("completed", 0)
        ) >= 1
    )
    if len(current_review_gws_with_results) > 1:
        raise RuntimeError(
            "Official FPL payload contains multiple current events with completed "
            "fixtures; refusing to guess REVIEW_GW."
        )

    current_review_gw = (
        current_review_gws_with_results[0]
        if current_review_gws_with_results
        else None
    )
    review_gw = (
        int(current_review_gw)
        if current_review_gw is not None
        else latest_completed_gw
    )
    if review_gw is None:
        review_status = None
        review_fixture_state: dict[str, int] = {}
    else:
        review_status = (
            "FINAL"
            if (
                int(review_gw) in event_scores_locked_gws
                and fixture_completion_by_gw.get(int(review_gw), False)
            )
            else "LIVE/PARTIAL"
        )
        review_fixture_state = dict(
            fixture_state_counts_by_gw.get(int(review_gw), {})
        )

    completion_source_by_gw: dict[int, list[str]] = {}
    for gw in review_ready_gws:
        sources: list[str] = []
        if gw in event_finished_gws:
            sources.append("event.finished")
        if gw in event_data_checked_gws:
            sources.append("event.data_checked")
        if gw in event_previous_gws:
            sources.append("event.is_previous")
        if gw in transitional_current_gws:
            sources.append("event.is_current+deadline_passed")
        sources.append("fixtures.started+90m+status+scores")
        completion_source_by_gw[int(gw)] = sources

    # ------------------------------------------------------------------
    # NEXT GAMEWEEK — OFFICIAL POINTER FIRST, DEADLINE-ONLY TRANSITION
    # ------------------------------------------------------------------
    # Prefer FPL's unique is_next row. During a short provider transition where
    # is_next is temporarily absent, use only the earliest future official
    # deadline. If neither exists, stop instead of guessing max(event) or any
    # fixed Gameweek number.
    next_rows = events.loc[event_next_signal].copy()
    if len(next_rows) > 1:
        raise RuntimeError(
            "Official FPL payload contains multiple is_next events; refusing to guess NEXT_GW."
        )

    if len(next_rows) == 1:
        next_gw = int(next_rows.iloc[0]["id"])
        next_gw_source = "event.is_next"
    else:
        deadline_series = pd.to_datetime(events["deadline_time"], errors="coerce", utc=True)
        now_utc = pd.Timestamp.now(tz="UTC")
        future_mask = deadline_series.notna() & deadline_series.gt(now_utc)
        future_events = events.loc[future_mask].copy()
        if future_events.empty:
            raise RuntimeError(
                "Official FPL payload has no is_next event and no future deadline. "
                "NEXT_GW cannot be resolved without guessing."
            )
        future_events["_vx_deadline"] = deadline_series.loc[future_events.index]
        future_events = future_events.sort_values(["_vx_deadline", "id"])
        next_gw = int(future_events.iloc[0]["id"])
        next_gw_source = "earliest_future_official_deadline"

    if next_gw in set(review_ready_gws):
        raise RuntimeError(
            f"Official FPL status contradiction: NEXT_GW={next_gw} is already review-ready."
        )

    return {
        "bootstrap": bootstrap,
        "players": players,
        "teams": teams,
        "events": events,
        "element_types": element_types,
        "fixtures": fixtures,
        "next_gw": next_gw,
        "next_gw_source": next_gw_source,
        "latest_completed_gw": latest_completed_gw,
        "review_gw": review_gw,
        "review_status": review_status,
        "review_fixture_state": review_fixture_state,
        "review_ready_gws": review_ready_gws,
        "completion_source_by_gw": completion_source_by_gw,
        "event_finished_gws": sorted(event_finished_gws),
        "event_data_checked_gws": sorted(event_data_checked_gws),
        "event_previous_gws": sorted(event_previous_gws),
        "event_current_gws": sorted(event_current_gws),
        "event_terminal_gws": sorted(event_terminal_gws),
        "transitional_current_gws": sorted(transitional_current_gws),
        "fixture_finished_gws": sorted(fixture_finished_gws),
        "fixture_completion_by_gw": fixture_completion_by_gw,
        "fixture_counts_by_gw": fixture_counts_by_gw,
        "fixture_state_counts_by_gw": fixture_state_counts_by_gw,
        "team_name_map": team_name_map,
        "team_short_map": team_short_map,
        "position_map": position_map,
    }


def fetch_gw_review_snapshot(
    entry_id: int,
    review_gw: int,
    *,
    bootstrap: dict[str, Any] | None = None,
    fixtures: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    # ONE immutable entry-specific GW Review snapshot.
    # Reuses the canonical bootstrap/full fixture snapshot when supplied,
    # so P9/P10 never refetch those endpoints.
    entry_id = int(entry_id)
    review_gw = int(review_gw)
    if entry_id <= 0:
        raise ValueError("entry_id must be positive")
    if not 1 <= review_gw <= 38:
        raise ValueError("review_gw must be in 1..38")

    session = _vx_http_session()
    if bootstrap is None:
        bootstrap = _vx_get_json(session, "/bootstrap-static/")
    if fixtures is None:
        fixtures = _vx_sanitize_fixture_rows(_vx_get_json(session, "/fixtures/"))

    return {
        "entry_id": entry_id,
        "gw": review_gw,
        "bootstrap": bootstrap,
        "entry": _vx_get_json(session, f"/entry/{entry_id}/"),
        "history": _vx_get_json(session, f"/entry/{entry_id}/history/"),
        "picks": _vx_get_json(session, f"/entry/{entry_id}/event/{review_gw}/picks/"),
        "live": _vx_get_json(session, f"/event/{review_gw}/live/"),
        "fixtures": fixtures,
    }


def fetch_event_live(event_id: int, *, snapshot_path: str | None = None) -> dict[str, Any]:
    """Fetch one fresh official FPL event-live payload through the canonical retry session.

    Persistent files are write-through historical snapshots only. They are never
    read as a substitute for the live FPL endpoint, so a manual Day 1 run cannot
    inherit a partially-settled Gameweek from an earlier run.
    """
    event_id = int(event_id)
    if not 1 <= event_id <= 38:
        raise ValueError("event_id must be in 1..38")

    session = _vx_http_session()
    api_path = f"/event/{event_id}/live/"

    # A previous caller in THIS run may already have read event-live while FPL
    # was still settling. Remove only this endpoint from the run cache, then
    # force a new no-cache HTTP request via _vx_get_json.
    _VX_RUN_JSON_CACHE.pop(api_path, None)
    payload = _vx_get_json(session, api_path)

    if snapshot_path:
        from pathlib import Path
        import json

        snapshot = Path(snapshot_path)
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        temporary = snapshot.with_name(f".{snapshot.name}.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )
        temporary.replace(snapshot)

    return payload


def fetch_recent_player_match_snapshot(
    events,
    *,
    lookback_gws: int = 6,
    snapshot_dir: str | None = None,
) -> pd.DataFrame:
    """Return completed historical player-Gameweek raw statistics from fresh official event-live.

    Only review-ready gameweeks are used. Optional persistent files are refreshed
    from the API on every call and are never used as an input cache.
    """
    frame = events.copy() if isinstance(events, pd.DataFrame) else pd.DataFrame(events)
    if frame.empty or "id" not in frame.columns:
        return pd.DataFrame()

    if "vx_review_ready" not in frame.columns:
        raise RuntimeError(
            "fetch_recent_player_match_snapshot requires canonical events.vx_review_ready; "
            "run fetch_fpl_data() from this module first."
        )
    completed = frame.loc[frame["vx_review_ready"].fillna(False).astype(bool)].copy()

    if completed.empty:
        return pd.DataFrame()

    completed["id"] = pd.to_numeric(completed["id"], errors="coerce")
    completed = completed.dropna(subset=["id"]).sort_values("id")
    gws = completed["id"].astype(int).tolist()[-max(1, int(lookback_gws)):]

    rows: list[dict[str, Any]] = []
    snapshot_root = None
    if snapshot_dir:
        from pathlib import Path
        snapshot_root = Path(snapshot_dir)
        snapshot_root.mkdir(parents=True, exist_ok=True)

    for gw in gws:
        snapshot_path = (
            str(snapshot_root / f"gw_{gw:02d}_live.json")
            if snapshot_root
            else None
        )
        payload = fetch_event_live(gw, snapshot_path=snapshot_path)
        for element in payload.get("elements", []):
            stats = dict(element.get("stats") or {})
            rows.append({
                "event": int(gw),
                "player_id": int(element.get("id") or 0),
                **stats,
            })

    result = pd.DataFrame(rows)
    if not result.empty:
        result = result.loc[result["player_id"] > 0].sort_values(["player_id", "event"]).reset_index(drop=True)
    return result

