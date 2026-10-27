from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from day3.live_evidence import DC_THRESHOLDS, number, player_projection, team_context


def forecast_text(value: Any) -> str:
    try:
        return f"{number(value, 'forecast'):.1f}"
    except ValueError:
        return "—"


def fixture_phrase(snapshot: dict[str, Any], team_id: int) -> str:
    fixtures = [row for row in snapshot["fixtures"] if row.get("event") == snapshot["next_gw"]
                and team_id in (row["team_h"], row["team_a"]) and not row.get("finished")]
    phrases = []
    for row in sorted(fixtures, key=lambda row: str(row.get("kickoff_time") or "")):
        home = row["team_h"] == team_id
        opponent = snapshot["teams"][int(row["team_a"] if home else row["team_h"])]["name"]
        phrases.append(("at home to " if home else "away to ") + opponent)
    return " and ".join(phrases) if phrases else "with no fixture currently assigned to this Gameweek"


def next_fixture_packs(snapshot: dict[str, Any], model_fdr: Any, team_id: int, position: str,
                       limit: int = 5) -> list[dict[str, Any]]:
    rows = model_fdr.to_dict(orient="records")
    by_fixture = {int(row["fixture_id"]): row for row in rows}
    if len(rows) != len(by_fixture):
        raise RuntimeError("Duplicate fixture FDR identity")
    output = []
    for gameweek in sorted(event for event in snapshot["event_ids"] if event >= snapshot["next_gw"]):
        fixtures = sorted([row for row in snapshot["fixtures"] if row.get("event") == gameweek
                           and team_id in (row["team_h"], row["team_a"]) and not row.get("finished")],
                          key=lambda row: str(row.get("kickoff_time") or ""))
        if not fixtures:
            output.append({"gw": gameweek, "fixture_id": None, "fixture": "BLANK", "score_text": "—", "fdr_value": None, "band": "none"})
        for fixture in fixtures:
            home = fixture["team_h"] == team_id
            opponent_id = int(fixture["team_a"] if home else fixture["team_h"])
            opponent = snapshot["teams"][opponent_id]["name"]
            key = ("defence" if position in {"GK", "DEF"} else "attack") + ("_fdr_home" if home else "_fdr_away")
            value = by_fixture.get(int(fixture["id"]), {}).get(key)
            if value is not None:
                value = number(value, "fixture FDR")
                if not 1 <= value <= 5:
                    raise RuntimeError("Fixture FDR is outside its model scale")
            output.append({"gw": gameweek, "fixture_id": int(fixture["id"]),
                           "fixture": opponent + (" (H)" if home else " (A)"),
                           "score_text": f"{value:.1f}" if value is not None else "—",
                           "fdr_value": value, "band": "none"})
        if len(output) >= limit:
            break
    return output[:limit]


