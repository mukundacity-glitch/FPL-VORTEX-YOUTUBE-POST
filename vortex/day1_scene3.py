"""Day 1 Scene 3 data, editorial beats and existing renderer handoff."""
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from html import escape
from math import isfinite
from pathlib import Path
from statistics import mean
from zoneinfo import ZoneInfo
import base64
import json

ROOT = Path(__file__).resolve().parent
EASTERN = ZoneInfo("America/New_York")
POSITIONS = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
STATUS = {"a": "Available", "d": "Doubt", "i": "Injured", "s": "Suspended",
          "u": "Unavailable", "n": "Unavailable"}


def number(value):
    try:
        result = float(value)
        return result if isfinite(result) else None
    except (TypeError, ValueError):
        return None


def tile_rating(value):
    value = number(value)
    if value is None or not 1 <= value <= 5:
        return {"rating": "N/A", "band": "missing"}
    rounded = Decimal(str(value)).quantize(Decimal(".1"), rounding=ROUND_HALF_UP)
    band = "easy" if rounded <= Decimal("2.5") else "medium" if rounded <= 3 else "hard" if rounded <= 4 else "very-hard"
    return {"rating": f"{rounded:.1f}", "band": band}


def build_scene(gw, fixtures, teams, players, model, fetch_history, photo, stamp, season, forecasts=()):
    horizon = list(range(gw, min(39, gw + 5)))
    matches = sorted((f for f in fixtures if f["event"] == gw),
                     key=lambda f: (f.get("kickoff_time") or "~", f["id"]))
    ratings = {(int(m["fixture_id"]), int(m["team_id"])): m for m in model}
    forecast_by_player = {int(row["player_id"]): row for row in forecasts if row["gameweek"] == gw}
    rows = {}
    for tid, team in teams.items():
        weeks = [[] for _ in horizon]
        for fixture in fixtures:
            if fixture["event"] not in horizon or tid not in (fixture["team_h"], fixture["team_a"]):
                continue
            home = tid == fixture["team_h"]
            opp = teams[fixture["team_a"] if home else fixture["team_h"]]
            match = ratings.get((fixture["id"], tid), {})
            weeks[horizon.index(fixture["event"])].append({
                "id": fixture["id"], "opponent": opp["short"], "name": opp["name"], "venue": "H" if home else "A",
                "attack": tile_rating(match.get("attack_fdr_model")), "defence": tile_rating(match.get("defence_fdr_model")),
            })
        def weekly(side):
            return [mean(float(t[side]["rating"]) for t in week)
                    if week and all(t[side]["band"] != "missing" for t in week) else None for week in weeks]
        attack = weekly("attack")
        defence = weekly("defence")
        complete = len(attack) == 5 and all(v is not None for v in attack)
        rows[tid] = dict(team=team, weeks=weeks, attack=attack[0], defence=defence[0],
                         average=mean(attack) if complete else None,
                         swing=mean(attack[3:]) - mean(attack[:2]) if complete else None)
    complete = sorted((r for r in rows.values() if r["average"] is not None), key=lambda r: r["average"])
    heatmap = complete[:3] + complete[max(3, len(complete)-3):]
    if not heatmap:
        heatmap = list(rows.values())[:6]
    swings = sorted((r for r in complete if r["swing"]), key=lambda r: r["swing"])

    finished = {f["id"] for f in fixtures if f.get("finished") and f.get("event") in range(max(1, gw-5), gw)}
    def observed(player):
        try:
            history = fetch_history(player["id"]).get("history", [])
        except (OSError, ValueError):
            return None
        records = [r for r in history if r.get("fixture") in finished]
        keys = ("minutes", "total_points", "goals_scored", "assists", "clean_sheets", "saves")
        if not records or any(number(r.get(key)) is None for r in records for key in keys):
            return None
        return {key: sum(int(r[key]) for r in records) for key in keys} | {"matches": len(records)}

    def card(p, side, recent):
        team = teams[p["team"]]
        row = rows[p["team"]]
        fixtures_card = [{
            "gw": week, "opponent": "+".join(t["opponent"] for t in tiles) or "BLANK",
            "venue": "+".join(t["venue"] for t in tiles), "fixdiff": " / ".join(t[side]["rating"] for t in tiles) or "N/A",
        } for week, tiles in zip(horizon, row["weeks"])]
        stats = [("minutes", "RECENT MINUTES", "clock"), ("total_points", "RECENT POINTS", "star"),
                 ("goals_scored", "GOALS", "goal"), ("assists", "ASSISTS", "assist"),
                 ("clean_sheets", "CLEAN SHEETS", "shield"), ("saves", "SAVES", "glove")]
        forecast = forecast_by_player.get(p["id"], {})
        xp = number(forecast.get("gameweek_expected_points"))
        name = p["web_name"]
        image = photo(p)
        status = STATUS.get(p.get("status"), "Unknown")
        position = POSITIONS[p["element_type"]]
        assessment = "MONITOR" if not recent or recent["minutes"] < recent["matches"]*60 or status != "Available" else "OPPORTUNITY"
        return dict(name=name, team=team, recent=recent, side=side, next=row["weeks"][0], status=status,
                    news=p.get("news") or "", assessment=assessment, xpts=xp,
                    card=dict(id=p["id"], name=name, first_name=p.get("first_name"), surname=p.get("second_name"),
                              position=position, position_label=position, club=team["name"], club_badge=team["badge"],
                              player_image=image, price=f"£{p['now_cost']/10:.1f}m" if number(p.get("now_cost")) is not None else "N/A",
                              ownership=f"{p['selected_by_percent']}%" if number(p.get("selected_by_percent")) is not None else "N/A",
                              display_stats=[dict(label=label, icon=icon, value=str(recent[key]) if recent else "N/A")
                                             for key,label,icon in stats], fixtures=fixtures_card,
                              season_label=season, verdict_main=assessment))

    picks = {}
    for side, positions, limit in (("attack", (3,4), 3), ("defence", (1,2), 2)):
        eligible = [p for p in players if p.get("element_type") in positions and p.get("status") == "a"
                    and p["team"] in rows and rows[p["team"]][side] is not None and (number(p.get("minutes")) or 0) > 0]
        eligible.sort(key=lambda p: (rows[p["team"]][side], -(number(p.get("form")) or 0),
                                     -(number(p.get("minutes")) or 0), p["id"]))
        selected = []
        seen = set()
        for p in eligible:
            if p["team"] in seen:
                continue
            recent = observed(p)
            selected.append(card(p, side, recent))
            seen.add(p["team"])
            if len(selected) == limit:
                break
        picks[side] = selected

    flagged = [p for p in players if p.get("status") in {"d","i","s","u","n"} and p["team"] in rows
               and rows[p["team"]]["weeks"][0] and (number(p.get("minutes")) or 0) > 0]
    flagged.sort(key=lambda p: (-(number(p.get("selected_by_percent")) or 0), p["id"]))
    risk = [p for group in picks.values() for p in group if p["assessment"] == "MONITOR"]
    for p in flagged[:3]:
        side = "attack" if p["element_type"] in (3,4) else "defence"
        row = rows[p["team"]]
        risk.append(dict(name=p["web_name"], team=teams[p["team"]], recent=observed(p), side=side,
                         next=row["weeks"][0], status=STATUS[p["status"]], news=p.get("news") or ""))
    watch = {side: next((p for p in group if p["assessment"] == "OPPORTUNITY"), None)
             for side, group in picks.items()}
    return dict(gw=gw, horizon=horizon, stamp=stamp, watch=watch, fixtures=[dict(
        home=teams[f["team_h"]], away=teams[f["team_a"]], kickoff=kickoff(f.get("kickoff_time"))) for f in matches],
        rows=heatmap, picks=picks, risk=risk[:3], improving=[r for r in swings if r["swing"]<0][:2],
        hardening=[r for r in reversed(swings) if r["swing"]>0][:2], easiest=complete[0] if complete else None)


