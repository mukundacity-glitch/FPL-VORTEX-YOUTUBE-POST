from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from day3.live_evidence import collect, date


def number(value: Any) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def chance_field(events: list[dict[str, Any]], gameweek: int) -> str | None:
    for flag, field in (
        ("is_current", "chance_of_playing_this_round"),
        ("is_next", "chance_of_playing_next_round"),
    ):
        if any(row.get(flag) is True and int(row["id"]) == gameweek for row in events):
            return field
    return None


def player_health(
    player: dict[str, Any], events: list[dict[str, Any]], gameweek: int, *, verified: bool,
) -> dict[str, Any]:
    status = str(player.get("status") or "").strip().lower()
    field = chance_field(events, gameweek)
    raw_chance = player.get(field) if field else None
    chance = number(raw_chance)
    invalid_chance = raw_chance is not None and (chance is None or not 0 <= chance <= 100)
    if invalid_chance:
        chance = None
    news = str(player.get("news") or "").strip()
    labels = {"i": "INJURED", "s": "SUSPENDED", "u": "UNAVAILABLE", "n": "UNAVAILABLE"}
    # Explicit provider status takes precedence over any contradictory percentage.
    blocked = status in labels or chance == 0
    if blocked:
        label, color, probability = labels.get(status, "UNAVAILABLE"), "red", 0.0
    elif not verified or status not in {"a", "d"} or invalid_chance:
        label, color, probability = "STATUS UNVERIFIED", "grey", 0.0
    elif status == "d" or (chance is not None and chance < 100):
        label, color = "DOUBTFUL", "yellow"
        probability = chance / 100 if chance is not None else 0.0
    elif field is None:
        label, color, probability = "ROUND UNVERIFIED", "grey", 0.0
    else:
        label, color, probability = "AVAILABLE", "none", 1.0
    if not verified:
        label, color, probability = "STATUS UNVERIFIED", "grey", 0.0
    health_clear = verified and label == "AVAILABLE"
    return {
        "player_id": int(player["id"]),
        "name": str(player.get("web_name") or player.get("second_name") or player["id"]),
        "team_id": int(player["team"]),
        "status": status,
        "label": label,
        "color": color,
        "news": news,
        "news_added": str(player.get("news_added") or ""),
        "chance_field": field,
        "chance_percent": chance,
        "probability": probability,
        "verified": bool(verified),
        "health_clear": bool(health_clear),
        "blocked": bool(blocked),
        "recommendation_eligible": False,
        "starting_status": "NOT YET ASSESSED",
        "reason": label.lower().capitalize() + (": " + news if news else ""),
    }