def player_analysis(snapshot: dict[str, Any], player_id: int, rank: int,
                    displayed: dict[str, Any] | None = None) -> tuple[str, str]:
    player = snapshot["players"][int(player_id)]
    projection = player_projection(snapshot, player_id)
    if displayed is not None:
        try:
            displayed_actions = number(displayed.get("xdefcon"), "displayed DC forecast")
        except ValueError:
            displayed_actions = None
        projection["actions"] = displayed_actions
        projection["reason"] = str(displayed.get("projection_status") or projection["reason"])
    name = player["name"]
    cue = (f"The historical player leader is {name}" if rank == 1 else f"Next comes {name}")
    rate = player["rate90"]
    parts = [f"{cue}: {player['actions']:.0f} defensive actions across {player['appearances']} appearances "
             f"work out at {rate:.1f} per ninety, with {player['last_dc']:.0f} in the latest completed Gameweek."]
    reason = projection["reason"]
    if reason == "BLANK_GAMEWEEK":
        parts.append(f"{name} has no fixture assigned to his club in the next Gameweek. "
                     f"That explains {name}'s zero; it is not an injury diagnosis. "
                     f"Plan cover if you already own {name}.")
    elif reason in {"SUSPENDED", "INJURED", "UNAVAILABLE"}:
        status = {"SUSPENDED": "suspended", "INJURED": "injured", "UNAVAILABLE": "unavailable"}[reason]
        news = player["news"].strip().rstrip(".")
        parts.append(f"The official FPL snapshot lists {name} as {status}" + (f": {news}." if news else "."))
        if projection["expected_minutes"] == 0:
            parts.append(f"{name}'s next-round availability is zero in that snapshot, so the estimate gives "
                         f"{name} no playing time. Avoid a new transfer in until an official update clears {name}.")
        else:
            parts.append(f"The latest availability estimate still gives {name} a {100 * player['availability']:.0f} percent playing chance. "
                         f"That is uncertainty for {name}, not a confirmed absence for every fixture; "
                         f"wait for a clearer update before buying.")
    elif projection["actions"] is None:
        parts.append(f"{name}'s next fixture is {fixture_phrase(snapshot, player['team_id'])}, but the forecast "
                     f"is unavailable because {reason.lower().replace('_', ' ')}. I cannot support a buy or "
                     f"sell call for {name} from a missing estimate.")
    else:
        parts.append(f"{name}'s next schedule is {fixture_phrase(snapshot, player['team_id'])}.")
        if reason == "NO_RECENT_APPEARANCES":
            parts.append(f"{name} has not appeared in the last {len(player['recent_minutes'])} completed club fixtures. "
                         f"That drives {name}'s minutes estimate to zero; the data does not establish an injury "
                         f"or a tactical reason. Monitor {name}'s next team sheet before buying.")
        else:
            parts.append(f"Using {name}'s recent official minutes, the estimate is {projection['expected_minutes']:.0f} minutes "
                         f"and {projection['actions']:.1f} actions across {len(projection['fixtures'])} fixture" + ("s." if len(projection['fixtures']) > 1 else "."))
            threshold = DC_THRESHOLDS[player["position"]]
            hit_rate = player["hits"] / player["appearances"]
            parts.append(f"{name} has reached the points threshold in {player['hits']} of {player['appearances']} appearances; "
                         f"his positional target is {threshold} actions in each match, worth a maximum of two points per fixture.")
            if len(projection["fixtures"]) > 1:
                parts.append(f"{name}'s fixtures are scored separately; two sub-threshold games do not combine "
                             "into a defensive-contribution award.")
            if len(player["recent_minutes"]) < 3:
                parts.append(f"At {player['price']:.1f} million, this is a monitoring option: only {len(player['recent_minutes'])} current-club games support the minutes estimate.")
            elif player["recent_minutes"][-1] < 60:
                parts.append(f"{name}'s latest appearance was {player['recent_minutes'][-1]:.0f} minutes, below the "
                             f"clean-sheet minutes threshold. Check {name}'s starting place before spending a "
                             f"transfer; the recorded data does not tell us why {name}'s minutes fell.")
            elif hit_rate >= 0.5:
                parts.append(f"At {player['price']:.1f} million, {name}'s contribution points have arrived in at least half his appearances, supporting a place on a value shortlist for this scoring route rather than a prediction of attacking returns.")
            else:
                parts.append(f"At {player['price']:.1f} million, {name}'s season action total has produced points in fewer than half his appearances; compare attacking upside and total projected points before using a transfer on him.")
    if player["transferred"]:
        parts.append(f"{name}'s season total includes his previous club; the playing-time estimate uses only "
                     f"evidence from {name}'s current club.")
    return cue, " ".join(parts)


