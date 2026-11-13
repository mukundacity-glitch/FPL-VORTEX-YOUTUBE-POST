"""Scene 4: Phase 10 forecasts, observed player returns and official FPL flows."""
from collections import defaultdict
from pathlib import Path
from statistics import median
from html import escape
import base64
import json

from .football_identity import full_club_name
from .day1_scene3 import number, tile_rating, timing as beat_timing

ASSETS = Path(__file__).resolve().parent
POSITIONS = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
SOCIAL_CHANNELS = (
    ("YouTube", "▶", "@FPLVORTEX"),
    ("X", "𝕏", "@FPLVORTEXM"),
    ("Telegram", "➤", "t.me/FPLVortexDailyBot"),
    ("Instagram", "◎", "@fplvortex"),
)
METRICS = (
    ("expected_goals", "xG"), ("expected_assists", "xA"), ("expected_goal_involvements", "xGI"),
    ("shots", "Shots"), ("big_chances", "Big chances"), ("minutes", "Minutes"),
)


def fixture_metric(tile):
    return f"fixtures.{tile['gw']}.{tile['id']}"


def build_outlook(gw, fixtures, teams, players, forecast, fdr, completed, history, photo, season, stamp, model_mode="Research only", match_stats=(), fixture_forecast=(), clean_sheet_forecast=()):
    clean_sheet_by_fixture = {int(r["fixture_id"]): r for r in clean_sheet_forecast}
    weeks = list(range(gw, min(39, gw + 5)))
    fixtures_by_team = defaultdict(list)
    for f in fixtures:
        if f["event"] in weeks:
            for side, other in (("h", "a"), ("a", "h")):
                fixtures_by_team[f[f"team_{side}"]].append((f, f[f"team_{other}"], side.upper()))
    fdr_by_fixture = {(int(r["fixture_id"]), int(r["team_id"])): r for r in fdr}
    forecast_by_player = defaultdict(list)
    for r in forecast:
        if r["gameweek"] in weeks:
            forecast_by_player[int(r["player_id"])].append(r)
    concentration = set()
    for row in fixture_forecast:
        if row.get("gameweek") in weeks and any(
            (number(row.get(key)) or 0) >= .90 for key in ("goal_share", "assist_share")
        ):
            concentration.add(int(row["player_id"]))
    rows = []
    for p in players:
        pid, team = p["id"], p["team"]
        if team not in teams or p.get("element_type") not in POSITIONS:
            continue
        pos = POSITIONS[p["element_type"]]
        schedule = sorted(fixtures_by_team[team], key=lambda t: (t[0]["event"], t[0].get("kickoff_time") or "", t[0]["id"]))
        projections = defaultdict(list)
        for r in forecast_by_player[pid]:
            if r.get("team_id") == team:
                projections[r["gameweek"]].append(r)
        scores = []
        for week in weeks:
            scheduled = sum(f["event"] == week for f, _, _ in schedule)
            data = projections[week]
            projection = number(data[0].get("gameweek_expected_points")) if len(data) == 1 else None
            if scheduled == 0 and not data:
                scores.append(0.0)
            elif scheduled > 0 and projection is not None and number(data[0].get("fixture_count")) == scheduled:
                scores.append(projection)
            else:
                scores.append(None)
        total = sum(scores) if all(x is not None for x in scores) else None
        cost = number(p.get("now_cost"))
        price = cost / 10 if cost is not None and cost > 0 else None
        ti, to = (number(p.get(k)) for k in ("transfers_in_event", "transfers_out_event"))
        net = ti - to if ti is not None and to is not None else None
        tile_side = "defence" if pos in ("DEF", "GK") else "attack"
        tiles = [dict(id=f["id"], gw=f["event"], opponent_id=opp, opponent=teams[opp]["short"], venue=venue,
                      **tile_rating(fdr_by_fixture.get((f["id"], team), {}).get(f"{tile_side}_fdr_model")))
                 for f, opp, venue in schedule]
        easiest = min((f for f in tiles if f["band"] != "missing"), key=lambda f: float(f["rating"]), default=None)
        rows.append(dict(id=pid, raw=p, name=p["web_name"], team=teams[team], team_id=team, position=pos,
                         weeks=scores, total=total, price=price, value=total/price if total is not None and price else None,
                         incoming=ti, outgoing=to, net=net, ownership=number(p.get("selected_by_percent")),
                         price_move=number(p.get("cost_change_event")), tiles=tiles, easiest=easiest,
                         forecast_review=pid in concentration))
    qualified = [r for r in rows if r["total"] is not None and r["tiles"]]
    leaders = sorted(qualified, key=lambda r: (-r["total"], r["id"]))[:5]
    averages = {pos: median(r["total"] for r in qualified if r["position"] == pos)
                for pos in {r["position"] for r in qualified}}
    for row in rows:
        valid = row["total"] is not None and row["position"] in averages
        status = row["raw"].get("status")
        available = status == "a"
        flagged = status in {"d", "i", "s", "u", "n"}
        outflow = row["net"] is not None and row["net"] < 0
        inflow = row["net"] is not None and row["net"] > 0
        above = valid and row["total"] > averages[row["position"]]
        has_minutes = (number(row["raw"].get("minutes")) or 0) > 0
        row["verdict"] = ("REVIEW" if row["forecast_review"] else
                          "SELL" if outflow and (flagged or valid and not above) else
                          "BUY" if above and available and inflow and has_minutes else "HOLD")
        row["horizon"] = "Review availability" if not available else "Monitor market"
        if available and valid and row["tiles"]:
            next_score = row["weeks"][0]
            future = row["weeks"][1:]
            if next_score > 0 and future and next_score >= 1.5 * (sum(future) / len(future)):
                row["horizon"] = "Next GW first"
            elif above and sum(future) > next_score:
                row["horizon"] = "Several Gameweeks"
            else:
                row["horizon"] = "Review the fixture run"
        if row["verdict"] == "SELL":
            row["horizon"] = "Review the squad slot"
        if row["forecast_review"]:
            row["horizon"] = "Check model allocation"
        row["reason"] = (
            "At least 90% modeled team goal or assist share in a fixture" if row["forecast_review"] else
            "Net selling plus an official availability flag" if row["verdict"] == "SELL" and flagged else
            "Net selling and a below-median or median positional projection" if row["verdict"] == "SELL" else
            "Net buying and an above-median positional projection" if row["verdict"] == "BUY" else
            "Check the official availability update" if flagged else
            "Official availability is unknown" if not available else
            "Transfer flow is unavailable" if row["net"] is None else
            "Projection and transfer flow give a mixed signal"
        )
    flow = {key: sorted((r for r in rows if r[key] is not None and r[key] > 0),
                        key=lambda r: (-r[key], r["id"]))[:3] for key in ("incoming", "outgoing")}
    value = sorted((r for r in qualified if r["value"] is not None and r["raw"].get("status") == "a" and not r["forecast_review"]),
                   key=lambda r: (-r["value"], -r["total"], r["id"]))[:5]
    extra = next((r for r in value if r not in leaders), None)
    board = leaders + ([extra] if extra is not None else [])
    if extra is not None:
        extra["value_pick"] = True
    # These are the latest completed event IDs, not the calendar GWs immediately before the deadline.
    recent_gws = set(sorted(completed)[-5:])
    provider = defaultdict(list)
    for m in match_stats:
        if m.get("gameweek") in recent_gws:
            provider[(m.get("player_code"),m["gameweek"])].append(m)
    for r in board:
        try:
            h = history(r["id"]).get("history") or []
        except (OSError, ValueError):
            h = []
        h = [x for x in h if x.get("round") in recent_gws]
        r["recent"] = {key: sum(float(x[key]) for x in h)
                       if h and all(number(x.get(key)) is not None for x in h) else None for key, _ in METRICS}
        p = r["raw"]
        r["full_name"] = " ".join(filter(None, (p.get("first_name"), p.get("second_name")))) or r["name"]
        r["team"] = dict(r["team"], full_name=full_club_name(r["team"]))
        for key in ("starts","total_points","goals_scored","assists","defensive_contribution_points"):
            r["recent"][key] = sum(float(x[key]) for x in h) if h and all(number(x.get(key)) is not None for x in h) else None
        r["sample_matches"] = len(h) if h else None
        r["sample_window"] = f"GW{min(recent_gws)}–GW{max(recent_gws)}" if h and recent_gws else ""
        r["team_news"] = p.get("news") or None
        if r["position"] in ("GK","DEF"):
            team_fixtures = [f for f in fixtures if f.get("event") in recent_gws and
                             p["team"] in (f["team_h"],f["team_a"])]
            conceded = [number(f.get("team_a_score" if f["team_h"] == p["team"] else "team_h_score"))
                        for f in team_fixtures if f.get("finished")]
            team_cs = sum(x == 0 for x in conceded) if team_fixtures and len(conceded)==len(team_fixtures) and None not in conceded else None
            next_tiles = [t for t in r["tiles"] if t["gw"] == gw]
            cs_probabilities = []
            for tile in next_tiles:
                key = "home_clean_sheet_probability" if tile["venue"] == "H" else "away_clean_sheet_probability"
                cs_probabilities.append(number(clean_sheet_by_fixture.get(tile["id"],{}).get(key)))
            r["defence"] = dict(clean_sheets=team_cs, team_xgc=None, cs_probabilities=cs_probabilities)
        matches = [m for week in recent_gws for m in provider[(p.get("code"), week)]]
        # Require the same match count and minutes per GW before taking provider-only totals.
        official_minutes = {week: sorted(number(x.get("minutes")) for x in h if x.get("round")==week and number(x.get("minutes")) is not None) for week in recent_gws}
        provider_minutes = {week: sorted(number(x.get("minutes_played")) for x in provider[(p.get("code"),week)] if number(x.get("minutes_played")) is not None) for week in recent_gws}
        if h and matches and official_minutes == provider_minutes and len(matches)==len(h):
            for key, field in (("shots","total_shots"),("big_chances","big_chances")):
                if r["recent"][key] is None and all(number(m.get(field)) is not None for m in matches):
                    r["recent"][key] = sum(float(m[field]) for m in matches)
        completed_owners = {}
        for item in sorted(h,key=lambda x:x["round"]):
            if number(item.get("selected")) is not None:
                completed_owners[item["round"]] = int(float(item["selected"]))
        owners = sorted(completed_owners.items())[-2:]
        r["owner_change"] = owners[1][1]-owners[0][1] if len(owners)==2 else None
        r["owner_window"] = f"GW{owners[0][0]}–{owners[1][0]}" if len(owners)==2 else ""
        if not r["forecast_review"] and r["recent"]["minutes"] is not None and r["recent"]["minutes"] < 60 * len(h):
            if r["verdict"] == "BUY":
                r["verdict"], r["reason"] = "HOLD", "Recent minutes are below 60 per recorded match"
            r["horizon"] = "Check recent minutes"
        r["card"] = dict(id=r["id"], name=r["name"], first_name=p.get("first_name"), surname=p.get("second_name"),
                         position=r["position"], position_label=r["position"], club=r["team"]["full_name"],
                         club_badge=r["team"]["badge"], player_image=photo(p),
                         price=f"£{r['price']:.1f}m" if r["price"] else "N/A",
                         ownership=f"{r['ownership']:.1f}%" if r["ownership"] is not None else "N/A",
                         season_label=season, verdict_main=r["verdict"],
                         display_stats=[dict(icon=icon,label=label,value=f"{r['recent'][key]:.2f}" if r["recent"][key] is not None else "N/A")
                                        for (key,label),icon in zip(METRICS, ("ball","boot","target","goal","star","clock"))],
                         fixtures=[dict(**t, fixdiff=t["rating"]) for t in r["tiles"][:5]])
    buys = sorted((r for r in qualified if r["verdict"] == "BUY"), key=lambda r: (-r["total"], -r["net"], r["id"]))[:3]
    holds = sorted((r for r in qualified if r["verdict"] == "HOLD" and r["raw"].get("status") == "a"
                    and r["total"] > averages[r["position"]]), key=lambda r: (-r["total"], r["id"]))[:3]
    sells = sorted((r for r in rows if r["verdict"] == "SELL"), key=lambda r: (r["net"], r["id"]))[:3]
    for r in rows:
        r.pop("raw")
    return dict(gw=gw, weeks=weeks, stamp=stamp, teams=teams, leaders=leaders, board=board, flow=flow, value=value,
                verdicts={"BUY":buys,"HOLD":holds,"SELL":sells}, recent_gws=sorted(recent_gws), model_mode=model_mode)


