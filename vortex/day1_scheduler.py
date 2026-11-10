"""GitHub issue-backed, duplicate-safe Day 1 dispatch ledger.

One season/review/preview identity can have only one successful production.
Workflow-run completion updates the persistent issue; failures may retry at
most the configured number of times, but never overlap active builds.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

MAX_RETRIES = 3
TITLE_PREFIX = "FPL VORTEX DAY 1 | "
MARK = "vortex-day1-state:"


def call_gh(method, endpoint, payload=None):
    cmd = ["gh", "api", "--method", method, endpoint]
    if payload is not None:
        cmd.extend(["--input", "-"])
    proc = subprocess.run(cmd, input=json.dumps(payload) if payload is not None else None,
                          text=True, capture_output=True, check=False)
    if proc.returncode:
        raise RuntimeError(f"GitHub API {method} {endpoint} failed: {proc.stderr[-800:]}")
    return json.loads(proc.stdout) if proc.stdout.strip() else {}


def repo():
    value = os.environ.get("GITHUB_REPOSITORY", "")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value):
        raise RuntimeError("Expected GITHUB_REPOSITORY owner/repository")
    return value


def title(identity):
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-review-GW\d+-preview-GW\d+", identity):
        raise ValueError("Invalid Day 1 production identity")
    return TITLE_PREFIX + identity


def issue_body(state):
    return "<!-- " + MARK + json.dumps(state, sort_keys=True, separators=(",", ":")) + " -->\n" + (
        "Internal Day 1 generation state. Public publication is never authorized by this issue.\n"
    )


def parse_state(issue):
    m = re.search(r"<!-- " + re.escape(MARK) + r"(\{[^\n]*\}) -->",
                  str(issue.get("body") or ""))
    if not m:
        raise RuntimeError("Found an existing Day 1 issue without its persisted state")
    return json.loads(m.group(1))


def find_issue(name):
    # Paginate: issue state must survive across seasons, breaks and artifact expiry.
    page = 1
    while True:
        items = call_gh("GET", f"repos/{repo()}/issues?state=all&per_page=100&page={page}")
        for issue in items:
            if "pull_request" not in issue and issue.get("title") == name:
                return issue
        if len(items) < 100:
            return None
        page += 1


def upsert(issue, state, close=False):
    r = repo()
    if issue is None:
        if close:
            raise RuntimeError("Cannot close missing Day 1 ledger")
        return call_gh("POST", f"repos/{r}/issues",
                       {"title": title(state["id"]), "body": issue_body(state)})
    return call_gh("PATCH", f"repos/{r}/issues/{issue['number']}", {
        "body": issue_body(state), "state": "closed" if close else "open",
    })


def runs(identity):
    page = 1
    all_matching = []
    expected = TITLE_PREFIX + identity
    while page <= 5:
        payload = call_gh(
            "GET",
            f"repos/{repo()}/actions/workflows/day-1.yml/runs?branch=main&per_page=100&page={page}"
        )
        items = payload.get("workflow_runs", [])
        all_matching.extend(
            run for run in items
            if run.get("display_title") == expected and run.get("head_branch") == "main"
        )
        if len(items) < 100:
            break
        page += 1
    return all_matching


def dispatch(report):
    if not report.get("ready"):
        print("Day 1 scheduler: SKIP:", report.get("reason", "not finalized"))
        return
    identity = report["production_identity"]
    name = title(identity)
    issue = find_issue(name)
    previous = parse_state(issue) if issue else {}
    if previous.get("state") == "success":
        print("Day 1 scheduler: already verified:", identity)
        return
    matching = runs(identity)
    if any(r.get("status") in {"queued", "in_progress", "waiting", "pending", "requested"}
           for r in matching):
        print("Day 1 scheduler: existing production is still active")
        return
    if any(r.get("conclusion") == "success" for r in matching):
        new = {**previous, "id": identity, "state": "success"}
        upsert(issue, new, close=True)
        print("Day 1 scheduler: existing successful production already recorded")
        return
    # Avoid repeated dispatch before GitHub has indexed the newly queued workflow.
    if previous.get("state") == "dispatching":
        started = datetime.fromisoformat(previous["dispatched_utc"])
        if datetime.now(timezone.utc) - started < timedelta(minutes=45):
            print("Day 1 scheduler: recent dispatch is still being indexed")
            return
    attempts = int(previous.get("attempts", 0))
    if attempts >= MAX_RETRIES:
        print("Day 1 scheduler: retry limit reached; manual investigation required")
        return
    current = {
        "id": identity,
        "state": "dispatching",
        "attempts": attempts + 1,
        "snapshot_version": report["snapshot_version"],
        "revision": os.environ.get("GITHUB_SHA", ""),
        "dispatched_utc": datetime.now(timezone.utc).isoformat(),
        "private_upload_requested": os.environ.get("DAY1_AUTO_PRIVATE_UPLOAD", "").lower() == "true",
    }
    issue = upsert(issue, current)
    private = "true" if current["private_upload_requested"] else "false"
    command = [
        "gh", "workflow", "run", "day-1.yml", "--ref", "main",
        "-f", f"release_private={private}", "-f", f"production_identity={identity}",
    ]
    proc = subprocess.run(command, text=True, capture_output=True, check=False)
    if proc.returncode:
        current["state"] = "dispatch_error"
        current["error"] = proc.stderr[-400:]
        upsert(issue, current)
        raise RuntimeError("Day 1 dispatch was refused: " + proc.stderr[-500:])
    print("Day 1 scheduler: dispatched", identity,
          "with QA-gated private upload:", private)


def record(run_id):
    data = call_gh("GET", f"repos/{repo()}/actions/runs/{run_id}")
    label = str(data.get("display_title") or "")
    if not label.startswith(TITLE_PREFIX):
        print("Day 1 scheduler: completion was not a scheduled production")
        return
    identity = label[len(TITLE_PREFIX):]
    name = title(identity)
    issue = find_issue(name)
    if not issue:
        print("Day 1 scheduler: no persistent ledger for this manual production")
        return
    state = parse_state(issue)
    if data.get("head_branch") != "main" or data.get("status") != "completed":
        raise RuntimeError("Cannot record a production before it finishes on main")
    state.update(state="success" if data.get("conclusion") == "success" else "failed",
                 finished_utc=datetime.now(timezone.utc).isoformat(),
                 run_id=int(run_id), conclusion=data.get("conclusion"),
                 run_url=data.get("html_url"))
    upsert(issue, state, close=state["state"] == "success")
    print("Day 1 scheduler: completion", identity, state["state"])


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="action", required=True)
    go = sub.add_parser("dispatch")
    go.add_argument("--gate", type=Path, required=True)
    done = sub.add_parser("record")
    done.add_argument("--run-id", type=int, required=True)
    args = parser.parse_args()
    if args.action == "dispatch":
        dispatch(json.loads(args.gate.read_text(encoding="utf-8")))
    elif args.action == "record":
        record(args.run_id)


if __name__ == "__main__":
    main()
