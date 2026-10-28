# CELL 15 — AUTO GW REVIEW DATA + RYAN NARRATION TIMING
# ============================================================

from pathlib import Path
import json, subprocess, sys, re, unicodedata, math

ROOT   = Path(globals().get("PROJECT_ROOT", "/content/drive/MyDrive/FPL_VORTEX"))
AUDIO  = Path(globals().get("AUDIO_WORK_DIR", "/content/FPL_VORTEX_FIRST_DAY_WORK/audio")) / "review_segments"
TIMING = Path(globals().get("DATA_DIR", "/content/FPL_VORTEX_FIRST_DAY_WORK/data"))
AUDIO.mkdir(parents=True, exist_ok=True)
TIMING.mkdir(parents=True, exist_ok=True)

if "GW_REVIEW" not in globals() or "REVIEW_GW" not in globals():
    raise RuntimeError("Run GW REVIEW DATA SNAPSHOT before this cell.")
if int(GW_REVIEW["gw"]) != int(REVIEW_GW):
    raise RuntimeError(
        f"GW_REVIEW snapshot GW{GW_REVIEW['gw']} does not match upstream REVIEW_GW{REVIEW_GW}."
    )

GW_REVIEW_STATUS_LOCAL = str(
    GW_REVIEW.get("status") or globals().get("GW_REVIEW_STATUS") or "FINAL"
).upper()
GW_REVIEW_PARTIAL = GW_REVIEW_STATUS_LOCAL == "LIVE/PARTIAL"

boot  = GW_REVIEW["bootstrap"]
picks = GW_REVIEW["picks"]
hist  = GW_REVIEW["history"]
live  = GW_REVIEW["live"]
all_review_fixtures = list(GW_REVIEW["fixtures"])
review_fx = [
    f for f in all_review_fixtures
    if int(f.get("event") or 0) == REVIEW_GW
]

review_teams = {x["id"]: x for x in boot["teams"]}
review_elements = {x["id"]: x for x in boot["elements"]}
review_live_map = {x["id"]: x["stats"] for x in live["elements"]}

# previous overall rank → arrow direction
current_hist=picks["entry_history"]
previous=[
    x for x in hist.get("current",[])
    if int(x["event"]) < REVIEW_GW
]

prev_rank=previous[-1]["overall_rank"] if previous else None
cur_rank=current_hist.get("overall_rank")

rank_dir="flat"
if prev_rank and cur_rank:
    rank_dir="up" if cur_rank < prev_rank else "down" if cur_rank > prev_rank else "flat"

def _review_fixture_state(f):
    if not f:
        return "PENDING"
    started=bool(f.get("started"))
    minutes=int(f.get("minutes") or 0)
    status_complete=bool(f.get("finished") or f.get("finished_provisional"))
    score_complete=(
        f.get("team_h_score") is not None
        and f.get("team_a_score") is not None
    )
    if started and minutes>=90 and status_complete and score_complete:
        return "FINAL"
    if started:
        return "LIVE"
    return "PENDING"


def fixture_for(team_id):
    fixtures = [
        fixture for fixture in review_fx
        if team_id in (fixture.get("team_h"), fixture.get("team_a"))
    ]
    if not fixtures:
        return {"opp":"—","ha":"","score":"—","state":"UNKNOWN"}

    states = [_review_fixture_state(fixture) for fixture in fixtures]
    if all(state == "FINAL" for state in states):
        aggregate_state = "FINAL"
    elif all(state == "PENDING" for state in states):
        aggregate_state = "PENDING"
    elif "LIVE" in states:
        aggregate_state = "LIVE"
    else:
        aggregate_state = "PARTIAL"

    # A double Gameweek must not be marked final while another fixture remains.
    fixture = next(
        (item for item, state in zip(fixtures, states) if state != "FINAL"),
        fixtures[-1],
    )
    home = fixture["team_h"] == team_id
    opponent = review_teams[fixture["team_a"] if home else fixture["team_h"]]["short_name"]
    score = (
        f'{fixture.get("team_h_score")}–{fixture.get("team_a_score")}'
        if fixture.get("team_h_score") is not None
        and fixture.get("team_a_score") is not None
        else "—"
    )
    return {
        "opp": opponent,
        "ha": "H" if home else "A",
        "score": score,
        "state": aggregate_state,
    }


def next_fixture_for(team_id):
    """First scheduled fixture after the reviewed GW from the canonical snapshot."""
    candidates=[]
    for f in all_review_fixtures:
        event=int(f.get("event") or 0)
        if event <= REVIEW_GW:
            continue
        if f.get("team_h") != team_id and f.get("team_a") != team_id:
            continue
        kickoff=str(f.get("kickoff_time") or "")
        candidates.append((event, kickoff, f))
    if not candidates:
        return {"gw":None,"opp":"—","opp_name":"","ha":"","is_home":None,"kickoff_time":""}
    _, _, f=sorted(candidates,key=lambda x:(x[0],x[1]))[0]
    home=f["team_h"]==team_id
    opp_team=review_teams[f["team_a"] if home else f["team_h"]]
    return {
        "gw":int(f.get("event") or 0),
        "opp":opp_team["short_name"],
        "opp_name":opp_team["name"],
        "ha":"H" if home else "A",
        "is_home":bool(home),
        "kickoff_time":str(f.get("kickoff_time") or "")
    }


# Team clean-sheet card values are mapped from the shared WC/FH snapshot.
_review_next_cs_by_team={}
if "fixture_projection_df" in globals():
    try:
        _cs_tmp={}
        for _,r in fixture_projection_df.iterrows():
            if int(r.get("gw") or 0) != int(NEXT_GW):
                continue
            _cs_tmp.setdefault(int(r["home_id"]),[]).append(float(r["home_cs"]))
            _cs_tmp.setdefault(int(r["away_id"]),[]).append(float(r["away_cs"]))
        _review_next_cs_by_team={
            tid:sum(vals)/len(vals)
            for tid,vals in _cs_tmp.items()
            if vals
        }
    except Exception:
        _review_next_cs_by_team={}

POS={1:"GK",2:"DEF",3:"MID",4:"FWD"}
review_players=[]

