from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


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
    ) -> None:
        self.gameweek = int(gameweek)
        self.fetched_at = fetched_at or datetime.now(timezone.utc).isoformat()
        self.source = dict(source_state)
        self.verified = source_state.get("source") == "LIVE_FPL_API" and not source_state.get("fallback_used", True)
        self.players = {
            int(player["id"]): player_health(player, bootstrap.get("events", []), self.gameweek,
                                              verified=self.verified)
            for player in bootstrap.get("elements", [])
        }
        self.fixtures = fixtures.copy()
        self.bound = False

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
            state.update(
                start_probability=start, expected_minutes=minutes,
                last_started=bool(last_start), last_minutes=last_minutes,
                latest_role_date=latest["_date"].isoformat() if latest else None,
                has_fixture=has_fixture,
                starting_status="PROJECTED STARTER" if secure else "MINUTES RISK",
                recommendation_eligible=bool(state["health_clear"] and has_fixture and secure),
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
        message = state["reason"] if include_news else state["label"].lower().capitalize() + "."
        if state["blocked"] or not state["health_clear"]:
            message += " Reassess only after an official availability update; a stated return date does not confirm fitness or a start."
        elif not state["recommendation_eligible"]:
            message += " Wait for stronger minutes evidence before treating him as a target."
        return message

    def public_registry(self) -> dict[str, Any]:
        return {str(player_id): dict(state) for player_id, state in self.players.items()}

    def save_audit(self, folder: Path) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "player_availability_audit.json").write_text(json.dumps({
            "source": self.source, "fetched_at": self.fetched_at, "gameweek": self.gameweek,
            "players": self.public_registry(),
        }, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def install_availability(namespace: dict[str, Any]) -> AvailabilityContext:
    data = namespace["data"]
    context = AvailabilityContext(
        data["bootstrap"], namespace["fixtures"], int(namespace["NEXT_GW"]),
        namespace.get("FPL_API_SOURCE_STATUS", {}).get("/bootstrap-static/", {}),
    )
    namespace["DAY3_AVAILABILITY"] = context
    return context
