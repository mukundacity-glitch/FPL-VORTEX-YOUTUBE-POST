"""Fixture-relative trigger for the isolated FPL VORTEX Value Board."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

API = "https://fantasy.premierleague.com/api"
ET = ZoneInfo("America/New_York")


def fetch(path):
    response = requests.get(API + path, timeout=30, headers={"User-Agent": "FPL-VORTEX-Value-Board/1"})
    response.raise_for_status()
    return response.json()


def stamp(value):
    if not isinstance(value, str) or not value:
        raise ValueError("Official FPL date or kickoff is missing")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Official timestamp lacks timezone")
    return parsed.astimezone(timezone.utc)


def selected_gameweek(bootstrap, fixtures):
    events = bootstrap.get("events") or []
    upcoming = [event for event in events if event.get("is_next")]
    if len(upcoming) != 1:
        # FPL sometimes clears is_next briefly between events; fail instead of guessing.
        raise RuntimeError("Official FPL next Gameweek flag missing or ambiguous")
    event = upcoming[0]
    gw = int(event["id"])
    matches = [f for f in fixtures if f.get("event") == gw and not f.get("finished")]
    if not matches:
        raise RuntimeError(f"GW{gw} has no unplayed scheduled fixtures; cannot derive a 26-hour trigger")
    if any(not f.get("kickoff_time") for f in matches):
        raise RuntimeError(f"GW{gw} contains an undated fixture; schedule not verified")
    first = min(stamp(f["kickoff_time"]) for f in matches)
    deadline = stamp(event["deadline_time"])
    return {
        "gameweek": gw,
        "first_kickoff_utc": first.isoformat(),
        "first_kickoff_et": first.astimezone(ET).isoformat(),
        "due_utc": (first - timedelta(hours=26)).isoformat(),
        "due_et": (first - timedelta(hours=26)).astimezone(ET).isoformat(),
        "deadline_utc": deadline.isoformat(),
        "deadline_et": deadline.astimezone(ET).isoformat(),
        "fixture_ids": sorted(int(f["id"]) for f in matches),
    }


def issued(gw):
    """A completed artifact is a second idempotency gate alongside workflow concurrency."""
    token, repository = os.getenv("GITHUB_TOKEN"), os.getenv("GITHUB_REPOSITORY")
    if not token or not repository:
        return False
    url = f"https://api.github.com/repos/{repository}/actions/artifacts"
    response = requests.get(url, headers={"Authorization": f"Bearer {token}",
                             "Accept": "application/vnd.github+json"},
                            params={"name": f"value-board-GW{gw}", "per_page": 100}, timeout=25)
    response.raise_for_status()
    return any(not artifact.get("expired") for artifact in response.json().get("artifacts", []))


def check(*, force=False, wait=False, now=None, fetcher=fetch, sleeper=time.sleep):
    now = now or datetime.now(timezone.utc)
    boot = fetcher("/bootstrap-static/")
    fixtures = fetcher("/fixtures/")
    meta = selected_gameweek(boot, fixtures)
    gw = meta["gameweek"]
    if issued(gw):
        return False, meta, "already generated"
    due = stamp(meta["due_utc"])
    first = stamp(meta["first_kickoff_utc"])
    if first <= now:
        return False, meta, "first kickoff already started"
    if not force:
        # GitHub scheduled runs may be delayed; accept a 2h late dispatch, not stale GW data.
        if now < due - timedelta(minutes=19) or now > due + timedelta(hours=2):
            return False, meta, "outside 26-hour run window"
        if wait and now < due:
            sleeper(max(0, (due - now).total_seconds()))
            now = datetime.now(timezone.utc)
            refreshed = selected_gameweek(fetcher("/bootstrap-static/"), fetcher("/fixtures/"))
            if refreshed != meta:
                return False, refreshed, "fixture/deadline changed during wait; re-evaluate next check"
            meta = refreshed
    return True, meta, "due"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--wait", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("value_board/trigger.json"))
    args = parser.parse_args()
    try:
        run, meta, reason = check(force=args.force, wait=args.wait)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(dict(meta, run=run, reason=reason), indent=2))
        print(f"Value Board GW{meta['gameweek']}: {reason}; ET due {meta['due_et']}; kickoff {meta['first_kickoff_et']}")
        target = os.getenv("GITHUB_OUTPUT")
        if target:
            with open(target, "a", encoding="utf-8") as handle:
                handle.write(f"run={'true' if run else 'false'}\n")
                handle.write(f"gw={meta['gameweek']}\n")
    except Exception as exc:
        print(f"Value Board schedule verification failed: {exc}", file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
