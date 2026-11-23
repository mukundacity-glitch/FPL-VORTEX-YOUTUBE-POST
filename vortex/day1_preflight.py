"""Check whether the final-review Day 1 production can start."""
import argparse
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from http.client import IncompleteRead
import json
import os
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .day1_player_hero import analyze, completed_week

FPL_API = "https://fantasy.premierleague.com/api"
RETRYABLE = {429, 500, 502, 503, 504}


class NotReady(RuntimeError):
    """The official feeds have yet to settle or there is no upcoming preview."""


def _retry_delay(header, attempt):
    delay = 2 ** attempt
    if not header:
        return delay
    try:
        return max(delay, int(header))
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(header)
        except (TypeError, ValueError):
            return delay
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)
        return max(delay, (retry_at - datetime.now(timezone.utc)).total_seconds())


def fetch_json(path):
    request = Request(
        f"{FPL_API}{path}?_vx={time.time_ns()}",
        headers={"User-Agent": "FPL-VORTEX-Day1/1.0", "Accept": "application/json",
                 "Cache-Control": "no-cache, no-store"},
    )
    return _fetch_json(request, f"FPL {path}")


def _fetch_json(request, label):
    for attempt in range(1, 5):
        try:
            with urlopen(request, timeout=20) as response:
                return json.load(response)
        except HTTPError as exc:
            detail = f"HTTP {exc.code}"
            if label == "Google Drive OAuth":
                try:
                    payload = json.loads(exc.read(4096))
                except (ValueError, UnicodeError):
                    payload = {}
                reason = payload.get("error") if isinstance(payload, dict) else None
                if reason in ("invalid_grant", "invalid_client", "invalid_scope", "unauthorized_client"):
                    detail += f" ({reason}); verify the Google Drive OAuth secrets and consent"
            delay = _retry_delay(exc.headers.get("Retry-After") if exc.headers else None, attempt)
            if exc.code not in RETRYABLE or attempt == 4 or delay > 60:
                raise RuntimeError(f"{label} failed: {detail} (attempt {attempt}/4)") from None
        except (URLError, TimeoutError, ConnectionError, IncompleteRead) as exc:
            detail = type(exc).__name__
            delay = _retry_delay(None, attempt)
            if attempt == 4:
                raise RuntimeError(f"{label} failed: {detail} after 4 attempts") from exc
        except (UnicodeError, ValueError) as exc:
            raise RuntimeError(f"{label} returned invalid JSON") from exc
        print(f"{label}: {detail}; retrying in {delay:.0f}s ({attempt}/4)", flush=True)
        time.sleep(delay)


def _rows(value, label):
    if not isinstance(value, list) or not value or any(not isinstance(row, dict) for row in value):
        raise ValueError(f"Official FPL {label} must contain a nonempty list of records")
    return value


def _deadline(event):
    value = event.get("deadline_time")
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Official FPL GW{event['id']} has an invalid deadline") from exc
    if stamp.tzinfo is None:
        raise ValueError(f"Official FPL GW{event['id']} deadline is missing a timezone")
    return stamp.astimezone(timezone.utc)


def _fixture_complete(fixture, *, allow_provisional=False):
    return (
        fixture.get("started") is True
        and isinstance(fixture.get("minutes"), (int, float))
        and fixture["minutes"] >= 90
        and (fixture.get("finished") is True
             or (allow_provisional and fixture.get("finished_provisional") is True))
        and all(type(fixture.get(key)) is int and fixture[key] >= 0
                for key in ("team_h_score", "team_a_score"))
    )


def require_final_review(bootstrap, fixtures, *, now=None, review_gw=None):
    if not isinstance(bootstrap, dict):
        raise ValueError("Official FPL bootstrap-static must be a JSON object")
    for field in ("elements", "teams", "element_types"):
        _rows(bootstrap.get(field), f"bootstrap-static.{field}")
    events = _rows(bootstrap.get("events"), "bootstrap-static.events")
    fixtures = _rows(fixtures, "fixtures")
    if any(type(event.get("id")) is not int or event["id"] < 1 for event in events):
        raise ValueError("Official FPL events contain an invalid Gameweek ID")
    by_id = {event["id"]: event for event in events}
    if len(by_id) != len(events):
        raise ValueError("Official FPL events contain duplicate Gameweek IDs")
    now = datetime.now(timezone.utc) if now is None else now
    deadlines = {event["id"]: _deadline(event) for event in events}
    next_ids = [event["id"] for event in events if event.get("is_next") is True]
    if len(next_ids) > 1:
        raise ValueError("Official FPL marked multiple Gameweeks as next")
    future_ids = [gw for gw, deadline in deadlines.items() if deadline > now]
    if not future_ids:
        raise NotReady("No upcoming official Gameweek with a future deadline")
    preview = next_ids[0] if next_ids else min(future_ids, key=lambda gw: (deadlines[gw], gw))
    if preview not in future_ids:
        raise NotReady(f"Official FPL still points at GW{preview}, whose deadline has passed; retry after the feed advances")

    # Keep the retrospective score-checked while allowing the preview to use today's feed.
    review = completed_week(bootstrap) if review_gw is None else review_gw
    event = by_id.get(review)
    if not event or not 1 <= review < preview:
        raise NotReady(f"GW{preview} preview has no earlier score-checked Gameweek to review")
    matches = [fixture for fixture in fixtures if fixture.get("event") == review]
    if not any(fixture.get("event") == preview for fixture in fixtures):
        raise NotReady(f"Official FPL has no fixtures for upcoming GW{preview}")
    if not matches or not all(_fixture_complete(fixture) for fixture in matches):
        raise NotReady(f"Official FPL GW{review} review is missing finalized fixture data")
    if event.get("finished") is not True or event.get("data_checked") is not True:
        raise NotReady(f"Official FPL GW{review} review is not score-checked")
    return review, preview, deadlines[preview]


