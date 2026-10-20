"""Creator narration from official review facts and published ownership data."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
import math
import re
from typing import Any


ELITE_CUES = (
    "Your elite ownership snapshot",
    "Start with the most owned players",
    "Now your captaincy comparison",
    "Chip use in Gameweek",
    "What this means for your next deadline",
)


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _integer(value: Any) -> int | None:
    number = _number(value)
    return int(number) if number is not None and number.is_integer() else None


def _count(value: int, singular: str, plural: str | None = None) -> str:
    spoken = f"minus {abs(value)}" if value < 0 else str(value)
    return f"{spoken} {singular if abs(value) == 1 else plural or singular + 's'}"


def _join(values: Sequence[str]) -> str:
    return " and ".join(values) if len(values) < 3 else ", ".join(values[:-1]) + " and " + values[-1]


def _fixture_state(player: Mapping[str, Any], snapshot: Mapping[str, Any], gameweek: int) -> str:
    elements = {int(row["id"]): row for row in snapshot.get("bootstrap", {}).get("elements", [])}
    team = elements.get(int(player["id"]), {}).get("team")
    matches = [row for row in snapshot.get("fixtures", [])
               if _integer(row.get("event")) == gameweek and team in (row.get("team_h"), row.get("team_a"))]
    if not matches:
        if team is not None and snapshot.get("fixtures") and str(snapshot.get("status") or "").upper() == "FINAL":
            return "BLANK"
        return str(player.get("review_state") or "PENDING").upper()
    states = []
    for match in matches:
        final = (match.get("started") and (match.get("finished") or match.get("finished_provisional"))
                 and (_integer(match.get("minutes")) or 0) >= 90
                 and match.get("team_h_score") is not None and match.get("team_a_score") is not None)
        states.append("FINAL" if final else "LIVE" if match.get("started") else "PENDING")
    return "FINAL" if all(state == "FINAL" for state in states) else (
        "LIVE" if "LIVE" in states else "PARTIAL" if "FINAL" in states else "PENDING")


def _facts(player: Mapping[str, Any], stats: Mapping[str, Any]) -> list[str]:
    position = str(player.get("pos") or "")
    minutes = _integer(stats.get("minutes"))
    sheets = _integer(stats.get("clean_sheets"))
    fields = [("goals_scored", "goal"), ("assists", "assist")]
    facts = []
    for key, noun in fields:
        value = _integer(stats.get(key))
        if value is not None and value > 0:
            facts.append(_count(value, noun))
    if (position in {"GK", "DEF", "MID"} and sheets is not None and sheets > 0
            and minutes is not None and minutes >= 60 * sheets):
        facts.append(_count(sheets, "clean sheet"))
    for key, noun in (("penalties_saved", "penalty save"), ("saves", "save"),
                      ("bonus", "bonus point"), ("red_cards", "red card"),
                      ("yellow_cards", "yellow card")):
        value = _integer(stats.get(key))
        if value is not None and value > 0:
            facts.append(_count(value, noun))
    return facts


def _bench_totals(
    bench: Sequence[Mapping[str, Any]], stats: Mapping[int, Mapping[str, Any]],
) -> dict[str, Any]:
    unused, counted, clean_sheets = [], [], 0
    complete = True
    sheets_complete = True
    for player in bench:
        official = stats.get(int(player["id"]), {})
        points = _integer(official.get("total_points"))
        multiplier = _integer(player.get("multiplier"))
        if points is None or multiplier is None:
            complete = False
            if player.get("pos") in {"GK", "DEF", "MID"}:
                sheets_complete = False
            continue
        if multiplier > 0:
            counted.append(points * multiplier)
        else:
            unused.append(points)
            sheets, minutes = _integer(official.get("clean_sheets")), _integer(official.get("minutes"))
            if player.get("pos") in {"GK", "DEF", "MID"} and (sheets is None or minutes is None):
                sheets_complete = False
            if (player.get("pos") in {"GK", "DEF", "MID"} and sheets is not None and sheets > 0
                    and minutes is not None and minutes >= 60 * sheets):
                clean_sheets += sheets
    return {"complete": complete, "unused_points": sum(unused) if complete else None,
            "counted_points": sum(counted) if complete else None,
            "unused_clean_sheets": clean_sheets if sheets_complete else None,
            "unused_count": len(unused),
            "counted_count": len(counted)}


def _player_line(
    player: Mapping[str, Any], stats: Mapping[str, Any], *, index: int, bench: bool,
    state: str, chip_code: str, auto_ids: set[int],
) -> str:
    name = str(player["name"])
    points, minutes = _integer(stats.get("total_points")), _integer(stats.get("minutes"))
    if points is None or minutes is None:
        return f"For {name}, the official return needs an update."
    points_text = _count(points, "point")
    facts = _facts(player, stats)
    detail = ", with " + _join(facts[:3]) if facts else ""
    multiplier = _integer(player.get("multiplier")) or 0
    if state in {"PENDING", "LIVE", "PARTIAL"}:
        status = {"PENDING": "His fixture has not started.", "LIVE": "His match is still live.",
                  "PARTIAL": "He still has a fixture to play."}[state]
        return f"{name} has {points_text} so far{detail}. {status}"
    if state == "BLANK":
        return f"{name} had no fixture in this Gameweek."
    if minutes == 0:
        return f"{name} did not play. His return stayed at {points_text}."
    if bench or int(player["id"]) in auto_ids:
        if chip_code == "bboost":
            return f"{name} added {points_text} through your Bench Boost{detail}."
        if multiplier > 0:
            return f"{name} came in for you with {points_text}{detail}."
        return (f"{name} scored {points_text} on your bench{detail}." if index % 2 == 0 else
                f"You left {points_text} from {name} unused{detail}.")
    if facts:
        leads = (
            f"{name} finished on {points_text}{detail}.",
            f"{name} gave you {points_text}{detail}.",
            f"You got {points_text} from {name}{detail}.",
        )
        return leads[index % len(leads)]
    if points <= 2:
        return f"{name} played {_count(minutes, 'minute')} but finished on {points_text}."
    return (f"{name} contributed {points_text}." if index % 2 else
            f"For {name}, the return came to {points_text}.")


def _transfer_line(
    transfers: Sequence[Mapping[str, Any]], elements: Mapping[int, Mapping[str, Any]],
    stats: Mapping[int, Mapping[str, Any]], count: int, cost: int, chip: str, partial: bool,
) -> str:
    if chip == "freehit":
        return "Your Free Hit covered this week. Your previous squad returns for the next Gameweek."
    if chip == "wildcard":
        return "You used your Wildcard. Judge the rebuild across the fixtures ahead."
    if count == 0:
        return "You made no transfers this week."
    if len(transfers) != count:
        return f"You made {_count(count, 'transfer')}. The detailed return comparison needs an official update."
    changes = Counter()
    for transfer in transfers:
        incoming, outgoing = _integer(transfer.get("element_in")), _integer(transfer.get("element_out"))
        if incoming is None or outgoing is None:
            return "Your transfer return comparison needs an official update."
        changes[incoming] += 1
        changes[outgoing] -= 1
    incoming = [player_id for player_id, change in changes.items() if change > 0]
    outgoing = [player_id for player_id, change in changes.items() if change < 0]
    if any(_integer(stats.get(player_id, {}).get("total_points")) is None
           for player_id in incoming + outgoing):
        return "Your transfer points comparison needs the complete official player returns."
    gained = sum(int(stats[player_id]["total_points"]) for player_id in incoming)
    removed = sum(int(stats[player_id]["total_points"]) for player_id in outgoing)
    net = gained - removed - cost
    timing = "so far" if partial else "this week"
    line = (f"Your arrivals scored {gained} points and the departures {removed} {timing}. "
            f"The player-points difference after your hit is {_count(net, 'point')}.")
    return line + " Captaincy and bench roles can change the team impact."


def creator_review_segments(
    segments: Sequence[Mapping[str, Any]], players: Sequence[Mapping[str, Any]],
    snapshot: Mapping[str, Any], *, gameweek: int, current_history: Mapping[str, Any],
    previous_rank: int | None, transfer_rows: Sequence[Mapping[str, Any]], transfer_count: int,
    transfer_cost: int, chip_code: str, next_gameweek: int, elite_selected: bool,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Rewrite text while retaining every segment ID and player-card window."""
    if not players or len({int(player["id"]) for player in players}) != len(players):
        raise ValueError("Creator review requires distinct official squad players")
    stats = {int(row["id"]): row.get("stats") or {}
             for row in snapshot.get("live", {}).get("elements", [])}
    elements = {int(row["id"]): row for row in snapshot.get("bootstrap", {}).get("elements", [])}
    partial = str(snapshot.get("status") or "FINAL").upper() == "LIVE/PARTIAL"
    auto_ids = {int(row["element_in"]) for row in snapshot.get("picks", {}).get("automatic_subs", [])
                if row.get("element_in") is not None}
    bench = [player for player in players if player.get("bench") or int(player["id"]) in auto_ids]
    starters = [player for player in players if not player.get("bench")]
    bench_audit = _bench_totals(bench, stats)
    points = _integer(current_history.get("points"))
    overall_rank = _integer(current_history.get("overall_rank"))
    gw_rank = _integer(current_history.get("rank"))
    score = _count(points, "point") if points is not None else "an official score still updating"
    headline = (f"Your FPL Gameweek {gameweek} review: {score} so far. The totals can still change."
                if partial else f"Your FPL Gameweek {gameweek} review: {score}.")
    counted_captains = [player for player in players if (_integer(player.get("multiplier")) or 0) >= 2]
    captain = max(counted_captains, key=lambda player: int(player["multiplier"]), default=None)
    original_captain = next((player for player in players if player.get("captain")), None)
    vice = next((player for player in players if player.get("vice")), None)
    captain_points = None
    extra = 0
    if captain is not None:
        raw = _integer(stats.get(int(captain["id"]), {}).get("total_points"))
        factor = int(captain["multiplier"])
        if raw is not None:
            captain_points = raw * factor
            extra = raw * (factor - 1)
            prefix = "Your vice took over" if original_captain and int(captain["id"]) != int(original_captain["id"]) else "Your captain"
            captain_text = f"{prefix}, {captain['name']}, turned {_count(raw, 'point')} into {captain_points}."
            if partial:
                captain_text += " That total is provisional."
        else:
            captain_text = f"For {captain['name']}, the captaincy return needs an official update."
    else:
        captain_name = str(original_captain["name"]) if original_captain else "Your selected captain"
        captain_text = (f"{captain_name} has no settled captaincy bonus yet." if partial else
                        f"{captain_name} provided no counted captaincy multiplier.")
    if vice is not None and captain is not None and int(vice["id"]) != int(captain["id"]):
        vice_points = _integer(stats.get(int(vice["id"]), {}).get("total_points"))
        vice_text = (f"{vice['name']} scored {_count(vice_points, 'point')} as your vice. "
                     "That does not change the armband once your captain plays."
                     if vice_points is not None else f"For {vice['name']}, the vice-captain return needs an update.")
    elif vice is not None and captain is not None:
        vice_text = f"{vice['name']} supplied the captaincy cover you selected."
    elif vice is not None:
        vice_text = (f"{vice['name']} has no settled vice-captain bonus yet." if partial else
                     f"{vice['name']} supplied no counted captaincy bonus.")
    else:
        vice_text = "Your vice-captain comparison has no settled return yet."

    states = {int(player["id"]): _fixture_state(player, snapshot, gameweek) for player in players}
    final_starters = [player for player in starters if states[int(player["id"])] == "FINAL"]
    quiet = sum(1 for player in final_starters
                if _integer(stats.get(int(player["id"]), {}).get("total_points")) in (0, 1, 2))
    process = (f"{quiet} of your starters finished on two points or fewer." if quiet else
               "Your player returns show how the squad score came together.")
    unused = bench_audit["unused_points"]
    counted = bench_audit["counted_points"]
    if not bench_audit["complete"]:
        bench_verdict = "Your bench total needs a complete official update."
    elif chip_code == "bboost":
        bench_verdict = f"Your Bench Boost counted {_count(int(counted), 'point')} from the bench."
    elif partial:
        bench_verdict = (f"Your bench has {_count(int(unused), 'point')} outside the current score. "
                         "Automatic substitutions can still change that.")
    else:
        bench_verdict = (f"Your bench left {_count(int(unused), 'point')} unused. "
                         + (f"Automatic substitutions brought in {_count(int(counted), 'point')}."
                            if bench_audit["counted_count"] else
                            "Those are bench returns, not a guaranteed gain from a different lineup."))
    sheets = bench_audit["unused_clean_sheets"]
    bench_metric = (f"That unused bench included {_count(sheets, 'clean sheet')}."
                    if sheets else "No credited clean sheet stayed on your unused bench.")
    if partial and sheets is not None:
        bench_metric = f"Your unused bench has {_count(sheets, 'clean sheet')} recorded so far."
    if chip_code == "bboost":
        bench_metric = "Your bench returns counted through the chip, not automatic substitutions."
    if not bench_audit["complete"] or sheets is None:
        bench_metric = "Your bench clean-sheet count needs complete official returns."
    if partial:
        rank_text = f"Your provisional overall rank is {overall_rank:,}." if overall_rank else "Your overall rank is still updating."
    elif overall_rank and previous_rank:
        change = int(previous_rank) - overall_rank
        rank_text = (f"Your overall rank rose {_count(change, 'place')} to {overall_rank:,}." if change > 0 else
                     f"Your overall rank fell {_count(-change, 'place')} to {overall_rank:,}." if change < 0 else
                     f"Your overall rank stayed at {overall_rank:,}.")
    else:
        rank_text = f"Your overall rank is {overall_rank:,}." if overall_rank else "Your overall rank is still updating."
    average = next((_number(event.get("average_entry_score"))
                    for event in snapshot.get("bootstrap", {}).get("events", [])
                    if _integer(event.get("id")) == gameweek), None)
    if average is not None and points is not None:
        difference = points - average
        metric_points = (f"You are {abs(difference):g} points {'above' if difference > 0 else 'below'} "
                         f"the {'current ' if partial else ''}Gameweek average."
                         if difference else "Your score matches the Gameweek average.")
    else:
        metric_points = "Your score follows the official entry return, with captaincy and counted substitutes."
    hit_text = "You took no transfer hit." if transfer_cost == 0 else f"Your transfer hit cost {_count(transfer_cost, 'point')}."
    ownership_text = "Ownership alone does not tell you which decision worked."
    counted_players = [player for player in players if (_integer(player.get("multiplier")) or 0) > 0]
    known_owned = [(player, _number(player.get("ownership"))) for player in counted_players]
    known_owned = [(player, ownership) for player, ownership in known_owned
                   if ownership is not None and 0 <= ownership <= 100
                   and (_integer(stats.get(int(player["id"]), {}).get("total_points")) or 0) > 2]
    if known_owned:
        player, ownership = min(known_owned, key=lambda pair: (pair[1], -int(stats[int(pair[0]["id"])]["total_points"])))
        ownership_text = (f"{player['name']} scored {stats[int(player['id'])]['total_points']} points "
                          f"at {ownership:g} percent current overall ownership. "
                          "That is not ownership measured at the deadline.")
    texts = {
        "headline": headline, "captaincy_intro": "First, your captaincy return.",
        "captain_summary": captain_text, "vice_summary": vice_text,
        "starting_xi_intro": "Here is how your starting eleven scored.", "process_lesson": process,
        "bench_intro": f"Now your {_count(len(bench), 'substitute')}.",
        "bench_verdict": bench_verdict,
        "transfer_review": _transfer_line(transfer_rows, elements, stats, transfer_count, transfer_cost, chip_code, partial),
        "ownership_review": ownership_text, "metrics_intro": "Your week in numbers.",
        "metric_points": metric_points, "metric_orank": rank_text,
        "metric_gwrank": (f"Your {'provisional ' if partial else ''}Gameweek rank is {gw_rank:,}."
                          if gw_rank else "Your Gameweek rank is still updating."),
        "metric_captain": ("Your captaincy bonus can still change." if partial and captain is None else
                           f"The captaincy multiplier added {_count(extra, 'extra point')}."
                           if extra >= 0 else f"The captaincy multiplier cost {_count(-extra, 'extra point')}."),
        "metric_bench": bench_metric, "metric_hit": hit_text,
        "review_close": ("For your next FPL deadline, check minutes and fixtures before changing your bench order. "
                         + ("Next, your elite ownership snapshot." if elite_selected else
                            f"Next, your Gameweek {next_gameweek} plan.")),
    }
    if chip_code == "bboost":
        texts["chip_emphasis"] = "Judge your Bench Boost against the fixtures and minutes you expected before the deadline."
    elif chip_code == "3xc":
        texts["chip_emphasis"] = (f"Your Triple Captain added {_count(extra, 'point')} above the player's normal score."
                                  if captain is not None else "Your Triple Captain had no settled multiplier return.")
    elif chip_code == "freehit":
        texts["chip_emphasis"] = "Assess your Free Hit as a one-week squad decision."
    by_id = {int(player["id"]): player for player in players}
    rewritten = []
    for index, segment in enumerate(segments):
        updated = dict(segment)
        player_id = _integer(segment.get("player_id"))
        if player_id is not None:
            player = by_id[player_id]
            updated["text"] = _player_line(
                player, stats.get(player_id, {}), index=index, bench=bool(player.get("bench")),
                state=states[player_id], chip_code=chip_code, auto_ids=auto_ids)
        elif segment["id"] in texts:
            updated["text"] = texts[segment["id"]]
        else:
            raise RuntimeError(f"Unknown creator-review segment: {segment['id']}")
        rewritten.append(updated)
    return rewritten, {"version": "CREATOR_REVIEW_V1", "bench": bench_audit,
                       "player_states": {str(key): value for key, value in states.items()},
                       "captain_counted_points": captain_points, "captain_extra_points": extra}


