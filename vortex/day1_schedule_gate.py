"""Official-FPL finalization gate for scheduled Day 1 production.

No synthetic points or fixed weekday logic: only finalized review GW
plus the next five scheduled FPL events permit a Day 1 production.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from urllib.request import Request, urlopen

API = "https://fantasy.premierleague.com/api"


def _season(deadline):
    day = datetime.fromisoformat(str(deadline).replace("Z", "+00:00"))
    first = day.year if day.month >= 7 else day.year - 1
    return f"{first}-{(first + 1) % 100:02d}"


def evaluate(bootstrap, fixtures):
    """Return a fail-closed, machine-readable production decision."""
    def reject(reason):
        return {"ready": False, "reason": reason}
    if not isinstance(bootstrap, dict) or not isinstance(fixtures, list):
        return reject("Official FPL API payload has an unexpected schema")
    events = bootstrap.get("events")
    if not isinstance(events, list):
        return reject("Official FPL event table is missing")
    upcoming = [event for event in events if event.get("is_next") is True]
    if len(upcoming) != 1:
        return reject("Exactly one officially designated next gameweek is required")
    preview = upcoming[0]
    preview_gw = int(preview["id"])
    review_gw = preview_gw - 1
    if review_gw < 1 or preview_gw > 34:
        return reject("No preceding GW or complete five-GW forecast horizon")
    reviews = [event for event in events if int(event.get("id") or -1) == review_gw]
    if len(reviews) != 1:
        return reject("Previous event was not found in official FPL")
    review = reviews[0]
    if review.get("finished") is not True or review.get("data_checked") is not True:
        return reject("Previous FPL gameweek is not fully finished and data-checked")
    played = [f for f in fixtures if f.get("event") == review_gw]
    if not played or any(
        f.get("finished") is not True
        or f.get("team_h_score") is None or f.get("team_a_score") is None
        for f in played
    ):
        return reject("Previous FPL fixtures or final scores are incomplete")
    future_events = {int(e["id"]) for e in events if e.get("id") is not None}
    if not all(gw in future_events for gw in range(preview_gw, preview_gw + 5)):
        return reject("Next five official FPL gameweeks are not available")
    future_fixtures = [
        f for f in fixtures if f.get("event") in range(preview_gw, preview_gw + 5)
    ]
    if not any(f.get("event") == preview_gw for f in future_fixtures):
        return reject("Next gameweek fixture schedule is unavailable")
    if len(bootstrap.get("teams") or []) != 20 or len(bootstrap.get("elements") or []) < 200:
        return reject("Live club or player pool is incomplete")
    try:
        season = _season(review["deadline_time"])
    except (KeyError, ValueError, TypeError):
        return reject("Cannot determine official FPL season")
    canonical = {
        "review": review_gw,
        "preview": preview_gw,
        "fixtures": sorted(
            [(f.get("id"), f.get("event"), f.get("kickoff_time"),
              f.get("team_h"), f.get("team_a"), f.get("finished"),
              f.get("team_h_score"), f.get("team_a_score"))
             for f in played + future_fixtures],
            key=lambda row: str(row[0]),
        ),
        "prices_market": sorted(
            [(p.get("id"), p.get("now_cost"), p.get("status"),
              p.get("chance_of_playing_next_round"), p.get("selected_by_percent"),
              p.get("transfers_in_event"), p.get("transfers_out_event"))
             for p in bootstrap["elements"]],
            key=lambda row: str(row[0]),
        ),
    }
    snapshot_version = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:20]
    identity = f"{season}-review-GW{review_gw}-preview-GW{preview_gw}"
    return {
        "ready": True, "season": season, "review_gameweek": review_gw,
        "preview_gameweek": preview_gw, "production_identity": identity,
        "snapshot_version": snapshot_version, "completed_fixtures": len(played),
        "future_fixtures": len(future_fixtures),
    }


def official_json(endpoint):
    req = Request(API + endpoint, headers={
        "User-Agent": "FPL-VORTEX-Day1-Scheduler/1.0",
        "Accept": "application/json",
    })
    with urlopen(req, timeout=30) as response:
        return json.load(response)


def main():
    report = evaluate(
        official_json("/bootstrap-static/"), official_json("/fixtures/")
    )
    report["checked_utc"] = datetime.now(timezone.utc).isoformat()
    json.dump(report, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
