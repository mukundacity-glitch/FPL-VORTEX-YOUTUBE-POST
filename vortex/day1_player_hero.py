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
    "goals_scored": "Goals",
    "assists": "Assists",
    "bonus": "Bonus",
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
PLAYER_LIMIT = 3
DIFFERENTIAL_OWNERSHIP = 10
# Leave room for encoder padding when the final scene is extracted.
NARRATION_LIMIT = 119
PLAYER_CUES = ("The overall hero", "The second profile", "The third profile")



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
        match_ids = list(dict.fromkeys(item["fixture"] for item in row["explain"]))
        team = player["team"]
        player_matches = [matches[match_id] for match_id in match_ids]
        if any(team not in (match["team_h"], match["team_a"]) for match in player_matches):
            continue
        ratings = [number(match.get("team_h_difficulty" if team == match["team_h"] else "team_a_difficulty"))
                   for match in player_matches]
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

    if len(pool) < PLAYER_LIMIT:
        raise ValueError("Fewer than three verified players reconcile to their official points breakdown")
    # Compare observed values on the same scale. Missing observations contribute no evidence.
    maxima = {key: max((p["measures"][key] or 0 for p in pool), default=0) for key in WEIGHTS}
    for candidate in pool:
        candidate["score"] = sum(weight * candidate["measures"][key] / maxima[key]
                                 for key, weight in WEIGHTS.items()
                                 if maxima[key] > 0 and candidate["measures"][key] is not None)
    return select_profiles(pool, bootstrap, matches, gameweek)