for pick in picks["picks"]:
    e=review_elements[pick["element"]]
    s=review_live_map.get(pick["element"],{})
    t=review_teams[e["team"]]
    fixture=fixture_for(e["team"])

    review_players.append({
        "id":e["id"],
        "name":e["web_name"],
        "first_name":e.get("first_name", ""),
        "second_name":e.get("second_name", ""),
        "full_name":f'{e["first_name"]} {e["second_name"]}'.strip(),
        "team":t["short_name"],
        "team_name":t["name"],
        "team_code":t.get("code"),
        "pos":POS[e["element_type"]],
        "season_total_points":int(e.get("total_points",0) or 0),
        "season_form":float(e.get("form",0) or 0),
        "season_xg":float(e.get("expected_goals",0) or 0),
        "season_xa":float(e.get("expected_assists",0) or 0),
        "season_xgi":float(e.get("expected_goal_involvements",0) or 0),
        "season_xgc":float(e.get("expected_goals_conceded",0) or 0),
        "season_ppg":float(e.get("points_per_game",0) or 0),
        "season_bonus":int(e.get("bonus",0) or 0),
        "season_bps":int(e.get("bps",0) or 0),
        "season_penalties_saved":int(e.get("penalties_saved",0) or 0),
        # Official current-season totals for the responsive player card.
        # Frozen here so downstream cells never read preseason/shadow values.
        "season_minutes":int(e.get("minutes",0) or 0),
        "season_starts":int(e.get("starts",0) or 0),
        "season_goals":int(e.get("goals_scored",0) or 0),
        "season_assists":int(e.get("assists",0) or 0),
        "season_clean_sheets":int(e.get("clean_sheets",0) or 0),
        "season_goals_conceded":int(e.get("goals_conceded",0) or 0),
        "season_saves":int(e.get("saves",0) or 0),
        "bench":pick["position"]>11,
        "squad_position":pick["position"],
        "captain":pick["is_captain"],
        "vice":pick["is_vice_captain"],
        "multiplier":pick["multiplier"],

        "points":int(s.get("total_points",0) or 0),
        "minutes":int(s.get("minutes",0) or 0),
        "goals":int(s.get("goals_scored",0) or 0),
        "assists":int(s.get("assists",0) or 0),
        "clean_sheets":int(s.get("clean_sheets",0) or 0),
        "goals_conceded":int(s.get("goals_conceded",0) or 0),
        "saves":int(s.get("saves",0) or 0),
        "bonus":int(s.get("bonus",0) or 0),
        "bps":int(s.get("bps",0) or 0),
        "gw_xg":float(s.get("expected_goals",0) or 0),
        "gw_xa":float(s.get("expected_assists",0) or 0),
        "gw_xgi":float(s.get("expected_goal_involvements",0) or 0),
        "gw_xgc":float(s.get("expected_goals_conceded",0) or 0),

        "price":float(e["now_cost"])/10,
        "ownership":float(e.get("selected_by_percent",0) or 0),

        "photo": resolve_player_photo(e),

        "fixture":fixture,
        "review_state":str(fixture.get("state") or "PENDING").upper(),
        "next_fixture":next_fixture_for(e["team"]),
        "next_cs_pct":_review_next_cs_by_team.get(int(e["team"])),

    })

review_starters=sorted(
    [p for p in review_players if not p["bench"]],
    key=lambda x:(["GK","DEF","MID","FWD"].index(x["pos"]),x["squad_position"])
)

review_bench=sorted(
    [p for p in review_players if p["bench"]],
    key=lambda x:x["squad_position"]
)

# ------------------------------------------------------------
# NATURAL GAMEWEEK REVIEW — SHORT, HUMAN, ANALYTICAL
# ------------------------------------------------------------

bank=float(current_hist.get("bank",0))/10
value=float(current_hist.get("value",0))/10
gw_points=int(current_hist.get("points",0) or 0)
gw_rank=current_hist.get("rank")
transfer_cost=int(current_hist.get("event_transfers_cost",0) or 0)

from typing import Any


