from __future__ import annotations

import hashlib
import json
import math
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


API_ROOT = "https://fantasy.premierleague.com/api"
VERSION = "DAY3-LIVE-EVIDENCE-V3-DATA-CHECKED-LOCK"
RULE_SOURCE = "https://www.premierleague.com/en/news/4361991/"
DC_THRESHOLDS = {"DEF": 10, "MID": 12, "FWD": 12}
EVIDENCE_POLL_INTERVAL_SECONDS = 60.0
EVIDENCE_MAX_WAIT_SECONDS = 3 * 60 * 60


def number(value: Any, label: str, minimum: float = 0.0) -> float:
    if value is None or isinstance(value, bool):
        raise ValueError(f"Missing {label}")
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Invalid {label}: {value!r}") from error
    if not math.isfinite(result) or result < minimum:
        raise ValueError(f"Invalid {label}: {value!r}")
    return result


def digest(payload: Any) -> str:
    def canonical(value: Any) -> Any:
        if isinstance(value, dict):
            return {str(key): canonical(item) for key, item in value.items()}
        if isinstance(value, list):
            return [canonical(item) for item in value]
        if isinstance(value, float) and value.is_integer():
            return int(value)
        return value
    return hashlib.sha256(json.dumps(canonical(payload), sort_keys=True, allow_nan=False).encode()).hexdigest()


