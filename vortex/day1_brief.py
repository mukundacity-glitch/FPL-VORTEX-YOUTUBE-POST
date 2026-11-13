"""The Gameweek Brief: one source-aware opening for the existing Day 1 renderer.

No API calls, sample teams, guessed forecasts or scoring-rule constants live here.
The caller supplies the canonical snapshot and its actual endpoint retrieval times.
"""
from __future__ import annotations

from datetime import datetime, timezone
from html import escape
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

VERSION = "GAMEWEEK-BRIEF-1"
TARGET_SECONDS = 38.0
MAX_AGE_SECONDS = 3600
EASTERN = ZoneInfo("America/New_York")
API = "https://fantasy.premierleague.com/api"


def _time(value):
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return stamp if stamp.tzinfo else None
    except (TypeError, ValueError):
        return None


def datum(value=None, *, source=None, retrieved_at=None, gameweek=None,
          now=None, methodology=None, status="FINAL"):
    """Missing provenance never acquires a verified label, even with a value."""
    now = now or datetime.now(timezone.utc)
    stamp = _time(retrieved_at)
    age = (now - stamp).total_seconds() if stamp else None
    finite = not isinstance(value, float) or math.isfinite(value)
    freshness = "unavailable" if value is None or not finite else (
        "not_verified" if not source or stamp is None or gameweek is None
        or age < -60 else "stale" if age > MAX_AGE_SECONDS else "fresh"
    )
    return dict(value=value if finite else None, source=source,
                retrievedAt=stamp.isoformat() if stamp else None,
                gameweek=gameweek, freshnessStatus=freshness,
                confidence="sourced" if freshness == "fresh" else "unverified",
                methodologyVersion=methodology, dataStatus=status)


def format_datum(item):
    state = item.get("freshnessStatus")
    if state in {"unavailable", "not_verified"}:
        return "Unavailable" if state == "unavailable" else "Not verified"
    value = item["value"]
    return f"{value:,}" if isinstance(value, int) else str(value)


def badge(item):
    state = item.get("freshnessStatus")
    stamp = _time(item.get("retrievedAt"))
    local = stamp.astimezone(EASTERN).strftime("%Y-%m-%d %H:%M:%S %Z %z") if stamp else "Timestamp unavailable"
    label = {"fresh": "Data verified", "stale": "Data may be stale",
             "unavailable": "Unavailable", "not_verified": "Not verified"}.get(state, "Not verified")
    status = str(item.get("dataStatus") or "UNKNOWN")
    version = " · " + str(item["methodologyVersion"]) if item.get("methodologyVersion") else ""
    return f"{label}: {local} · GW{item.get('gameweek') or '—'} · {status}{version}"