def team_analysis(snapshot: dict[str, Any], team_id: int, rank: int, tier: str,
                  clean_sheet: float | None = None) -> tuple[str, str]:
    team = team_context(snapshot, int(team_id))
    cue = (
        f"The defensive workload for {team['name']}",
        f"Next on the workload board, {team['name']}",
        f"Moving to {team['name']}",
        f"{team['name']}'s defensive-action record",
    )[(rank - 1) % 4]
    matches = team["matches"]
    if not matches:
        return cue, f"{cue}. There are no completed current-season matches to judge; no defensive-strength recommendation is supported yet."
    per_match = team["actions"] / matches
    conceded_rate = team["conceded"] / matches
    clean_label = "clean sheet" if team['clean_sheets'] == 1 else "clean sheets"
    parts = [f"{cue}: ranked {rank}, with {per_match:.1f} actions per match. {team['name']} have conceded {team['conceded']:.0f} goals "
             f"and kept {team['clean_sheets']} {clean_label} in {matches} matches."]
    parts.append(f"{team['name']}'s next schedule is {fixture_phrase(snapshot, int(team_id))}.")
    if clean_sheet is not None:
        parts.append(f"The independent fixture model puts {team['name']}'s chance of at least one clean sheet at "
                     f"{100 * clean_sheet:.0f} percent.")
    if tier == "high":
        if conceded_rate > 1:
            parts.append(f"That is {conceded_rate:.1f} goals conceded per match for {team['name']} despite the busy defensive workload; individual action points may help, but this ranking does not establish a strong clean-sheet target.")
        else:
            parts.append(f"{team['name']}'s goals-conceded rate is {conceded_rate:.1f} per match; read that alongside the action volume rather than using either measure alone to choose a defender.")
    elif tier == "low":
        if team["clean_sheets"] / matches >= 0.4:
            parts.append(f"{team['name']}'s low action total comes alongside clean sheets in at least forty percent of matches, so low workload is not a reason by itself to avoid their defenders.")
        else:
            parts.append(f"{team['name']}'s lower workload means fewer observed actions, not a confirmed poor defence; judge individuals using minutes, price and other routes to points.")
    elif clean_sheet is not None:
        parts.append(f"For {team['name']}, the clean-sheet estimate and the {team['clean_sheets']}-in-{matches} record answer a different question from the action ranking.")
    else:
        parts.append(f"A verified next-fixture clean-sheet estimate for {team['name']} is unavailable, so their season record alone does not support a buy recommendation.")
    return cue, " ".join(parts)


def defcon_narration(namespace: dict[str, Any]) -> str:
    snapshot = namespace["DAY3_EVIDENCE"]
    top = namespace["DAY3_DEFCON_TARGETS"].to_dict(orient="records")
    teams = namespace["DAY3_DEFCON_TEAMS"].to_dict(orient="records")
    if len(top) != 5 or len(teams) != len(snapshot["teams"]):
        raise RuntimeError("DEFCON narration requires the live player cards and every current club")
    expected_order = sorted(snapshot["teams"], key=lambda team_id: (
        -team_context(snapshot, team_id)["actions"],
        -team_context(snapshot, team_id)["actions"] / max(1, team_context(snapshot, team_id)["matches"]),
        snapshot["teams"][team_id]["name"], team_id))
    if [int(row["team_id"]) for row in teams] != expected_order:
        raise RuntimeError("Graphic team ranks disagree with official current-season evidence")
    opening = "For the upcoming Gameweek, let's separate defensive workload from defensive quality."
    parts = [opening,
             "These are historical action leaders, not five automatic transfers. The forecasts are our independent estimates, not official FPL predictions."]
    individuals = []
    for rank, row in enumerate(top, 1):
        cue, text = player_analysis(snapshot, int(row["player_id"]), rank, row)
        individuals.append({"player_id": int(row["player_id"]), "anchor": cue})
        parts.append(text)
    team_intro = "Now let's examine every club on the defensive-workload board."
    parts += [team_intro, "An action total does not measure chances prevented. The recorded evidence does not provide a tactical explanation for every change, so I will distinguish measured outcomes from possible causes."]
    top_cues, bottom_cues = [], []
    bottom_intro = "Now to the clubs with the lowest recorded defensive workload."
    model = namespace.get("PROJECTED_GOALS_PAYLOAD", {}).get("teams", {})
    for rank, row in enumerate(teams, 1):
        if rank == len(teams) - 2:
            parts.append(bottom_intro)
        team_id = int(row["team_id"])
        model_row = model.get(team_id, model.get(str(team_id), {}))
        probability = model_row.get("clean_sheet_pct")
        if probability is not None:
            probability = number(probability, "clean-sheet percentage") / 100
            if probability > 1:
                raise RuntimeError("Clean-sheet probability exceeds one")
        cue, text = team_analysis(snapshot, team_id, rank,
                                  "high" if rank <= 5 else "low" if rank > len(teams) - 3 else "middle", probability)
        parts.append(text)
        if rank <= 5:
            top_cues.append({"team_id": team_id, "anchor": cue})
        elif rank > len(teams) - 3:
            bottom_cues.append({"team_id": team_id, "anchor": cue})
    parts.append("Use defensive actions to judge this particular points route. Check availability and minutes first, then compare price, attacking potential and total expected points. Next, we move to the transfer decision desk.")
    namespace["DEFCON_NARRATION_CUES"] = {
        "opening": opening.rstrip("."), "individual": individuals, "team_intro": team_intro.rstrip("."),
        "target_teams": top_cues, "avoid_intro": bottom_intro.rstrip("."), "avoid_teams": bottom_cues,
    }
    return "\n\n".join(parts)


