"""Production handoff contract for Day 1's *retrospective* review artifacts.

The review renderer needs player reveal timestamps, not forward projections,
editorial-source annotations, TTS byte payloads, or model forecasts. Keep that
private execution metadata outside the published animation manifest.

The separate completed narration transcript is a legitimate DATA/*.txt file:
the pre-publish check validates exact current-run contents rather than blocking
the extension or silently removing an important deliverable.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import re
from typing import Any


_ANIMATION_TIMES = (
    "t0", "t1", "speech_end_at", "reveal_at",
    "hero_on", "hero_exit_at", "hero_off",
)
_ANIMATION_FIELDS = ("id", "player_id", "spotlight_player_id", "kind", *_ANIMATION_TIMES)
_MANDATORY_DISCLOSURE = "Expected points are forecasts, not guaranteed returns"


def snapshot_review_animation_segments(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return only the identity and measured animation cues Cell 17 needs.

    The source package remains unchanged: the full narration and its provenance
    remain available to the editorial QA and TTS stages.
    """
    if not isinstance(segments, list) or not segments:
        raise ValueError("GW Review timeline requires current narration segments")
    output: list[dict[str, Any]] = []
    ids: set[str] = set()
    players: set[int] = set()
    starter_count = 0
    for source in segments:
        if not isinstance(source, dict):
            raise ValueError("GW Review segment must be a mapping")
        identifier = str(source.get("id") or "").strip()
        if not identifier or identifier in ids:
            raise ValueError(f"Missing or repeated GW Review segment id: {identifier!r}")
        ids.add(identifier)
        item: dict[str, Any] = {"id": identifier}
        for key in _ANIMATION_FIELDS[1:]:
            if key not in source or source[key] is None:
                continue
            if key in _ANIMATION_TIMES:
                try:
                    value = float(source[key])
                except (ValueError, TypeError) as exc:
                    raise ValueError(f"Invalid review cue {identifier}.{key}") from exc
                if not math.isfinite(value) or value < 0:
                    raise ValueError(f"Invalid review cue {identifier}.{key}")
                item[key] = value
            elif key == "player_id":
                if isinstance(source[key], bool):
                    raise ValueError(f"Invalid review player id {identifier}")
                player_id = int(source[key])
                if player_id <= 0 or player_id in players:
                    raise ValueError(f"Invalid or duplicated review player id {player_id}")
                players.add(player_id)
                item[key] = player_id
            elif key == "spotlight_player_id":
                item[key] = int(source[key])
            elif key == "kind":
                item[key] = str(source[key])
        if "player_id" in item:
            if item.get("kind") not in {"starter", "bench"}:
                raise ValueError(f"Missing starter/bench identity in {identifier}")
            for key in ("t0", "t1", "reveal_at"):
                if key not in item:
                    raise ValueError(f"Missing player animation cue {identifier}.{key}")
            if not item["t0"] <= item["reveal_at"] < item["t1"]:
                raise ValueError(f"Player reveal outside narration in {identifier}")
            if item["kind"] == "starter":
                starter_count += 1
                for key in ("hero_on", "hero_exit_at", "hero_off"):
                    if key not in item:
                        raise ValueError(f"Missing hero cue {identifier}.{key}")
                if not item["hero_on"] < item["hero_exit_at"] < item["hero_off"]:
                    raise ValueError(f"Invalid hero fade in {identifier}")
            elif any(key in item for key in ("hero_on", "hero_exit_at", "hero_off")):
                raise ValueError(f"Bench segment contains starter hero cues: {identifier}")
        output.append(item)
    if len(players) != 15 or starter_count != 11:
        raise ValueError(
            f"GW Review animation requires eleven starters and four reserves, "
            f"got players={len(players)} starters={starter_count}"
        )
    for item in output:
        if "spotlight_player_id" in item and (
            item["spotlight_player_id"] not in players
            or not item["t0"] <= item["reveal_at"] < item["speech_end_at"] <= item["t1"]
        ):
            raise ValueError(f"Invalid spoken hero cue in {item['id']}")
    return output


def assert_review_animation_manifest_current(
    manifest: dict[str, Any], segments: list[dict[str, Any]], review_gw: int
) -> None:
    """Reject stale/contaminated manifests before expensive animation or upload."""
    if not isinstance(manifest, dict):
        raise ValueError("GW Review animation manifest must be a mapping")
    try:
        actual_gw = int(manifest.get("gw"))
    except (ValueError, TypeError) as exc:
        raise ValueError("GW Review animation manifest has no verified Gameweek") from exc
    if actual_gw != int(review_gw):
        raise ValueError(
            f"Stale GW Review animation manifest: GW{actual_gw} != current GW{review_gw}"
        )
    expected = snapshot_review_animation_segments(segments)
    if manifest.get("segments") != expected:
        raise ValueError("Stale or unfiltered GW Review animation manifest segments")
    # A manifest is exclusively operational animation metadata, not a model
    # delivery surface. The Phase-0 global scanner remains fully active.
    payload = json.dumps(manifest, ensure_ascii=False).casefold()
    if re.search(r"\bxpts\b", payload):
        raise ValueError("Forbidden forward-looking xPts in GW Review animation manifest")


def assert_review_script_current(
    path: str | Path, segments: list[dict[str, Any]]
) -> None:
    """Allow only a readable, complete transcript matching this run's TTS."""
    file = Path(path)
    if file.name != "gw_review_final_script.txt":
        raise ValueError(f"Unexpected review script filename: {file.name}")
    if not file.is_file() or file.stat().st_size <= 50:
        raise ValueError("Missing or empty current GW Review narration script")
    if not isinstance(segments, list) or not segments:
        raise ValueError("No current narrated review package to verify script against")
    expected = "\n\n".join(str(seg.get("text") or "") for seg in segments)
    if not expected.strip() or any(not str(seg.get("text") or "").strip() for seg in segments):
        raise ValueError("Current GW Review narration contains an empty segment")
    actual = file.read_text(encoding="utf-8")
    if actual != expected:
        raise ValueError("Stale/mismatched GW Review narration script; differs from current segments")
    if _MANDATORY_DISCLOSURE not in actual:
        raise ValueError("Current review script is missing its forecast disclosure")