def build_brief(snapshot, *, next_gw, now=None, forecasts=None,
                player_model_rows=(), fixture_model_rows=()):
    """Derive presenter results using applied multipliers; never invent bank/FT."""
    now = now or datetime.now(timezone.utc)
    gw = snapshot.get("gw")
    if not isinstance(gw, int) or not 1 <= gw < int(next_gw) <= 38:
        raise ValueError("Review and next gameweek are inconsistent")
    boot = snapshot.get("bootstrap") or {}
    events = {e["id"]: e for e in boot.get("events", [])}
    if gw not in events or next_gw not in events:
        raise ValueError("Gameweek absent from official event snapshot")
    event = events[gw]
    fixtures = [f for f in snapshot.get("fixtures", []) if f.get("event") == gw]
    final = bool(fixtures) and bool(event.get("finished")) and bool(event.get("data_checked")) and all(
        f.get("finished") and f.get("team_h_score") is not None
        and f.get("team_a_score") is not None for f in fixtures)
    status = "FINAL" if final and snapshot.get("status") == "FINAL" else "PROVISIONAL"
    meta = snapshot.get("provenance") or {}

    def official(value, endpoint, *, methodology=None):
        provenance = meta.get(endpoint) or {}
        return datum(value, source=provenance.get("source"),
                     retrieved_at=provenance.get("retrievedAt"), gameweek=gw,
                     now=now, methodology=methodology, status=status)

    history = snapshot.get("history") or {}
    current = next((h for h in history.get("current", []) if h.get("event") == gw), {})
    previous = next((h for h in history.get("current", []) if h.get("event") == gw - 1), {})
    picks_payload = snapshot.get("picks") or {}
    entry_history = picks_payload.get("entry_history") or {}
    picks = picks_payload.get("picks") or []
    stats = {p["id"]: p.get("stats", {}) for p in (snapshot.get("live") or {}).get("elements", [])}
    identities = {p["id"]: p for p in boot.get("elements", [])}
    complete = bool(picks) and all(p.get("element") in stats and
        stats[p["element"]].get("total_points") is not None and p.get("multiplier") is not None for p in picks)
    gross = sum(stats[p["element"]]["total_points"] * p["multiplier"] for p in picks) if complete else None
    cost = current.get("event_transfers_cost")
    net = gross - cost if gross is not None and cost is not None else None
    recorded = current.get("points")
    if recorded is not None and entry_history.get("points") is not None and recorded != entry_history["points"]:
        raise ValueError("Presenter points disagree between picks and history")
    if recorded is not None and gross is not None and recorded not in {gross, net}:
        raise ValueError("Presenter points do not reconcile with applied player points")
    old_rank, rank = previous.get("overall_rank"), current.get("overall_rank")
    # Official multipliers include vice-captain promotion and triple captain;
    # the originally selected captain flag alone is not the applied outcome.
    captain = next((p for p in picks if (p.get("multiplier") or 0) > 1), None)
    captain = captain or next((p for p in picks if p.get("is_captain")), None)
    captain_points = (stats[captain["element"]]["total_points"] * captain["multiplier"]
                      if captain and complete else None)
    bench = [p for p in picks if p.get("position", 0) > 11]
    bench_points = sum(stats[p["element"]]["total_points"] for p in bench) if bench and complete else None
    scoreboard = {
        "Official GW points": official(recorded, "history"),
        "Before deductions": official(gross, "live", methodology="official-applied-multipliers-v1"),
        "After deductions": official(net, "live", methodology="applied-points-minus-official-hit-v1"),
        "Average score": official(event.get("average_entry_score"), "bootstrap"),
        "Previous overall rank": official(old_rank, "history"),
        "Overall rank": official(rank, "history"),
        "Rank movement": official(old_rank - rank if old_rank is not None and rank is not None else None, "history"),
        "Gameweek rank": official(current.get("rank"), "history"),
        "Captain points (applied)": official(captain_points, "live", methodology="official-applied-multipliers-v1"),
        "Bench points (raw)": official(bench_points, "live", methodology="original-bench-raw-points-v1"),
        "Transfer cost": official(cost, "history"),
    }
    # Derived values inherit the least fresh of ALL their input sources.
    for key in ("Before deductions", "After deductions", "Captain points (applied)", "Bench points (raw)"):
        item = scoreboard[key]
        dependencies = [official(1, endpoint) for endpoint in ("live", "picks", "history")]
        if any(d["freshnessStatus"] == "not_verified" for d in dependencies):
            item["freshnessStatus"] = "not_verified"
        elif any(d["freshnessStatus"] == "stale" for d in dependencies):
            item["freshnessStatus"] = "stale"
        item["inputs"] = dependencies
        stamps = [_time(d["retrievedAt"]) for d in dependencies]
        if all(stamps):
            item["retrievedAt"] = min(stamps).isoformat()
        item["source"] = "Official FPL event-live + presenter picks + history"
        item["confidence"] = "sourced" if item["freshnessStatus"] == "fresh" else "unverified"
    players = []
    for pick in picks:
        pid = pick.get("element")
        identity, actual = identities.get(pid, {}), stats.get(pid, {})
        # Raw provider fields only: no hard-coded BPS or DEFCON scoring formula.
        fields = {k: official(actual.get(k), "live") for k in (
            "minutes", "goals_scored", "assists", "clean_sheets", "saves", "bonus",
            "defensive_contribution", "defensive_contribution_points", "yellow_cards",
            "red_cards", "own_goals", "penalties_saved", "penalties_missed", "total_points")}
        availability = {"a":"Available in official FPL snapshot", "d":"Doubtful — official FPL",
                        "i":"Injured — official FPL", "s":"Suspended — official FPL",
                        "u":"Unavailable — official FPL"}.get(identity.get("status"))
        fields["availability"] = official(identity.get("news") or availability, "bootstrap")
        fields["ownership"] = official(identity.get("selected_by_percent"), "bootstrap")
        fields["availability"]["gameweek"] = next_gw
        fields["ownership"]["gameweek"] = next_gw
        fields["expectedMinutes"] = datum(gameweek=next_gw)
        fields["xPts"] = datum(gameweek=next_gw)
        model_rows = [r for r in player_model_rows if r.get("player_id") == pid and r.get("gameweek") == next_gw]
        next_fixtures = [f for f in snapshot.get("fixtures", []) if f.get("event") == next_gw
                         and identity.get("team") in (f.get("team_h"), f.get("team_a"))]
        # Complete fixture coverage is mandatory for a double; a missing leg
        # must never silently become a single-fixture GW projection.
        expected_ids = {f.get("id") for f in next_fixtures}
        models_by_id = {r.get("fixture_id"): r for r in model_rows}
        if expected_ids and expected_ids == set(models_by_id) and len(model_rows) == len(expected_ids):
            for field, source_field in (("expectedMinutes", "expected_minutes"), ("xPts", "fixture_expected_points")):
                ready = all(r.get("calculation_status") == "READY" for r in model_rows)
                values = [r.get(source_field) for r in model_rows]
                stamps = [_time(r.get("forecast_timestamp")) for r in model_rows]
                if ready and all(isinstance(v, (int,float)) and math.isfinite(v) for v in values) and all(stamps):
                    versions = {r.get("model_version") for r in model_rows}
                    sources = {r.get("source_name") for r in model_rows}
                    if len(versions) == 1 and all(versions) and all(sources):
                        fields[field] = datum(round(sum(values), 1), source=" / ".join(sorted(sources)),
                            retrieved_at=min(stamps).isoformat(), gameweek=next_gw, now=now,
                            methodology=next(iter(versions)), status="MODEL ESTIMATE")
        fixtures_out = []
        teams = {t["id"]:t for t in boot.get("teams", [])}
        for f in next_fixtures:
            side = "home" if f.get("team_h") == identity.get("team") else "away"
            opponent = teams.get(f.get("team_a" if side == "home" else "team_h"), {})
            models = [r for r in fixture_model_rows if r.get("fixture_id") == f.get("id") and r.get("gameweek") == next_gw]
            model = models[0] if len(models) == 1 else {}
            ratings = {}
            for label in ("attack", "defence"):
                value = model.get(f"{label}_fdr_{side}")
                ratings[label] = datum(value if model.get("model_version") else None,
                    source=model.get("source_name"), retrieved_at=model.get("source_timestamp"),
                    methodology=model.get("model_version"), gameweek=next_gw, now=now, status="MODEL ESTIMATE")
            fixture = official(f"{opponent.get('short_name', 'Opponent unavailable')} ({'H' if side == 'home' else 'A'})", "fixtures")
            fixture["gameweek"] = next_gw
            fixtures_out.append(dict(opponent=fixture, ratings=ratings))
        players.append(dict(name=identity.get("web_name") or "Identity unavailable", fields=fields,
                            nextFixtures=fixtures_out))
    forecasts = forecasts or {}
    projections = {}
    for key, missing in (("xPts", "Projection unavailable"), ("xMinutes", "Minutes projection unavailable"),
                         ("attackFDR", "Fixture model unavailable"), ("defenceFDR", "Fixture model unavailable")):
        item = forecasts.get(key) or {}
        projections[key] = datum(item.get("value"), source=item.get("source"),
            retrieved_at=item.get("retrievedAt"), gameweek=item.get("gameweek"),
            methodology=item.get("methodologyVersion"), now=now, status="MODEL ESTIMATE")
        if item.get("gameweek") != next_gw or not item.get("methodologyVersion"):
            projections[key]["value"] = None
            projections[key]["freshnessStatus"] = "unavailable"
        projections[key]["missingLabel"] = missing
    return dict(version=VERSION, reviewGW=gw, nextGW=next_gw, status=status,
                generatedAt=now.astimezone(EASTERN).isoformat(), scoreboard=scoreboard,
                players=players, projections=projections, personalTeamAvailable=bool(current and picks),
                modelDataAvailable=any(p["fields"]["xPts"]["freshnessStatus"] == "fresh" for p in players),
                nextTeamStatus="Current starting XI, bank and free transfers not verified",
                reviewSource=official(gw, "live"))


