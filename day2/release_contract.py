"""Day 2 release provenance: bind metadata to fresh, complete model data."""
from __future__ import annotations
import json
from pathlib import Path

SCENES = (
    "scene_01_intro", "scene_02_expected_minutes", "scene_03_split_screen",
    "scene_04_top1k_matrix", "scene_05_top10_differentials",
    "scene_06_traps_blueprint", "scene_07_outro",
)


def verify_current_scene_package(root: str | Path) -> dict:
    path = Path(root).resolve() / "Data" / "scene_data.json"
    if not path.is_file():
        raise RuntimeError("Current Day 2 scene_data.json is missing")
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise RuntimeError("Day 2 scene data must be an object")
    absent = [key for key in SCENES if key not in obj]
    if absent:
        raise RuntimeError("Day 2 scenes incomplete: " + ", ".join(absent))
    gws = set()
    for label in SCENES:
        record = obj[label]
        if not isinstance(record, dict):
            raise RuntimeError("Invalid Day 2 scene: " + label)
        try:
            gw = int(record.get("target_gw"))
        except (ValueError, TypeError):
            raise RuntimeError("Missing target GW for " + label)
        if not 1 <= gw <= 38:
            raise RuntimeError("Invalid target GW for " + label)
        gws.add(gw)
    if len(gws) != 1:
        raise RuntimeError("Mixed Gameweeks across Day 2 scenes")
    gw = gws.pop()
    minutes = obj["scene_02_expected_minutes"].get("featured_4")
    diffs = obj["scene_05_top10_differentials"].get("top_3_narrated")
    if not isinstance(minutes, list) or len(minutes) != 4:
        raise RuntimeError("Day 2 needs four verified minutes-model players")
    if not isinstance(diffs, list) or len(diffs) != 3:
        raise RuntimeError("Day 2 needs three verified differential picks")
    ids = []
    for player in minutes + diffs:
        if not isinstance(player, dict):
            raise RuntimeError("Day 2 player identity is invalid")
        try:
            pid = int(player["id"])
        except (ValueError, TypeError, KeyError):
            raise RuntimeError("Day 2 player has no official FPL ID")
        if pid <= 0:
            raise RuntimeError("Day 2 player has invalid FPL ID")
        ids.append(pid)
    if len(set(ids[:4])) != 4 or len(set(ids[4:])) != 3:
        raise RuntimeError("Day 2 featured player IDs are duplicated")
    return {
        "gameweek": gw,
        "expected_minutes_players": [
            {"id": int(p["id"]), "name": p.get("full_name") or p.get("name") or "N/A"}
            for p in minutes
        ],
        "differential_players": [
            {"id": int(p["id"]), "name": p.get("full_name") or p.get("name") or "N/A"}
            for p in diffs
        ],
        "model_versions": {
            label: obj[label].get("model_version") or "N/A"
            for label in SCENES if obj[label].get("model_version")
        },
        "source_manifest": "Data/day2_editorial_sources.json",
    }