def creator_elite_narration(
    namespace: Mapping[str, Any], spoken_player: Callable[[int], str],
) -> str:
    starters = list(namespace.get("ELITE1000_TEMPLATE_STARTERS") or [])
    team = list(namespace.get("ELITE1000_TEMPLATE_TEAM") or [])
    bench = list(namespace.get("ELITE1000_TEMPLATE_BENCH") or [])
    captains = list(namespace.get("ELITE1000_CAPTAINS") or [])
    chips = namespace.get("ELITE1000_CHIP_USAGE") or {}
    if len(team) != 15 or len(starters) != 11 or len(bench) != 4 or len(captains) != 7:
        raise RuntimeError("Elite creator narration needs the displayed template and captain records")

    def rate(value: Any) -> str:
        number = _number(value)
        return f"{number:g} percent" if number is not None and 0 <= number <= 100 else "an unavailable rate"

    def chip(scope: str, key: str, population: str = "top10k") -> Any:
        return chips.get(scope, {}).get(population, {}).get("metrics", {}).get(key, {}).get("pct")

    leaders = sorted(starters, key=lambda row: -(_number(row.get("ownership")) or 0))[:3]
    ranked_captains = sorted(captains, key=lambda row: -(_number(row.get("captaincy")) or 0))[:3]
    sample = str(namespace.get("ELITE1000_SAMPLE_LABEL") or "").strip()
    sample_text = f" It covers {sample} sampled managers." if re.fullmatch(r"\d[\d, ]*", sample) else ""
    source_gw = _integer(namespace.get("ELITE1000_SOURCE_GW"))
    gameweek_text = f" for Gameweek {source_gw}" if source_gw is not None else ""
    lines = [f"{ELITE_CUES[0]}: FPL top ten thousand{gameweek_text}.{sample_text}"]
    lines.append(f"{ELITE_CUES[1]}. " + " ".join(
        f"{spoken_player(int(row['player_id']))} has {rate(row.get('ownership'))} ownership."
        for row in leaders))
    lines.append(f"{ELITE_CUES[2]}. " + " ".join(
        f"{spoken_player(int(row['player_id']))} takes {rate(row.get('captaincy'))} of captain selections."
        for row in ranked_captains))
    chip_gw = _integer(chips.get("gameweek"))
    lines.append(
        f"{ELITE_CUES[3]} {chip_gw if chip_gw is not None else 'still updating'}: "
        f"{rate(chip('gw', 'total'))} in the top ten thousand sample, "
        f"against {rate(chip('gw', 'total', 'overall'))} overall.")
    used = [f"{name} {rate(chip('total', key))}" for key, name in (
        ("wildcard", "Wildcard"), ("freehit", "Free Hit"),
        ("triple_captain", "Triple Captain"), ("bench_boost", "Bench Boost"))]
    lines.append("Season chip use in this sample: " + _join(used) + ".")
    lines.append(
        f"{ELITE_CUES[4]}: compare your captain with the leading choices. "
        "Check the chips you still have before following the sample. "
        "Ownership shows how common a pick is; your minutes and fixtures still drive the decision.")
    return "\n\n".join(lines)