def build_timeline(words, *, duration, phrase_span, cards):
    """Measured speech cues; frame capture must never guess a narration boundary."""
    if not 35 <= duration <= 40:
        raise ValueError(f"Opening must measure 35–40 seconds; got {duration:.2f}s. Edit text, never accelerate voice.")
    def at(phrase):
        result = phrase_span(words, phrase, required=True, context="Gameweek Brief")
        return round(float(result[0]), 3)
    timeline = dict(hook=0.0, brand=at("This is"), title=at("Welcome"),
                    cards=[at(c["anchor"]) for c in cards],
                    transition=at("Let's review"), end=duration)
    order = [timeline["hook"], timeline["brand"], timeline["title"], *timeline["cards"], timeline["transition"], duration]
    if any(b <= a for a, b in zip(order, order[1:])):
        raise ValueError("Opening narration boundaries overlap or are out of order")
    return timeline


def build_intro_agenda(selected_scenes, *, next_gw, review_gw=None,
                       review_status=None, review_segments=None, brief=None):
    """Editorial promises, not fabricated mini-statistics in the agenda."""
    if "00_intro" not in selected_scenes:
        return []
    if "gw_review" not in selected_scenes or review_gw is None or not 1 <= int(review_gw) < int(next_gw) <= 38:
        raise ValueError("The Gameweek Brief must lead directly into a valid Gameweek Review")
    available = {s.get("id") for s in review_segments or []}
    if not {"headline", "editorial_squad_context", "editorial_routes", "editorial_verdict"} <= available:
        raise ValueError("Review agenda references missing editorial sections")
    rows = [
        ("gw_review", "review", "GAMEWEEK REVIEW", f"GW{review_gw} · " + ("Final points" if review_status == "FINAL" else "Provisional — results may change"),
         "Gameweek review", "First, the Gameweek review: the moment that swung the score."),
        ("02_fdr", "fixtures", "PLAYERS AND FIXTURES", "Role · minutes · next opponents",
         "Players and fixtures", "Players and fixtures: who can make the most of the matchup?"),
        ("03_projected_goals", "numbers", "NUMBERS BEHIND THE POINTS", "Actual returns and model estimates kept separate",
         "Numbers behind the points", "Numbers behind the points: how much of an upgrade does the model see?"),
    ]
    cards = [dict(key=k, title=t, subtitle=s, anchor=a, speech=v)
             for scene, k, t, s, a, v in rows if scene in selected_scenes]
    if brief:
        by_key = {card["key"]: card for card in cards}
        score = brief["scoreboard"]["Official GW points"]
        rank = brief["scoreboard"]["Rank movement"]
        by_key["review"]["subtitle"] = f"GW{review_gw} · {format_datum(score)} points · rank movement {format_datum(rank)} · {brief['status']}"
        if "numbers" in by_key:
            if not brief.get("modelDataAvailable") and brief["projections"]["xPts"]["freshnessStatus"] != "fresh":
                by_key["numbers"]["subtitle"] = "Actual returns verified where sourced · projection unavailable"
            else:
                by_key["numbers"]["subtitle"] = "FPL VORTEX model estimates · actual points kept separate"
        if not brief["personalTeamAvailable"]:
            by_key["review"]["subtitle"] = f"GW{review_gw} · Presenter team unavailable"
    return cards


