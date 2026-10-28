# P9 soccer-pitch slide and P10 narration both consume GW_REVIEW.
# Bootstrap + fixtures come ONLY from the canonical FPL snapshot loaded above.
# Review GW is fully automatic; no hard-coded GW and no NEXT_GW-1 arithmetic.
# ============================================================

import json
from pathlib import Path
import numpy as np
import pandas as pd
from day1.fpl_data import fetch_gw_review_snapshot

TEAM_ID_LOCAL = int(
    globals().get("FPL_TEAM_ID", 0)
    or globals().get("TEAM_ID", 0)
    or globals().get("ENTRY_ID", 0)
    or 0
)
if TEAM_ID_LOCAL <= 0:
    raise RuntimeError("FPL_TEAM_ID is missing. Set it in Cell 0.")

# A reused Colab runtime can retain last week's globals. Clear only the old
# review handoff, then rebuild it from THIS run's canonical FPL snapshot.
for _stale_review_name in (
    "GW_REVIEW", "GW_REVIEW_PACKAGE", "review_package",
    "GW_REVIEW_STATUS", "GW_REVIEW_FIXTURE_STATE", "GW_REVIEW_AVAILABLE",
):
    globals().pop(_stale_review_name, None)

_resolved_review_gw = data.get("review_gw")
if _resolved_review_gw is None:
    _events_diag = []
    _events_frame = data.get("events")
    if isinstance(_events_frame, pd.DataFrame) and not _events_frame.empty:
        _diag_cols = [
            c for c in (
                "id", "name", "is_previous", "is_current", "is_next",
                "finished", "data_checked", "vx_review_ready"
            ) if c in _events_frame.columns
        ]
        _events_diag = _events_frame[_diag_cols].head(4).to_dict(orient="records")
    raise RuntimeError(
        "Canonical FPL data could not resolve a current or completed review Gameweek. "
        "Run Cells 2 and 3 again to refresh the official API snapshot. "
        f"Event diagnostics: {_events_diag}"
    )

REVIEW_GW = int(_resolved_review_gw)
if not 1 <= REVIEW_GW <= 38:
    raise RuntimeError(f"Resolved invalid REVIEW_GW={REVIEW_GW}")

GW_REVIEW_STATUS = str(data.get("review_status") or "FINAL").upper()
if GW_REVIEW_STATUS not in {"FINAL", "LIVE/PARTIAL"}:
    raise RuntimeError(f"Resolved invalid GW_REVIEW_STATUS={GW_REVIEW_STATUS!r}")
GW_REVIEW_FIXTURE_STATE = dict(data.get("review_fixture_state") or {})

# A review can be marked FINAL only after FPL's official data_checked score-lock signal
# and a consistent entry-feed reconciliation. Before lock, completed fixtures remain
# provisional because player points, automatic substitutions and ranks can change.
# No score, rank, Gameweek or chip is hard-coded.
_review_fixture_total = int(GW_REVIEW_FIXTURE_STATE.get("fixtures", 0) or 0)
_review_fixture_completed = int(GW_REVIEW_FIXTURE_STATE.get("completed", 0) or 0)
_review_all_fixtures_complete = (
    _review_fixture_total > 0
    and _review_fixture_completed == _review_fixture_total
)
_review_event_row = next(
    (
        row for row in data["bootstrap"].get("events", [])
        if int(row.get("id") or 0) == REVIEW_GW
    ),
    {},
)
_review_official_scores_locked = bool(_review_event_row.get("data_checked"))


def _vx_review_clear_entry_cache():
    _run_cache = getattr(_fpl_module, "_VX_RUN_JSON_CACHE", None)
    if not isinstance(_run_cache, dict):
        return
    for _path in (
        f"/entry/{TEAM_ID_LOCAL}/",
        f"/entry/{TEAM_ID_LOCAL}/history/",
        f"/entry/{TEAM_ID_LOCAL}/event/{REVIEW_GW}/picks/",
        f"/event/{REVIEW_GW}/live/",
    ):
        _run_cache.pop(_path, None)


def _vx_review_fetch_snapshot(*, fresh=False):
    if fresh:
        _vx_review_clear_entry_cache()
    return fetch_gw_review_snapshot(
        entry_id=TEAM_ID_LOCAL,
        review_gw=REVIEW_GW,
        bootstrap=data["bootstrap"],
        fixtures=data["fixtures"].to_dict(orient="records"),
    )


