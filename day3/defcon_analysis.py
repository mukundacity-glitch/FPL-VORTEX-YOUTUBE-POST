"""One recommendation contract for DEFCON narration and graphics."""
from __future__ import annotations

import ast
from typing import Any

import pandas as pd

from day3.player_availability import AvailabilityContext, number


def annotate_players(frame: pd.DataFrame, context: AvailabilityContext, projections: pd.DataFrame) -> pd.DataFrame:
    if not {"projection_verified", "player_id"}.issubset(projections.columns):
        raise RuntimeError("DEFCON selection requires validated fixture projections")
    result = context.annotate(frame)
    result["projection_verified"] = result.player_id.map(lambda pid: bool(context.state(pid).get("projection_verified")))
    result["recommendation_eligible"] &= result.projection_verified
    result["positional_threshold"] = result.position.map((context.research or {}).get("scoring", {}).get("thresholds", {}))
    result["historical_rank"] = pd.to_numeric(result.cumulative_dc).rank(ascending=False, method="min").astype(int)
    result["recommendation_score"] = pd.to_numeric(result.next_dc_points, errors="coerce").where(result.recommendation_eligible)
    return result


def rank_profiles(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.sort_values(
        ["recommendation_eligible", "recommendation_score", "dc_hit_rate", "cumulative_dc", "player_id"],
        ascending=[False, False, False, False, True], na_position="last", kind="stable",
    ).reset_index(drop=True)
    result["rank"] = range(1, len(result) + 1)
    return result


def annotate_teams(frame: pd.DataFrame, players: pd.DataFrame, context: AvailabilityContext) -> pd.DataFrame:
    result = frame.copy()
    # Unknown forecasts from players with real season minutes make the sum incomplete.
    affected = set()
    for row in players.to_dict("records"):
        minutes = number(context.official_players.get(int(row["player_id"]), {}).get("minutes"))
        if not row["projection_verified"] and (minutes is None or minutes > 0):
            affected.add(int(row["team_id"]))
    result["projection_verified"] = ~result.team_id.astype(int).isin(affected)
    result["projection_status"] = result.projection_verified.map({True: "VERIFIED_MODEL", False: "INCOMPLETE_PLAYER_FORECASTS"})
    return result


def forecast_text(row: Any, field: str = "xdefcon", *, digits: int = 1) -> str:
    value = number(row.get(field))
    return f"{value:.{digits}f}" if row.get("projection_verified") and value is not None else "—"


def narration(namespace: dict[str, Any]) -> tuple[str, dict]:
    context = namespace["DAY3_AVAILABILITY"]
    profiles = namespace["DAY3_DEFCON_TARGETS"].to_dict("records")
    teams = namespace["DAY3_DEFCON_TEAMS"].to_dict("records")
    if len(profiles) != 5 or len({int(row["player_id"]) for row in profiles}) != 5:
        raise RuntimeError("DEFCON needs five distinct analysis profiles, including explicitly labeled watchlist entries")
    team_name = namespace["vx_narration_team"]
    player_name = namespace["vx_narration_player"]
    opening = "Let's talk defensive contributions, because the biggest numbers don't always mean the best FPL picks."
    parts = [opening]
    historical = namespace.get("DAY3_DEFCON_ELIGIBLE_PLAYERS")
    if historical is not None and not historical.empty:
        leader = historical.sort_values("cumulative_dc", ascending=False, kind="stable").iloc[0]
        leader_id = int(leader["player_id"])
        state = context.state(leader_id)
        if state["blocked"] and leader_id not in {int(row["player_id"]) for row in profiles}:
            parts.append(f"The season leader, {player_name(leader_id)}, has {float(leader['cumulative_dc']):.0f} actions, "
                         f"but official FPL currently marks him {state['label'].lower()}. He's off the immediate target list.")
    player_cues = []
    for index, row in enumerate(profiles):
        pid = int(row["player_id"])
        name = str(player_name(pid))
        state = context.state(pid)
        total = number(row.get("cumulative_dc"))
        rate = number(row.get("dc_per90"))
        threshold = number(row.get("positional_threshold"))
        award = number((context.research or {}).get("scoring", {}).get("points_by_position", {}).get(row.get("position")))
        anchor = f"{name} has" if index % 2 == 0 else f"For {name}, the season total is"
        line = f"{anchor} {total:.0f} defensive actions" if total is not None else f"{anchor} an unverified defensive-actions total"
        line += ". "
        if row.get("recommendation_eligible") and context.eligible(pid):
            if threshold is not None and rate is not None and award is not None:
                line += f"His {rate:.1f} per ninety compares with a {threshold:.0f}-action threshold for {award:g} extra points in each match. "
            hits, appearances = number(row.get("dc_hits")), number(row.get("appearances"))
            if hits is not None and appearances is not None and appearances > 0:
                line += f"He's reached it in {hits:.0f} of {appearances:.0f} appearances. "
            line += f"The next projection is {forecast_text(row)} actions, with {state['expected_minutes']:.0f} expected minutes."
        elif state["blocked"]:
            line += f"Official FPL currently marks him {state['label'].lower()}. He's off the immediate target list."
        elif state["label"] == "TEAM NEWS CHECK":
            line += "Recent team news needs checking against his availability and role, so I'd wait for confirmation before buying."
        elif not row.get("projection_verified"):
            line += "The next projection isn't verified, so this is a historical watchlist entry, not a buy recommendation."
        else:
            line += "His fitness or starting minutes aren't sufficiently verified for an immediate recommendation."
        parts.append(line)
        player_cues.append({"player_id": pid, "anchor": anchor})
    team_intro = "Now, here's where the team data gets interesting"
    parts.append(team_intro + ".")
    leaders = namespace["DAY3_DEFCON_TOP_TEAMS"].to_dict("records")
    lower = namespace["DAY3_DEFCON_AVOID_TEAMS"].to_dict("records")
    target_cues = []
    for index, row in enumerate(leaders):
        name = str(team_name(int(row["team_id"])))
        phrases = ("lead the season workload", "have recorded", "have accumulated", "are on", "round out this group with")
        anchor = f"{name} {phrases[index]}"
        line = f"{anchor} {'of ' if index == 0 else ''}{float(row['dc_for']):.0f} actions, averaging {float(row['dc_for_per_game']):.1f} per match."
        projection = number(row.get("xdefcon"))
        average = number(row.get("dc_for_per_game"))
        if row.get("projection_verified") and projection is not None:
            line += f" The next projection {'rises to' if projection > average else 'drops to' if projection < average else 'holds at'} {projection:.1f}."
        else:
            line += " Their next projection is incomplete, so I wouldn't use it to rank the fixture."
        if index == 1 and row.get("projection_verified") and leaders[0].get("projection_verified"):
            gap = projection - float(leaders[0]["xdefcon"])
            if gap > 0:
                line += f" That's {gap:.1f} more than {team_name(int(leaders[0]['team_id']))}, despite the lower season total."
        parts.append(line)
        target_cues.append({"team_id": int(row["team_id"]), "anchor": anchor})
    avoid_intro = "At the lower end of the season workload"
    parts.append(avoid_intro + ".")
    avoid_cues = []
    for row in lower:
        name = str(team_name(int(row["team_id"])))
        anchor = f"{name} sit lower on this workload chart"
        line = f"{anchor}, with {float(row['dc_for']):.0f} actions."
        if row.get("projection_verified") and number(row.get("xdefcon")) is not None:
            line += f" Their next projection is {float(row['xdefcon']):.1f}, against a {float(row['dc_for_per_game']):.1f} season average."
        parts.append(line)
        avoid_cues.append({"team_id": int(row["team_id"]), "anchor": anchor})
    parts.append("Defensive contributions measure workload, not defensive quality. A team can defend less often and still offer good clean-sheet potential. Look for available players, reliable minutes and regular positional-threshold returns, then compare the fixtures. Next, let's see what that means for our transfer decisions.")
    return "\n\n".join(parts), {"opening": "Let's talk defensive contributions", "individual": player_cues,
        "team_intro": team_intro, "target_teams": target_cues, "avoid_intro": avoid_intro, "avoid_teams": avoid_cues}


def replace_function(source: str, name: str, replacement: str) -> str:
    nodes = [node for node in ast.walk(ast.parse(source)) if isinstance(node, ast.FunctionDef) and node.name == name]
    if len(nodes) != 1:
        raise RuntimeError(f"Expected exactly one {name} function")
    node = nodes[0]
    lines = source.splitlines(keepends=True)
    lines[node.lineno - 1:node.end_lineno] = [" " * node.col_offset + line for line in replacement.splitlines(keepends=True)]
    return "".join(lines)


def patch_narration(source: str) -> str:
    return replace_function(source, "_d3_defcon_narration", '''def _d3_defcon_narration():
    from day3.defcon_analysis import narration
    text, cues = narration(globals())
    globals()["DEFCON_NARRATION_CUES"] = cues
    return text
''')
