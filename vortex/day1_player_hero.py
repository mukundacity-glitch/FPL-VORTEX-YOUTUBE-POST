"""Retrospective Day 1 hero analysis based on official, final FPL data."""
from collections import defaultdict
from datetime import datetime, timezone
from html import escape
import json
from math import isfinite
from pathlib import Path

from .football_identity import full_club_name

SCORING = {
    "minutes": ("Appearance", "appearance points"),
    "goals_scored": ("Goals", "goals"),
    "assists": ("Assists", "assists"),
    "clean_sheets": ("Clean sheets", "clean sheets"),
    "goals_conceded": ("Goals conceded", "goals conceded"),
    "own_goals": ("Own goals", "own goals"),
    "saves": ("Saves", "saves"),
    "penalties_saved": ("Penalty saves", "penalty saves"),
    "penalties_missed": ("Missed penalties", "missed penalties"),
    "yellow_cards": ("Yellow cards", "yellow cards"),
    "red_cards": ("Red cards", "red cards"),
    "bonus": ("Bonus", "bonus"),
    "defensive_contribution": ("Defensive contribution", "defensive contribution"),
    "defensive_contribution_points": ("Defensive contribution", "defensive contribution"),
}
METRICS = {
    "minutes": "Minutes played",
    "starts": "Starts",
    "expected_goals": "Expected goals",
    "expected_assists": "Expected assists",
    "shots": "Shots",
    "shots_on_target": "Shots on target",
    "key_passes": "Key passes",
    "chances_created": "Chances created",
    "big_chances_created": "Big chances created",
    "defensive_contribution": "Defensive actions",
    "saves": "Saves",
    "penalties_saved": "Penalty saves",
    "clean_sheets": "Clean sheets",
}
WEIGHTS = {
    "points": .36, "value": .14, "minutes": .09, "goals": .05, "assists": .04,
    "expected_goals": .06, "expected_assists": .04, "shots": .015, "shots_on_target": .02,
    "key_passes": .015, "chances_created": .01, "big_chances_created": .015,
    "defensive_contribution": .04, "clean_sheets": .035, "saves": .035,
    "penalties_saved": .015, "bonus": .035, "ownership": .015, "difficulty": .025, "captaincy": .015, "relevance": .035,
}
SECTIONS = {
    "score": "Here is the points breakdown",
    "metrics": "Now for the underlying numbers",
    "context": "Here is the fixture context",
    "takeaway": "The Fantasy takeaway",
}


def number(value):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
        return result if isfinite(result) else None
    except (ValueError, TypeError):
        return None


def _fmt(value):
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _join(items):
    return ", ".join(items[:-1]) + f" and {items[-1]}" if len(items) > 1 else "".join(items)


def spoken_scoring(points):
    return _join([f"{_fmt(abs(points[key]))} {'from' if points[key] > 0 else 'lost to'} "
                  f"{SCORING.get(key, (key.replace('_', ' '),) * 2)[1]}"
                  for key in points if points[key]])


def completed_week(bootstrap):
    return max((int(row["id"]) for row in bootstrap["events"]
                if row.get("finished") is True and row.get("data_checked") is True), default=0)


def _score_breakdown(row, fixtures):
    by_stat = defaultdict(float)
    for explanation in row.get("explain") or []:
        if explanation["fixture"] not in fixtures:
            return {}
        for item in explanation.get("stats") or []:
            points = number(item.get("points"))
            if points is None or not item.get("identifier"):
                return {}
            by_stat[item["identifier"]] += points
    return dict(by_stat)