def _decimal(value, digits):
    integer, _, fraction = f"{value:.{digits}f}".partition(".")
    digit_words = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine")
    return integer + (" point " + " ".join(digit_words[int(d)] for d in fraction) if fraction else "")


def outlook_script(scene, team_name, player_name):
    """Keep text, semantic cells and spoken values together until speech alignment."""
    beats = [("opening", None, [
        ("The fixtures give us a shortlist. Which players are worth a transfer?", None, None),
        ("Let’s compare projected points, recent performances and the transfer market.", None, None),
    ])]
    for p in scene["board"]:
        lines = []
        def say(text, metric=None, value=None):
            lines.append((text, metric, value))

        pid = p["id"]
        name = player_name(pid, p["name"])
        club = team_name(p["team_id"])
        say(f"Let’s look at {name} of {club}.", "identity.player")
        if p["price"] is not None:
            price = _decimal(p["price"], 1)
            say(f"{name} costs {price} million pounds.", "identity.price", price)
        for tile in (t for t in p["tiles"] if t["gw"] == scene["gw"]):
            opponent = team_name(tile["opponent_id"])
            venue = "at home" if tile["venue"] == "H" else "away"
            if tile["band"] == "missing":
                say(f"{name} faces {opponent} {venue}.", fixture_metric(tile))
            else:
                fdr = _decimal(float(tile["rating"]), 1)
                say(f"{name} faces {opponent} {venue}, with a fixture difficulty of {fdr}.", fixture_metric(tile), fdr)
        for value, label, metric in (
            (p["weeks"][0], "in the next gameweek", "forecast.nextGwXpts"),
            (p["total"], f"over {len(scene['weeks'])} gameweeks", "forecast.fiveGwXpts"),
        ):
            if value is not None:
                points = _decimal(value, 2)
                say(f"The Vortex model projects {points} points for {name} {label}.", metric, points)
        if p.get("value_pick") and p["value"] is not None:
            value = _decimal(p["value"], 2)
            say(f"For {name}, that works out at {value} projected points per million pounds.", "forecast.valuePerMillion", value)

        recent = p["recent"]
        if recent.get("minutes") is not None and p["sample_matches"]:
            minutes = str(int(recent["minutes"]))
            say(f"Over the last {p['sample_matches']} recorded matches, {name} played {minutes} minutes.", "performance.minutes", minutes)
        if recent.get("total_points") is not None:
            points = str(int(recent["total_points"]))
            say(f"{name} scored {points} actual Fantasy Premier League points in that sample.", "performance.actualPoints", points)
        if recent.get("expected_goal_involvements") is not None:
            threat = _decimal(recent["expected_goal_involvements"], 2)
            say(f"{name} recorded {threat} expected goal involvements in that sample.", "performance.xGI", threat)
        defence = p.get("defence")
        probabilities = defence["cs_probabilities"] if defence else []
        if len(probabilities) == 1 and probabilities[0] is not None and 0 <= probabilities[0] <= 1:
            chance = _decimal(100 * probabilities[0], 1)
            say(f"For {name}, the model puts the next match clean sheet chance at {chance} percent.", "defensive.cleanSheetChance", chance)
        if p["forecast_review"]:
            say(f"The model gives {name} an unusually large share of the attack, so I would review that assumption before using the estimate.", "verdict")
        if p["net"] is not None:
            net = str(abs(int(p["net"])))
            if p["net"] == 0:
                say(f"The market snapshot shows a net movement of {net} transfers for {name}.", "transfers.net", net)
            else:
                direction = "net transfers in" if p["net"] > 0 else "net transfers out"
                say(f"The market snapshot shows {net} {direction} for {name}.", "transfers.net", net)
        say(f"My verdict for {name} is {p['verdict'].lower()}, because {p['reason'][:1].lower() + p['reason'][1:]}.", "verdict")
        beats.append((f"hero-{pid}", pid, lines))
    beats.append(("summary", None, [
        ("Compare the next fixture with the longer run, then check the latest line-up news before deciding where to use your transfer.", None, None),
    ]))
    return beats