def kickoff(value):
    if not value:
        return "Kickoff N/A"
    return datetime.fromisoformat(value.replace("Z","+00:00")).astimezone(EASTERN).strftime("%a %b %d · %H:%M ET")


def narration(scene):
    fixtures, picks = scene["fixtures"], scene["picks"]
    def matchup(p):
        return " and ".join(f"{t['name']} {'at home' if t['venue']=='H' else 'away'}" for t in p["next"])
    def list_names(players):
        return ", ".join(p["name"] for p in players)
    def club_names(rows):
        return ", ".join(r["team"]["name"] for r in rows)
    featured = " ".join(f"{f['home']['name']} host {f['away']['name']}." for f in fixtures[:2])
    easiest = scene["easiest"]
    best_run = f"{easiest['team']['name']} lead the five-week attack comparison at {easiest['average']:.1f}." if easiest else "There is insufficient data for a full five-week leader."
    beats = [
        ("opening", "The road ahead starts here. The review told us where the points came from. Now let’s see which upcoming fixtures are worth a closer look."),
        ("fixtures", f"Here is the full schedule. Gameweek {scene['gw']} has {len(fixtures)} scheduled matches. {featured} Keep an eye on the venue as well as the opponent. A useful matchup at home can look different away, and confirmed kickoff times are shown on the board. If a club plays twice, each match is shown separately. A missing kickoff stays open until the schedule confirms it."),
        ("heatmap", f"This is the five gameweek fixture map. Green sits at the easier end, then blue, pink and red. These are Vortex attacking fixture ratings. {best_run} The colours identify where to investigate. They cannot tell us who starts or who returns points. Look across each row before focusing on the next match. The longer view helps explain whether the first opponent is part of a sustained run or a one-week opportunity."),
        ("attack", f"Now for the attacking opportunities. {'On the board: '+list_names(picks['attack'])+'.' if picks['attack'] else 'The attacking shortlist is unavailable.'} We’re comparing next opponents with verified recent minutes and returns. A favourable opponent is most useful when the player has enough time on the pitch to exploit it. Points describe past returns. Goals and assists show how those attacking returns were earned. We’ll compare that evidence with the next opponent."),
    ]
    for side in ("attack","defence"):
        for index, p in enumerate(picks[side]):
            lead = (["First in attack", "Our second attacking watch", "The third attacking matchup"] if side=="attack"
                    else ["Turning to defence", "Our second defensive watch"])[index]
            r = p["recent"]
            evidence = f"He logged {r['minutes']} minutes and {r['total_points']} points in {r['matches']} recorded matches." if r else "Recent match evidence is unavailable."
            if r and side == "attack":
                evidence += f" That includes {r['goals_scored']} goals and {r['assists']} assists."
            if r and side == "defence":
                evidence += f" The record includes {r['clean_sheets']} clean sheets" + (f" and {r['saves']} saves." if p["card"]["position"] == "GK" else ".")
            verdict = "Keep him on the watchlist and check the starting role." if p["assessment"] == "OPPORTUNITY" else "Monitor his minutes before drawing a conclusion."
            if p["xpts"] is not None:
                evidence += f" The Vortex forecast is {p['xpts']:.1f} expected points, which is an estimate."
            beats.append((f"{side}-{index}", f"{lead}, {p['name']} of {p['team']['name']}. The next matchup is {matchup(p)}. {evidence} {verdict}"))
    risk = scene["risk"]
    beats.append(("risk", "Availability changes the picture. " + (" ".join(
        f"{p['name']} is listed as {p['status'].lower()}." if p["status"] != "Available" else
        f"{p['name']} needs a minutes check." for p in risk) if risk else "There is no verified individual risk entry to show.") +
        " The official flag and recent minutes describe different things. Check the team update before drawing a conclusion about the starting eleven."))
    beats.append(("swings", "Now look at the fixture swings. " +
        (f"The ratings ease for {club_names(scene['improving'])}. " if scene["improving"] else "") +
        (f"The run hardens for {club_names(scene['hardening'])}. " if scene["hardening"] else "") +
        "We compare the first two gameweeks with the last two. The arrows describe fixture difficulty. This is useful for judging whether an attractive single match is part of a longer run."))
    attack = scene["watch"]["attack"]["name"] if scene["watch"]["attack"] else "unavailable"
    defence = scene["watch"]["defence"]["name"] if scene["watch"]["defence"] else "unavailable"
    monitor = risk[0]["name"] if risk else "unavailable"
    beats.extend([
        ("watchlist", f"Here is the final watchlist. The attacking opportunity is {attack}. The defensive opportunity is {defence}. The minutes or availability watch is {monitor}. Each sits here for a different reason. Use the matchup to start the investigation, then use role and team news to test it."),
        ("conclusion", f"The main lesson is simple. {best_run} A favourable fixture creates the opening, but the player’s role and availability determine whether it matters. Keep those questions separate as we move from the schedule to the numbers."),
        ("transition", "Next, the numbers and market outlook. Let’s see what the recorded returns and projections say about those matchups."),
    ])
    return beats