class AvailabilityContext:
    def __init__(
        self, bootstrap: dict[str, Any], fixtures: pd.DataFrame, gameweek: int,
        source_state: dict[str, Any], *, fetched_at: str | None = None,
        research: dict[str, Any] | None = None,
    ) -> None:
        self.gameweek = int(gameweek)
        self.fetched_at = fetched_at or datetime.now(timezone.utc).isoformat()
        self.source = dict(source_state)
        self.research = research
        self.official_players = {int(player["id"]): dict(player) for player in bootstrap.get("elements", [])}
        self.positions = {int(row["id"]): str(row["singular_name_short"]).replace("GKP", "GK")
                          for row in bootstrap.get("element_types", [])}
        self.verified = source_state.get("source") == "LIVE_FPL_API" and not source_state.get("fallback_used", True)
        self.players = {
            int(player["id"]): player_health(player, bootstrap.get("events", []), self.gameweek,
                                              verified=self.verified)
            for player in bootstrap.get("elements", [])
        }
        self.fixtures = fixtures.copy()
        self.bound = False
        if research is not None:
            self.apply_research()

    def apply_research(self) -> None:
        assert self.research is not None
        checked = date(self.research.get("checked_at"))
        fresh = checked is not None and 0 <= (datetime.now(timezone.utc) - checked).total_seconds() <= 3600
        for player_id, state in self.players.items():
            player = self.official_players[player_id]
            reports = self.research.get("news", {}).get("players", {}).get(str(player_id), [])
            coverage = self.research.get("news", {}).get("coverage", {}).get(str(state["team_id"]), {})
            state.update(research_reports=reports, evidence_checked_at=self.research.get("checked_at"),
                         official_position=self.positions.get(int(player["element_type"])))
            if not fresh or self.research.get("gameweek") != self.gameweek:
                state.update(health_clear=False, label="EVIDENCE STALE", color="grey", reason="Current Gameweek research needs refreshing.")
            elif player.get("can_select") is False or player.get("removed") is True:
                state.update(health_clear=False, blocked=True, label="NOT SELECTABLE", color="red",
                             reason="Official FPL marks this player unavailable for selection.")
            elif state["health_clear"] and player.get("scout_risks"):
                state.update(health_clear=False, label="OFFICIAL SCOUT RISK", color="yellow",
                             reason="Official FPL lists a current risk that needs checking before a recommendation.")
            elif state["health_clear"] and any(report.get("unresolved_concern") for report in reports):
                state.update(health_clear=False, label="TEAM NEWS CHECK", color="yellow",
                             reason="Recent team news needs checking against official status and role forecasts.")
            elif state["health_clear"] and not any(coverage.values()):
                state.update(health_clear=False, label="RESEARCH INCOMPLETE", color="grey",
                             reason="Current club and credible team-news coverage could not be checked.")
            if not state["health_clear"]:
                state["probability"] = 0.0

    def current_history(self, player_id: int) -> list[dict[str, Any]]:
        if self.research is None:
            return []
        player = self.official_players.get(player_id)
        if not player:
            return []
        fixtures = {int(row["id"]): row for row in self.research.get("fixtures", [])}
        joined_raw = str(player.get("team_join_date", ""))
        joined = date(joined_raw) or date(joined_raw + "T00:00:00+00:00")
        result = []
        for row in self.research.get("histories", {}).get(str(player_id), {}).get("history", []):
            fixture = fixtures.get(int(row.get("fixture", -1)))
            played = date(row.get("kickoff_time"))
            if not fixture or fixture.get("finished") is not True or played is None or played > datetime.now(timezone.utc):
                continue
            own_team = fixture.get("team_h") if row.get("was_home") is True else fixture.get("team_a")
            if int(own_team or -1) != int(player["team"]) or joined is not None and played < joined:
                continue
            if number(row.get("starts")) not in {0.0, 1.0} or number(row.get("minutes")) is None:
                continue
            result.append(dict(row))
        return sorted(result, key=lambda row: (row["kickoff_time"], int(row["fixture"])))

    def model_roles(self, existing: pd.DataFrame, player_id: int, player_code: int, season: str) -> pd.DataFrame:
        if self.research is None:
            return existing
        rows = []
        for row in self.current_history(player_id):
            age = max(0.0, (datetime.now(timezone.utc) - date(row["kickoff_time"])).total_seconds() / 86400)
            rows.append({"player_code": player_code, "season_label": season,
                         "match_id": f'official-prem-{int(row["fixture"])}', "match_date": row["kickoff_time"],
                         "minutes_played": row["minutes"], "is_starting": row["starts"] == 1,
                         "appeared": row["minutes"] > 0, "played_60": row["minutes"] >= 60,
                         "recency_weight": math.exp(-math.log(2) * age / 30),
                         "rest_days_since_prior_role": float("nan")})
        # Official current-club starts supersede stale or inferred Core lineups.
        return pd.DataFrame(rows, columns=list(existing.columns) or None)

    def state(self, player_id: Any) -> dict[str, Any]:
        player_id = number(player_id)
        if player_id is not None and int(player_id) in self.players:
            return self.players[int(player_id)]
        return {
            "player_id": player_id, "name": "Player", "label": "STATUS UNVERIFIED",
            "color": "grey", "news": "", "probability": 0.0, "verified": False,
            "health_clear": False, "blocked": False, "recommendation_eligible": False,
            "starting_status": "NO CURRENT EVIDENCE", "reason": "Current player status is unverified.",
        }

    def probability(self, player_id: Any) -> float:
        return float(self.state(player_id)["probability"])

    def eligible(self, player_id: Any) -> bool:
        return bool(self.state(player_id)["recommendation_eligible"])

    def bind_model(
        self, features: pd.DataFrame, roles: pd.DataFrame, official_players: pd.DataFrame,
        season: str,
    ) -> None:
        upcoming_teams: set[int] = set()
        latest_completed: dict[int, pd.Timestamp] = {}
        fixtures = self.fixtures
        if {"event", "team_h", "team_a"}.issubset(fixtures.columns):
            upcoming = fixtures.loc[pd.to_numeric(fixtures["event"], errors="coerce").eq(self.gameweek)]
            upcoming_teams = set(pd.to_numeric(upcoming.team_h).astype(int)) | set(pd.to_numeric(upcoming.team_a).astype(int))
            if {"finished", "kickoff_time"}.issubset(fixtures.columns):
                done = fixtures.loc[fixtures["finished"].eq(True)].copy()
                done["_kickoff"] = pd.to_datetime(done.kickoff_time, utc=True, errors="coerce")
                for row in done.dropna(subset=["_kickoff"]).to_dict("records"):
                    for team in (int(row["team_h"]), int(row["team_a"])):
                        latest_completed[team] = max(latest_completed.get(team, row["_kickoff"]), row["_kickoff"])

        role_by_id: dict[int, dict[str, Any]] = {}
        required = {"player_code", "season_label", "match_id", "match_date", "minutes_played", "is_starting"}
        if required.issubset(roles.columns) and {"id", "code"}.issubset(official_players.columns):
            history = roles.copy()
            history["_date"] = pd.to_datetime(history.match_date, utc=True, errors="coerce")
            season_start = str(season).replace("/", "-").split("-")[0]
            current = history.season_label.astype(str).str.replace("/", "-", regex=False).str.split("-").str[0].eq(season_start)
            history = history.loc[current & history.match_id.astype(str).str.contains("-prem-", case=False, regex=False)].dropna(subset=["_date"])
            history = history.loc[history["_date"].le(pd.Timestamp.now(tz="UTC"))]
            code_to_id = dict(zip(official_players.code.astype(int), official_players.id.astype(int)))
            history["player_id"] = pd.to_numeric(history.player_code, errors="coerce").map(code_to_id)
            for row in history.sort_values(["_date", "match_id"]).drop_duplicates("player_id", keep="last").to_dict("records"):
                if pd.notna(row["player_id"]):
                    role_by_id[int(row["player_id"])] = row

        if self.research is not None:
            role_by_id.clear()
            for player_id in self.players:
                history = self.current_history(player_id)
                if history:
                    row = history[-1]
                    role_by_id[player_id] = dict(row, _date=pd.Timestamp(row["kickoff_time"]),
                                                 is_starting=row["starts"] == 1, minutes_played=row["minutes"])

        for model in features.to_dict("records"):
            player_id = int(model["player_id"])
            state = self.state(player_id)
            if player_id not in self.players:
                continue
            start = number(model.get("start_probability"))
            minutes = number(model.get("expected_minutes"))
            latest = role_by_id.get(player_id)
            last_start = latest is not None and str(latest.get("is_starting")).lower() in {"true", "1", "1.0"}
            last_minutes = number(latest.get("minutes_played")) if latest else None
            team_last = latest_completed.get(state["team_id"])
            recent = bool(latest) and (team_last is None or latest["_date"].date() >= team_last.date())
            secure = (
                start is not None and start >= 0.70 and minutes is not None and minutes >= 70
                and last_start and last_minutes is not None and last_minutes >= 60 and recent
            )
            has_fixture = state["team_id"] in upcoming_teams
            identity_ok = number(model.get("team_id")) in (None, state["team_id"])
            if self.research is not None:
                identity_ok = identity_ok and str(model.get("position")) == state.get("official_position")
            state.update(
                start_probability=start, expected_minutes=minutes,
                last_started=bool(last_start), last_minutes=last_minutes,
                latest_role_date=latest["_date"].isoformat() if latest else None,
                has_fixture=has_fixture,
                starting_status="PROJECTED STARTER" if secure else "MINUTES RISK",
                recommendation_eligible=bool(state["health_clear"] and has_fixture and secure and identity_ok),
                role_evidence="OFFICIAL_FPL_CURRENT_CLUB_HISTORY" if self.research is not None and latest else "CORE_LEAGUE_HISTORY",
            )
            if state["health_clear"] and not has_fixture:
                state.update(label="BLANK GAMEWEEK", color="yellow", reason="No fixture in the target Gameweek.")
            elif state["health_clear"] and not secure:
                state.update(label="MINUTES RISK", color="yellow", reason="A secure starting role is not supported by current forecasts and the latest completed league lineup.")
            elif state["recommendation_eligible"]:
                state["reason"] = (
                    f"Available; projected start probability {100 * start:.0f} percent and "
                    f"{minutes:.0f} expected minutes. Starting eleven is a forecast, not a confirmed lineup."
                )
        self.bound = True

    def validate_projections(self, frame: pd.DataFrame) -> pd.DataFrame:
        result = frame.copy()
        fixtures = {int(row["id"]): row for row in self.fixtures.to_dict("records")
                    if number(row.get("event")) == self.gameweek}
        statuses = []
        for row in result.to_dict("records"):
            player_id = int(row["player_id"])
            player = self.official_players.get(player_id, {})
            fixture_value = number(row.get("fixture_id"))
            fixture = fixtures.get(int(fixture_value)) if fixture_value is not None else None
            status = "VERIFIED_MODEL"
            if number(row.get("team_id")) != number(player.get("team")) or row.get("position") != self.positions.get(int(player.get("element_type", 0))):
                status = "IDENTITY_OR_TRANSFER_MISMATCH"
            elif "player_code" in row and number(row.get("player_code")) != number(player.get("code")):
                status = "IDENTITY_OR_TRANSFER_MISMATCH"
            elif not fixture or int(player.get("team", -1)) not in {int(fixture["team_h"]), int(fixture["team_a"])}:
                status = "FIXTURE_MISMATCH"
            elif row.get("calculation_status") != "READY" or number(row.get("gameweek")) != self.gameweek:
                status = "MODEL_NOT_READY"
            elif any(number(row.get(key)) is None or number(row.get(key)) < 0 for key in (
                    "fixture_expected_points", "expected_minutes", "start_probability", "defcon_expected_contributions", "defcon_points")):
                status = "MISSING_MODEL_INPUT"
            elif number(row["expected_minutes"]) > 90 or number(row["start_probability"]) > 1:
                status = "INVALID_MINUTES_FORECAST"
            elif not self.state(player_id)["verified"]:
                status = "STATUS_UNVERIFIED"
            elif number(row.get("defcon_expected_contributions")) == 0 and not self.state(player_id)["blocked"]:
                history = self.current_history(player_id)
                if not history or not (all(number(item.get("minutes")) == 0 for item in history)
                                       or all(number(item.get("defensive_contribution")) == 0 for item in history)):
                    status = "ZERO_REQUIRES_VALIDATION"
            statuses.append(status)
        result["projection_status"] = statuses
        result["projection_verified"] = result.projection_status.eq("VERIFIED_MODEL")
        groups = dict(tuple(result.loc[pd.to_numeric(result.gameweek).eq(self.gameweek)].groupby("player_id")))
        for player_id in self.players:
            group = groups.get(player_id, result.iloc[:0])
            state = self.state(player_id)
            expected = {fid for fid, fixture in fixtures.items() if state.get("team_id") in {fixture["team_h"], fixture["team_a"]}}
            valid = bool(len(group)) and group.projection_verified.all() and not group.fixture_id.duplicated().any() and set(group.fixture_id.astype(int)) == expected
            state["projection_verified"] = bool(valid)
            if not valid:
                state["recommendation_eligible"] = False
                if state["health_clear"] and state.get("has_fixture"):
                    state.update(label="PROJECTION UNVERIFIED", color="grey",
                                 reason="A complete, current fixture forecast is not verified.")
        return result

    def eligible_ids(self) -> set[int]:
        return {player_id for player_id in self.players if self.eligible(player_id)}

    def annotate(self, frame: pd.DataFrame) -> pd.DataFrame:
        out = frame.copy()
        if "player_id" not in out:
            raise RuntimeError("Availability annotation requires player_id")
        out["recommendation_eligible"] = out.player_id.map(self.eligible)
        out["official_status_label"] = out.player_id.map(lambda pid: self.state(pid)["label"])
        out["official_status_news"] = out.player_id.map(lambda pid: self.state(pid)["news"])
        return out

    def caution(self, player_id: Any, *, include_news: bool = True) -> str:
        state = self.state(player_id)
        name = str(state["name"])
        reason = state["reason"] if include_news else state["label"].lower().capitalize() + "."
        # Several cards can share a status or provider notice; keep every sentence tied to its player.
        sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", reason)
                     if sentence.strip()]
        message = " ".join(f"{name}: {sentence.rstrip('.!?')}." for sentence in sentences)
        if include_news and state["label"] == "MINUTES RISK":
            evidence = []
            start = number(state.get("start_probability"))
            minutes = number(state.get("expected_minutes"))
            if start is not None and 0 <= start <= 1:
                evidence.append(f"a {100 * start:.0f} percent start probability")
            if minutes is not None and 0 <= minutes <= 90:
                evidence.append(f"{minutes:.0f} expected minutes")
            if evidence:
                message += f" The current forecast for {name} is " + " and ".join(evidence) + "."
        if state["blocked"] or not state["health_clear"]:
            message += f" Reassess {name} only after an official availability update; a stated return date does not confirm fitness or a start."
        elif not state["recommendation_eligible"]:
            message += f" Wait for stronger minutes evidence before treating {name} as a target."
        return message

    def public_registry(self) -> dict[str, Any]:
        return {str(player_id): dict(state) for player_id, state in self.players.items()}

    def save_audit(self, folder: Path) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "player_availability_audit.json").write_text(json.dumps({
            "source": self.source, "fetched_at": self.fetched_at, "gameweek": self.gameweek,
            "players": self.public_registry(),
        }, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        if self.research is not None:
            (folder / "live_analysis_evidence.json").write_text(json.dumps(self.research, ensure_ascii=False,
                                                                         indent=2, allow_nan=False), encoding="utf-8")


def install_availability(namespace: dict[str, Any]) -> AvailabilityContext:
    data = namespace["data"]
    research = collect(data["bootstrap"], namespace["fixtures"].to_dict("records"), int(namespace["NEXT_GW"]))
    context = AvailabilityContext(
        data["bootstrap"], namespace["fixtures"], int(namespace["NEXT_GW"]),
        namespace.get("FPL_API_SOURCE_STATUS", {}).get("/bootstrap-static/", {}),
        research=research,
    )
    namespace["DAY3_AVAILABILITY"] = context
    return context