def _vx_review_validate_snapshot(_snapshot):
    _picks_payload = _snapshot.get("picks") or {}
    _history_payload = _snapshot.get("history") or {}
    _entry_payload = _snapshot.get("entry") or {}
    _live_payload = _snapshot.get("live") or {}
    _entry_history = _picks_payload.get("entry_history") or {}
    _entry_event = _entry_history.get("event")
    _history_rows = list(_history_payload.get("current") or [])
    _history_events_local = {
        int(row.get("event"))
        for row in _history_rows
        if row.get("event") is not None
    }
    _errors = []

    if _entry_event is not None and int(_entry_event) != REVIEW_GW:
        _errors.append(
            f"picks endpoint returned GW{_entry_event}, expected GW{REVIEW_GW}"
        )
    if _history_events_local and REVIEW_GW not in _history_events_local:
        _errors.append(f"entry history does not yet contain GW{REVIEW_GW}")

    _history_row = next(
        (
            row for row in _history_rows
            if int(row.get("event") or 0) == REVIEW_GW
        ),
        None,
    )
    if _history_row is None:
        _errors.append(f"GW{REVIEW_GW} is missing from entry history")
        return _errors, None, {}

    _live_by_id = {
        int(row.get("id")): (row.get("stats") or {})
        for row in (_live_payload.get("elements") or [])
        if row.get("id") is not None
    }
    _applied_points = 0
    _missing_live_ids = []
    for _pick in (_picks_payload.get("picks") or []):
        _pid = int(_pick.get("element") or 0)
        if _pid not in _live_by_id:
            _missing_live_ids.append(_pid)
            continue
        _applied_points += (
            int(_live_by_id[_pid].get("total_points", 0) or 0)
            * int(_pick.get("multiplier", 0) or 0)
        )

    if _missing_live_ids:
        _errors.append(
            "event-live is missing picked player IDs "
            + str(sorted(_missing_live_ids))
        )

    _pick_points = _entry_history.get("points")
    _hist_points = _history_row.get("points")
    _transfer_cost = int(
        _entry_history.get("event_transfers_cost")
        or _history_row.get("event_transfers_cost")
        or 0
    )
    _valid_applied_totals = {
        int(_applied_points),
        int(_applied_points) - int(_transfer_cost),
    }

    if _pick_points is None or _hist_points is None:
        _errors.append("entry points are missing")
    elif int(_pick_points) != int(_hist_points):
        _errors.append(
            f"picks points {_pick_points} != history points {_hist_points}"
        )
    elif int(_pick_points) not in _valid_applied_totals:
        _errors.append(
            f"entry points {_pick_points} do not match applied player total "
            f"{_applied_points} with transfer cost {_transfer_cost}"
        )

    for _rank_field in ("rank", "overall_rank"):
        _pick_rank = _entry_history.get(_rank_field)
        _hist_rank = _history_row.get(_rank_field)
        if _pick_rank is None or _hist_rank is None:
            _errors.append(f"{_rank_field} is missing")
        elif int(_pick_rank) != int(_hist_rank):
            _errors.append(
                f"picks {_rank_field} {_pick_rank} != history {_rank_field} {_hist_rank}"
            )

    _latest_history_event = max(_history_events_local) if _history_events_local else None
    _summary_rank = _entry_payload.get("summary_overall_rank")
    if (
        _latest_history_event == REVIEW_GW
        and _summary_rank is not None
        and _history_row.get("overall_rank") is not None
        and int(_summary_rank) != int(_history_row.get("overall_rank"))
    ):
        # FPL propagates the live entry summary rank independently from the
        # event-specific history row. A small propagation lag here must not
        # invalidate an otherwise internally consistent GW snapshot.
        # The published GW rank is taken from the event history row below.
        print(
            f"⚠️ FPL summary overall rank {_summary_rank} differs from "
            f"GW{REVIEW_GW} history overall rank {_history_row.get('overall_rank')}; "
            "using the event history rank for this GW."
        )

    _signature = None
    if not _errors:
        _signature = (
            int(_hist_points),
            int(_history_row.get("rank")),
            int(_history_row.get("overall_rank")),
            int(_applied_points),
            int(_transfer_cost),
        )

    _parts = {
        "picks": _picks_payload,
        "history": _history_payload,
        "entry": _entry_payload,
        "live": _live_payload,
        "entry_history": _entry_history,
        "history_rows": _history_rows,
        "history_events": _history_events_local,
        "history_row": _history_row,
        "applied_points": _applied_points,
        "transfer_cost": _transfer_cost,
    }
    return _errors, _signature, _parts


_review_snapshot = _vx_review_fetch_snapshot(fresh=False)
_review_finalisation_errors, _review_signature, _review_parts = _vx_review_validate_snapshot(
    _review_snapshot
)