def caption_cues(words):
    """Readable groups of measured words, never single-word flashing captions."""
    cues, chunk = [], []
    for word in words:
        if chunk and (len(chunk) >= 8 or float(word["start"]) - float(chunk[0]["start"]) > 3.4):
            cues.append(dict(start=chunk[0]["start"],
                end=float(chunk[-1]["start"])+float(chunk[-1]["duration"]),
                text=" ".join(w["text"] for w in chunk)))
            chunk = []
        chunk.append(word)
    if chunk:
        cues.append(dict(start=chunk[0]["start"],
            end=float(chunk[-1]["start"])+float(chunk[-1]["duration"]),
            text=" ".join(w["text"] for w in chunk)))
    return cues


def render_brief(brief, *, logo_html="", cards=(), timeline=None, review_uri=None):
    """One responsive HTML surface, deterministic __seek for the existing 4K renderer."""
    template = Path(__file__).with_name("day1_brief.html").read_text(encoding="utf-8")
    metrics = "".join(
        '<article class="metric"><span>'+escape(label)+'</span><strong>'+escape(format_datum(item))+
        '</strong><small>'+escape(badge(item))+'</small></article>' for label, item in brief["scoreboard"].items())
    agenda = "".join('<button class="agenda-card" data-index="'+str(i)+'" type="button">'
        '<span class="number">'+f"{i+1:02}"+'</span><span><strong>'+escape(c["title"])+
        '</strong><small>'+escape(c["subtitle"])+'</small></span><span class="arrow" aria-hidden="true">↗</span></button>'
        for i, c in enumerate(cards))
    player_rows = []
    for player in brief["players"]:
        fields = player["fields"]
        cells = "".join('<td>'+escape(format_datum(fields[k]))+'<small>'+escape(badge(fields[k]))+'</small></td>'
            for k in ("minutes", "total_points", "availability", "xPts", "expectedMinutes"))
        fixtures = "".join('<p>'+escape(format_datum(f["opponent"]))+'<small>'+escape(badge(f["opponent"]))+'</small>'+
            'Attack FDR: '+escape(format_datum(f["ratings"]["attack"]))+' · Defence FDR: '+escape(format_datum(f["ratings"]["defence"]))+
            '<small>'+escape(badge(f["ratings"]["attack"]))+' · '+escape(badge(f["ratings"]["defence"]))+'</small></p>'
            for f in player.get("nextFixtures", [])) or "Blank GW or fixtures unavailable"
        player_rows.append('<tr><th scope="row">'+escape(player["name"])+'</th>'+cells+'<td>'+fixtures+'</td></tr>')
    payload = json.dumps(dict(brief=brief, timeline=timeline, reviewUri=review_uri), ensure_ascii=False).replace("<", "\\u003c")
    for key, value in {"LOGO": logo_html, "AGENDA": agenda, "METRICS": metrics,
                       "GW": str(brief["reviewGW"]), "NEXT": str(brief["nextGW"]),
                       "STATUS": escape(brief["status"]), "STAMP": escape(badge(brief["reviewSource"])),
                       "PLAYERS": "".join(player_rows), "PAYLOAD": payload}.items():
        template = template.replace("__"+key+"__", value)
    return template