def _once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise RuntimeError(f"Creator narration notebook contract changed: {old[:85]!r}")
    return source.replace(old, new, 1)


def patch_creator_narration_source(cell_index: int, source: str) -> str:
    if cell_index == 29:
        source = "from day3.creator_narration import creator_review_segments\n" + source
        marker = "    # Full-review QA: preserve the exact one-segment-per-player animation contract."
        source = _once(source, marker, '''    segments, REVIEW_CREATOR_AUDIT = creator_review_segments(
        segments, review_players, GW_REVIEW, gameweek=int(REVIEW_GW),
        current_history=current_hist, previous_rank=prev_rank,
        transfer_rows=_review_transfer_rows, transfer_count=transfer_count,
        transfer_cost=transfer_cost, chip_code=review_chip_code,
        next_gameweek=_next_review_gw,
        elite_selected=bool(globals().get("SLIDE_SELECTION", {}).get("05_elite_1000_trends", False)),
    )

''' + marker)
        source = _once(source, '"narration_style":"club_results_continuous_timing_fix5",',
                       '"narration_style":"creator_review_v1",\n        "narration_audit":REVIEW_CREATOR_AUDIT,')
    elif cell_index == 32:
        start = source.index("    def _d3_elite1000_narration():")
        end = source.index("\n    def ", start + 10)
        source = source[:start] + '''    def _d3_elite1000_narration():
        return creator_elite_narration(globals(), vx_narration_player)
''' + source[end:]
        source = "from day3.creator_narration import creator_elite_narration\n" + source
        old_cues = (
            "Elite Ownership Trends reveal where rank pressure is concentrated",
            "The strongest ownership anchors in the Top ten thousand template",
            "Captaincy is even more concentrated", "Chip use in Gameweek",
            "The takeaway: ownership measures your exposure",
        )
        for old, new in zip(old_cues, ELITE_CUES):
            if old != new:
                source = _once(source, '"' + old + '"', '"' + new + '"')
        excluded = '"03_defcon", "05_transfer_decision_desk", "06_benching_dilemma", "04_final_shortlists"'
        if source.count(excluded) != 4:
            raise RuntimeError("Creator elite narration needs four full-word speech contracts")
        source = source.replace(excluded, excluded + ', "05_elite_1000_trends"')
    return source
