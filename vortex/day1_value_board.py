"""Scene 05 reusable Value Board payload — no screenshot data, no speculative values.

The existing squad optimiser remains the source of the 15 selected players.
This module verifies that squad and derives the best legal XI for each of the
next five GWs from the supplied model forecasts. It does NOT choose 15 players
from the full player pool or fetch unverified market data.
"""
from collections import Counter
from itertools import combinations
from math import isfinite

POSITION = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
FORMATION = {"GK": (1, 1), "DEF": (3, 5), "MID": (2, 5), "FWD": (1, 3)}


def _number(value, label):
    try:
        value = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} is missing or invalid") from exc
    if not isfinite(value):
        raise ValueError(f"{label} must be finite")
    return value


def _best_xi(players, gw):
    valid = []
    for xi in combinations(players, 11):
        counts = Counter(p["position"] for p in xi)
        if any(not lo <= counts.get(pos, 0) <= hi for pos, (lo, hi) in FORMATION.items()):
            continue
        score = sum(p["weekly"][gw] for p in xi)
        valid.append((score, tuple(sorted(p["id"] for p in xi)), xi))
    if not valid:
        raise ValueError("No legal starting XI available")
    # Tie-break by canonical player IDs to make the same model snapshot deterministic.
    _, _, lineup = min(valid, key=lambda r: (-r[0], r[1]))
    return list(lineup)