def get_json(path: str) -> Any:
    if not path.startswith("/") or ".." in path:
        raise ValueError("Invalid official FPL path")
    request = urllib.request.Request(
        API_ROOT + path + "?_vortex=" + str(time.time_ns()),
        headers={"User-Agent": "FPL-VORTEX/3.0", "Cache-Control": "no-cache", "Pragma": "no-cache"},
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except (OSError, ValueError):
            if attempt == 2:
                raise
            time.sleep(attempt + 1)
    raise RuntimeError("Official FPL request failed")


def material_state(bootstrap: dict[str, Any], fixtures: list[dict[str, Any]]) -> dict[str, Any]:
    fields = ("id", "code", "team", "team_join_date", "element_type", "status", "chance_of_playing_next_round", "news",
              "minutes", "starts", "defensive_contribution")
    fixture_fields = ("id", "event", "team_h", "team_a", "kickoff_time", "started", "finished",
                      "finished_provisional", "team_h_score", "team_a_score", "stats")
    return {
        "players": [{key: row.get(key) for key in fields} for row in sorted(bootstrap["elements"], key=lambda row: row["id"])],
        "fixtures": [{key: row.get(key) for key in fixture_fields} for row in sorted(fixtures, key=lambda row: row["id"])],
        "events": [{key: row.get(key) for key in ("id", "deadline_time", "finished", "data_checked")}
                   for row in bootstrap["events"]],
    }


def availability(player: dict[str, Any]) -> tuple[float | None, str]:
    status = str(player.get("status", "")).lower()
    chance = player.get("chance_of_playing_next_round")
    if chance is not None:
        chance = number(chance, "chance of playing")
        if chance > 100:
            raise ValueError("Chance of playing exceeds 100")
        if status == "a" and chance == 0:
            return None, "CONFLICTING_AVAILABILITY"
        return chance / 100, {"s": "SUSPENDED", "i": "INJURED", "u": "UNAVAILABLE", "n": "UNAVAILABLE"}.get(
            status, "DOUBTFUL" if chance < 100 else "AVAILABLE")
    if status == "a":
        return 1.0, "AVAILABLE"
    if status in {"s", "i", "u", "n"}:
        return 0.0, {"s": "SUSPENDED", "i": "INJURED"}.get(status, "UNAVAILABLE")
    return None, "AVAILABILITY_UNCONFIRMED"


def poisson_tail(mean: float, threshold: int) -> float:
    term = math.exp(-mean)
    cumulative = term
    for count in range(1, threshold):
        term *= mean / count
        cumulative += term
    return max(0.0, min(1.0, 1 - cumulative))


def dc_forecast(rate90: Any, position: str, minutes_pmf: list[tuple[float, float]],
                probability_override: Any = None) -> tuple[float, float]:
    if position in {"GK", "GKP"}:
        return 0.0, 0.0
    if position not in DC_THRESHOLDS:
        raise ValueError(f"Unknown FPL position {position}")
    if minutes_pmf and all(minutes == 0 for minutes, weight in minutes_pmf if weight > 0):
        if not math.isclose(sum(weight for _, weight in minutes_pmf), 1.0, abs_tol=1e-6):
            raise ValueError("Minutes distribution does not sum to one")
        return 0.0, 0.0
    # A missing rate is unknown, even if pandas would otherwise sum it as zero.
    try:
        rate = number(rate90, "defensive-contribution rate")
    except ValueError:
        return math.nan, math.nan
    expected = probability = appearance = total_mass = 0.0
    for minutes, weight in minutes_pmf:
        minutes = number(minutes, "PMF minutes")
        weight = number(weight, "PMF weight")
        if minutes > 90 + 1e-8 or weight > 1 + 1e-8:
            raise ValueError("Invalid minutes distribution")
        minutes, weight = min(90.0, minutes), min(1.0, weight)
        total_mass += weight
        mean = rate * minutes / 90
        expected += weight * mean
        if minutes > 0:
            appearance += weight
            probability += weight * poisson_tail(mean, DC_THRESHOLDS[position])
    if not math.isclose(total_mass, 1.0, abs_tol=1e-6):
        raise ValueError("Minutes distribution does not sum to one")
    if probability_override is not None:
        probability = number(probability_override, "DEFCON probability override")
        if probability > appearance + 1e-8:
            raise ValueError("DEFCON award probability exceeds appearance probability")
    return expected, min(appearance, probability)



def _upcoming_event(bootstrap: dict[str, Any], cutoff: str) -> dict[str, Any]:
    """Return the official event with the nearest deadline still in the future."""
    now = datetime.fromisoformat(cutoff.replace("Z", "+00:00"))
    next_events = [
        event for event in bootstrap["events"]
        if datetime.fromisoformat(event["deadline_time"].replace("Z", "+00:00")) > now
    ]
    if not next_events:
        raise RuntimeError("No upcoming official FPL deadline")
    return min(next_events, key=lambda event: event["deadline_time"])


def _score_locked_gameweeks(bootstrap: dict[str, Any] | None) -> set[int]:
    """Official FPL score lock; fixture flags can lag behind the Gameweek lock."""
    if not isinstance(bootstrap, dict):
        return set()
    return {
        int(event["id"])
        for event in bootstrap.get("events", [])
        if event.get("id") is not None and bool(event.get("data_checked"))
    }


def _fixture_verified_final(
    fixture: dict[str, Any], score_locked_gameweeks: set[int] | None = None
) -> bool:
    if bool(fixture.get("finished")) and bool(fixture.get("finished_provisional", True)):
        return True

    # FPL occasionally leaves fixture.finished=False after a match has ended.
    # Only override that stale fixture flag when the same official Gameweek is
    # score-locked (data_checked=True) and this fixture is marked provisionally
    # finished. The live payload is still reconciled against bootstrap totals below.
    event_id = fixture.get("event")
    return (
        bool(fixture.get("started"))
        and bool(fixture.get("finished_provisional"))
        and event_id is not None
        and int(event_id) in (score_locked_gameweeks or set())
    )


def _completed_prior_fixtures(
    fixtures: list[dict[str, Any]], next_gw: int,
    bootstrap: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    score_locked = _score_locked_gameweeks(bootstrap)
    return [
        row for row in fixtures
        if row.get("event") is not None
        and int(row["event"]) < next_gw
        and _fixture_verified_final(row, score_locked)
    ]


def _unfinished_prior_fixtures(
    fixtures: list[dict[str, Any]], next_gw: int,
    bootstrap: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Started earlier-Gameweek fixtures that do not yet have verified final stats."""
    score_locked = _score_locked_gameweeks(bootstrap)
    return sorted(
        [
            row for row in fixtures
            if row.get("event") is not None
            and int(row["event"]) < next_gw
            and row.get("started")
            and not _fixture_verified_final(row, score_locked)
        ],
        key=lambda row: (
            int(row.get("event") or 0),
            str(row.get("kickoff_time") or ""),
            int(row.get("id") or 0),
        ),
    )


def _describe_fixture_status(fixture: dict[str, Any], bootstrap: dict[str, Any]) -> str:
    teams = {int(row["id"]): str(row.get("name") or f"Team {row['id']}") for row in bootstrap.get("teams", [])}

    def team_name(value: Any) -> str:
        try:
            team_id = int(value)
        except (TypeError, ValueError):
            return f"team {value}"
        return teams.get(team_id, f"team {team_id}")

    return (
        f"GW{fixture.get('event', '?')} fixture #{fixture.get('id', '?')} "
        f"({team_name(fixture.get('team_h'))} vs {team_name(fixture.get('team_a'))}; "
        f"kickoff={fixture.get('kickoff_time') or 'unknown'}; "
        f"started={bool(fixture.get('started'))}, finished={bool(fixture.get('finished'))}, "
        f"finished_provisional={fixture.get('finished_provisional', True)})"
    )


def _describe_fixtures(fixtures: list[dict[str, Any]], bootstrap: dict[str, Any]) -> str:
    return "; ".join(_describe_fixture_status(row, bootstrap) for row in fixtures)

def build_evidence(bootstrap: dict[str, Any], fixtures: list[dict[str, Any]],
                   live_events: dict[int, dict[str, Any]], cutoff: str) -> dict[str, Any]:
    target = _upcoming_event(bootstrap, cutoff)
    next_gw = int(target["id"])
    teams = {int(row["id"]): row for row in bootstrap["teams"]}
    master = {int(row["id"]): row for row in bootstrap["elements"]}
    fixture_map = {int(row["id"]): row for row in fixtures}
    if len(master) != len(bootstrap["elements"]) or len(fixture_map) != len(fixtures):
        raise RuntimeError("Duplicate official player or fixture identity")
    positions = {int(row["id"]): str(row["singular_name_short"]).replace("GKP", "GK")
                 for row in bootstrap["element_types"]}
    completed = _completed_prior_fixtures(fixtures, next_gw, bootstrap)
    unfinished = _unfinished_prior_fixtures(fixtures, next_gw, bootstrap)
    if unfinished:
        raise RuntimeError(
            "An earlier Gameweek fixture is not verified final: "
            + _describe_fixtures(unfinished, bootstrap)
        )
    history_gws = sorted({int(row["event"]) for row in completed})
    if set(history_gws) != set(live_events):
        raise RuntimeError("Official event history does not cover the completed fixture set")
    observations: dict[int, list[dict[str, Any]]] = {player_id: [] for player_id in master}
    event_totals: dict[int, list[dict[str, float]]] = {player_id: [] for player_id in master}
    for gameweek in history_gws:
        seen: set[int] = set()
        for element in live_events[gameweek].get("elements", []):
            player_id = int(element["id"])
            if player_id in seen:
                raise RuntimeError(f"Duplicate player {player_id} in GW{gameweek}")
            seen.add(player_id)
            if player_id not in master:
                continue
            stats = element["stats"]
            minutes = number(stats.get("minutes"), "official minutes")
            actions = number(stats.get("defensive_contribution"), "official DC")
            starts = number(stats.get("starts"), "official starts")
            explained_minutes = 0.0
            fixture_ids: set[int] = set()
            for match in element.get("explain", []):
                fixture_id = int(match["fixture"])
                if fixture_id not in fixture_map or fixture_id in fixture_ids:
                    raise RuntimeError("Unknown or repeated player-history fixture")
                fixture_ids.add(fixture_id)
                if int(fixture_map[fixture_id].get("event") or 0) != gameweek:
                    raise RuntimeError("Player history belongs to the wrong Gameweek")
                match_stats = {item["identifier"]: item for item in match["stats"]}
                match_minutes = number(match_stats.get("minutes", {}).get("value", 0), "fixture minutes")
                if match_minutes > 90:
                    raise RuntimeError("Per-fixture player minutes exceed 90")
                explained_minutes += match_minutes
                award = number(match_stats.get("defensive_contribution", {}).get("points", 0), "DC award")
                if award not in {0, 2}:
                    raise RuntimeError("DC award violates the verified per-fixture scoring rule")
                observations[player_id].append({"fixture_id": fixture_id, "minutes": match_minutes,
                                                "dc_hit": int(award > 0), "gameweek": gameweek})
            if not math.isclose(explained_minutes, minutes, abs_tol=1e-6):
                raise RuntimeError(f"Player {player_id} GW{gameweek}: minutes do not reconcile")
            event_totals[player_id].append({"gameweek": gameweek, "minutes": minutes, "dc": actions, "starts": starts})
    output: dict[int, dict[str, Any]] = {}
    for player_id, player in master.items():
        team_id = int(player["team"])
        if team_id not in teams:
            raise RuntimeError(f"Player {player_id} has no current club mapping")
        totals = event_totals[player_id]
        minutes = sum(row["minutes"] for row in totals)
        actions = sum(row["dc"] for row in totals)
        if not math.isclose(minutes, number(player.get("minutes"), "season minutes"), abs_tol=1e-6):
            raise RuntimeError(f"Player {player_id}: bootstrap/history season minutes conflict")
        if not math.isclose(actions, number(player.get("defensive_contribution"), "season DC"), abs_tol=1e-6):
            raise RuntimeError(f"Player {player_id}: bootstrap/history DC conflict")
        appearances = sum(row["minutes"] > 0 for row in observations[player_id])
        matches = sorted([row for row in completed if team_id in (int(row["team_h"]), int(row["team_a"]))],
                         key=lambda row: (str(row.get("kickoff_time") or ""), int(row["id"])))
        observed = {row["fixture_id"]: row["minutes"] for row in observations[player_id]}
        transferred = any(row["minutes"] > 0 and team_id not in (
            int(fixture_map[row["fixture_id"]]["team_h"]), int(fixture_map[row["fixture_id"]]["team_a"]))
            for row in observations[player_id])
        recent = matches[-6:]
        join_date = player.get("team_join_date")
        if join_date:
            try:
                joined_at = datetime.fromisoformat(str(join_date).replace("Z", "+00:00")).date()
            except ValueError as error:
                raise RuntimeError(f"Player {player_id}: invalid current-club join date") from error
            recent = [row for row in recent if datetime.fromisoformat(str(row["kickoff_time"]).replace("Z", "+00:00")).date() >= joined_at]
        if transferred:
            joined = min((fixture_id for fixture_id, value in observed.items() if value > 0
                          and team_id in (int(fixture_map[fixture_id]["team_h"]), int(fixture_map[fixture_id]["team_a"]))),
                         key=lambda fixture_id: str(fixture_map[fixture_id].get("kickoff_time") or ""), default=None)
            if joined is None:
                recent = []
            else:
                joined_time = str(fixture_map[joined].get("kickoff_time") or "")
                recent = [row for row in recent if str(row.get("kickoff_time") or "") >= joined_time]
        recent_minutes = [observed.get(int(row["id"]), 0.0) for row in recent]
        starts_by_gw = {int(row["gameweek"]): row["starts"] for row in totals}
        recent_starts = [min(1.0, starts_by_gw.get(int(row["event"]), 0) / sum(
            item["event"] == row["event"] for item in matches)) for row in recent]
        weights = [0.85 ** (len(recent_minutes) - index - 1) for index in range(len(recent_minutes))]
        denominator = sum(weights)
        mean = min(90.0, sum(value * weight for value, weight in zip(recent_minutes, weights)) / denominator) if denominator else None
        app = min(1.0, sum(weight for value, weight in zip(recent_minutes, weights) if value > 0) / denominator) if denominator else None
        p60 = min(1.0, sum(weight for value, weight in zip(recent_minutes, weights) if value >= 60) / denominator) if denominator else None
        chance, reason = availability(player)
        output[player_id] = {
            "player_id": player_id, "player_code": int(player["code"]),
            "name": (str(player.get("first_name", "")) + " " + str(player.get("second_name", ""))).strip() or str(player["web_name"]),
            "team_id": team_id, "team_name": str(teams[team_id]["name"]),
            "position": positions[int(player["element_type"])], "price": number(player["now_cost"], "price") / 10,
            "minutes": minutes, "actions": actions, "appearances": appearances,
            "average_minutes": minutes / appearances if appearances else None,
            "rate90": actions * 90 / minutes if minutes else None,
            "hits": sum(row["dc_hit"] for row in observations[player_id]),
            "recent_minutes": recent_minutes, "recent_mean": mean, "appearance_rate": app, "p60_rate": p60,
            "start_rate": sum(value * weight for value, weight in zip(recent_starts, weights)) / denominator if denominator else None,
            "availability": chance, "availability_reason": reason, "news": str(player.get("news") or ""),
            "news_added": player.get("news_added"), "transferred": transferred,
            "last_dc": next((row["dc"] for row in totals if row["gameweek"] == max(history_gws)), None) if history_gws else None,
        }
    snapshot = {
        "version": VERSION, "cutoff": cutoff, "next_gw": next_gw, "deadline": target["deadline_time"],
        "history_gameweeks": history_gws, "players": output, "teams": teams, "fixtures": fixtures,
        "event_ids": [int(event["id"]) for event in bootstrap["events"]],
        "source_hash": digest(material_state(bootstrap, fixtures)),
        "sources": [API_ROOT + "/bootstrap-static/", API_ROOT + "/fixtures/"]
                   + [API_ROOT + f"/event/{gameweek}/live/" for gameweek in history_gws],
        "rules_source": RULE_SOURCE, "projection_method": "Current-season DC/90 times recency-weighted official fixture minutes; Poisson threshold per fixture. Uncalibrated independent estimate.",
    }
    return snapshot


def capture_evidence(
    data: dict[str, Any],
    loader: Callable[[str], Any] = get_json,
    *,
    poll_interval_seconds: float = EVIDENCE_POLL_INTERVAL_SECONDS,
    max_wait_seconds: float = EVIDENCE_MAX_WAIT_SECONDS,
) -> dict[str, Any]:
    """
    Capture consistent official evidence, waiting for started fixtures to be verified final.

    The notebook's initial bootstrap/fixtures can become stale while a match is live.
    Refresh both official endpoints on every attempt; never bypass the final-statistics
    guard or build a snapshot from a partially updated Gameweek.
    """
    if data.get("api_fallback_used"):
        raise RuntimeError("Day 3 narration requires fresh official data; cached fallback is forbidden")
    if poll_interval_seconds < 0 or max_wait_seconds < 0:
        raise ValueError("Day 3 evidence wait intervals must be non-negative")

    requested_next_gw = int(data["next_gw"])
    wait_started = time.monotonic()

    while True:
        # Re-fetch official sources every attempt. A single snapshot can straddle
        # a live match's completion, so never reuse the notebook's older fixture map.
        bootstrap = loader("/bootstrap-static/")
        fixtures = loader("/fixtures/")
        if not isinstance(bootstrap, dict) or not isinstance(fixtures, list):
            raise RuntimeError("Official FPL bootstrap/fixtures responses have an unexpected shape")

        cutoff = datetime.now(timezone.utc).isoformat()
        target = _upcoming_event(bootstrap, cutoff)
        current_next_gw = int(target["id"])
        if current_next_gw != requested_next_gw:
            raise RuntimeError(
                "The official FPL deadline changed during Day 3 data capture "
                f"(started for GW{requested_next_gw}, now GW{current_next_gw}); "
                "restart Day 3 so all projections use one Gameweek."
            )

        unfinished = _unfinished_prior_fixtures(fixtures, current_next_gw, bootstrap)
        if unfinished:
            elapsed = time.monotonic() - wait_started
            remaining = max_wait_seconds - elapsed
            details = _describe_fixtures(unfinished, bootstrap)
            if remaining <= 0:
                raise RuntimeError(
                    f"Day 3 waited {max_wait_seconds / 60:.0f} minutes, but official FPL "
                    f"still reports earlier-Gameweek fixture(s) without verified final "
                    f"statistics: {details}. No video was rendered from incomplete data."
                )
            delay = min(poll_interval_seconds, remaining)
            print(
                f"[DAY 3] Waiting for official final statistics ({elapsed / 60:.1f} min elapsed; "
                f"retry in {delay:.0f}s): {details}"
            )
            time.sleep(delay)
            continue

        completed = _completed_prior_fixtures(fixtures, current_next_gw, bootstrap)
        history_gws = sorted({int(row["event"]) for row in completed})
        with ThreadPoolExecutor(max_workers=6) as executor:
            responses = list(executor.map(
                lambda gameweek: loader(f"/event/{gameweek}/live/"),
                history_gws,
            ))
        live_events = dict(zip(history_gws, responses))
        snapshot = build_evidence(bootstrap, fixtures, live_events, cutoff)
        snapshot["_event_payloads"] = live_events
        snapshot["_bootstrap"] = bootstrap
        if snapshot["next_gw"] != requested_next_gw:
            raise RuntimeError("The official deadline changed during data capture")
        return snapshot

def live_role(snapshot: dict[str, Any], player_id: int) -> dict[str, float]:
    player = snapshot["players"][int(player_id)]
    if player["recent_mean"] is None:
        if player["minutes"] > 0:
            raise RuntimeError(f"Player {player_id}: no current-club minutes evidence; do not fabricate a role")
        return {"mean": 0.0, "app": 0.0, "p60": 0.0, "start": 0.0, "sample": 0}
    return {"mean": player["recent_mean"], "app": player["appearance_rate"], "p60": player["p60_rate"],
            "start": min(player["appearance_rate"], player["start_rate"]),
            "sample": len(player["recent_minutes"])}


def player_projection(snapshot: dict[str, Any], player_id: int) -> dict[str, Any]:
    player = snapshot["players"][int(player_id)]
    upcoming = [row for row in snapshot["fixtures"] if row.get("event") == snapshot["next_gw"]
                and player["team_id"] in (row["team_h"], row["team_a"]) and not row.get("finished")]
    reason = player["availability_reason"]
    if not upcoming:
        return {"actions": 0.0, "dc_points": 0.0, "expected_minutes": 0.0, "reason": "BLANK_GAMEWEEK", "fixtures": []}
    if player["availability"] is None or player["recent_mean"] is None or player["rate90"] is None:
        return {"actions": None, "dc_points": None, "expected_minutes": None,
                "reason": reason if player["availability"] is None else "MISSING_CURRENT_SEASON_EVIDENCE", "fixtures": upcoming}
    chance = player["availability"]
    mean = player["recent_mean"] * chance
    app = player["appearance_rate"] * chance
    conditional_minutes = min(90, mean / app) if app else 0.0
    actions, probability = dc_forecast(player["rate90"], player["position"], [(0, 1 - app), (conditional_minutes, app)])
    if mean == 0 and chance > 0:
        reason = "NO_RECENT_APPEARANCES"
    elif actions == 0 and mean > 0:
        reason = "OBSERVED_ZERO_ACTION_RATE"
    return {"actions": actions * len(upcoming), "dc_points": 2 * probability * len(upcoming),
            "expected_minutes": mean * len(upcoming), "reason": reason, "fixtures": upcoming}


def team_context(snapshot: dict[str, Any], team_id: int) -> dict[str, Any]:
    completed = [row for row in snapshot["fixtures"] if row.get("event") in snapshot["history_gameweeks"] and row.get("finished")
                 and team_id in (row["team_h"], row["team_a"])]
    actions = conceded = clean_sheets = 0.0
    for fixture in completed:
        home = fixture["team_h"] == team_id
        dc = [item for item in fixture["stats"] if item["identifier"] == "defensive_contribution"]
        if len(dc) != 1:
            raise RuntimeError("Completed fixture lacks official team defensive-contribution evidence")
        actions += sum(number(item["value"], "fixture DC") for item in dc[0]["h" if home else "a"])
        goals = number(fixture["team_a_score" if home else "team_h_score"], "goals conceded")
        conceded += goals
        clean_sheets += int(goals == 0)
    forecasts = [player_projection(snapshot, player_id) for player_id, player in snapshot["players"].items()
                 if player["team_id"] == team_id and player["position"] in DC_THRESHOLDS and player["minutes"] > 0]
    projected = sum(row["actions"] for row in forecasts) if forecasts and all(row["actions"] is not None for row in forecasts) else None
    return {"team_id": team_id, "name": snapshot["teams"][team_id]["name"], "matches": len(completed),
            "actions": actions, "conceded": conceded, "clean_sheets": int(clean_sheets), "projection": projected}


def save_snapshot(snapshot: dict[str, Any], directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    public = {key: value for key, value in snapshot.items() if not key.startswith("_")}
    (directory / "day3_live_evidence.json").write_text(json.dumps(public, indent=2, allow_nan=False), encoding="utf-8")


def freeze_official_module(module: Any, snapshot: dict[str, Any]) -> None:
    import copy
    original_get = module._vx_get_json

    def frozen_get(session: Any, path: str) -> Any:
        if path == "/bootstrap-static/":
            return copy.deepcopy(snapshot["_bootstrap"])
        if path == "/fixtures/":
            return copy.deepcopy(snapshot["fixtures"])
        match = __import__("re").fullmatch(r"/event/(\d+)/live/", path)
        if match:
            gameweek = int(match.group(1))
            if gameweek not in snapshot["_event_payloads"]:
                raise RuntimeError(f"GW{gameweek} is outside the verified narration cutoff")
            return copy.deepcopy(snapshot["_event_payloads"][gameweek])
        return original_get(session, path)

    module._vx_get_json = frozen_get


def assert_snapshot_current(snapshot: dict[str, Any], loader: Callable[[str], Any] = get_json) -> None:
    cutoff = datetime.fromisoformat(snapshot["cutoff"].replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    deadline = datetime.fromisoformat(snapshot["deadline"].replace("Z", "+00:00"))
    if not 0 <= (now - cutoff).total_seconds() <= 6 * 3600 or now >= deadline:
        raise RuntimeError("Day 3 evidence is stale or its planning deadline has passed; regenerate")
    bootstrap = loader("/bootstrap-static/")
    fixtures = loader("/fixtures/")
    if digest(material_state(bootstrap, fixtures)) != snapshot["source_hash"]:
        raise RuntimeError("Official availability, identity or fixture evidence changed; regenerate before upload")


def audit_fixture_rows(frame: Any, snapshot: dict[str, Any]) -> None:
    fixtures = {int(row["id"]): row for row in snapshot["fixtures"]}
    seen: set[tuple[int, int]] = set()
    for row in frame.to_dict(orient="records"):
        player_id, fixture_id = int(row["player_id"]), int(row["fixture_id"])
        if (player_id, fixture_id) in seen:
            raise RuntimeError("Duplicate player-fixture identity in the expected-points engine")
        seen.add((player_id, fixture_id))
        if player_id not in snapshot["players"] or fixture_id not in fixtures:
            raise RuntimeError("Expected-points engine used an unknown official identity")
        player, fixture = snapshot["players"][player_id], fixtures[fixture_id]
        if (int(row["player_code"]) != player["player_code"] or int(row["team_id"]) != player["team_id"]
                or player["team_id"] not in (fixture["team_h"], fixture["team_a"])
                or int(row["gameweek"]) != fixture.get("event") or str(row["position"]) != player["position"]):
            raise RuntimeError("Model player, club, position or Gameweek mapping disagrees with official fixtures")
        minutes = number(row["expected_minutes"], "expected fixture minutes")
        appearance = number(row["appearance_probability"], "appearance probability")
        if appearance > 1 or minutes > 90 * appearance + 1e-6:
            raise RuntimeError("Expected minutes exceed possible appearance exposure")
        if int(row["gameweek"]) == snapshot["next_gw"]:
            if player["availability"] == 0 and minutes > 0:
                raise RuntimeError("A confirmed unavailable player received positive next-round minutes")
            if player["availability"] and (player["recent_mean"] or 0) > 0 and minutes == 0:
                raise RuntimeError(f"Player {player_id}: zero minutes contradicts fresh appearance evidence")
        if player["position"] in DC_THRESHOLDS and player["rate90"] is not None:
            expected_actions = player["rate90"] * minutes / 90
            actual_actions = number(row["defcon_expected_contributions"], "expected DC actions")
            if not math.isclose(actual_actions, expected_actions, abs_tol=1e-6):
                raise RuntimeError("Expected DC actions do not reconcile to official rate and fixture minutes")