def analyze(bootstrap, fixtures, live, gameweek):
    if not gameweek or gameweek != completed_week(bootstrap):
        raise ValueError("Hero analysis requires the latest completed and checked FPL gameweek")
    matches = {f["id"]: f for f in fixtures if f.get("event") == gameweek}
    if not matches or not all(f.get("finished") for f in matches.values()):
        raise ValueError("Hero analysis requires finalized fixtures")
    players = {p["id"]: p for p in bootstrap["elements"]}
    event = next(row for row in bootstrap["events"] if row["id"] == gameweek)
    entries = number(event.get("entries"))
    pool = []
    for row in live["elements"]:
        player = players.get(row["id"])
        stats = row.get("stats") or {}
        minutes, points = number(stats.get("minutes")), number(stats.get("total_points"))
        if not player or not player.get("web_name") or minutes is None or minutes <= 0 or points is None:
            continue
        breakdown = _score_breakdown(row, matches)
        if not breakdown or not any(breakdown.values()) or sum(breakdown.values()) != points:
            continue
        price = number(player.get("now_cost"))
        match_ids = [x["fixture"] for x in row["explain"]]
        team = player["team"]
        ratings = [number(f.get("team_h_difficulty" if team == f["team_h"] else "team_a_difficulty"))
                   for match_id in match_ids for f in [matches[match_id]] if team in (f["team_h"], f["team_a"])]
        difficulty = sum(ratings) / len(ratings) if ratings and all(r is not None for r in ratings) else None
        measures = {key: number(stats.get(key)) for key in WEIGHTS}
        captain_count = number(stats.get("captained") if stats.get("captained") is not None else row.get("captained"))
        captaincy = 100 * captain_count / entries if entries and captain_count is not None and 0 <= captain_count <= entries else None
        measures.update(points=points, minutes=minutes, value=points / (price / 10) if price else None,
                        goals=number(stats.get("goals_scored")), ownership=number(player.get("selected_by_percent")),
                        relevance=number(player.get("chance_of_playing_next_round")),
                        difficulty=difficulty, captaincy=captaincy)
        pool.append(dict(player=player, stats=stats, points=points, price=price / 10 if price else None,
                         breakdown=breakdown, fixtures=match_ids, measures=measures))

    if not pool:
        raise ValueError("No verified hero candidate reconciles to its official points breakdown")
    # Compare observed values on the same scale. Missing observations contribute no evidence.
    maxima = {key: max((p["measures"][key] or 0 for p in pool), default=0) for key in WEIGHTS}
    for candidate in pool:
        candidate["score"] = sum(weight * candidate["measures"][key] / maxima[key]
                                 for key, weight in WEIGHTS.items()
                                 if maxima[key] > 0 and candidate["measures"][key] is not None)
    hero = max(pool, key=lambda p: (p["score"], p["points"], -p["player"]["id"]))
    player = hero["player"]
    teams = {team["id"]: team for team in bootstrap["teams"]}
    position = next(t["singular_name"] for t in bootstrap["element_types"] if t["id"] == player["element_type"])
    contexts = []
    for match_id in dict.fromkeys(hero["fixtures"]):
        match = matches[match_id]
        contexts.append({
            "home": full_club_name(teams[match["team_h"]], speech=True),
            "away": full_club_name(teams[match["team_a"]], speech=True),
            "home_score": match["team_h_score"], "away_score": match["team_a_score"],
        })
    return {
        "gameweek": gameweek, "name": player["web_name"], "player_id": player["id"],
        "club": full_club_name(teams[player["team"]], speech=True), "position": position,
        "player": player, "price": hero["price"], "points": hero["points"],
        "captain_points": hero["points"] * 2, "breakdown": hero["breakdown"],
        "metrics": {label: value for key, label in METRICS.items()
                    if (value := number(hero["stats"].get(key))) is not None},
        "fixtures": contexts, "observation_scope": "Completed gameweek",
        "current_ownership": hero["measures"]["ownership"],
        "gameweek_captaincy_rate": hero["measures"]["captaincy"],
        "points_per_million": hero["measures"]["value"],
        "selection": {"candidates": len(pool), "weights": WEIGHTS, "score": hero["score"],
                      "measures": hero["measures"],
                      "reason": "Highest combined score across official points, minutes, value and available performance and fixture indicators."},
        "sources": ["FPL bootstrap-static", "FPL fixtures", f"FPL event/{gameweek}/live"],
        "analyzed_at_utc": datetime.now(timezone.utc).isoformat(),
    }



def add_recent_context(hero, history):
    previous = sorted({int(row["round"]) for row in history
                       if row.get("round") and int(row["round"]) < hero["gameweek"]})[-3:]
    minutes = [number(row.get("minutes")) for row in history if row.get("round") in previous]
    if len(previous) == 3 and all(value is not None for value in minutes):
        hero["recent_context"] = {"gameweeks": previous, "minutes": int(sum(minutes))}
        hero["sources"].append(f"FPL element-summary/{hero['player_id']}")

def narration(hero, spoken_name):
    points = _fmt(hero["points"])
    opening = (f"{spoken_name} is the player in focus for Gameweek {hero['gameweek']}. "
               f"The {hero['club']} {hero['position'].lower()} finished on {points} points. "
               f"That is {_fmt(hero['captain_points'])} with standard captaincy.")
    scoring = spoken_scoring(hero["breakdown"])
    breakdown = f"{SECTIONS['score']}. The official scoring shows {scoring}."
    metrics = hero["metrics"]
    details = [f"{_fmt(value)} {label.lower()}" for label, value in metrics.items()
               if value or label in {"Expected goals", "Expected assists"}]
    underlying = f"{SECTIONS['metrics']}. "
    if details:
        underlying += f"The gameweek records {_join(details)}. "
    xg = metrics.get("Expected goals")
    goals = hero["selection"]["measures"]["goals"]
    if xg is not None and goals is not None:
        relation = "above" if goals > xg else "below" if goals < xg else "in line with"
        underlying += f"The goal return was {relation} the expected goal total for this gameweek. "
    history = hero.get("recent_context")
    if history:
        underlying += f"Across the previous three Gameweeks, {spoken_name} played {history['minutes']} minutes. "
    underlying += "Check whether the same playing time and involvement hold across several fixtures before using this return to judge future points."
    results = [f"{m['home']} {m['home_score']}, {m['away']} {m['away_score']}" for m in hero["fixtures"]
               if m["home_score"] is not None and m["away_score"] is not None]
    context = f"{SECTIONS['context']}. "
    if results:
        context += f"The final {'scores were' if len(results) > 1 else 'score was'} {_join(results[:3])}. "
    difficulty = hero["selection"]["measures"]["difficulty"]
    if difficulty is not None:
        context += f"The official fixture rating was {_fmt(difficulty)} out of five on average. "
    if hero["price"] is not None:
        context += f"At the time of analysis, {spoken_name} cost {_fmt(hero['price'])} million pounds. "
    if hero["current_ownership"] is not None:
        context += f"Current ownership was {_fmt(hero['current_ownership'])} percent. "
    if hero["gameweek_captaincy_rate"] is not None:
        context += f"The gameweek captaincy rate was {_fmt(hero['gameweek_captaincy_rate'])} percent. "
    takeaway = (f"{SECTIONS['takeaway']}. Use the verified scoring actions to understand this return, "
                "then check the role, the playing time and the upcoming opponents before making a transfer.")
    return " ".join((opening, breakdown, underlying, context, takeaway))