def timing(beats, words, span, normalize):
    result = []
    for i, (key, line) in enumerate(beats):
        anchor = normalize(line.split(". ")[0], context="Scene 3 anchor")
        at = 0.0 if i == 0 else float(span(words, anchor, required=True, context=f"Scene 3 {key}")[0])
        if result and at <= result[-1]["at"]:
            raise ValueError(f"Scene 3 cue is out of order: {key}")
        result.append(dict(key=key, at=at))
    return result


def render_html(scene, cues, captions, original_css, original_js, logo, handoff=None):
    css = (ROOT / "day1_scene3.css").read_text()
    market = "targets" in scene
    js = (ROOT / ("day1_scene3_market.js" if market else "day1_scene3.js")).read_text()
    for family, asset in (("Inter", ROOT.parent / "day2/assets/Inter.ttf"),
                          ("Rajdhani", ROOT / "scene3_assets/rajdhani-bold.woff2"),
                          ("Sora", ROOT / "scene3_assets/sora-semibold.woff2")):
        if asset.is_file():
            mime = "font/woff2" if asset.suffix == ".woff2" else "font/ttf"
            css += f"@font-face{{font-family:{family};src:url(data:{mime};base64,{base64.b64encode(asset.read_bytes()).decode()})}}"
    payload = json.dumps(dict(scene=scene, cues=cues, captions=captions, card_css=original_css), ensure_ascii=False).replace("<", "\\u003c")
    prior = ""
    if handoff and handoff.is_file():
        uri = base64.b64encode(handoff.read_bytes()).decode()
        prior = f'<img class="vx-s3-handoff" src="data:image/png;base64,{uri}" alt="">'
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Day 1 · Players &amp; Fixtures</title><style>{css}</style></head>'
            f'<body><main class="vx-s3{" vx-s3-market" if market else ""}"><header class="vx-s3-header"><div class="vx-s3-brand">{logo}<span>FPL VORTEX</span></div>'
            f'<span>CHAPTER 03 · PLAYERS &amp; FIXTURES · GW{scene["gw"]}</span></header>'
            f'<div class="vx-s3-stage"></div><div class="vx-s3-scanner"></div><div class="vx-s3-caption"></div>{prior}'
            f'<footer>THE ROAD AHEAD <span>FPL DATA · {escape(scene["stamp"])}</span></footer></main>'
            f'{original_js}<script>const S3={payload};\n{js}</script></body></html>')


