"""Resolve the manager's real 15-player squad from the public FPL API.

Day 3 must never build a transfer plan from a remembered squad. The GitHub
``workflow_dispatch`` OUT dropdowns are static YAML, and the production Drive
notebook keeps its own entry ID, so both can drift away from the team that is
actually on FPL. This module is the single checked-in source of truth.

Only public endpoints are used (no FPL login):

* ``/api/bootstrap-static/``            events, elements, teams
* ``/api/entry/<id>/history/``          chip usage (Free Hit detection)
* ``/api/entry/<id>/event/<gw>/picks/`` the submitted 15 for a Gameweek

``/api/my-team/<id>/`` is deliberately NOT used: it returns
``Authentication credentials were not provided`` without an FPL session.

A Free Hit squad is temporary, so the resolver walks back to the most recent
permanent 15. There is no cached or hardcoded squad fallback: if the official
data cannot be read, resolution fails loudly instead of rendering somebody
else's team.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

FPL_API_BASE = "https://fantasy.premierleague.com/api"
POSITION_SHORT = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
POSITION_ORDER = {"GK": 0, "DEF": 1, "MID": 2, "FWD": 3}
FREE_HIT_CHIPS = {"freehit", "freehit2"}

_HEADERS = {
    "User-Agent": "FPL-VORTEX/3.0 (public entry picks)",
    "Accept": "application/json",
    "Cache-Control": "no-cache, no-store",
    "Pragma": "no-cache",
}

Fetcher = Callable[[str], Any]


class LiveSquadError(RuntimeError):
    """Raised when the official FPL squad cannot be trusted."""


@dataclass(frozen=True)
class SquadPlayer:
    player_id: int
    web_name: str
    position: str
    team: str
    price: float
    status: str

    @property
    def choice(self) -> str:
        """The exact ``ID | Name | POS`` string used in workflow dropdowns."""
        return f"{self.player_id} | {self.web_name} | {self.position}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "player_id": self.player_id,
            "web_name": self.web_name,
            "position": self.position,
            "team": self.team,
            "price": self.price,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SquadPlayer":
        return cls(
            player_id=int(payload["player_id"]),
            web_name=str(payload["web_name"]),
            position=str(payload["position"]),
            team=str(payload["team"]),
            price=float(payload["price"]),
            status=str(payload.get("status") or "a"),
        )


@dataclass(frozen=True)
class LiveSquad:
    entry_id: int
    base_gw: int
    latest_visible_gw: int
    planning_gw: int
    free_hit_gws_skipped: tuple[int, ...]
    players: tuple[SquadPlayer, ...]

    @property
    def squad_ids(self) -> tuple[int, ...]:
        return tuple(player.player_id for player in self.players)

    @property
    def id_set(self) -> set[int]:
        return set(self.squad_ids)

    @property
    def choices(self) -> list[str]:
        ordered = sorted(
            self.players,
            key=lambda player: (
                POSITION_ORDER.get(player.position, 9),
                player.web_name.casefold(),
                player.player_id,
            ),
        )
        return [player.choice for player in ordered]

    @property
    def digest(self) -> str:
        return hashlib.sha256(
            ",".join(map(str, sorted(self.id_set))).encode("ascii")
        ).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "resolver": "FPL_ENTRY_PUBLIC_PICKS_V1",
            "entry_id": self.entry_id,
            "base_gw": self.base_gw,
            "latest_visible_gw": self.latest_visible_gw,
            "planning_gw": self.planning_gw,
            "free_hit_gws_skipped": list(self.free_hit_gws_skipped),
            "squad_digest": self.digest,
            "players": [player.to_dict() for player in self.players],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "LiveSquad":
        if not isinstance(payload, dict) or int(payload.get("schema_version", 0)) != 1:
            raise LiveSquadError("Unsupported live-squad snapshot payload")
        players = tuple(
            SquadPlayer.from_dict(dict(row)) for row in (payload.get("players") or [])
        )
        if len(players) != 15 or len({p.player_id for p in players}) != 15:
            raise LiveSquadError("Live-squad snapshot must contain 15 unique players")
        squad = cls(
            entry_id=int(payload["entry_id"]),
            base_gw=int(payload["base_gw"]),
            latest_visible_gw=int(payload["latest_visible_gw"]),
            planning_gw=int(payload["planning_gw"]),
            free_hit_gws_skipped=tuple(
                int(gw) for gw in (payload.get("free_hit_gws_skipped") or [])
            ),
            players=players,
        )
        if str(payload.get("squad_digest")) != squad.digest:
            raise LiveSquadError("Live-squad snapshot digest mismatch")
        return squad


def _default_fetcher(url: str) -> Any:
    """Read one public FPL JSON endpoint; ``None`` means 'not published yet'."""
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            request = urllib.request.Request(url, headers=_HEADERS)
            with urllib.request.urlopen(request, timeout=25) as response:
                status = int(getattr(response, "status", 200) or 200)
                if status == 404:
                    return None
                if status != 200:
                    raise LiveSquadError(f"FPL API returned HTTP {status}: {url}")
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            last_error = exc
        except Exception as exc:  # noqa: BLE001 - network failures are retried
            last_error = exc
        if attempt < 3:
            time.sleep(0.6 * (attempt + 1))
    raise LiveSquadError(f"FPL request failed after 4 attempts: {url}") from last_error


def _normalize_chip_name(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())


def resolve_live_squad(entry_id: int, *, fetcher: Fetcher | None = None) -> LiveSquad:
    """Return the manager's latest permanent 15 from the official FPL API."""
    fetch = fetcher or _default_fetcher
    entry_id = int(entry_id)
    if entry_id <= 0:
        raise LiveSquadError("FPL_ENTRY_ID must be a positive integer")

    def required(path: str, label: str) -> dict[str, Any]:
        payload = fetch(f"{FPL_API_BASE}{path}")
        if not isinstance(payload, dict) or not payload:
            raise LiveSquadError(f"Official FPL {label} response is unavailable")
        return payload

    bootstrap = required("/bootstrap-static/", "bootstrap-static")
    events = [event for event in (bootstrap.get("events") or []) if isinstance(event, dict)]
    if not events:
        raise LiveSquadError("Official FPL bootstrap has no events")
    elements = {
        int(element["id"]): element
        for element in (bootstrap.get("elements") or [])
        if element.get("id") is not None
    }
    teams = {
        int(team["id"]): str(team.get("short_name") or team.get("name") or team["id"])
        for team in (bootstrap.get("teams") or [])
        if team.get("id") is not None
    }
    if not elements or not teams:
        raise LiveSquadError("Official FPL bootstrap has no players or teams")

    history = required(f"/entry/{entry_id}/history/", "entry history")
    chips_by_event: dict[int, set[str]] = {}
    for chip in history.get("chips") or []:
        try:
            gw = int(chip.get("event"))
        except (TypeError, ValueError):
            continue
        name = _normalize_chip_name(chip.get("name"))
        if name:
            chips_by_event.setdefault(gw, set()).add(name)

    current = next((event for event in events if event.get("is_current")), None)
    finished_ids = [
        int(event["id"]) for event in events if event.get("id") and event.get("finished")
    ]
    if current is not None:
        upper_gw = int(current["id"])
    elif finished_ids:
        upper_gw = max(finished_ids)
    else:
        next_event = next((event for event in events if event.get("is_next")), None)
        upper_gw = max(1, int(next_event["id"]) - 1) if next_event else 1

    event_ids = sorted(
        {
            int(event["id"])
            for event in events
            if event.get("id") is not None and int(event["id"]) <= upper_gw
        },
        reverse=True,
    )
    if not event_ids:
        raise LiveSquadError("Could not determine a public FPL picks event")

    picks_cache: dict[int, dict[str, Any] | None] = {}

    def fetch_picks(gw: int) -> dict[str, Any] | None:
        gw = int(gw)
        if gw in picks_cache:
            return picks_cache[gw]
        payload = fetch(f"{FPL_API_BASE}/entry/{entry_id}/event/{gw}/picks/")
        rows = payload.get("picks") if isinstance(payload, dict) else None
        if not isinstance(rows, list) or len(rows) != 15:
            picks_cache[gw] = None
            return None
        try:
            ids = [int(row["element"]) for row in rows]
        except (KeyError, TypeError, ValueError):
            picks_cache[gw] = None
            return None
        if len(set(ids)) != 15:
            picks_cache[gw] = None
            return None
        picks_cache[gw] = payload
        return payload

    latest_visible_gw: int | None = None
    latest_payload: dict[str, Any] | None = None
    for gw in event_ids:
        payload = fetch_picks(gw)
        if payload is not None:
            latest_visible_gw, latest_payload = gw, payload
            break
    if latest_payload is None or latest_visible_gw is None:
        raise LiveSquadError(
            f"No public 15-player FPL squad is published for entry {entry_id} yet"
        )

    base_gw = int(latest_visible_gw)
    base_payload = latest_payload
    free_hit_gws: list[int] = []
    while True:
        active_chip = _normalize_chip_name(base_payload.get("active_chip"))
        event_chips = set(chips_by_event.get(base_gw, set()))
        is_free_hit = active_chip in FREE_HIT_CHIPS or bool(event_chips & FREE_HIT_CHIPS)
        if not is_free_hit:
            break
        free_hit_gws.append(base_gw)
        previous: tuple[int, dict[str, Any]] | None = None
        for gw in event_ids:
            if gw >= base_gw:
                continue
            payload = fetch_picks(gw)
            if payload is not None:
                previous = (int(gw), payload)
                break
        if previous is None:
            raise LiveSquadError(
                f"GW{base_gw} is a Free Hit but no earlier permanent squad is published"
            )
        base_gw, base_payload = previous

    players: list[SquadPlayer] = []
    for pick in base_payload["picks"]:
        player_id = int(pick["element"])
        element = elements.get(player_id)
        if element is None:
            raise LiveSquadError(f"FPL bootstrap has no metadata for player {player_id}")
        position_id = int(element.get("element_type", 0) or 0)
        players.append(
            SquadPlayer(
                player_id=player_id,
                web_name=str(
                    element.get("web_name") or element.get("second_name") or player_id
                ),
                position=POSITION_SHORT.get(position_id, "?"),
                team=teams.get(int(element.get("team", 0) or 0), "?"),
                price=float(element.get("now_cost", 0) or 0) / 10.0,
                status=str(element.get("status") or "a"),
            )
        )
    if len(players) != 15 or len({p.player_id for p in players}) != 15:
        raise LiveSquadError("The official FPL picks did not yield 15 unique players")

    next_event = next((event for event in events if event.get("is_next")), None)
    max_event_id = max(int(event["id"]) for event in events)
    planning_gw = (
        int(next_event["id"]) if next_event else min(base_gw + 1, max_event_id)
    )

    return LiveSquad(
        entry_id=entry_id,
        base_gw=base_gw,
        latest_visible_gw=int(latest_visible_gw),
        planning_gw=planning_gw,
        free_hit_gws_skipped=tuple(free_hit_gws),
        players=tuple(players),
    )


