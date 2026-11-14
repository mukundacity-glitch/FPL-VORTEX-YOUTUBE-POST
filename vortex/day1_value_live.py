"""Live, auditable FPL Value Board optimisation for Day 1.

Primary source is the official public FPL API, never fixture/ownership numbers
copied from screenshots. Projected xPts are a clearly labelled VORTEX research
estimate derived from published FPL performance indicators plus opponents and
availability; they are NOT official forward projections or guarantees.
"""
from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite
from pathlib import Path
import json
import unicodedata
from typing import Any

from scipy.optimize import Bounds, LinearConstraint, milp
import numpy as np
import requests

from .day1_value_board import SQUAD_BUDGET, build_value_board
from .football_identity import full_club_name

API = "https://fantasy.premierleague.com/api"
USER_AGENT = "FPL-VORTEX-Day1-ValueBoard/1.0"


def fetch_json(url: str, session=None) -> Any:
    transport = session or requests
    response = transport.get(url, timeout=30, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    return response.json()


def fnum(raw, fallback=0.0):
    try:
        n = float(raw)
        return n if isfinite(n) else fallback
    except (ValueError, TypeError):
        return fallback


def select_next_gw(events):
    upcoming = [event for event in events if event.get("is_next")]
    if len(upcoming) != 1:
        raise ValueError("Could not resolve exactly one official upcoming FPL GW")
    gw = int(upcoming[0]["id"])
    if gw > 34:
        raise ValueError("A full five-gameweek horizon is not available")
    return gw


def _status_factor(player):
    status = player.get("status")
    if status in {"i", "s", "u", "n"}:
        return 0.0
    chance = player.get("chance_of_playing_next_round")
    if status == "d":
        if chance is None:
            return 0.30
        return max(0.0, min(1.0, fnum(chance) / 100.0))
    return 1.0 if status == "a" else 0.55


def _recent_minutes(player, recent):
    # Exact most recent official player-summary minutes are strongly preferred.
    if recent:
        matches = [m for m in recent[-5:] if m.get("minutes") is not None]
        if matches:
            return sum(fnum(m["minutes"]) for m in matches) / len(matches)
    starts = max(0.0, fnum(player.get("starts")))
    appearances = max(starts, fnum(player.get("appearances"), starts))
    if appearances:
        return min(90.0, fnum(player.get("minutes")) / appearances)
    # No appearances: treat as an unproven pick, not a regular starter.
    return 0.0


def _model_points(player, opponent_rating, minutes_avg, next_gw=False):
    # No model should present unverified minutes or availability as certainty.
    readiness = _status_factor(player)
    if readiness <= 0:
        return 0.0
    historic = fnum(player.get("points_per_game"))
    form = fnum(player.get("form"))
    official_next = fnum(player.get("ep_next"), -1.0)
    attack_xgi = fnum(player.get("expected_goal_involvements_per_90"))
    # We apply published forecast ep_next ONLY to the immediate upcoming GW.
    # Future weeks use observed PPG/form and a conservative per-90 xGI signal.
    base = .55 * historic + .35 * form + .10 * min(8.0, attack_xgi * 4.0)
    if next_gw and official_next >= 0:
        base = .60 * base + .40 * official_next
    # Fixtures rating 1=easiest, 5=hardest. Limit adjustment to +/- 18%.
    fixture_factor = 1.0 + max(-.18, min(.18, (3.0-opponent_rating)*.09))
    # Conservative minutes model: full-match regulars earn larger share.
    minutes_factor = .25 + .75 * min(1.0, max(0.0, minutes_avg / 78.0))
    return round(max(0.0, base * fixture_factor * minutes_factor * readiness), 3)


def _fetch_recent(players, session, priority=()):
    # Limit API calls to the strongest preliminary candidates, not the full pool.
    candidates = sorted(players, key=lambda p: (
        p["id"] not in priority,
        -(_status_factor(p) * (fnum(p.get("form")) + fnum(p.get("points_per_game")))),
        -fnum(p.get("selected_by_percent")), p["id"],
    ))[:110]
    result = {}
    for player in candidates:
        try:
            payload = fetch_json(f"{API}/element-summary/{player['id']}/", session)
            result[player["id"]] = payload.get("history", [])
        except (requests.RequestException, ValueError, KeyError):
            # Missing summaries are marked as fallback to season minutes.
            result[player["id"]] = []
    return result


def _week_ratings(fixtures, team_id, gw):
    matches = [f for f in fixtures if f.get("event") == gw and
               team_id in (f.get("team_h"), f.get("team_a"))]
    if not matches:
        return [(None, 3.0)]
    out = []
    for fixture in matches:
        home = fixture["team_h"] == team_id
        # Official FDR is the starting point. FPL rates the opponent from 1-5.
        raw_rating = fixture.get("team_h_difficulty" if home else "team_a_difficulty")
        rating = fnum(raw_rating, None)
        if rating is not None and not 1 <= rating <= 5:
            rating = None
        out.append((fixture["id"], rating))
    return out


def _name_key(name):
    normalized = unicodedata.normalize("NFKD", name.casefold()).replace("ß", "ss")
    return "".join(c for c in normalized if c.isascii() and c.isalnum())


def _resolve_picks(players, preferences):
    def resolve(name, position):
        matches = []
        for player in players:
            if player.get("element_type") != position:
                continue
            first, last = player.get("first_name", ""), player.get("second_name", "")
            aliases = (player.get("web_name", ""), f"{first} {last}",
                       *(f"{first} {part}" for part in last.split()))
            if _name_key(name) in {_name_key(alias) for alias in aliases}:
                matches.append(player)
        return matches[0]["id"] if len(matches) == 1 else None

    preferred, options, unresolved = {}, {}, []
    for position, group in enumerate(("goalkeepers", "defenders", "midfielders", "forwards"), 1):
        for name in preferences[group]:
            player_id = resolve(name, position)
            if player_id is None:
                unresolved.append(name)
            else:
                preferred[player_id] = position
            for option in preferences["alternatives"].get(name, []):
                if (option_id := resolve(option, position)) is not None:
                    options[option_id] = player_id
    return preferred, options, unresolved


DEFCON_THRESHOLD = 10


def _hero_stats(player, history, gameweek):
    def optional(key):
        return fnum(player.get(key), None)

    def rate(key):
        minutes, total = optional("minutes"), optional(key)
        return round(total * 90 / minutes, 2) if minutes and total is not None else None

    # History is match-level. Season minutes also include substitute minutes.
    starts = [fnum(match.get("minutes"), None) for match in history
              if match.get("starts") == 1 and fnum(match.get("round")) < gameweek]
    dc = [fnum(match.get("defensive_contribution"), None) for match in history
          if fnum(match.get("minutes")) > 0 and fnum(match.get("round")) < gameweek]
    dc = [value for value in dc if value is not None]
    return {
        "xg90": optional("expected_goals_per_90"), "xa90": optional("expected_assists_per_90"),
        "goals90": rate("goals_scored"), "assists90": rate("assists"), "saves90": rate("saves"),
        "minutesPerStart": round(sum(starts) / len(starts)) if starts and None not in starts else None,
        "defensiveActions90": optional("defensive_contribution_per_90"),
        "defconHits": sum(value >= DEFCON_THRESHOLD for value in dc) if dc else None,
        "defconAppearances": len(dc) if dc else None,
    }


def _optimise(players, cost, points, next_scores, minutes, *, budget, preferred, options):
    n = len(players)
    if n < 15:
        raise ValueError("Fewer than 15 eligible players")
    owned = np.array([max(0, min(100, fnum(p.get("selected_by_percent")))) for p in players])
    # Ownership and net transfer activity serve as minor tie-breakers, never
    # a replacement for minutes, injury probability and xPts.
    net = np.array([fnum(p.get("transfers_in_event")) - fnum(p.get("transfers_out_event")) for p in players])
    market = np.clip(net / 100000.0, -1.0, 1.0)
    objective = np.asarray(points)*.83 + np.asarray(next_scores)*.12 + owned*.001 + market*.03
    # Preserve the requested keepers, defenders and forwards before considering
    # sideways moves. With equal retention, reward minutes and projected returns.
    objective = 80 * objective / max(1, objective.max()) + np.minimum(minutes, 90) / 9
    cost_by_id = {p["id"]: cost[i] for i, p in enumerate(players)}
    for i, player in enumerate(players):
        player_id = player["id"]
        if player_id in preferred:
            objective[i] += 100000 if player["element_type"] in (1, 2, 4) else 2000
        elif player_id in options and (options[player_id] is None or
                cost[i] < cost_by_id.get(options[player_id], float("inf"))):
            objective[i] += 140
    rows, lower, upper = [], [], []

    def constraint(values, lo, hi):
        rows.append(np.asarray(values, dtype=float))
        lower.append(lo)
        upper.append(hi)

    for position, amount in ((1, 2), (2, 5), (3, 5), (4, 3)):
        constraint([int(p["element_type"] == position) for p in players], amount, amount)
    for club_id in {p["team"] for p in players}:
        constraint([int(p["team"] == club_id) for p in players], 0, 3)
    constraint([round(c * 10) for c in cost], 0, round(budget * 10))
    # A named alternative fills the same roster slot as the original pick.
    for option, original in options.items():
        if original is not None:
            constraint([int(p["id"] in (option, original)) for p in players], 0, 1)

    result = milp(c=-objective, integrality=np.ones(n),
                  bounds=Bounds(np.zeros(n), np.ones(n)),
                  constraints=LinearConstraint(np.vstack(rows), lower, upper),
                  options={"time_limit": 60, "mip_rel_gap": 0.0})
    if result.x is None or result.status not in (0, 1):
        raise ValueError(f"No valid £{budget:g}m squad with two playing goalkeepers: status={result.status}")
    selected = [p for p, flag in zip(players, result.x) if flag > .5]
    if len(selected) != 15:
        raise ValueError("MIP solver returned an incomplete squad")
    return selected


def make_live_value_board(*, session=None, snapshot=None):
    bootstrap = snapshot["bootstrap"] if snapshot else fetch_json(f"{API}/bootstrap-static/", session)
    fixtures = snapshot["fixtures"] if snapshot else fetch_json(f"{API}/fixtures/", session)
    gw = select_next_gw(bootstrap["events"])
    all_players = bootstrap["elements"]
    raw_teams = bootstrap["teams"]
    team_map = {t["id"]: {
        "id": t["id"], "name": t["name"], "short": t["short_name"],
        "badge": f"https://resources.premierleague.com/premierleague/badges/100/t{t['code']}.png",
    } for t in raw_teams}
    preferences = json.loads(Path(__file__).with_name("day1_value_picks.json").read_text(encoding="utf-8"))
    budget = preferences.get("budget", SQUAD_BUDGET)
    preferred, options, unresolved = _resolve_picks(all_players, preferences)
    recent = (_fetch_recent(all_players, session, preferred.keys() | options.keys())
              if snapshot is None else snapshot.get("recent", {}))
    valid = []
    forecast = []
    price = []
    totals = []
    next_points = []
    recent_minutes = []
    recent_weeks = range(max(1, gw - 5), gw)
    recent_club_matches = {team: 0 for team in team_map}
    for match in fixtures:
        if match.get("finished") and match.get("event") in recent_weeks:
            recent_club_matches[match["team_h"]] += 1
            recent_club_matches[match["team_a"]] += 1

    for player in all_players:
        if player.get("element_type") not in (1, 2, 3, 4):
            continue
        if player.get("team") not in team_map or _status_factor(player) <= 0:
            continue
        cost = fnum(player.get("now_cost")) / 10
        if cost < 3 or cost > 16:
            continue
        history = recent.get(player["id"], [])
        avg = _recent_minutes(player, history)
        if player["element_type"] == 1:
            club_matches = recent_club_matches[player["team"]]
            starts = sum(fnum(m.get("starts")) for m in history
                         if fnum(m.get("round")) in recent_weeks)
            reliable_role = (not club_matches or starts >= min(3, club_matches)
                             or (not history and
                                 fnum(player.get("starts")) >= max(1, gw - 3)))
            if avg < 60 or _status_factor(player) < 1 or not reliable_role:
                continue
        elif player["id"] not in preferred:
            season_starts = fnum(player.get("starts"))
            recent_starts = sum(fnum(m.get("starts")) for m in history if fnum(m.get("round")) in recent_weeks)
            established = recent_starts >= 3 if history else season_starts >= max(3, gw * .55)
            if avg < 60 or _status_factor(player) < 1 or not established:
                continue
        series = []
        for index, week in enumerate(range(gw, gw+5)):
            actual_fixtures = [(fid, rating) for fid, rating in
                               _week_ratings(fixtures, player["team"], week) if fid is not None]
            match_scores = [_model_points(player, rating if rating is not None else 3.0,
                                          avg, next_gw=index==0 and len(actual_fixtures)==1)
                            for _, rating in actual_fixtures]
            score = sum(match_scores)
            if index == 0 and len(match_scores) > 1:
                # ep_next is a whole-GW estimate; never apply it once per
                # fixture or a double gameweek will double count the signal.
                ep = fnum(player.get("ep_next"), -1.0)
                if ep >= 0:
                    score = .75 * score + .25 * ep * _status_factor(player)
            series.append(round(score, 3))
            forecast.append({"player_id": player["id"], "team_id": player["team"],
                             "gameweek": week, "gameweek_expected_points": score})
        valid.append(player)
        price.append(cost)
        totals.append(sum(series))
        next_points.append(series[0])
        recent_minutes.append(avg)
    selected = _optimise(valid, price, totals, next_points, np.asarray(recent_minutes),
                         budget=budget, preferred=preferred, options=options)
    selected_ids = {p["id"] for p in selected}
    selected_forecast = [row for row in forecast if row["player_id"] in selected_ids]
    enriched = []
    for match in fixtures:
        if match.get("event") not in range(gw, gw+6):
            continue
        item = dict(match)
        item["fdr_by_team"] = {
            match["team_h"]: _week_ratings([match], match["team_h"], match["event"])[0][1],
            match["team_a"]: _week_ratings([match], match["team_a"], match["event"])[0][1],
        }
        enriched.append(item)
    board = build_value_board(
        gameweek=gw, squad=selected, forecasts=selected_forecast,
        fixtures=enriched, teams=team_map,
        model_label="VORTEX research xPts · official FPL form / price / minutes / FDR",
        budget=budget,
    )
    board["marketSnapshotUTC"] = datetime.now(timezone.utc).isoformat()
    board["dataOrigin"] = "official FPL bootstrap-static, fixtures, element-summary"
    board["method"] = ("Weighted historic PPG/form, next-week FPL ep_next when provided, "
                       "xGI/90, injury availability, observed minutes and fixture FDR. "
                       f"Constrained 15-player MILP, £{budget:g}m, 3 per club, two playing keepers.")
    preferred_rows = [p for p in all_players if p["id"] in preferred]
    board["preferredCost"] = round(sum(p["now_cost"] for p in preferred_rows) / 10, 1) if not unresolved else None
    board["selectionChanges"] = {
        "omitted": [p["web_name"] for p in preferred_rows if p["id"] not in selected_ids],
        "added": [p["web_name"] for p in selected if p["id"] not in preferred],
        "unresolved": unresolved,
    }
    market_by_id = {p["id"]: p for p in selected}
    for row in [*board["starters"], *board["bench"]]:
        raw = market_by_id[row["id"]]
        row["photoCode"] = raw.get("code")
        row["clubSpeechName"] = full_club_name({**team_map[raw["team"]], "code": next(t["code"] for t in raw_teams if t["id"] == raw["team"])}, speech=True)
        for tile in row["fixtures"]:
            opponent_id = tile["opponentId"]
            tile["opponentSpeechName"] = full_club_name({**team_map[opponent_id], "code": next(t["code"] for t in raw_teams if t["id"] == opponent_id)}, speech=True)
        row["ownership"] = fnum(raw.get("selected_by_percent"), None)
        row["heroStats"] = _hero_stats(raw, recent.get(row["id"], []), gw)
        row["netTransfers"] = int(fnum(raw.get("transfers_in_event")) - fnum(raw.get("transfers_out_event")))
        row["minutesPerAppearance"] = round(_recent_minutes(raw, recent.get(row["id"], [])), 1)
        row["availability"] = raw.get("status") or "unknown"
    board["marketTrends"] = [
        {"playerId": p["id"], "ownership": fnum(p.get("selected_by_percent")),
         "transfersIn": p.get("transfers_in_event"), "transfersOut": p.get("transfers_out_event")}
        for p in selected
    ]
    return board


if __name__ == "__main__":
    import json
    print(json.dumps(make_live_value_board(), ensure_ascii=False, indent=2))