def validated_fixture_forecasts(features: Any, forecast_rows: Any, snapshot: dict[str, Any]) -> Any:
    import pandas as pd
    frame = forecast_rows.copy()
    frame = frame.loc[pd.to_numeric(frame["gameweek"], errors="coerce").eq(snapshot["next_gw"])]
    if frame.duplicated(["player_id", "fixture_id"]).any():
        raise RuntimeError("Duplicate player-fixture forecasts cannot be silently discarded")
    results = []
    for _, row in features.iterrows():
        player_id = int(row["player_id"])
        player = snapshot["players"][player_id]
        if int(row["team_id"]) != player["team_id"] or str(row["position"]) != player["position"]:
            raise RuntimeError("Player identity or current position differs between model and official data")
        projection = player_projection(snapshot, player_id)
        expected_ids = {int(fixture["id"]) for fixture in projection["fixtures"]}
        rows = frame.loc[pd.to_numeric(frame["player_id"], errors="coerce").eq(player_id)]
        actual_ids = set(pd.to_numeric(rows["fixture_id"], errors="raise").astype(int))
        status = projection["reason"]
        if not expected_ids:
            if actual_ids:
                raise RuntimeError("Forecast contains a fixture in an official blank Gameweek")
            actions, points = 0.0, 0.0
        elif actual_ids != expected_ids or projection["actions"] is None:
            actions = points = None
            status = status if projection["actions"] is None else "MISSING_FIXTURE_FORECAST"
        else:
            actions = points = 0.0
            for _, fixture_row in rows.iterrows():
                minutes = number(fixture_row["expected_minutes"], "fixture expected minutes")
                action_value = number(fixture_row["defcon_expected_contributions"], "fixture DC estimate")
                points_value = number(fixture_row["defcon_points"], "fixture DC points")
                expected = number(player["rate90"], "official DC/90") * minutes / 90
                if points_value > 2 or minutes > 90 or not math.isclose(action_value, expected, abs_tol=1e-6):
                    raise RuntimeError(f"Player {player_id}: forecast arithmetic or points cap is wrong")
                if player["availability"] == 0 and minutes > 0:
                    raise RuntimeError("Unavailable player received positive next-round minutes")
                actions += action_value
                points += points_value
            if projection["actions"] > 0 and actions == 0:
                raise RuntimeError(f"Player {player_id}: unexplained zero contradicts live minutes and DC evidence")
        results.append({"player_id": player_id, "next_fixture_count": len(expected_ids),
                        "xdefcon": actions, "next_dc_points": points, "projection_status": status})
    return pd.DataFrame(results)


def write_script_manifest(namespace: dict[str, Any]) -> None:
    from day3.live_evidence import VERSION, digest
    scripts = dict(namespace.get("scripts") or {})
    if not scripts:
        raise RuntimeError("No regenerated narration to bind to the live snapshot")
    snapshot = namespace["DAY3_EVIDENCE"]
    payload = {"version": VERSION, "source_hash": snapshot["source_hash"], "cutoff": snapshot["cutoff"],
               "next_gw": snapshot["next_gw"], "scripts": scripts, "scripts_hash": digest(scripts)}
    folder = Path(namespace["DATA_DIR"])
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "day3_script_evidence.json").write_text(json.dumps(payload, indent=2, allow_nan=False), encoding="utf-8")