def market_board(gw, fixtures, teams, model, market, stamp, source="Vortex bookmaker benchmark"):
    """Rank a single upcoming GW by unrounded attacking FDR, independent of odds."""
    fixtures_by_id = {f["id"]: f for f in fixtures if f.get("event") == gw}
    odds_by_id = {int(row["fixture_id"]): row for row in market}
    candidates = []
    for rating in model:
        f = fixtures_by_id.get(int(rating["fixture_id"]))
        value = number(rating.get("attack_fdr_model"))
        if f is None or value is None or not 1 <= value <= 5:
            continue
        team_id = int(rating["team_id"])
        if team_id not in (f["team_h"], f["team_a"]):
            continue
        home = f["team_h"] == team_id
        side = "home" if home else "away"
        odds = odds_by_id.get(f["id"], {})
        def probability(metric):
            p = number(odds.get(f"market_{side}_{metric}_probability"))
            return p if p is not None and 0 <= p <= 1 else None
        candidates.append(dict(fdr=value, **tile_rating(value), team=teams[team_id],
            opponent=teams[f["team_a"] if home else f["team_h"]], venue="H" if home else "A",
            win=probability("win"), clean_sheet=probability("clean_sheet"),
            snapshot=market_timestamp(odds.get("market_snapshot_timestamp"))))
    candidates.sort(key=lambda r: (r["fdr"], r["team"]["name"], r["opponent"]["name"], r["venue"]))
    return dict(gw=gw, stamp=stamp, targets=candidates[:5], market_source=source)


