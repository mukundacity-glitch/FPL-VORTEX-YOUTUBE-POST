"""Day 2 editorial lens; never change the model-led player shortlist.

Ideas are extracted from same-GW current AllAboutFPL articles by
vortex.day1_live_editorial, not from a static GW10 JSON or copied article copy.
The narrator discusses an attributed opinion in the first person while the
model's minutes, xPts, official status and final advice remain independent.
"""
from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from vortex.day1_live_editorial import _fresh, source_credits as _source_credits


def _player_ids(rows: Iterable[dict[str, Any]]) -> set[int]:
    result = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            val = int(row.get("id") or row.get("player_id") or 0)
            if val > 0:
                result.add(val)
        except (ValueError, TypeError):
            continue
    return result


def decisions(gameweek: int, highlighted_rows: Iterable[dict[str, Any]],
              *, path: str | Path | None = None, limit: int = 2) -> list[dict]:
    """Return only decisions about current model-highlighted FPL players.

    One general roll/chip plan may be used when no named player overlaps.
    Never select players solely because an external editorial article said so.
    """
    if not 1 <= int(gameweek) <= 38 or limit < 1:
        return []
    report = _fresh(gameweek, path=path)
    if not report:
        return []
    focused = _player_ids(highlighted_rows)
    ranked = []
    for op in report.get("opinions") or []:
        if op.get("gw") != gameweek or not op.get("url") or not op.get("author"):
            continue
        candidates = _player_ids(op.get("players") or [])
        if candidates and (candidates & focused):
            ranked.append((0, op))
        elif not candidates and op.get("action") in {"ROLL", "BENCH_BOOST"}:
            ranked.append((1, op))
    ranked.sort(key=lambda item: (item[0],
                                  {"BUY_CONSIDER":0,"CAPTAIN_COMPARE":1,
                                   "START":2,"BENCH":3}.get(item[1].get("action"),9),
                                  item[1].get("author", "")))
    chosen = [op for _, op in ranked if op.get("decision") and op.get("topic")]
    # Keep the existing outro short: never double-up on the same decision.
    unique, seen = [], set()
    for op in chosen:
        key = (op["action"], tuple(sorted(_player_ids(op.get("players") or []))))
        if key in seen:
            continue
        seen.add(key)
        unique.append(op)
        if len(unique) >= min(2, max(0, limit)):
            break
    return unique


def spoken_comparison(gameweek: int, highlighted_rows: Iterable[dict[str, Any]],
                      *, path: str | Path | None = None) -> str:
    choices = decisions(gameweek, highlighted_rows, path=path)
    if not choices:
        return ""
    sentence = ["One more thing I've been checking before settling on the final shortlist."]
    for op in choices:
        label = str(op["decision"]).strip().rstrip(".")
        sentence.append(f"In the latest All About FPL team discussion, "
                        f"{op['author']} is {label}.")
    sentence.append(
        "I wouldn't copy another manager's team blindly. For my decision here, "
        "I'm checking verified minutes, availability, fixtures and our Vortex projections "
        "first. The forecast is an estimate, not a guaranteed return."
    )
    return " ".join(sentence)


def youtube_credits(gameweek: int, *, path: str | Path | None = None) -> str:
    return _source_credits(gameweek) if path is None else (
        _source_credits(gameweek) if _fresh(gameweek, path=path) else ""
    )