def build_value_board(*, gameweek, squad, forecasts, fixtures, teams,
                      portraits=None, market=None, narration_cues=None,
                      model_label="VORTEX model · research estimates"):
    """Return validated JSON-ready data for tools/day1-broadcast/ValueBoard.jsx.

    squad: the existing optimiser's selected 15 official player dicts.
    forecasts: rows with player_id, gameweek, gameweek_expected_points.
    fixtures: official fixture rows; projections can supply projected home/away goals.
    """
    if not isinstance(gameweek, int) or not 1 <= gameweek <= 34:
        raise ValueError("A complete five-gameweek horizon must exist")
    if len(squad) != 15 or len({p["id"] for p in squad}) != 15:
        raise ValueError("Value Board requires 15 unique selected players")
    expected = Counter({1: 2, 2: 5, 3: 5, 4: 3})
    actual = Counter(p.get("element_type") for p in squad)
    if actual != expected:
        raise ValueError(f"Illegal FPL squad positions: {actual}")
    clubs = Counter(p["team"] for p in squad)
    if any(amount > 3 for amount in clubs.values()):
        raise ValueError("More than three players selected from a single club")

    model = {}
    for row in forecasts:
        key = (row.get("player_id"), row.get("gameweek"))
        if key in model:
            raise ValueError(f"Ambiguous duplicate projection: {key}")
        model[key] = _number(row.get("gameweek_expected_points"), f"Forecast {key}")
    photo = portraits or {}
    players = []
    for player in squad:
        pid, tid = player["id"], player["team"]
        team = teams.get(tid)
        if not team:
            raise ValueError(f"Missing canonical club for player {pid}")
        price = _number(player.get("now_cost"), f"Player {pid} price") / 10
        if price < 0:
            raise ValueError("Negative player price")
        weekly = {}
        for gw in range(gameweek, gameweek + 5):
            key = (pid, gw)
            if key not in model:
                raise ValueError(f"Missing player projection: {key}")
            weekly[gw] = model[key]
        team_fixtures = sorted(
            (f for f in fixtures if gameweek <= f.get("event", -1) < gameweek + 5
             and tid in (f.get("team_h"), f.get("team_a"))),
            key=lambda f: (f["event"], f.get("kickoff_time") or "", f["id"]),
        )
        tiles = []
        for fixture in team_fixtures:
            home = fixture["team_h"] == tid
            opponent = teams.get(fixture["team_a"] if home else fixture["team_h"])
            if not opponent:
                raise ValueError(f"Missing opponent club for fixture {fixture['id']}")
            tiles.append({
                "id": fixture["id"],
                "gw": fixture["event"],
                "opponentId": opponent["id"],
                "opponentShortName": opponent["short"],
                "opponentFullName": opponent["name"],
                "venue": "H" if home else "A",
                "fdr": fixture.get("fdr_by_team", {}).get(tid),
            })
        players.append({
            "id": pid,
            "name": player.get("web_name") or player.get("second_name") or str(pid),
            "fullName": " ".join(filter(None, (player.get("first_name"), player.get("second_name")))),
            "position": POSITION[player["element_type"]],
            "teamId": tid,
            "clubLogo": team.get("badge") or "",
            "portrait": photo.get(pid, ""),
            "price": price,
            "weekly": weekly,
            "fixtures": tiles,
        })
    total_cost = sum(p["price"] for p in players)
    if total_cost > 100.00001:
        raise ValueError(f"Value Board exceeds £100m: {total_cost:.1f}")
    market = market or {}
    if market.get("bank") is not None:
        bank = _number(market["bank"], "bank")
        if abs((100 - total_cost) - bank) > .11:
            raise ValueError("Bank and £100m squad budget disagree")
    else:
        bank = 100 - total_cost

    lineups, projections = {}, []
    for gw in range(gameweek, gameweek + 5):
        xi = _best_xi(players, gw)
        lineup_ids = {p["id"] for p in xi}
        captain = sorted(xi, key=lambda p: (-p["weekly"][gw], p["id"]))[0]
        vice = sorted((p for p in xi if p["id"] != captain["id"]),
                      key=lambda p: (-p["weekly"][gw], p["id"]))[0]
        # Projected captain multiplier is an estimate; live FPL scoring remains canonical.
        xpts = sum(p["weekly"][gw] for p in xi) + captain["weekly"][gw]
        projections.append({"gameweek": gw, "xpts": round(xpts, 2)})
        lineups[gw] = (xi, lineup_ids, captain["id"], vice["id"])

    selected, selected_ids, captain_id, vice_id = lineups[gameweek]
    starters = [{**p, "nextGwXpts": p["weekly"][gameweek],
                 "captain": p["id"] == captain_id, "viceCaptain": p["id"] == vice_id}
                for p in sorted(selected, key=lambda p: (list(POSITION.values()).index(p["position"]), p["id"]))]
    remaining = [p for p in players if p["id"] not in selected_ids]
    # Reserve goalkeeper remains first; remaining substitutes by projected xPts.
    bench = sorted(remaining, key=lambda p: (p["position"] != "GK", -p["weekly"][gameweek], p["id"]))
    bench = [{**p, "nextGwXpts": p["weekly"][gameweek]} for p in bench]
    next_matches = sorted(
        (f for f in fixtures if f.get("event") == gameweek),
        key=lambda f: (f.get("kickoff_time") or "", f["id"]),
    )
    next_fixtures = [{
        "id": f["id"],
        "homeShort": teams[f["team_h"]]["short"],
        "awayShort": teams[f["team_a"]]["short"],
        "kickoffLabel": f.get("kickoff_label") or "TBC",
        "projectedHomeGoals": f.get("projected_home_goals"),
        "projectedAwayGoals": f.get("projected_away_goals"),
    } for f in next_matches]
    cues = narration_cues or []
    for cue in cues:
        if cue.get("playerId") not in {p["id"] for p in players}:
            raise ValueError("Narration cue references unknown player")
        if not (0 <= _number(cue.get("start"), "cue start") < _number(cue.get("end"), "cue end")):
            raise ValueError("Invalid narration cue")
    weekly_plans = []
    for week in range(gameweek, gameweek + 5):
        xi, ids, captain, vice = lineups[week]
        reserves = [p for p in players if p["id"] not in ids]
        reserves.sort(key=lambda p: (p["position"] != "GK", -p["weekly"][week], p["id"]))
        form = {pos: sum(p["position"] == pos for p in xi) for pos in ("DEF", "MID", "FWD")}
        weekly_plans.append({
            "gameweek": week,
            "formation": "{}-{}-{}".format(form["DEF"], form["MID"], form["FWD"]),
            "starters": [p["id"] for p in xi],
            "bench": [p["id"] for p in reserves],
            "captainId": captain,
            "viceCaptainId": vice,
        })
    return {
        "nextGameweek": gameweek,
        "formation": f"{sum(p['position']=='DEF' for p in starters)}-"
                     f"{sum(p['position']=='MID' for p in starters)}-"
                     f"{sum(p['position']=='FWD' for p in starters)}",
        "starters": starters,
        "bench": bench,
        "totalCost": round(total_cost, 2),
        "bank": round(bank, 2),
        "fiveGwXpts": round(sum(p["xpts"] for p in projections), 2),
        "projections": projections,
        "weeklyPlans": weekly_plans,
        "maxProjection": max(p["xpts"] for p in projections),
        "nextFixtures": next_fixtures,
        "modelLabel": model_label,
        "narrationCues": cues,
    }
