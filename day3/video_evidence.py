"""Identify the official FPL facts a selected Day 3 video uses."""
from __future__ import annotations

import re
import unicodedata


def _normalized(value):
    value = unicodedata.normalize("NFKD", str(value).casefold())
    return " ".join(re.findall(r"[^\W_]+", "".join(c for c in value if not unicodedata.combining(c))))


def video_scope(namespace, scripts):
    snapshot = namespace["DAY3_EVIDENCE"]
    selected = namespace["SLIDE_SELECTION"]
    player_ids, decision_ids, defcon_teams = set(), set(), set()
    defcon_ids = set()

    def collect(value, target=player_ids):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {"player_id", "in_id", "out_id", "incoming_id", "outgoing_id",
                           "element", "captain_id", "vice_id"} or key.endswith("_player_id"):
                    if item is not None and str(item).isdigit():
                        target.add(int(item))
                elif key in {"current_squad_ids", "final_squad_ids", "trigger_player_ids"}:
                    target.update(int(x) for x in item)
                else:
                    collect(item, target)
        elif isinstance(value, (list, tuple)):
            for item in value:
                collect(item, target)

    for scene, variable in (
        ("05a_my_plan_roll", "DAY3_MY_PLAN_5A_PACKAGE"),
        ("05b_my_plan_transfer", "DAY3_MY_PLAN_5B_PACKAGE"),
    ):
        if selected.get(scene):
            collect(namespace[variable], decision_ids)
            if not decision_ids:
                raise RuntimeError(f"Day 3 cannot seal {scene} without player IDs")

    for scene, variable in (
        ("06_benching_dilemma", "DAY3_BENCHING_START16"),
        ("06_benching_dilemma", "DAY3_BENCHING_BENCH16"),
    ):
        if selected.get(scene):
            player_ids.update(int(value) for value in namespace[variable]["player_id"])
    if selected.get("03_defcon"):
        defcon_ids.update(int(pid) for pid in namespace["DAY3_DEFCON_PLAYERS"]["player_id"])
        player_ids.update(defcon_ids)
        defcon_teams.update(snapshot["players"][pid]["team_id"] for pid in defcon_ids)
        for name in ("DAY3_DEFCON_TOP_TEAMS", "DAY3_DEFCON_AVOID_TEAMS"):
            defcon_teams.update(int(value) for value in namespace[name]["team_id"])
    if selected.get("05_transfer_decision_desk"):
        collect(namespace["_d3_desk_manifest"]["players"], decision_ids)
    if selected.get("05_elite_1000_trends"):
        collect(namespace["ELITE1000_MANIFEST"])

    review_gw = None
    review_teams = set()
    if selected.get("gw_review"):
        review = namespace["LIVE_REVIEW_DATA"]
        review_gw = int(review["event"]["id"])
        review_ids = {int(row["id"]) for row in review["players"]}
        review_teams.update(snapshot["players"][pid]["team_id"] for pid in review_ids)
        player_ids.update(review_ids)

    player_ids.update(decision_ids)
    original_speech = "\n".join(scripts.values())
    speech = " " + " ".join(_normalized(line) for line in scripts.values()) + " "
    quoted_news_players = set()
    narrate = namespace.get("vx_narration_player")
    for row in snapshot["_bootstrap"]["elements"]:
        pid = int(row["id"])
        names = [snapshot["players"][pid]["name"], row.get("web_name")]
        if narrate:
            names.append(narrate(pid))
        for name in names:
            normalized = _normalized(name) if name else ""
            if (len(normalized) > 2 and f" {normalized} " in speech
                    and (" " in normalized or re.search(rf"(?<!\w){re.escape(name)}(?!\w)", original_speech))):
                player_ids.add(pid)
                break
        news = _normalized(row.get("news") or "")
        if pid in player_ids and len(news) > 8 and f" {news} " in speech:
            quoted_news_players.add(pid)

    unknown = player_ids - snapshot["players"].keys()
    if unknown:
        raise RuntimeError(f"Day 3 video refers to unknown FPL players: {sorted(unknown)}")
    gw = snapshot["next_gw"]
    fixture_horizons = {str(snapshot["players"][pid]["team_id"]): gw for pid in player_ids}
    for team_id in defcon_teams:
        fixture_horizons[str(team_id)] = gw + 2
    for pid in decision_ids:
        team_id = snapshot["players"][pid]["team_id"]
        fixture_horizons[str(team_id)] = gw + int(namespace.get("DAY3_PHASE10_FIXTURE_HORIZON_GWS", 5)) - 1
    return {
        "player_ids": sorted(player_ids),
        "decision_player_ids": sorted(decision_ids),
        "defcon_player_ids": sorted(defcon_ids),
        "quoted_news_player_ids": sorted(quoted_news_players),
        "fixture_horizons": fixture_horizons,
        "next_gameweek_all_fixtures": bool(selected.get("03_projected_goals")),
        "review_gw": review_gw,
        "review_team_ids": sorted(review_teams),
    }