def _split_tokens(value: str | Iterable[object] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned or cleaned.upper() == "NONE":
            return []
        return [part.strip() for part in re.split(r"[,;\n]+", cleaned) if part.strip()]
    return [str(item).strip() for item in value if str(item).strip()]


def parse_player_choice(value: str | int, squad: LiveSquad) -> int:
    """Resolve ``"ID | Name | POS"``, a bare ID, or a squad player's name."""
    text = str(value or "").strip()
    if not text or text.upper() == "NONE":
        raise LiveSquadError("Empty player choice")
    leading = re.match(r"^\s*(\d+)\b", text)
    if leading:
        player_id = int(leading.group(1))
        if player_id > 0:
            return player_id
    if "|" in text:
        parts = [part.strip() for part in text.split("|")]
        if len(parts) > 1:
            text = parts[1]

    def key(name: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", name.casefold())

    wanted = key(text)
    matches = [player for player in squad.players if key(player.web_name) == wanted]
    if len(matches) == 1:
        return matches[0].player_id
    raise LiveSquadError(
        f"Player choice {value!r} is neither an ID nor a name in the live FPL squad"
    )


def validate_transfer_selections(
    squad: LiveSquad,
    outs: str | Iterable[object] | None,
    ins: str | Iterable[object] | None,
) -> tuple[list[int], list[int]]:
    """Fail unless every OUT is owned and every IN is new; return normalized IDs."""
    out_ids = [parse_player_choice(token, squad) for token in _split_tokens(outs)]
    in_ids = [parse_player_choice(token, squad) for token in _split_tokens(ins)]
    if not 1 <= len(out_ids) <= 5 or len(out_ids) != len(in_ids):
        raise LiveSquadError(
            f"Manual transfers need 1–5 complete OUT/IN pairs, got "
            f"{len(out_ids)} OUT and {len(in_ids)} IN"
        )
    if len(set(out_ids)) != len(out_ids) or len(set(in_ids)) != len(in_ids):
        raise LiveSquadError("A player cannot be selected more than once in OUT/IN")
    if set(out_ids) & set(in_ids):
        raise LiveSquadError("A player cannot appear in both OUT and IN")

    owned = squad.id_set
    unknown_outs = [pid for pid in out_ids if pid not in owned]
    if unknown_outs:
        raise LiveSquadError(
            f"Player OUT {unknown_outs} is not in your live FPL squad "
            f"(entry {squad.entry_id}, GW{squad.base_gw}). "
            "Refresh the Day 3 OUT choices from the official FPL API. "
            "Live 15: " + " / ".join(squad.choices)
        )
    already_owned = [pid for pid in in_ids if pid in owned]
    if already_owned:
        raise LiveSquadError(
            f"Player IN {already_owned} is already in your live FPL squad "
            f"(entry {squad.entry_id}, GW{squad.base_gw})"
        )
    return out_ids, in_ids


def describe(squad: LiveSquad) -> str:
    lines = [
        f"Live FPL squad • entry {squad.entry_id} • GW{squad.base_gw} "
        f"(visible GW{squad.latest_visible_gw}, planning GW{squad.planning_gw}) "
        f"• digest {squad.digest}"
    ]
    if squad.free_hit_gws_skipped:
        lines.append(
            "Free Hit gameweeks skipped: "
            + ", ".join(f"GW{gw}" for gw in squad.free_hit_gws_skipped)
        )
    lines.extend(f"  {choice}" for choice in squad.choices)
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Resolve the live FPL squad for a Day 3 run."
    )
    parser.add_argument("--entry-id", type=int, required=True)
    parser.add_argument("--out-json", type=Path, default=None)
    args = parser.parse_args(argv)
    squad = resolve_live_squad(args.entry_id)
    print(describe(squad))
    if args.out_json is not None:
        args.out_json.parent.mkdir(parents=True, exist_ok=True)
        args.out_json.write_text(
            json.dumps(squad.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Live squad snapshot written to {args.out_json}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    try:
        sys.exit(main())
    except LiveSquadError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