def market_timestamp(value):
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return ""
    return dt.astimezone(EASTERN).strftime("%b %d · %H:%M %Z") if dt.tzinfo else ""


def market_narration(scene, pair=(), *, team_name=None, player_name=None):
    beats = [("opening", f"Here’s where I’d look in Gameweek {scene['gw']}. "
              "I want a player who can use the matchup and stay useful afterwards.")]
    reads = [
        "This is the highest-rated attacking fixture on the board.",
        "Check the venue.",
        "Check who gets the attacking minutes.",
        "Look one week ahead here.",
        "That rounds out the shortlist.",
    ]
    leads = ("First", "Next", "Third on the board", "Fourth", "Last on the shortlist")
    for i, row in enumerate(scene["targets"]):
        where = "at home" if row["venue"] == "H" else "away"
        club = team_name(row["team"]["id"]) if team_name and "id" in row["team"] else row["team"]["name"]
        opponent = team_name(row["opponent"]["id"]) if team_name and "id" in row["opponent"] else row["opponent"]["name"]
        beats.append((f"target-{i}", f"{leads[i]}, {club} face {opponent} {where}. {reads[i]}"))
    if pair:
        lead, alternative = sorted(pair, key=lambda p: (-p["weeks"][0], -p["total"], p["id"]))
        names = [player_name(p["id"], p["name"]) for p in (lead, alternative)]
        lines = [f"For the same squad spot, I'd compare {names[0]} with {names[1]}."]
        for p, name in zip((lead, alternative), names):
            fixtures = [tile for tile in p["tiles"] if tile["gw"] == scene["gw"]]
            if len(fixtures) == 1:
                fixture = fixtures[0]
                where = "at home" if fixture["venue"] == "H" else "away"
                lines.append(f"{name} has {team_name(fixture['opponent_id'])} {where} on the schedule.")
            elif len(fixtures) > 1:
                lines.append(f"{name} has two or more fixtures on the schedule this Gameweek. "
                             "Check both the spread of minutes and the opposition on the fixture list.")
            if p["price"] is not None:
                lines.append(f"The asking price for {name} is {p['price']:.1f} million pounds.")
            recent = p.get("recent") or {}
            if p.get("sample_matches") and recent.get("minutes") is not None:
                minutes = round(recent["minutes"] / p["sample_matches"])
                lines.append(f"In the recent sample, {name} averaged {minutes} minutes per recorded match.")
        lines.append(f"I'd look at {names[0]} first, based on the model's ranking for this deadline. "
                     "I'd still check the role before buying. A good matchup goes further if the player "
                     "gets chances in the box or takes set pieces. When the first fixture "
                     "does most of the work, check who you'd start a week later. "
                     "If the manager hints at a bench role or a managed return, I'd keep the transfer.")
        transition = " ".join(lines)
    else:
        transition = ("I'd shortlist from the fixtures, then check recent minutes and who actually starts. "
                      "If I can't verify a like-for-like upgrade, my lean is to keep the transfer.")
    beats.append(("transition", transition))
    return beats


def render_market_html(scene, cues, captions, logo, handoff=None):
    return render_html(scene, cues, captions, "", "", logo, handoff)