def drive_credentials():
    names = ("GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET", "GOOGLE_OAUTH_REFRESH_TOKEN")
    secrets = {name: os.getenv(name, "").strip() for name in names}
    missing = [name for name in names if not secrets[name]]
    if missing:
        raise RuntimeError("Missing required Google Drive secret(s): " + ", ".join(missing))
    if not secrets[names[0]].endswith(".apps.googleusercontent.com"):
        raise RuntimeError("GOOGLE_OAUTH_CLIENT_ID has an invalid format")
    request = Request(
        "https://oauth2.googleapis.com/token",
        data=urlencode(dict(client_id=secrets[names[0]], client_secret=secrets[names[1]],
                            refresh_token=secrets[names[2]], grant_type="refresh_token")).encode("ascii"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    token = _fetch_json(request, "Google Drive OAuth")
    if not isinstance(token, dict) or not token.get("access_token"):
        raise RuntimeError("Google Drive OAuth response did not include an access token")
    scopes = str(token.get("scope") or "").split()
    if scopes and "https://www.googleapis.com/auth/drive" not in scopes:
        raise RuntimeError("Google Drive OAuth grant lacks the Drive scope used by production rclone")
    return secrets, token


def verify_environment(review, preview, deadline):
    expected = tuple(os.environ.get(name) for name in
                     ("VORTEX_DAY1_REVIEW_GW", "VORTEX_DAY1_PREVIEW_GW", "VORTEX_DAY1_PREVIEW_DEADLINE"))
    actual = (str(review), str(preview), deadline.isoformat())
    if actual != expected:
        raise NotReady(f"Official Gameweek identity changed since preflight: expected {expected}, got {actual}. "
                       "Start a fresh Day 1 run.")



def verify_run_gameweeks(bootstrap, fixtures):
    review, preview, deadline = require_final_review(
        bootstrap, fixtures, review_gw=int(os.environ["VORTEX_DAY1_REVIEW_GW"])
    )
    verify_environment(review, preview, deadline)
    return review, preview, deadline


def verify_notebook_snapshot(namespace):
    data = namespace["data"]
    loader = namespace["_fpl_module"]
    with loader._vx_http_session() as session:
        fixtures = loader._vx_get_json(session, "/fixtures/")
    review, preview, _ = verify_run_gameweeks(data["bootstrap"], fixtures)
    if data["next_gw"] != preview or review not in data["review_ready_gws"]:
        raise NotReady("The notebook and official Day 1 readiness check disagree on the final review and preview.")
    data.update(review_gw=review, review_status="FINAL",
                review_fixture_state=data["fixture_state_counts_by_gw"][review])
    namespace["LATEST_COMPLETED_GW"] = review
    namespace["AUTO_REVIEW_GW"] = review
    print(f"Day 1 notebook confirmed final GW{review} and upcoming GW{preview}.", flush=True)


def check_live(*, verify=False):
    bootstrap = fetch_json("/bootstrap-static/")
    fixtures = fetch_json("/fixtures/")
    select_gameweeks = verify_run_gameweeks if verify else require_final_review
    review, preview, deadline = select_gameweeks(bootstrap, fixtures)
    if verify:
        print(f"Day 1 Gameweek unchanged: final GW{review}, preview GW{preview}, deadline {deadline.isoformat()}.")
        return None
    live = fetch_json(f"/event/{review}/live/")
    if not isinstance(live, dict):
        raise ValueError(f"Official FPL GW{review} live feed must be a JSON object")
    _rows(live.get("elements"), f"GW{review} live.elements")
    analyzed = analyze(bootstrap, fixtures, live, review)
    print(f"Day 1 FPL data ready: final GW{review}, preview GW{preview}, "
          f"deadline {deadline.isoformat()}, {analyzed['candidates_analyzed']} verified hero candidates.")
    return {"review_gw": review, "preview_gw": preview, "preview_deadline_utc": deadline.isoformat()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check-drive", action="store_true")
    mode.add_argument("--verify-environment", action="store_true")
    args = parser.parse_args()
    try:
        if args.check_drive:
            _, token = drive_credentials()
            _fetch_json(Request("https://www.googleapis.com/drive/v3/about?fields=storageQuota(limit)",
                                headers={"Authorization": "Bearer " + token["access_token"]}), "Google Drive API")
            print("Google Drive OAuth and read access: PASS")
            return
        result = check_live(verify=args.verify_environment)
    except (RuntimeError, ValueError, KeyError, TypeError) as exc:
        raise SystemExit(f"Day 1 FPL preflight blocked production: {exc}") from exc
    if args.report and result is not None:
        args.report.write_text(json.dumps(result) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
