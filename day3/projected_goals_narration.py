"""Human narration for the existing live projection board; no model changes."""

from __future__ import annotations

import ast
import math
from collections.abc import Mapping
from typing import Any


def _number(value: Any) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Projection narration requires finite numbers")
    return result


def _records(value: Any) -> list[dict]:
    if hasattr(value, "to_dict"):
        return value.to_dict(orient="records")
    return list(value) if isinstance(value, (list, tuple)) else []


def _join(names: list[str]) -> str:
    if len(names) < 3:
        return " and ".join(names)
    return ", ".join(names[:-1]) + ", and " + names[-1]


def _player_options(namespace: Mapping, team_id: int, gw: int, *, attack: bool) -> list[str]:
    """Rank current, eligible players from this club using existing fixture forecasts."""
    availability = namespace.get("DAY3_AVAILABILITY")
    speak = namespace.get("vx_narration_player")
    if availability is None or getattr(availability, "gameweek", None) != gw or not callable(speak):
        return []
    official = {int(row["id"]): row for row in _records(namespace.get("players"))}
    groups: dict[int, dict] = {}
    for row in _records(namespace.get("SLIDE_PLAYER_FIXTURE_XPTS")):
        try:
            if int(row["gameweek"]) != gw or int(row["team_id"]) != team_id:
                continue
            pid = int(row["player_id"])
            player = official.get(pid, {})
            if int(player.get("team", -1)) != team_id or not availability.eligible(pid):
                continue
            position = int(player["element_type"])
            if position not in ({3, 4} if attack else {1, 2}):
                continue
            group = groups.setdefault(pid, {"position": position, "score": 0.0, "ready": True})
            if row.get("calculation_status") != "READY":
                group["ready"] = False
                continue
            score = (_number(row["goal_points"]) + _number(row["assist_points"]) if attack
                     else _number(row["fixture_expected_points"]))
            group["score"] += score
        except (KeyError, TypeError, ValueError, OverflowError):
            if "player_id" in row:
                try:
                    groups.setdefault(int(row["player_id"]), {"position": 0, "score": 0.0})["ready"] = False
                except (TypeError, ValueError, OverflowError):
                    pass
    ranked = sorted(
        (pid for pid, row in groups.items() if row.get("ready") and row["score"] > 0),
        key=lambda pid: (-groups[pid]["score"], pid),
    )
    if attack:
        selected = ranked[:2]
    else:
        selected = ([pid for pid in ranked if groups[pid]["position"] == 2][:2]
                    + [pid for pid in ranked if groups[pid]["position"] == 1][:1])
    return [str(speak(pid)).strip() for pid in selected if str(speak(pid)).strip()]