def outlook_narration(script):
    return [(key, " ".join(line for line, _, _ in lines)) for key, _, lines in script]


def outlook_timing(script, words, duration, span, normalize):
    """Align each spoken metric to provider WordBoundary events in script order."""
    beats = beat_timing(outlook_narration(script), words, span, normalize)
    metrics = []
    for i, ((key, player_id, lines), beat) in enumerate(zip(script, beats)):
        end = beats[i + 1]["at"] if i + 1 < len(beats) else duration
        remaining = [word for word in words if beat["at"] <= float(word["start"]) < end]
        for line, metric, value in lines:
            if metric is None:
                continue
            label = f"Scene 4 {key} {metric}"
            start, length = span(remaining, normalize(line, context=label), required=True, context=label)
            stop = start + length
            if not 0 <= start < stop <= min(end, duration) + .001:
                raise ValueError(f"{label} is outside the audio beat")
            emphasis = None
            if value is not None:
                segment = [word for word in remaining if start <= float(word["start"]) < stop]
                emphasis, _ = span(segment, normalize(value, context=label), required=True, context=label)
            metrics.append(dict(playerId=player_id, metricId=metric, start=start, end=stop, emphasis=emphasis))
            remaining = [word for word in remaining if float(word["start"]) >= stop - .001]
    return beats, metrics