if _review_all_fixtures_complete and _review_official_scores_locked:
    import time as _vx_review_time

    _settlement_wait_seconds = 15 * 60
    _settlement_poll_seconds = 30
    _settlement_deadline = _vx_review_time.monotonic() + _settlement_wait_seconds
    _last_valid_signature = _review_signature if not _review_finalisation_errors else None
    _stable_valid_polls = 1 if _last_valid_signature is not None else 0

    # The official score-lock flag is confirmed before entering this poll loop.
    # Still require two matching fresh entry/live signatures because the lock
    # can become visible before all entry/player feeds finish propagating.
    _required_stable_polls = 2

    while (
        _review_finalisation_errors
        or _stable_valid_polls < _required_stable_polls
    ):
        _remaining = _settlement_deadline - _vx_review_time.monotonic()
        if _remaining <= 0:
            _detail = "; ".join(_review_finalisation_errors) or (
                "valid entry feeds did not remain stable across consecutive polls"
            )
            raise RuntimeError(
                f"GW{REVIEW_GW} official FPL settlement did not stabilize within "
                f"the automatic wait window: {_detail}. "
                "Refusing to render or publish stale points/rank data."
            )

        print(
            f"⏳ GW{REVIEW_GW} fixtures complete; waiting for official entry "
            f"points/rank feeds to settle ({int(max(0, _remaining))}s remaining)"
        )
        _vx_review_time.sleep(
            min(_settlement_poll_seconds, max(1, _remaining))
        )

        _candidate_snapshot = _vx_review_fetch_snapshot(fresh=True)
        _candidate_errors, _candidate_signature, _candidate_parts = (
            _vx_review_validate_snapshot(_candidate_snapshot)
        )

        if _candidate_errors:
            _review_finalisation_errors = _candidate_errors
            _last_valid_signature = None
            _stable_valid_polls = 0
            continue

        if _candidate_signature == _last_valid_signature:
            _stable_valid_polls += 1
        else:
            _last_valid_signature = _candidate_signature
            _stable_valid_polls = 1

        _review_snapshot = _candidate_snapshot
        _review_finalisation_errors = []
        _review_signature = _candidate_signature
        _review_parts = _candidate_parts

    GW_REVIEW_STATUS = "FINAL"
    print(
        f"✅ GW{REVIEW_GW} entry settlement confirmed from matching official "
        "points/rank/player feeds"
    )
elif _review_all_fixtures_complete:
    # Completed fixtures are not sufficient to publish a final score before
    # FPL's official 09:00 UK next-day scoring lock.
    GW_REVIEW_STATUS = "LIVE/PARTIAL"
    print(
        f"⏳ GW{REVIEW_GW} fixtures are complete, but the official FPL score lock "
        "is not confirmed. Continuing with a clearly provisional review; "
        "points and ranks may still change."
    )
elif GW_REVIEW_STATUS == "FINAL" and _review_finalisation_errors:
    raise RuntimeError(
        f"GW{REVIEW_GW} official FPL finalisation is inconsistent: "
        + "; ".join(_review_finalisation_errors)
        + ". Refusing to render or publish stale points/rank data."
    )

_review_picks_payload = _review_parts.get("picks") or {}
_review_history_payload = _review_parts.get("history") or {}
_review_entry_payload = _review_parts.get("entry") or {}
_review_live_payload = _review_parts.get("live") or {}
_review_entry_history = _review_parts.get("entry_history") or {}
_review_history_rows = list(_review_parts.get("history_rows") or [])
_history_events = set(_review_parts.get("history_events") or set())

_review_snapshot["status"] = GW_REVIEW_STATUS
_review_snapshot["fixture_state"] = GW_REVIEW_FIXTURE_STATE
GW_REVIEW = _review_snapshot
GW_REVIEW_AVAILABLE = True

_sources = data.get("completion_source_by_gw", {}).get(REVIEW_GW, [])
if GW_REVIEW_STATUS == "LIVE/PARTIAL":
    _sources = ["event.is_current", "first_verified_fixture_complete"]
print(f"✅ ONE GW Review snapshot: entry {TEAM_ID_LOCAL} • GW{REVIEW_GW}")
print(f"✅ GW REVIEW STATUS: {GW_REVIEW_STATUS}")
if GW_REVIEW_FIXTURE_STATE:
    print(
        "✅ GW REVIEW FIXTURES: "
        f"{GW_REVIEW_FIXTURE_STATE.get('completed', 0)}/"
        f"{GW_REVIEW_FIXTURE_STATE.get('fixtures', 0)} verified complete"
    )
print("✅ P9 + P10 reuse this exact snapshot")
print(f"✅ Review GW source: {', '.join(_sources) if _sources else 'official FPL completion contract'}")
print("✅ No hard-coded Gameweek • no NEXT_GW-1 guess • no duplicate bootstrap/fixtures fetch")

# ============================================================
# CURRENT-SQUAD FORECAST DECISIONS — CLEARED
# Phase 0 rule: GW_REVIEW is a raw retrospective snapshot only.
# No transfer, captain, lineup recommendation or forecast object is created here.
# ============================================================

print("✅ GW_REVIEW remains descriptive/raw only")