def projected_goals_narration(namespace: Mapping) -> tuple[str, dict]:
    """Use the user's paragraph structure with current board facts and exact cues."""
    payload = namespace.get("PROJECTED_GOALS_PAYLOAD")
    if not isinstance(payload, dict) or not payload.get("teams"):
        raise RuntimeError("Projected Goals narration needs the live PROJECTED_GOALS_PAYLOAD")
    gw = int(payload["gameweek"])
    speak = namespace["vx_narration_team"]
    teams = {}
    for tid, row in payload["teams"].items():
        goals, cs = _number(row["projected_goals"]), _number(row["clean_sheet_pct"])
        if goals < 0 or not 0 <= cs <= 100:
            raise ValueError("Projection narration received out-of-range model values")
        teams[int(tid)] = dict(id=int(tid), name=str(speak(int(tid))).strip(), goals=goals, cs=cs)

    def bucket(key, count, metric, reverse):
        rows = [teams[int(item["team_id"])] for item in payload.get(key, [])]
        if len(rows) != count or len({row["id"] for row in rows}) != count:
            raise RuntimeError(f"Projected Goals {key} needs {count} distinct live teams")
        values = [row[metric] for row in rows]
        expected = sorted((row[metric] for row in teams.values()), reverse=reverse)[:count]
        if values != expected:
            raise RuntimeError(f"Projected Goals {key} differs from the live model ranking")
        return rows

    top = bucket("top5_goals", 5, "goals", True)
    low = bucket("bottom3_goals", 3, "goals", False)
    defense = bucket("top5_clean_sheet", 5, "cs", True)
    risk = bucket("bottom3_clean_sheet", 3, "cs", False)
    fixtures: dict[int, list[dict]] = {tid: [] for tid in teams}
    for fixture in payload.get("fixtures", []):
        home, away = int(fixture["home_team_id"]), int(fixture["away_team_id"])
        if home == away or home not in teams or away not in teams:
            raise RuntimeError("Projected Goals fixture does not match current teams")
        for tid, other, venue, cs_key in ((home, away, "H", "away_cs_pct"), (away, home, "A", "home_cs_pct")):
            cs = _number(fixture[cs_key])
            if not 0 <= cs <= 100:
                raise ValueError("Invalid opponent clean-sheet probability")
            fixtures[tid].append({"name": teams[other]["name"], "venue": venue, "cs": cs})
    for tid, row in teams.items():
        if not fixtures[tid] and (row["goals"] or row["cs"]):
            raise RuntimeError(f"Projected Goals lacks fixture evidence for {row['name']}")

    def fixture_text(row, *, include_venue=False):
        games = fixtures[row["id"]]
        if not games:
            return "with no fixture scheduled"
        if len(games) == 1:
            game = games[0]
            return ("away to " if include_venue and game["venue"] == "A" else "against ") + game["name"]
        return "across fixtures against " + _join([
            game["name"] + (" at home" if game["venue"] == "H" else " away") for game in games
        ])

    def pct(value):
        return f"{value:.1f}".removesuffix(".0")

    def possessive(name):
        return name + ("'" if name.endswith("s") else "'s")

    sections = []

    def section(key, board, intro, rows, anchors):
        sections.append({"bucket": key, "board": board, "intro": intro,
                         "rows": [{"team_id": row["id"], "anchor": anchor}
                                  for row, anchor in zip(rows, anchors)]})

    parts = [f"Let's look at where the numbers point for Gameweek {gw}, starting with attacking potential."]
    lead = top[0]
    attack_tie = round(lead["goals"], 2) == round(top[1]["goals"], 2)
    top_anchors = [f"{lead['name']} {'share the lead' if attack_tie else 'lead the model'} with {lead['goals']:.2f} expected goals"]
    line = f"{top_anchors[0]} {fixture_text(lead, include_venue=True)}."
    games = fixtures[lead["id"]]
    if len(games) == 1:
        line += f" With {possessive(games[0]['name'])} clean-sheet probability at {pct(games[0]['cs'])} percent,"
        line += (" their attackers share the strongest attacking projection on this list." if attack_tie else
                 f" {lead['name']} attackers offer the strongest attacking opportunity on this list.")
    attackers = _player_options(namespace, lead["id"], gw, attack=True)
    if attackers:
        line += f" {_join(attackers)} {'are threats' if len(attackers) > 1 else 'is a threat'}."
    parts.append(line)
    connectors = ("follow at", "sit at", "come in at", "completing the top five at")
    phrases = []
    for row, connector in zip(top[1:], connectors):
        anchor = f"{row['name']} {connector} {row['goals']:.2f} {fixture_text(row, include_venue=True)}"
        top_anchors.append(anchor)
        phrases.append(anchor)
    parts.append(f"{phrases[0]}, while {phrases[1]}. {phrases[2]}, with {phrases[3]}.")
    section("top5_goals", "goals", "starting with attacking potential", top, top_anchors)
    opponent_odds = [game["cs"] for row in top for game in fixtures[row["id"]]]
    if opponent_odds and all(fixtures[row["id"]] for row in top):
        single = all(len(fixtures[row["id"]]) == 1 for row in top)
        ceiling = max(opponent_odds)
        scope = "all five opponents have" if single else "across those fixtures, opponents have"
        line = f"Here's what stands out: {scope} clean-sheet probabilities of {pct(ceiling)} percent or lower."
        line += (" That's a strong signal when you're comparing attacking FPL assets." if ceiling <= 25 else
                 " Compare the individual matchups when you're choosing attacking FPL assets.")
        parts.append(line)

    low_anchors = [f"{low[0]['name']} project",
                   f"{low[1]['name']} sit at {low[1]['goals']:.2f} {fixture_text(low[1])}",
                   f"and {low[2]['name']} at"]
    parts.append(
        f"At the opposite end, {low_anchors[0]} just {low[0]['goals']:.2f} goals {fixture_text(low[0])}. "
        f"{low_anchors[1]}, "
        f"{low_anchors[2]} {low[2]['goals']:.2f} {fixture_text(low[2])}. "
        "I'd be cautious about relying on attacking returns from those three."
    )
    section("bottom3_goals", "goals", "At the opposite end", low, low_anchors)

    first, second, third = defense[:3]
    gap = round(first["cs"], 1) - round(second["cs"], 1)
    tied = round(gap, 1) == 0
    description = "share the lead" if tied else "are the clear leaders" if gap >= 5 else "lead the defensive numbers"
    cs_label = "chance of at least one clean sheet" if len(fixtures[first["id"]]) > 1 else "clean-sheet probability"
    cs_anchors = [f"{first['name']} {description}, with a {pct(first['cs'])} percent {cs_label}",
                  f"{second['name']}, who sit second"]
    line = f"Defensively, {cs_anchors[0]} {fixture_text(first)}. "
    line += (f"Alongside them are {cs_anchors[1]} at the same {pct(second['cs'])} percent."
             if tied else f"That's {pct(gap)} percentage points ahead of {cs_anchors[1]} at {pct(second['cs'])} percent.")
    defenders = _player_options(namespace, first["id"], gw, attack=False)
    if defenders:
        line += f" From {first['name']}, I'd consider {_join(defenders)} based on the current minutes and points forecasts."
    parts.append(line)
    follow = "follow closely" if second['cs'] - third['cs'] <= 2 else "take third"
    cs_anchors += [f"{third['name']} {follow} at {pct(third['cs'])} percent",
                   f"{defense[3]['name']} at {pct(defense[3]['cs'])} percent",
                   f"and {defense[4]['name']} complete"]
    parts.append(
        f"{cs_anchors[2]}, {cs_anchors[3]}, "
        f"{cs_anchors[4]} the top five at {pct(defense[4]['cs'])} percent."
    )
    section("top5_clean_sheet", "cs", "Defensively", defense, cs_anchors)
    narrow = round(second["cs"], 1) - round(third["cs"], 1)
    parts.append(
        f"One interesting detail: {second['name']} and {third['name']} are separated by "
        f"{'just ' if narrow <= 2 else ''}{pct(narrow)} percentage points. "
        + ("That's a narrow gap, so attacking potential could help decide between their defenders." if narrow <= 2 else
           "The clean-sheet odds favor the higher-ranked side, while attacking potential is another factor to weigh.")
    )
    risk_anchors = [f"{risk[0]['name']} have", f"{risk[1]['name']} sit at {pct(risk[1]['cs'])} percent",
                    f"with {risk[2]['name']} on"]
    chance = "odds of at least one clean sheet" if len(fixtures[risk[0]["id"]]) > 1 else "clean-sheet odds"
    parts.append(
        f"Meanwhile, {risk_anchors[0]} {'only ' if risk[0]['cs'] < 20 else ''}{pct(risk[0]['cs'])} percent {chance}. "
        f"{risk_anchors[1]}, {risk_anchors[2]} {pct(risk[2]['cs'])} percent. "
        "I'd want attacking upside before investing in defenders from those teams."
    )
    section("bottom3_clean_sheet", "cs", "Meanwhile", risk, risk_anchors)
    closing = f"So, {lead['name']} {'share the lead in' if attack_tie else 'lead'} the attacking numbers"
    parts.append(
        f"{closing}, but {first['name']} {'share' if tied else 'offer'} the strongest defensive probability. "
        "For close defensive calls, look beyond clean-sheet odds and consider attacking involvement."
    )
    if any(len(games) > 1 for games in fixtures.values()):
        parts.append("For teams playing more than once, goals are totaled across their fixtures, and clean-sheet odds are the chance of at least one clean sheet.")
    parts.append("And that brings us neatly to our next section: defensive contribution.")
    return "\n\n".join(parts), {"opening": "Let's look at where the numbers point", "sections": sections, "closing": closing}


def patch_projected_goals_narration_source(source: str) -> str:
    """Replace only this function, leaving every other scene and setting intact."""
    functions = [node for node in ast.walk(ast.parse(source))
                 if isinstance(node, ast.FunctionDef) and node.name == "_d3_projected_goals_narration"]
    if len(functions) != 1:
        raise RuntimeError("Expected exactly one Projected Goals narration function")
    node = functions[0]
    lines = source.splitlines(keepends=True)
    indent = " " * node.col_offset
    replacement = (
        "def _d3_projected_goals_narration():\n"
        "    from day3.projected_goals_narration import projected_goals_narration\n"
        "    text, cues = projected_goals_narration(globals())\n"
        "    globals()[\"PROJECTED_GOALS_NARRATION_CUES\"] = cues\n"
        "    return text\n"
    )
    lines[node.lineno - 1:node.end_lineno] = [indent + line for line in replacement.splitlines(keepends=True)]
    return "".join(lines)