def render(hero, cue_times, portrait, crest, logo):
    def rows(items, signed=False):
        return "".join(
            f'<div><span>{escape(label)}</span><b>{value:+g}</b></div>' if signed else
            f'<div><span>{escape(label)}</span><b>{_fmt(value)}</b></div>'
            for label, value in items
        )

    scoring_rows = rows([
        (SCORING.get(k, (k.replace("_", " ").title(),))[0], v)
        for k, v in hero["breakdown"].items() if v
    ], signed=True)
    images = "".join(f'<img class="{kind}" src="{escape(src, quote=True)}" alt="">'
                     for kind, src in (("portrait", portrait), ("crest", crest)) if src)
    results = "".join(
        f"<p>{escape(m['home'])} <b>{m['home_score']}–{m['away_score']}</b> {escape(m['away'])}</p>"
        for m in hero["fixtures"] if m["home_score"] is not None and m["away_score"] is not None
    )
    details = [
        ("Price at analysis", f"£{_fmt(hero['price'])}m") if hero["price"] is not None else None,
        ("Ownership at analysis", f"{_fmt(hero['current_ownership'])}%") if hero["current_ownership"] is not None else None,
    ]
    if hero["gameweek_captaincy_rate"] is not None:
        details.append(("Gameweek captaincy", f"{_fmt(hero['gameweek_captaincy_rate'])}%"))
    details = "".join(f"<p>{item[0]} <b>{item[1]}</b></p>" for item in details if item)
    metrics = rows(hero["metrics"].items())
    modules = [
        ("score", "How the points were earned", scoring_rows),
        ("metrics", "The underlying numbers", metrics),
        ("context", "Fixture context", results + details),
        ("takeaway", "The Fantasy takeaway", "<p>Check playing time, role and upcoming opposition before acting on one return.</p>"),
    ]
    sidebar = "".join(f'<section id="{key}"><h2>{heading}</h2><div class="rows">{body}</div></section>'
                      for key, heading, body in modules if body)
    style = Path(__file__).with_name("day1_player_hero.css").read_text()
    return f"""<!DOCTYPE html><html lang="en"><meta charset="utf-8"><style>{style}</style>
    <body><header>{logo}<div>FPL PLAYER HERO CARD<strong>The Numbers Behind the Points</strong></div>
    <b>GAMEWEEK {hero['gameweek']}</b></header>
    <main><article class="{'has-portrait' if portrait else 'without-portrait'}">{images}<div class="identity"><span>{escape(hero['club'])} · {escape(hero['position'])}</span>
    <h1>{escape(hero['name'])}</h1><div class="returns"><div><strong>{_fmt(hero['points'])}</strong>FPL points</div>
    <div><strong>{_fmt(hero['captain_points'])}</strong>With standard captaincy</div></div></div></article>
    <aside>{sidebar}</aside></main><footer>OFFICIAL FPL MATCH DATA <b>FPL VORTEX</b></footer>
    <script>
    const cues={json.dumps(cue_times)};
    window.__seek=t=>{{
      let active="score";
      for(const [key, start] of Object.entries(cues)) if(t>=start) active=key;
      const selected=document.getElementById(active);
      if(selected) for(const node of document.querySelectorAll("aside section")) {{
        node.hidden=node!==selected;
        if(node===selected) {{
          const phase=Math.max(0,Math.min(1,(t-(cues[active]??0))/.32));
          const progress=1-(1-phase)**3;
          node.style.opacity=.78+.22*progress;
          node.style.transform=`translateY(${{(1-progress)*16}}px)`;
        }}
      }}
    }};
    window.__seek(0);
    window.__ready=true;
    </script></body></html>"""
