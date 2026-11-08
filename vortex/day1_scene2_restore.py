"""Day 1 Scene 2 full-squad pitch / Hero Card production contract.

A non-destructive adapter for the existing HTML pitch + VXPlayerCard runtime.
The output contains animation instructions, not a rendered MP4. All player
identities, results and narration timing must originate in the episode snapshot.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import math

REVIEW_SEQUENCE = (
    "chapter", "results", "pitch_reveal", "starting_xi",
    "captaincy", "bench", "rank_arrows", "review_table",
    "transfers", "full_squad_recap", "scene3_transition",
)


def _number(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} is missing or invalid") from exc
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{label} must be a nonnegative finite number")
    return number


def build_scene2_manifest(
    *,
    gameweek: int,
    starters: list[dict[str, Any]],
    bench: list[dict[str, Any]],
    narration: list[dict[str, Any]],
    captain_id: int,
    vice_captain_id: int,
    captain_multiplier: int,
    gameweek_table: dict[str, Any],
    rank_movement: dict[str, Any] | None,
    transfers: list[dict[str, Any]],
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Produce the exact cue map for the existing pitch/hero runtime.

    The original Hero Card is first shown in the LEFT spotlight. During the
    player's narrated beat it animates INTO the assigned pitch or bench slot
    and stays there. Unlike a standard pop-out animation this is progressive
    squad assembly. All cue times are measured narration times, not guesses.
    """
    if not 1 <= gameweek <= 38:
        raise ValueError("Invalid reviewed Gameweek")
    if len(starters) != 11 or len(bench) != 4:
        raise ValueError("Scene 2 requires exactly 11 starters and four bench players")
    squad = starters + bench
    ids = [p.get("id") for p in squad]
    if any(not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0 for pid in ids) or len(set(ids)) != 15:
        raise ValueError("Original FPL squad identities must be 15 unique player ids")
    if captain_id not in ids[:11] or vice_captain_id not in ids or captain_id == vice_captain_id:
        raise ValueError("Captain/vice captain do not match original picks")
    if captain_multiplier not in (1, 2, 3):
        raise ValueError("Captain multiplier requires official verification (1, 2 or 3)")
    for p in squad:
        for field in ("id", "name", "position", "gw_points", "minutes", "club"):
            if field not in p or p[field] is None or p[field] == "":
                raise ValueError(f"Missing verified {field} for player {p['id']}")
        _number(p["gw_points"], f"points {p['id']}")
        _number(p["minutes"], f"minutes {p['id']}")
        if "slot" not in p:
            raise ValueError(f"Missing original formation/bench slot for {p['id']}")
    if len(narration) != 15 or [beat.get("player_id") for beat in narration] != ids:
        raise ValueError("Narration must contain one ordered beat for each of the 15 players")

    player_beats = []
    previous_end = 0.0
    for index, (p, beat) in enumerate(zip(squad, narration)):
        start = _number(beat.get("start"), f"start {p['id']}")
        end = _number(beat.get("end"), f"end {p['id']}")
        if end <= start or start < previous_end:
            raise ValueError(f"Overlapping or invalid player narration for {p['id']}")
        previous_end = end
        length = end - start
        # The original Hero Card is visible before the move, and stays
        # permanently in its formation slot after arrival.
        introduction = min(0.8, length * 0.18)
        flight = min(0.85, length * 0.18)
        arrival = min(end, start + introduction + flight)
        player_beats.append({
            "player_id": p["id"],
            "name": p["name"],
            "role": "starter" if index < 11 else "bench",
            "slot": p["slot"],
            "hero_component": "VXPlayerCard",
            "left_hero_enter": start,
            "left_hero_exit": start + introduction,
            "pitch_flight_start": start + introduction,
            "pitch_arrival": arrival,
            "points_reveal": min(end, start + min(2.0, length * 0.42)),
            "narration_start": start,
            "narration_end": end,
            "persist_in_pitch": True,
            "actual_points": p["gw_points"],
            "captain": p["id"] == captain_id,
            "vice": p["id"] == vice_captain_id,
            "narration_text": beat.get("text") or "",
        })
        if not player_beats[-1]["narration_text"].strip():
            raise ValueError(f"Player {p['id']} has no spoken explanation")

    required_table = ("gw_points", "captain_points", "bench_points", "net_points")
    missing = [k for k in required_table if gameweek_table.get(k) is None]
    if missing:
        raise ValueError(f"Missing original verified Gameweek data table: {', '.join(missing)}")
    if rank_movement:
        prior, current = rank_movement.get("previous"), rank_movement.get("current")
        if prior is not None and current is not None:
            if int(prior) <= 0 or int(current) <= 0:
                raise ValueError("Ranks must be positive")
            rank_movement = {**rank_movement, "direction": (
                "green_up" if int(current) < int(prior)
                else "red_down" if int(current) > int(prior) else "unchanged"
            )}
        else:
            rank_movement = {**rank_movement, "direction": "unavailable"}
    else:
        rank_movement = {"direction": "unavailable"}
    for transfer in transfers:
        if transfer.get("status") not in ("completed", "potential"):
            raise ValueError("Transfers must distinguish completed from potential")
        if transfer["status"] == "completed" and not transfer.get("verified"):
            raise ValueError("Do not claim an unverified transfer was completed")
    for match in results:
        if not all(k in match for k in ("home", "away", "home_score", "away_score", "status")):
            raise ValueError("Match results must come from verified fixture records")

    return {
        "scene": "day1_scene2",
        "gameweek": gameweek,
        "existing_opening_modified": False,
        "scene3_modified": False,
        "original_pitch_runtime": "existing HTML pitch",
        "original_hero_runtime": "VXPlayerCard",
        "progressive_roster": True,
        "sequence": list(REVIEW_SEQUENCE),
        "players": player_beats,
        "captaincy": {
            "captain_id": captain_id,
            "vice_captain_id": vice_captain_id,
            "verified_multiplier": captain_multiplier,
            "counted_points_must_follow_final_chip_and_autosub_state": True,
        },
        "gameweek_table": gameweek_table,
        "rank_movement": rank_movement,
        "transfers": transfers,
        "results": results,
        "final_pitch_player_ids": ids,
        "render_status": "NOT_RENDERED",
    }
