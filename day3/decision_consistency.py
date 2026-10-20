"""Reconcile Day 3 market SELL activity with independent start/bench advice."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def bench_sell_note(
    player_id: int,
    decision: str,
    sell_records: Sequence[Mapping[str, Any]],
    availability: Mapping[str, Any],
    *,
    player_name: str,
    expected_points: float,
    fixture_difficulty: float,
) -> str:
    """Explain a SELL overlap without equating a transfer decision with lineup advice."""
    matching = [
        record for record in sell_records
        if str(record.get("player_id")) == str(int(player_id))
    ]
    if not matching:
        return ""

    name = str(player_name).strip() or "This player"
    analysis = matching[0].get("sell_analysis") or {}
    assessment = str(analysis.get("assessment") or "MARKET_ONLY").upper()
    reasons = analysis.get("reasons") or []
    first_reason = next(
        (str(reason.get("short") or "").strip().lower()
         for reason in reasons if isinstance(reason, Mapping) and reason.get("short")),
        "",
    )
    reason_phrase = f" over {first_reason}" if first_reason else ""
    fixture = float(fixture_difficulty)
    points = float(expected_points)

    # The board itself requires verified availability and starting-role evidence.
    # If either section has contrary status, never promote the player to START.
    fit = (availability.get("recommendation_eligible") is True
           and availability.get("health_clear") is True
           and availability.get("blocked") is not True)
    if not fit or assessment in {"AVAILABILITY_FIRST", "CONDITIONAL_REVIEW"}:
        return (
            f"{name} is also on the transfer-out watchlist, but current availability "
            "or starting-role evidence does not support recommending a start."
        )

    if decision == "START":
        if assessment == "MARKET_ONLY":
            return (
                f"Despite transfers out for {name}, market activity alone is not a sell reason; "
                f"if you keep him, this {points:.1f}-point projection supports a start with a {fixture:.1f} fixture rating."
            )
        if assessment == "PATIENCE_CASE":
            return (
                f"Despite the sell watchlist, {name} has a case for patience; "
                f"if you retain him, his {points:.1f}-point projection supports starting against this {fixture:.1f}-rated fixture."
            )
        return (
            f"Although {name} is on the sell watchlist{reason_phrase}, "
            f"if you keep him, his {points:.1f}-point projection still puts him in the start group "
            f"for this {fixture:.1f}-rated fixture."
        )
    if decision == "BENCH":
        if assessment == "MARKET_ONLY":
            return (
                f"{name} is also seeing transfers out, but that alone does not justify selling; "
                f"if you keep him, benching is preferred in this {fixture:.1f}-rated fixture."
            )
        return (
            f"{name} is also on the sell watchlist{reason_phrase}; "
            f"if you keep him, benching is preferred against this {fixture:.1f}-rated fixture."
        )
    raise ValueError(f"Unsupported Day 3 benching decision: {decision!r}")


def patch_bench_sell_source(source: str) -> str:
    """Inject the shared decision note into the existing synchronized narration."""
    anchor = '        return {"player_id": pid, "anchor": anchor, "text": line}'
    if (source.count(anchor) != 1
            or source.count("    def _d3_bench_narr(frame, index, avoid=False):") != 1
            or "from day3.decision_consistency import bench_sell_note" in source):
        raise RuntimeError("Day 3 bench/sell narrator contract changed; refusing unsafe patch")
    injection = '''        note = bench_sell_note(
            pid, "BENCH" if avoid else "START",
            DAY3_TRANSFER_DESK.get("SELL", []), DAY3_AVAILABILITY.state(pid),
            player_name=name, expected_points=xpts, fixture_difficulty=fdr,
        )
        if note:
            line += " " + note
        return {"player_id": pid, "anchor": anchor, "text": line}'''
    return 'from day3.decision_consistency import bench_sell_note\n' + source.replace(anchor, injection, 1)