def vx_review_number(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def vx_review_price(value: float) -> str:
    names = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen")
    whole, fraction = divmod(int(round(float(value) * 10)), 10)
    return f"{names[whole]} point {names[fraction]} million" if 0 <= whole < len(names) else f"{value:.1f} million"


def vx_review_join(items: list[str]) -> str:
    return " and ".join(items) if len(items) < 3 else ", ".join(items[:-1]) + " and " + items[-1]


def vx_review_full_name(player: dict[str, Any]) -> str:
    # Official FPL web_name is the canonical spoken identity, not the legal surname.
    spoken = vx_narration_player(player)
    return str(spoken or player.get("name") or "").strip()


def vx_review_context(player: dict[str, Any]) -> dict[str, Any]:
    identity = int(player["id"])
    element = review_elements[identity]
    stats = review_live_map.get(identity, {})
    code = vx_review_number(element.get("code"))
    by_gameweek = {}
    for row in _review_history_records:
        if vx_review_number(row.get("player_code")) != code:
            continue
        if _review_history_season and str(row.get("season_label") or "") != _review_history_season:
            continue
        event = vx_review_number(row.get("gameweek", row.get("gw", row.get("round"))))
        if event is not None and max(1, REVIEW_GW - 2) <= event <= REVIEW_GW:
            by_gameweek[int(event)] = dict(row)
    if stats:
        by_gameweek[int(REVIEW_GW)] = dict(stats)
    last_three = {"gameweeks": sorted(by_gameweek)}
    for field in ("total_points", "minutes", "starts", "goals_scored", "assists", "clean_sheets", "saves", "bonus", "defensive_contribution"):
        numbers = [vx_review_number(row.get(field)) for row in by_gameweek.values()]
        last_three[field] = sum(numbers) if numbers and all(number is not None for number in numbers) else None
    last_three["complete"] = set(by_gameweek) == set(range(max(1, REVIEW_GW - 2), REVIEW_GW + 1))
    last_three["average_points"] = last_three["total_points"] / len(by_gameweek) if last_three["total_points"] is not None and by_gameweek else None
    return_fields = ["goals_scored", "assists", "bonus", "defensive_contribution_points"]
    if player["pos"] in {"GK", "DEF"}:
        return_fields.append("clean_sheets")
    last_three["return_count"] = sum(
        any((vx_review_number(row.get(field)) or 0) > 0 for field in return_fields)
        or player["pos"] == "GK" and (vx_review_number(row.get("saves")) or 0) >= 3
        for row in by_gameweek.values()
    )
    future = sorted(
        [fixture for fixture in all_review_fixtures if int(fixture.get("event") or 0) > REVIEW_GW and element["team"] in (fixture.get("team_h"), fixture.get("team_a"))],
        key=lambda fixture: (int(fixture["event"]), str(fixture.get("kickoff_time") or ""), int(fixture.get("id") or 0)),
    )[:3]
    fixtures = []
    for fixture in future:
        home = fixture["team_h"] == element["team"]
        opponent_id = fixture["team_a"] if home else fixture["team_h"]
        opponent = str((review_teams.get(opponent_id) or {}).get("name") or "")
        if opponent:
            fixtures.append({"opponent": opponent, "home": home, "gw": fixture["event"], "fdr": vx_review_number(fixture.get("fdr"))})
    points = {}
    live_element = next((row for row in live.get("elements", []) if int(row.get("id") or 0) == identity), {})
    for fixture in live_element.get("explain", []):
        for item in fixture.get("stats", []):
            value = vx_review_number(item.get("points"))
            if value is not None:
                key = str(item.get("identifier") or "")
                points[key] = points.get(key, 0) + value
    if (points.get("defensive_contribution") or 0) > 0 and not any((vx_review_number(stats.get(field)) or 0) > 0 for field in return_fields) and not (player["pos"] == "GK" and (vx_review_number(stats.get("saves")) or 0) >= 3):
        last_three["return_count"] += 1
    pick = next((row for row in picks["picks"] if int(row["element"]) == identity), {})
    current_price = vx_review_number(element.get("now_cost"))
    purchase_price = vx_review_number(pick.get("purchase_price"))
    selling_price = vx_review_number(pick.get("selling_price"))
    return {
        "full_name": vx_review_full_name(player), "position": player["pos"],
        "club": str(review_teams[element["team"]]["name"]), "stats": dict(stats),
        "last_three": last_three, "next_three": fixtures, "point_breakdown": points,
        "status": str(element.get("status") or ""), "news": str(element.get("news") or "").strip(),
        "current_price": current_price / 10 if current_price is not None else None,
        "purchase_price": purchase_price / 10 if purchase_price is not None else None,
        "selling_price": selling_price / 10 if selling_price is not None else None,
        "price_change": vx_review_number(element.get("cost_change_event")),
        "captain": bool(pick.get("is_captain")), "vice": bool(pick.get("is_vice_captain")),
        "selected_starter": not player["bench"],
    }


def vx_review_recent_phrase(context: dict[str, Any]) -> str:
    recent = context["last_three"]
    if recent["complete"] and len(recent["gameweeks"]) == 3 and recent["total_points"] is not None:
        return f"{int(recent['total_points'])} points across the last three Gameweeks"
    minutes = vx_review_number(context["stats"].get("minutes"))
    return f"{int(minutes)} minutes this week" if minutes is not None else ""


def vx_review_schedule(context: dict[str, Any], named: bool = False) -> str:
    fixtures = context["next_three"]
    if not fixtures:
        return ""
    if named:
        return "Next come " + vx_review_join([fixture["opponent"] for fixture in fixtures]) + "."
    difficulties = [fixture["fdr"] for fixture in fixtures]
    if len(difficulties) == 3 and all(value is not None for value in difficulties):
        average = sum(difficulties) / 3
        return "an encouraging fixture run" if average <= 2.5 else "a difficult fixture run" if average >= 3.5 else "a mixed fixture run"
    return "the next fixture run"


def vx_review_return_reason(player: dict[str, Any]) -> str:
    context = _review_narration_context[int(player["id"])]
    stats = context["stats"]
    details = []
    goals, assists = vx_review_number(stats.get("goals_scored")), vx_review_number(stats.get("assists"))
    if goals and goals > 0:
        details.append("a goal" if goals == 1 else f"{int(goals)} goals")
    if assists and assists > 0:
        details.append("an assist" if assists == 1 else f"{int(assists)} assists")
    if player["pos"] in {"GK", "DEF", "MID"} and (vx_review_number(stats.get("clean_sheets")) or 0) > 0:
        details.append("a clean sheet")
    if player["pos"] == "GK" and (vx_review_number(stats.get("saves")) or 0) >= 3:
        details.append(f"{int(stats['saves'])} saves")
    if (vx_review_number(stats.get("bonus")) or 0) > 0:
        details.append("bonus")
    if (context["point_breakdown"].get("defensive_contribution") or 0) > 0:
        details.append("defensive-contribution points")
    return vx_review_join(details[:2])


def vx_review_player_result_state(player: dict[str, Any]) -> str:
    fixture_state = str(player.get("review_state") or "UNKNOWN").upper()
    minutes = vx_review_number(player.get("minutes"))
    if fixture_state in {"PENDING", "UNKNOWN"}:
        return "AWAITING" if fixture_state == "PENDING" else "UNKNOWN"
    if minutes is None:
        return "UNKNOWN"
    if minutes <= 0:
        return "DID_NOT_PLAY" if fixture_state == "FINAL" else "AWAITING"
    return "COMPLETE" if fixture_state == "FINAL" else "PROVISIONAL"


def vx_review_creator_player_text(player: dict[str, Any], index: int, bench: bool = False) -> str:
    context = _review_narration_context[int(player["id"])]
    name = context["full_name"]
    points = vx_review_number(context["stats"].get("total_points"))
    minutes = vx_review_number(context["stats"].get("minutes"))
    result_state = vx_review_player_result_state(player)
    if bench:
        prefix = ("On the bench, ", "Next among the reserves, ", "Also on the bench, ", "And finally, ")[index % 4]
    elif index == 0:
        prefix = {"GK": "In goal, ", "DEF": "At the back, ", "MID": "In midfield, ", "FWD": "Up front, "}[player["pos"]]
    else:
        openings = ("Meanwhile, ", "Elsewhere, ", "Next, ", "And ")
        prefix = openings[(index + {"GK": 0, "DEF": 1, "MID": 2, "FWD": 3}[player["pos"]]) % len(openings)]
    if result_state == "AWAITING":
        if str(player.get("review_state") or "").upper() == "LIVE":
            return prefix + name + " has not featured yet; their match is still in progress."
        return prefix + name + " has not played yet; their Gameweek score is not settled."
    if result_state == "UNKNOWN":
        return prefix + name + " has no verified match result yet."
    if result_state == "DID_NOT_PLAY":
        return prefix + name + " did not feature in the completed fixture, so there is no performance to judge."
    if points is None:
        return prefix + name + " has no confirmed points return yet."
    points = int(points)
    point_word = "point" if points == 1 else "points"
    if result_state == "PROVISIONAL":
        return prefix + name + f" has {points} {point_word} so far, but their Gameweek is not finished."
    reason = vx_review_return_reason(player)
    story_index = int(player.get("squad_position") or index) % 4
    if player["pos"] == "GK" and not bench:
        text = prefix + name + f" returned {points} {point_word}" + (f" through {reason}." if reason else ".")
        recent = vx_review_recent_phrase(context)
        schedule = vx_review_schedule(context, named=True)
        if recent and schedule and len((text + " That is " + recent + ". " + schedule).split()) <= 32:
            text += " That is " + recent + "; " + schedule[:1].lower() + schedule[1:]
        elif recent:
            text += " The wider picture is " + recent + "."
            if context["next_three"]:
                text += " The next fixtures are the opportunity to respond."
        elif schedule and len((text + " " + schedule).split()) <= 32:
            text += " " + schedule
        price = context["current_price"]
        if price is not None and len(text.split()) <= 28:
            text += " The current price is " + vx_review_price(price) + "."
        return text
    if points <= 2:
        quiet_lines = (
            f" managed only {points} {point_word}.",
            f" had a quiet {points}-point week.",
            f" finished with {points}, without much reward.",
            f" returned just {points} this time.",
        )
        text = prefix + name + quiet_lines[story_index]
        recent, schedule = vx_review_recent_phrase(context), vx_review_schedule(context)
        if recent and schedule:
            context_lines = (
                f" That's {recent}, but {schedule} matters more than one result.",
                f" That's {recent}; now we need to weigh it against {schedule}.",
                f" The recent record is {recent}; {schedule} is the next test.",
                f" With {recent}, it's worth considering {schedule} before judging one score.",
            )
            text += context_lines[story_index]
        elif recent:
            text += f" The wider picture is {recent}."
        elif schedule:
            text += " The upcoming fixtures give the result more context."
    elif points <= 5:
        if reason:
            text = prefix + name + f" added {points} through {reason}."
        elif minutes is not None and minutes < 60:
            text = prefix + name + f" managed {points} from {int(minutes)} minutes."
        elif context["current_price"] is not None and context["current_price"] >= (8 if player["pos"] in {"MID", "FWD"} else 6):
            text = prefix + name + f" returned {points}; at {vx_review_price(context['current_price'])}, that was modest."
        else:
            text = prefix + name + f" finished with {points} points."
    else:
        text = prefix + name + f" delivered {points}" + (f" through {reason}." if reason else " points.")
    return text


def vx_review_clean_text(text: str) -> str:
    for abbreviation, expansion in (("xPts", "expected points"), ("xG", "expected goals"), ("xA", "expected assists"), ("FPL", "Fantasy Premier League"), ("GW", "Gameweek")):
        text = re.sub(r"\b" + abbreviation + r"\b", expansion, text, flags=re.I)
    text = text.replace(": ", ", ")
    protected = {}
    for index, context in enumerate(sorted(_review_narration_context.values(), key=lambda row: len(row["full_name"]), reverse=True)):
        name = context["full_name"]
        token = f"zzreviewspokenname{index}zz"
        if name in text:
            text = text.replace(name, token)
            protected[token] = name
    text = vx_full_word_narration(text, context="creator Gameweek review")
    for token, name in protected.items():
        text = text.replace(token, name)
    text = re.sub(r"£?(\d+(?:\.\d+)?)\s*m\b", lambda match: vx_review_price(float(match[1])), text, flags=re.I)
    text = re.sub(r"(\d+(?:\.\d+)?)%", r"\1 percent", text)
    text = re.sub(r"[\[\]{}|•:()]", " ", text)
    text = re.sub(r"[^\w\s.,'’!?;\-]", " ", text)
    text = re.sub(r"\.{2,}", ".", text)
    text = re.sub(r",\s*,+", ",", text)
    return re.sub(r"\s+", " ", text).strip()


def vx_review_validate_creator_script(narration: dict[str, Any], script_segments: list[dict[str, Any]]) -> None:
    player_segments = [segment for segment in script_segments if segment.get("player_id")]
    expected = [int(player["id"]) for player in review_starters + review_bench]
    if [int(segment["player_id"]) for segment in player_segments] != expected or len(set(expected)) != 15:
        raise RuntimeError("Creator review must account for all fifteen players once in the existing visual order")
    positions = [player["pos"] for player in review_starters]
    if positions.count("GK") != 1 or not 3 <= positions.count("DEF") <= 5 or not 2 <= positions.count("MID") <= 5 or not 1 <= positions.count("FWD") <= 3 or len(positions) != 11:
        raise RuntimeError("Selected starting XI does not have a valid formation")
    text = narration["tts_text"]
    if re.search(r"\b(?:sell|hold|monitor|remove|transfer|nailed|guaranteed)\b|secure and firm|must buy|must sell", text, flags=re.I):
        raise RuntimeError("Gameweek review contains a direct instruction or unsupported certainty")
    if re.search(r"\b(?:xG|xA|xPts|GW|FPL)\b|\b[A-Z]\.\s*[A-Z]", text):
        raise RuntimeError("Gameweek review contains narration shorthand")
    for team in review_teams.values():
        short = str(team.get("short_name") or "")
        if short and re.search(r"\b" + re.escape(short) + r"\b", text):
            raise RuntimeError("Gameweek review contains a club abbreviation")
    if text.lower().count("he scored") > 2:
        raise RuntimeError("Gameweek review repeats points-table language")
    captain = next((player for player in review_players if player.get("captain")), None)
    if captain and _review_final_available and int(captain["id"]) not in _review_final_ids and vx_review_number(_review_narration_context[int(captain["id"])]["stats"].get("minutes")) != 0:
        raise RuntimeError("Captain is outside the final XI without a confirmed non-playing exception")


_review_history_frame = globals().get("phase10_player_gw_all")
_review_history_records = _review_history_frame.to_dict("records") if hasattr(_review_history_frame, "to_dict") else []
_review_history_season = str(globals().get("_phase10_current_label") or globals().get("CURRENT_SEASON") or "")
_review_narration_context = {int(player["id"]): vx_review_context(player) for player in review_players}
_review_data_warnings = []
for _player_id, _context in _review_narration_context.items():
    if not _context["last_three"]["complete"]:
        _review_data_warnings.append(f"{_context['full_name']}: incomplete last-three Gameweek data; missing values omitted")
    if not _context["next_three"]:
        _review_data_warnings.append(f"{_context['full_name']}: next-three fixtures unavailable")

_review_selected_ids = {int(player["id"]) for player in review_starters}
_review_final_ids = set(_review_selected_ids)
_review_final_available = not GW_REVIEW_PARTIAL and "automatic_subs" in picks
if _review_final_available:
    _counted = {int(row["element"]) for row in picks["picks"] if int(row.get("multiplier") or 0) > 0}
    if len(_counted) == 11:
        _review_final_ids = _counted
    else:
        for _substitution in picks.get("automatic_subs") or []:
            _review_final_ids.discard(int(_substitution["element_out"]))
            _review_final_ids.add(int(_substitution["element_in"]))
_review_final_players = [player for player in review_players if int(player["id"]) in _review_final_ids]
_review_formation_counts = {position: sum(player["pos"] == position for player in _review_final_players) for position in ("GK", "DEF", "MID", "FWD")}
if len(_review_final_players) != 11 or _review_formation_counts["GK"] != 1 or not 3 <= _review_formation_counts["DEF"] <= 5 or not 2 <= _review_formation_counts["MID"] <= 5 or not 1 <= _review_formation_counts["FWD"] <= 3:
    _review_final_players = list(review_starters)
    _review_final_ids = set(_review_selected_ids)
    _review_final_available = False
    _review_data_warnings.append("Final XI unavailable or invalid; selected XI formation used")
    _review_formation_counts = {position: sum(player["pos"] == position for player in review_starters) for position in ("GK", "DEF", "MID", "FWD")}
formation = "-".join(str(_review_formation_counts[position]) for position in ("DEF", "MID", "FWD"))

_review_points_available = vx_review_number(current_hist.get("points")) is not None
_review_score_text = f" and {gw_points} points" if _review_points_available else ""
_review_opening = f"Let's review Gameweek {REVIEW_GW}: a {formation}{_review_score_text}."
if _review_final_ids != _review_selected_ids and _review_final_available:
    _review_opening = f"Gameweek {REVIEW_GW}: the final {formation}{_review_score_text}."
if not _review_points_available:
    _review_data_warnings.append("Team Gameweek points missing; score omitted from narration")
_review_narration = {
    "formation": formation, "gameweek_summary": _review_opening,
    "goalkeeper_review": "", "defender_review": "", "midfielder_review": "", "forward_review": "",
    "bench_review": "", "captain_review": "", "gameweek_hero": "", "quietest_return": "",
    "availability_alerts": "", "outro": "", "tts_text": "", "data_warnings": _review_data_warnings,
    "final_active_xi": _review_final_available, "player_context": _review_narration_context,
}
segments = [{"id": "headline", "text": _review_opening}]
_review_section_names = {"GK": "goalkeeper_review", "DEF": "defender_review", "MID": "midfielder_review", "FWD": "forward_review"}
_position_seen = {"GK": 0, "DEF": 0, "MID": 0, "FWD": 0}
for _player in review_starters:
    _position_index = _position_seen[_player["pos"]]
    _position_seen[_player["pos"]] += 1
    _spoken = vx_review_creator_player_text(_player, _position_index)
    if _review_final_available and int(_player["id"]) not in _review_final_ids:
        _spoken += " His place was covered by an automatic substitution."
    _review_narration[_review_section_names[_player["pos"]]] += _spoken + " "
    segments.append({"id": f"player_{_player['id']}", "player_id": _player["id"], "name": _player["name"], "spoken_name": vx_review_full_name(_player), "kind": "starter", "text": _spoken})
segments.append({"id": "bench_intro", "text": "Before we move on, let's check the bench."})
for _index, _player in enumerate(review_bench):
    _spoken = vx_review_creator_player_text(_player, _index, bench=True)
    if _review_final_available and int(_player["id"]) in _review_final_ids and int(_player["id"]) not in _review_selected_ids:
        _spoken += " His points counted after an automatic substitution."
    _review_narration["bench_review"] += _spoken + " "
    segments.append({"id": f"player_{_player['id']}", "player_id": _player["id"], "name": _player["name"], "spoken_name": vx_review_full_name(_player), "kind": "bench", "text": _spoken})

captain_player = next((player for player in review_players if player.get("captain")), None)
captain_return = 0
_captain_text = ""
if captain_player:
    _captain_stats = _review_narration_context[int(captain_player["id"])]["stats"]
    _captain_raw = vx_review_number(_captain_stats.get("total_points"))
    _captain_minutes = vx_review_number(_captain_stats.get("minutes"))
    _captain_name = vx_review_full_name(captain_player)
    _captain_multiplier = int(captain_player.get("multiplier") or 0)
    _captain_state = vx_review_player_result_state(captain_player)
    if _captain_state in {"AWAITING", "UNKNOWN"}:
        _captain_text = f"Captain {_captain_name} has not played yet, so their return is still unknown."
    elif _captain_state == "DID_NOT_PLAY":
        _captain_text = f"Captain {_captain_name} did not feature in the completed fixture."
        _vice_player = next((player for player in review_players if player.get("vice") and int(player.get("multiplier") or 0) > 1 and vx_review_player_result_state(player) == "COMPLETE"), None)
        if _vice_player:
            _vice_raw = vx_review_number(_review_narration_context[int(_vice_player["id"])]["stats"].get("total_points"))
            if _vice_raw is not None:
                _captain_text += f" The armband passed to {vx_review_full_name(_vice_player)}, contributing {int(_vice_raw) * int(_vice_player['multiplier'])} points."
    elif _captain_state == "PROVISIONAL" and _captain_raw is not None:
        _captain_text = f"Captain {_captain_name} has {int(_captain_raw)} points so far; the captaincy outcome remains provisional."
    elif _captain_raw is not None:
        captain_return = int(_captain_raw) * _captain_multiplier
        _other_returns = [vx_review_number(_review_narration_context[int(player["id"])]["stats"].get("total_points")) for player in _review_final_players if int(player["id"]) != int(captain_player["id"]) and vx_review_player_result_state(player) == "COMPLETE"]
        _other_returns = [value for value in _other_returns if value is not None]
        _captain_average = sum(_other_returns) / len(_other_returns) if _other_returns else None
        _captain_verdict = "above the other starters' average" if _captain_average is not None and _captain_raw > _captain_average else "below the other starters' average" if _captain_average is not None and _captain_raw < _captain_average else "level with the other starters' average" if _captain_average is not None else "the captain result this week"
        _multiplier_word = "doubled" if _captain_multiplier == 2 else "tripled" if _captain_multiplier == 3 else "counted"
        _captain_text = f"Captain {_captain_name} returned {int(_captain_raw)}, {_multiplier_word} to {captain_return}; that was {_captain_verdict}."
else:
    _review_data_warnings.append("Captain flag missing; captain result omitted")
if not _captain_text:
    _captain_text = "The captain result is not available in this snapshot."
_review_narration["captain_review"] = _captain_text

_review_known_active = [
    player for player in _review_final_players
    if vx_review_player_result_state(player) in {"COMPLETE", "PROVISIONAL"}
    and vx_review_number(_review_narration_context[int(player["id"])]["stats"].get("total_points")) is not None
]
if _review_known_active:
    highest_player = max(_review_known_active, key=lambda player: (player["points"], bool(player.get("captain") or int(player.get("multiplier") or 0) > 1), player.get("bonus", 0), player.get("goals", 0) + player.get("assists", 0), player.get("minutes", 0)))
    _hero_reason = vx_review_return_reason(highest_player)
    if vx_review_player_result_state(highest_player) == "COMPLETE":
        _review_narration["gameweek_hero"] = f"{vx_review_full_name(highest_player)} leads the verified returns with {highest_player['points']} points" + (f", including {_hero_reason}." if _hero_reason else ".")
    else:
        _review_narration["gameweek_hero"] = f"{vx_review_full_name(highest_player)} currently leads with {highest_player['points']} points, pending the remaining football."

    # Select the lowest completed return before considering an unfinished match.
    _completed_players = [player for player in _review_known_active if vx_review_player_result_state(player) == "COMPLETE"]
    _quietest_pool = _completed_players or _review_known_active
    _quietest_player = min(_quietest_pool, key=lambda player: (player["points"], player.get("minutes", 0)))
    if vx_review_player_result_state(_quietest_player) == "COMPLETE":
        _review_narration["quietest_return"] = f"At the other end, {vx_review_full_name(_quietest_player)} finished with {_quietest_player['points']} points. But one match is not the whole picture."
    else:
        _review_narration["quietest_return"] = f"{vx_review_full_name(_quietest_player)} has {_quietest_player['points']} points so far, with their fixture still unfinished."

_review_alerts = []
for _player in review_players:
    _context = _review_narration_context[int(_player["id"])]
    _status, _news = _context["status"], _context["news"]
    if _status == "s":
        _review_alerts.append(f"{_context['full_name']} is unavailable through suspension.")
    elif _status not in {"", "a"}:
        _summary = re.split(r"[.;]", _news, maxsplit=1)[0].strip()
        if _summary and len(_summary.split()) <= 14 and not re.search(r"\b[A-Z]{2,}[A-Z0-9]*\b|\b[A-Z]\.\s*[A-Z]", _summary):
            _review_alerts.append(f"Availability is the main concern for {_context['full_name']}; the official update says {_summary}.")
        else:
            _review_alerts.append(f"{_context['full_name']} has an official availability flag before the next deadline.")
if not _review_alerts:
    _limited = [vx_review_full_name(player) for player in _review_final_players if vx_review_player_result_state(player) in {"COMPLETE", "PROVISIONAL"} and 0 < int(player.get("minutes") or 0) < 30]
    if _limited:
        _review_alerts.append("Limited minutes for " + vx_review_join(_limited) + " change the short-term picture.")
_review_narration["availability_alerts"] = " ".join(_review_alerts)
_review_price_pressure = [
    context["full_name"] for context in _review_narration_context.values()
    if context["price_change"] is not None and context["price_change"] <= -2
]
if _review_price_pressure:
    _review_narration["availability_alerts"] += " A price drop adds value pressure around " + vx_review_join(_review_price_pressure) + "."
_clean_availability = all(context["status"] == "a" and not context["news"] for context in _review_narration_context.values())
_review_narration["outro"] = (
    ("There are no official availability flags in this squad. " if _clean_availability else "")
    + ("This is still a provisional review. " if GW_REVIEW_PARTIAL else "")
    + "That is where my squad stands. Thanks for watching FPL Vortex. Subscribe, and I will see you next time."
)
segments.append({"id": "metrics_intro", "text": "Now, did the captaincy pay off?"})
for _segment_id, _section in (("metric_captain", "captain_review"), ("hero_review", "gameweek_hero"), ("quietest_review", "quietest_return"), ("availability_review", "availability_alerts"), ("review_close", "outro")):
    if _review_narration[_section]:
        segments.append({"id": _segment_id, "text": _review_narration[_section]})
from day1.editorial import compact_review_segments
compact_review_segments(segments, max_words=500)
for _segment in segments:
    _segment["text"] = vx_review_clean_text(_segment["text"])
for _section in ("gameweek_summary", "goalkeeper_review", "defender_review", "midfielder_review", "forward_review", "bench_review", "captain_review", "gameweek_hero", "quietest_return", "availability_alerts", "outro"):
    _review_narration[_section] = vx_review_clean_text(_review_narration[_section].strip())
tts_text = " ".join(segment["text"] for segment in segments)
_review_narration["tts_text"] = tts_text
if len(tts_text.split()) > 235:
    _review_data_warnings.append("The complete fifteen-player review may exceed the preferred short duration at the requested neutral Ryan rate")
vx_review_validate_creator_script(_review_narration, segments)


# Hard brevity gates: all players remain explained, but the review cannot drift
# back into a long, repetitive monologue.
_draft_player_segments=[segment for segment in segments if segment.get("player_id")]
for _segment in _draft_player_segments:
    _words=re.findall(r"\b[\w'-]+\b",str(_segment["text"]))
    if len(_words)>58:
        raise RuntimeError(
            f"GW Review player narration is too long: {_segment['id']} has {len(_words)} words"
        )

GW_REVIEW_NARRATION_WORDS=sum(
    len(re.findall(r"\b[\w'-]+\b",str(segment.get("text", ""))))
    for segment in segments
)
if GW_REVIEW_NARRATION_WORDS>500:
    raise RuntimeError(
        f"GW Review narration exceeded the 500-word brevity gate: {GW_REVIEW_NARRATION_WORDS}"
    )

_opening_keys=[
    " ".join(re.findall(r"\b[\w'-]+\b",str(segment["text"]).lower())[:5])
    for segment in _draft_player_segments
]
if any(_opening_keys.count(key)>2 for key in set(_opening_keys)):
    raise RuntimeError("GW Review narration repeats the same player opening too often.")

# ------------------------------------------------------------
# NARRATION QA — NATURAL VARIETY + ONE SEGMENT PER PLAYER
# ------------------------------------------------------------

_player_segments=[s for s in segments if s.get("player_id")]
_expected_ids=[int(p["id"]) for p in review_starters+review_bench]
_segment_ids=[int(s["player_id"]) for s in _player_segments]

if _segment_ids != _expected_ids:
    raise RuntimeError(
        "GW Review narration/player order mismatch. "
        f"Expected {_expected_ids}, got {_segment_ids}"
    )

for s in _player_segments:
    if str(s.get("spoken_name") or s["name"]).lower() not in str(s["text"]).lower():
        raise RuntimeError(f"Player name missing from narration segment: {s['id']}")

_review_norm=[re.sub(r"\s+"," ",str(s["text"]).strip().lower()) for s in segments]
if len(_review_norm) != len(set(_review_norm)):
    raise RuntimeError("GW Review narration contains an exact repeated segment.")

# Catch the old robotic repeated constructions if they accidentally return.
_old_robotic_patterns=[
    r"\bnext is\b.*\bnext is\b",
    r"\bthe score was built on\b",
    r"\bthe useful evidence\b",
]
for pattern in _old_robotic_patterns:
    if sum(bool(re.search(pattern,s["text"].lower())) for s in _player_segments) > 2:
        raise RuntimeError(f"GW Review narration is becoming repetitive: {pattern}")

# EDGE-TTS — ONE SEGMENT AT A TIME = EXACT ANIMATION WINDOWS
# ------------------------------------------------------------

for _required_tts_name in ("VOICE", "MOODS", "vx_tts_profile", "vx_edge_tts_stream", "vx_full_word_narration", "vx_full_word_display", "vx_narration_team", "vx_narration_player"):
    if _required_tts_name not in globals():
        raise RuntimeError(
            "Run SHARED PRODUCTION HELPERS before narration — "
            f"missing {_required_tts_name}"
        )

def review_tts_mood(seg):
    sid = str(seg.get("id", ""))

    if sid == "headline":
        return "intro"

    if sid in {
        "metric_chip", "metric_points", "metric_orank", "metric_gwrank",
        "metric_captain", "metric_bench",
    }:
        return "key_stat"

    if sid == "metric_hit" and transfer_cost > 0:
        return "warning"

    if sid == "review_close":
        return "outro"

    return "analysis"


async def make_segment(seg):

    path=AUDIO/f'{seg["id"]}.mp3'
    audio=bytearray()
    words=[]

    mood = review_tts_mood(seg)
    profile = {"rate": "+0%", "pitch": "+0Hz", "volume": "+0%"}
    seg["tts_mood"] = mood
    seg["tts_profile"] = profile

    # CELL 22 is the final authority: no shorthand reaches Ryan or the
    # narration-facing display/package text.
    seg["text"] = vx_review_clean_text(seg["text"])
    seg["display_text"] = seg["text"]

    audio_bytes, words = await vx_edge_tts_stream(seg["text"], profile)
    audio.extend(audio_bytes)

    path.write_bytes(audio)

    seg["audio"]=str(path)
    seg["duration"]=vx_media_duration(path)
    seg["words"]=words

    # Exact moment Ryan says the player's canonical FPL web_name.
    #
    # Edge TTS does not guarantee that one written word == one WordBoundary
    # chunk. A name can arrive as one boundary ("Raya") or several adjacent
    # boundaries ("Ray", "a"). Match an EXACT normalized span of adjacent
    # Ryan boundaries; never fall back to segment start or an estimated time.
    seg["name_time"]=None

    if seg.get("name"):
        canonical_name = seg.get("spoken_name") or vx_narration_player(
            seg.get("player_id") if seg.get("player_id") is not None else seg["name"]
        )
        canonical_name = str(canonical_name or seg["name"]).strip()
        seg["name"] = canonical_name

        def _review_boundary_key(value):
            value = unicodedata.normalize("NFKD", str(value or "").casefold())
            value = "".join(ch for ch in value if not unicodedata.combining(ch))
            return "".join(ch for ch in value if ch.isalnum())

        target_key = _review_boundary_key(canonical_name)
        if not target_key:
            raise RuntimeError(
                f"Canonical player web name is empty for {seg['id']}; "
                "Ryan animation sync cannot be validated."
            )

        boundary_keys = [_review_boundary_key(w.get("text", "")) for w in words]

        # Search only adjacent spoken boundaries and accept only an exact
        # concatenated identity match. This handles TTS token splitting while
        # keeping timing sourced from Ryan's real WordBoundary timestamp.
        for j in range(len(boundary_keys)):
            combined = ""
            for k in range(j, min(len(boundary_keys), j + 8)):
                part = boundary_keys[k]
                if not part:
                    continue
                combined += part

                if combined == target_key:
                    seg["name_time"] = float(words[j]["start"])
                    seg["name_boundary_span"] = [int(j), int(k)]
                    break

                if len(combined) >= len(target_key):
                    break

            if seg["name_time"] is not None:
                break

        if seg["name_time"] is None:
            boundary_preview = [
                str(w.get("text", ""))
                for w in words[:16]
            ]
            raise RuntimeError(
                f"Ryan name boundary not found for canonical web name "
                f"{canonical_name!r} in {seg['id']}. "
                f"Received {len(words)} WordBoundary events; first boundaries: "
                f"{boundary_preview}. Animation sync is blocked rather than guessed."
            )
    else:
        seg["name_time"]=0.0

for seg in segments:
    await make_segment(seg)
# ------------------------------------------------------------
# OPENING NARRATION FIT — PRESERVE RYAN'S NATURAL DELIVERY
# ------------------------------------------------------------
# Ryan keeps the approved voice, mood, punctuation and speaking rate. Only the
# opening sentence is regenerated when its measured MP3 duration would collide
# with the goalkeeper's real WordBoundary-aligned reveal.
_headline_segment = next(
    (segment for segment in segments if str(segment.get("id", "")) == "headline"),
    None,
)
_first_review_player = next(
    (segment for segment in segments if segment.get("player_id") is not None),
    None,
)
if _headline_segment is None or _first_review_player is None:
    raise RuntimeError("GW Review opening-fit QA requires headline and player narration.")

_review_timing_override = globals().get("GW_REVIEW_ANIMATION_TIMING_OVERRIDES", {}) or {}
_headline_first_player_at = max(
    float(_review_timing_override.get("first_player_at", 0.0)),
    float(_headline_segment.get("duration") or 0.0)
    + float(_first_review_player.get("name_time") or 0.0)
    + 0.12,
)
_headline_name_time = float(_first_review_player.get("name_time") or 0.0)
_headline_safety_gap = 0.12
_headline_budget = (
    _headline_first_player_at
    - _headline_name_time
    - _headline_safety_gap
)
if not math.isfinite(_headline_budget) or _headline_budget <= 0:
    raise RuntimeError(
        "GW Review opening narration has no valid timing budget before the goalkeeper reveal."
    )

if float(_headline_segment.get("duration") or 0.0) > _headline_budget:
    _headline_segment["text"] = (
        f"Gameweek {REVIEW_GW}: {formation}{_review_score_text}."
    )
    await make_segment(_headline_segment)
    print(
        "ℹ️ GW Review headline compacted naturally to fit the goalkeeper reveal: "
        f"{float(_headline_segment['duration']):.3f}s / {_headline_budget:.3f}s budget"
    )

# Defensive fallback for a future Ryan/TTS cadence change. Do not speed the
# voice up: use a shorter natural line and leave Cell 16's hard overlap guard.
if float(_headline_segment.get("duration") or 0.0) > _headline_budget:
    _headline_segment["text"] = (
        f"Gameweek {REVIEW_GW}, {formation}{_review_score_text}."
    )
    await make_segment(_headline_segment)

if float(_headline_segment.get("duration") or 0.0) > _headline_budget:
    raise RuntimeError(
        "GW Review headline still exceeds its measured opening timing budget after "
        "natural text compaction; Ryan speed was intentionally left unchanged."
    )

# Keep the logged QA count aligned with the narration actually saved after any
# headline-only regeneration.
GW_REVIEW_NARRATION_WORDS = sum(
    len(re.findall(r"\b[\w'-]+\b", str(segment.get("text", ""))))
    for segment in segments
)

tts_text = " ".join(segment["text"] for segment in segments)
_review_narration["gameweek_summary"] = _headline_segment["text"]
_review_narration["tts_text"] = tts_text
vx_review_validate_creator_script(_review_narration, segments)

# ------------------------------------------------------------
# SAVE REVIEW PACKAGE
# ------------------------------------------------------------

review_package={
    "gw":REVIEW_GW,
    "status":GW_REVIEW_STATUS_LOCAL,
    "fixture_state":dict(GW_REVIEW.get("fixture_state") or {}),
    "players":review_players,
    "starters":review_starters,
    "bench":review_bench,
    "metrics":{
        "gw_points":gw_points,
        "bank":bank,
        "value":value,
        "gw_rank":gw_rank,
        "overall_rank":cur_rank,
        "previous_rank":prev_rank,
        "rank_dir":rank_dir,
        "transfer_cost":transfer_cost
    },
    "segments":segments,
    "narration":_review_narration,
    "tts_text":tts_text
}

# Canonical in-memory handoff for downstream review cells.
# If the DATA artifact disappears later in the same runtime,
# Cell 16 can restore this exact completed package without rebuilding it.
GW_REVIEW_PACKAGE = review_package

OUT=TIMING/"gw_review_package.json"

OUT.write_text(
    json.dumps(review_package,indent=2),
    encoding="utf-8"
)

print(f"✅ GW {REVIEW_GW} review data loaded")
print(f"✅ Starting XI: {len(review_starters)}")
print(f"✅ Bench: {len(review_bench)}")
print(f"✅ Ryan narration segments: {len(segments)}")
print(f"✅ Concise narration length: {GW_REVIEW_NARRATION_WORDS} words")
print("✅ Review Ryan profile: +0% rate / +0Hz pitch / +0% volume")
print(f"✅ Rank direction: {rank_dir.upper()}")
print("✅ Saved:",OUT)