def select_profiles(pool, bootstrap, matches, gameweek):
    def rank(candidate):
        return candidate["score"], candidate["points"], -candidate["player"]["id"]

    def underlying(candidate):
        measures = candidate["measures"]
        return sum(measures[key] or 0 for key in ("expected_goals", "expected_assists"))

    overall = max(pool, key=rank)
    remaining = [candidate for candidate in pool if candidate is not overall]
    priced = [candidate for candidate in remaining if candidate["measures"]["value"] is not None]
    value = max(priced, key=lambda p: (p["measures"]["value"], rank(p))) if priced else max(remaining, key=rank)
    remaining = [candidate for candidate in remaining if candidate is not value]
    differentials = [p for p in remaining if p["measures"]["ownership"] is not None
                     and 0 <= p["measures"]["ownership"] < DIFFERENTIAL_OWNERSHIP
                     and underlying(p) >= .35 and p["measures"]["minutes"] >= 45]
    defensive = [p for p in remaining if p["player"]["element_type"] in (1, 2)
                 and p["points"] >= 9 and any(p["breakdown"].get(key, 0) > 0 for key in (
                     "clean_sheets", "saves", "penalties_saved", "defensive_contribution",
                     "defensive_contribution_points"))]
    if differentials:
        third = max(differentials, key=lambda p: (underlying(p), rank(p)))
        category = "Differential"
        why = "Strongest combined expected goals and assists among eligible players below ten percent ownership."
    elif defensive:
        third = max(defensive, key=rank)
        category = "Defensive standout"
        why = "Highest weighted score among the remaining exceptional defensive returns."
    else:
        third = max(remaining, key=rank)
        category = "Underlying performance"
        why = "Highest remaining weighted score after the overall and value selections."
    choices = [
        (overall, "Overall hero", "Highest weighted score across official points, value and available match indicators."),
        (value, "Best value" if priced else "Performance profile",
         "Most points per million among the remaining players with a verified price."
         if priced else "Highest remaining weighted score with prices unavailable."),
        (third, category, why),
    ]
    teams = {team["id"]: team for team in bootstrap["teams"]}
    positions = {position["id"]: position["singular_name"] for position in bootstrap["element_types"]}
    return {
        "gameweek": gameweek,
        "candidates_analyzed": len(pool),
        "weights": WEIGHTS,
        "players": [_profile(candidate, label, why, teams, positions, matches)
                    for candidate, label, why in choices],
        "sources": ["FPL bootstrap-static", "FPL fixtures", f"FPL event/{gameweek}/live"],
        "analyzed_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def _profile(candidate, label, why, teams, positions, matches):
    player = candidate["player"]
    measures = candidate["measures"]
    stats = candidate["stats"]
    contexts = []
    for match_id in dict.fromkeys(candidate["fixtures"]):
        match = matches[match_id]
        home = match["team_h"] == player["team"]
        opponent = match["team_a"] if home else match["team_h"]
        contexts.append({
            "fixture": match_id,
            "opponent": full_club_name(teams[opponent], speech=True),
            "venue": "home" if home else "away",
            "goals_for": match["team_h_score" if home else "team_a_score"],
            "goals_against": match["team_a_score" if home else "team_h_score"],
        })
    metrics = {title: value for key, title in METRICS.items()
               if (value := number(stats.get(key))) is not None}
    takeaway = "Check repeat starts before acting on one gameweek."
    goals = measures["goals"]
    expected_goals = measures["expected_goals"]
    if goals is not None and expected_goals is not None and goals - expected_goals >= .5:
        takeaway = "Goals ran ahead of chance quality. Check whether the chances recur."
    elif label == "Best value":
        takeaway = "Check repeat minutes before treating the price as lasting value."
    elif label == "Defensive standout":
        takeaway = "Check the next opponent before expecting another defensive return."
    elif label == "Differential":
        takeaway = "Check whether the chance involvement carries into the next fixture."
    return {
        "name": player["web_name"], "player_id": player["id"], "player": player,
        "club": full_club_name(teams[player["team"]], speech=True),
        "position": positions[player["element_type"]], "price": candidate["price"],
        "points": candidate["points"], "captain_points": candidate["points"] * 2,
        "breakdown": candidate["breakdown"], "metrics": metrics, "fixtures": contexts,
        "current_ownership": measures["ownership"], "gameweek_captaincy_rate": measures["captaincy"],
        "points_per_million": measures["value"], "takeaway": takeaway,
        "goals_above_expected": goals - expected_goals if goals is not None and expected_goals is not None else None,
        "selection": {"category": label, "reason": why, "score": candidate["score"], "measures": measures},
    }


def add_recent_context(profile, history, gameweek):
    previous = set(range(max(1, gameweek - 3), gameweek))
    rows = [row for row in history if row.get("round") in previous]
    minutes = [number(row.get("minutes")) for row in rows]
    if previous and {row["round"] for row in rows} == previous and all(v is not None for v in minutes):
        profile["recent_context"] = {"gameweeks": sorted(previous), "minutes": int(sum(minutes)),
                                     "source": f"FPL element-summary/{profile['player_id']}"}


def narration(analysis, spoken_names, *, compact=False):
    lines = [f"Three players from Gameweek {analysis['gameweek']} show how different performances earn Fantasy Premier League points."]
    for cue, profile, name in zip(PLAYER_CUES, analysis["players"], spoken_names, strict=True):
        breakdown = sorted(((key, value) for key, value in profile["breakdown"].items() if value),
                           key=lambda item: (-abs(item[1]), item[0]))
        scoring = spoken_scoring(dict(breakdown[:2 if compact else 3]))
        opening = f"{cue} is {name}, with {_fmt(profile['points'])} points."
        category = profile["selection"]["category"]
        if category == "Best value":
            opening += " This was the best value among the remaining players."
        elif category == "Differential":
            opening += f" Ownership at analysis was {_fmt(profile['current_ownership'])} percent."
        elif category == "Defensive standout":
            opening += f" The {profile['position'].lower()} stood out for defensive returns."
        returns = f"The main scoring actions were {scoring}."
        details = []
        if profile["metrics"].get("Minutes played") is not None:
            details.append(f"{_fmt(profile['metrics']['Minutes played'])} minutes")
        if profile["selection"]["category"] == "Best value":
            details.append(f"{_fmt(profile['points_per_million'])} points per million")
        elif profile["selection"]["category"] == "Defensive standout":
            for metric in ("Saves", "Clean sheets", "Defensive actions"):
                if profile["metrics"].get(metric):
                    details.append(f"{_fmt(profile['metrics'][metric])} {metric.lower()}")
                    break
        else:
            for metric in ("Expected goals", "Expected assists"):
                if profile["metrics"].get(metric) is not None:
                    details.append(f"{_fmt(profile['metrics'][metric])} {metric.lower()}")
        evidence = f"The record shows {_join(details)}." if details else ""
        fixture = profile["fixtures"][0]
        venue = "at home" if fixture["venue"] == "home" else "away"
        context = ""
        if len(profile["fixtures"]) > 1 and not compact:
            context = "The return spans fixtures against " + _join([m["opponent"] for m in profile["fixtures"]]) + "."
        elif not compact:
            score = (fixture["goals_for"], fixture["goals_against"])
            if None not in score:
                context = f"The match against {fixture['opponent']} ended {score[0]} to {score[1]} {venue}."
            else:
                context = f"The match against {fixture['opponent']} was {venue}."
        history = profile.get("recent_context")
        if history and not compact:
            evidence += f" Recent playing time was {history['minutes']} minutes across {len(history['gameweeks'])} gameweeks."
        lines.append(" ".join(part for part in (opening, returns, evidence, context, profile["takeaway"]) if part))
    return "\n\n".join(lines)


def _rows(items, signed=False):
    return "".join(
        f'<div><span>{escape(label)}</span><b>{value:+g}</b></div>' if signed else
        f'<div><span>{escape(label)}</span><b>{_fmt(value)}</b></div>'
        for label, value in items
    )


def _card(profile, portrait, crest):
    scoring = _rows(((SCORING.get(k, (k.replace("_", " ").title(),))[0], v)
                     for k, v in profile["breakdown"].items() if v), signed=True)
    images = "".join(f'<img class="{kind}" src="{escape(src, quote=True)}" alt="">'
                     for kind, src in (("portrait", portrait), ("crest", crest)) if src)
    matches = " · ".join(
        f"{escape(m['opponent'])} ({m['venue'][0].upper()}) {m['goals_for']}–{m['goals_against']}"
        if m["goals_for"] is not None and m["goals_against"] is not None
        else f"{escape(m['opponent'])} ({m['venue'][0].upper()})"
        for m in profile["fixtures"])
    stats = [(label, value) for label, value in profile["metrics"].items() if value or label.startswith("Expected")]
    for field, name in (("points_per_million", "Points per million"),
                        ("current_ownership", "Ownership at analysis (%)"),
                        ("gameweek_captaincy_rate", "Gameweek captaincy (%)")):
        if profile[field] is not None:
            stats.append((name, profile[field]))
    price = f" · £{_fmt(profile['price'])}m" if profile["price"] is not None else ""
    difficulty = profile["selection"]["measures"]["difficulty"]
    difficulty_label = f" · Fixture difficulty {_fmt(difficulty)}/5" if difficulty is not None else ""
    return f"""<main class="profile" id="hero-{profile['player_id']}" hidden>
    <article class="{'has-portrait' if portrait else 'without-portrait'}">{images}
      <div class="identity"><span class="category">{escape(profile['selection']['category'])}</span>
      <h1>{escape(profile['name'])}</h1><span>{escape(profile['club'])} · {escape(profile['position'])}{price}</span>
      <div class="returns"><div><strong>{_fmt(profile['points'])}</strong>FPL points</div>
      <div><strong>{_fmt(profile['captain_points'])}</strong>With standard captaincy</div></div></div></article>
    <aside><h2>Where the points came from</h2><div class="rows scoring">{scoring}</div>
    <h2>Underlying numbers</h2><div class="rows metrics">{_rows(stats)}</div>
    <p class="fixture">{matches}{difficulty_label}</p>
    <p class="takeaway">{escape(profile['takeaway'])}</p></aside></main>"""


def render(analysis, cue_times, assets, logo):
    profiles = "".join(_card(profile, *assets[profile["player_id"]]) for profile in analysis["players"])
    style = Path(__file__).with_name("day1_player_hero.css").read_text()
    return f"""<!DOCTYPE html><html lang="en"><meta charset="utf-8"><style>{style}</style>
    <body><header>{logo}<div>FPL PLAYER HERO CARD<strong>The Numbers Behind the Points</strong></div>
    <b>GAMEWEEK {analysis['gameweek']}</b></header>
    <div class="profiles">{profiles}</div>
    <footer>OFFICIAL FPL MATCH DATA <b>FPL VORTEX</b></footer>
    <script>
    const cues={json.dumps(cue_times)};
    const cards=[...document.querySelectorAll(".profile")];
    window.__seek=t=>{{
      const active=Math.max(0,cues.findLastIndex(start=>t>=start));
      cards.forEach((card,index)=>{{
        card.hidden=index!==active;
        if(card.hidden)return;
        const phase=Math.max(0,Math.min(1,(t-(cues[active]??0))/.38));
        const progress=1-(1-phase)**3;
        card.style.opacity=.75+.25*progress;
        card.style.transform=`translateY(${{(1-progress)*22}}px)`;
      }});
    }};
    window.__seek(0);
    window.__ready=true;
    </script></body></html>"""


def upload_hero(output_root):
    """Extract the verified, mixed Scene 3 from the final episode and upload it."""
    import os
    import subprocess

    from .day1_media import _sha256
    from .youtube_private_upload import _safe_child, upload_day1_package
    from .youtube_studio_package import _vx23_probe_video

    data = output_root / "DATA"
    qa_path = data / "final_video_qa.json"
    qa = json.loads(qa_path.read_text())
    review = json.loads((data / "player_hero_analysis.json").read_text())
    scene = next(s for s in qa["verified_final_scenes"] if s["key"] == "03_projected_goals")
    if not 0 < scene["duration"] < 120:
        raise RuntimeError("Player Hero clip must be under two minutes")
    video_dir = output_root / "MP4"
    source = _safe_child(qa["final_file"], video_dir, "Verified Day 1 MP4")
    if not qa.get("passed") or _sha256(source) != qa["external_media_integration"]["final_sha256"]:
        raise RuntimeError("Player Hero upload requires the verified Day 1 master")
    gameweek = review["gameweek"]
    names = _join([profile["name"] for profile in review["players"]])
    clip = video_dir / f"FPL_VORTEX_GW{gameweek}_PLAYER_HERO.mp4"
    subprocess.run([
        "ffmpeg", "-v", "error", "-y", "-ss", str(scene["start_seconds"]),
        "-i", str(source), "-t", str(scene["duration"]), "-map", "0:v:0", "-map", "0:a:0",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(clip),
    ], check=True)
    probe = _vx23_probe_video(clip)
    if (probe["width"], probe["height"]) != (3840, 2160) or not 0 < probe["duration"] < 120:
        raise RuntimeError("Player Hero encode failed its 4K or runtime check")
    package = {
        "package_path": qa_path,
        "render_revision": os.environ.get("GITHUB_SHA"),
        "video_path": clip,
        "upload_tags": ["Fantasy Premier League", "FPL VORTEX", f"FPL GW{gameweek}", "FPL Player Hero Card"],
        "metadata": {
            "preview_gw": gameweek, "title": f"The Numbers Behind the Points | FPL Gameweek {gameweek}",
            "description": f"How {names} earned their FPL points in Gameweek {gameweek}. "
                           "The video uses official Fantasy Premier League scoring and available match stats.",
            "category_id": "17", "language": "en-GB",
        },
    }
    result = upload_day1_package(package, data / "player_hero_private_upload.json", hero=True)
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(summary).open("a", encoding="utf-8") as stream:
            stream.write(f"\n## Player Hero private draft\n\n{result['youtube']['studio_url']}\n")
    return result


if __name__ == "__main__":
    from .youtube_private_upload import DEFAULT_OUTPUT_ROOT

    upload_hero(DEFAULT_OUTPUT_ROOT)