def render_outlook(scene, cues, captions, original_css, original_js, logo, metric_cues=(), social=SOCIAL_CHANNELS):
    css = (ASSETS / "day1_scene4.css").read_text()
    js = (ASSETS / "day1_scene4.js").read_text()
    for name, asset, mime in (
        ("Rajdhani", ASSETS/"scene3_assets/rajdhani-bold.woff2", "font/woff2"),
        ("Inter", ASSETS.parent/"day2/assets/Inter.ttf", "font/ttf"),
    ):
        uri = base64.b64encode(asset.read_bytes()).decode()
        css += f"@font-face{{font-family:{name};src:url(data:{mime};base64,{uri});font-weight:700}}"
    display_scene = {key: scene[key] for key in ("gw", "weeks", "board", "stamp", "model_mode")}
    payload = json.dumps(dict(scene=display_scene,cues=cues,captions=captions,cardCss=original_css,metricCues=metric_cues),ensure_ascii=False).replace("<","\\u003c")
    return (f'<!doctype html><html><head><meta charset="utf-8"><title>Day 1 · Numbers &amp; Market Outlook</title><style>{css}</style></head>'
            f'<body><main class="vx-s4"><header>{logo}<div><small>FPL VORTEX · DAY 1 · SCENE 04</small>'
            f'<h1>NUMBERS &amp; MARKET OUTLOOK</h1></div><b>GW{escape(str(scene["gw"]))}</b></header>'
            '<section class="vx-s4-stage"></section><aside class="vx-s4-caption"></aside>'
            '<footer aria-label="FPL VORTEX social channels">' +
            ''.join(f'<span><i data-platform="{escape(platform.lower())}" aria-label="{escape(platform)}">{escape(icon)}</i>{escape(handle)}</span>'
                    for platform, icon, handle in social) +
            '</footer></main>' +
            f'{original_js}<script>const S4={payload};\n{js}</script></body></html>')
