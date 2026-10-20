"""Evidence-led SELL watchlist explanations; market selection stays unchanged."""

from __future__ import annotations

from collections.abc import Collection, Mapping
import math
import re
from typing import Any

import pandas as pd


MAX_QUIET_RECENT_AVERAGE = 3.0
MIN_POSITION_SAMPLE = 4


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _projection(record: Mapping[str, Any], key: str, flag: str) -> float | None:
    return _number(record.get(key)) if record.get(flag) is True else None


def sell_projection_benchmarks(
    projections: pd.DataFrame, eligible_ids: Collection[int],
) -> dict[str, dict[str, Any]]:
    """Compare forecasts with eligible same-position peers, never fixed players."""
    required = {"player_id", "position", "xpts", "next_5_xpts"}
    if not required.issubset(projections.columns):
        return {}
    pool = projections.loc[projections.player_id.isin(eligible_ids)].drop_duplicates("player_id").copy()
    pool["position"] = pool.position.fillna("").astype(str).str.upper()
    result = {}
    for position, rows in pool.groupby("position"):
        if position not in {"GK", "DEF", "MID", "FWD"}:
            continue
        summary = {}
        for column in ("xpts", "next_5_xpts"):
            values = pd.to_numeric(rows[column], errors="coerce").dropna()
            values = values.loc[values.map(math.isfinite)]
            if len(values) >= MIN_POSITION_SAMPLE:
                summary[column] = {
                    "sample": int(len(values)), "lower_quartile": float(values.quantile(.25)),
                    "upper_quartile": float(values.quantile(.75)),
                }
        result[position] = summary
    return result


def analyse_sell(
    record: Mapping[str, Any], status: Mapping[str, Any],
    benchmarks: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    reasons, counterpoints, missing = [], [], []
    verified = status.get("verified") is True
    health_clear = verified and status.get("health_clear") is True
    blocked = verified and status.get("blocked") is True
    label = str(status.get("label") or "").upper()
    position = str(record.get("position") or "").upper()
    peer = (benchmarks or {}).get(position, {})

    def add(code: str, short: str, sentence: str, evidence: Mapping[str, Any]) -> None:
        reasons.append({"code": code, "short": short, "sentence": sentence,
                        "evidence": dict(evidence)})

    if not verified:
        missing.append("live_availability")
    elif blocked or label == "DOUBTFUL":
        code = {"INJURED": "INJURY", "SUSPENDED": "SUSPENSION"}.get(
            label, "DOUBTFUL" if label == "DOUBTFUL" else "UNAVAILABLE")
        sentence = {
            "INJURY": "His official injury flag is the first concern.",
            "SUSPENSION": "His official suspension is the first concern.",
            "DOUBTFUL": "His official availability is doubtful.",
            "UNAVAILABLE": "Official availability data marks him unavailable.",
        }[code]
        news = re.sub(r"\s+", " ", str(status.get("news") or "")).strip()
        if news:
            sentence += " " + news.rstrip(".!?") + "."
        add(code, label, sentence, {"status": status.get("status"),
                                   "news": news, "chance_percent": status.get("chance_percent")})
    elif not health_clear:
        missing.append("verified_fitness_clearance")

    has_fixture = status.get("has_fixture")
    if verified and has_fixture is False:
        add("BLANK_GAMEWEEK", "NO FIXTURE", "He has no fixture in the target Gameweek.",
            {"has_fixture": False})
    elif health_clear and has_fixture is True and status.get("starting_status") == "MINUTES RISK":
        start = _number(status.get("start_probability"))
        minutes = _number(status.get("expected_minutes"))
        details = []
        if start is not None and 0 <= start <= 1:
            details.append(f"a {100 * start:.0f} percent starting chance")
        if minutes is not None and minutes >= 0:
            details.append(f"{minutes:.0f} expected minutes")
        sentence = "His starting role is uncertain"
        sentence += ", with " + " and ".join(details) + "." if details else "."
        add("MINUTES_RISK", "MINUTES RISK", sentence,
            {"start_probability": start, "expected_minutes": minutes,
             "last_started": status.get("last_started"),
             "latest_role_date": status.get("latest_role_date")})
    elif verified and status.get("starting_status") not in {"PROJECTED STARTER", "MINUTES RISK"}:
        missing.append("starting_role")

    recent = record.get("recent_performance")
    recent = recent if isinstance(recent, Mapping) else {}
    points, games = _number(recent.get("points")), _number(recent.get("gameweeks"))
    form = _number(recent.get("form"))
    if points is not None and games is not None and games >= 1 and games.is_integer():
        average = points / games
        if average <= MAX_QUIET_RECENT_AVERAGE:
            add("RECENT_RETURNS", "QUIET RECENT RETURNS",
                f"Recent returns are quiet: {points:.0f} points across {int(games)} completed Gameweeks.",
                {"points": points, "gameweeks": int(games), "average_points": average,
                 "source": recent.get("source")})
    elif form is not None:
        if form <= MAX_QUIET_RECENT_AVERAGE:
            add("RECENT_FORM", "LOW RECENT FORM",
                f"Official recent form is low at {form:.1f}.",
                {"form": form, "source": recent.get("source")})
    else:
        missing.append("recent_returns")

    difficulty = _number(record.get("next_fdr"))
    fixture_class = str(record.get("next_fdr_class") or "")
    known_fixture = str(record.get("next_fixture") or "").strip().upper() not in {
        "", "TBD", "TBC", "FIXTURE TBD", "BLANK", "NO FIXTURE"}
    valid_fixture = (has_fixture is not False and known_fixture and difficulty is not None
                     and 0 <= difficulty <= 5)
    if valid_fixture and fixture_class in {"fdr-4", "fdr-5"}:
        add("DIFFICULT_FIXTURE", "DIFFICULT NEXT FIXTURE",
            f"The next fixture is difficult, rated {difficulty:.1f} by the fixture model.",
            {"fixture": record.get("next_fixture"), "difficulty": difficulty,
             "canonical_class": fixture_class})
    elif valid_fixture and fixture_class in {"fdr-1", "fdr-2"}:
        counterpoints.append({
            "code": "FAVOURABLE_FIXTURE",
            "sentence": f"The next fixture is favourable, rated {difficulty:.1f}.",
            "difficulty": difficulty,
        })
    elif not valid_fixture or fixture_class not in {"fdr-3"}:
        missing.append("fixture_difficulty")

    forecast = _projection(record, "xpts", "has_projection")
    horizon = _projection(record, "next_5_xpts", "has_horizon")
    strong_projection = False
    for column, value in (("xpts", forecast), ("next_5_xpts", horizon)):
        benchmark = peer.get(column, {})
        lower = _number(benchmark.get("lower_quartile"))
        upper = _number(benchmark.get("upper_quartile"))
        if value is None:
            missing.append(column)
            continue
        # An unavailable player's displayed forecast must not override the flag.
        if not health_clear or has_fixture is False:
            if column == "xpts" and value > 0:
                counterpoints.append({
                    "code": "CONDITIONAL_PROJECTION",
                    "sentence": f"The displayed {value:.1f} point projection needs current availability confirmation.",
                    "xpts": value,
                })
            continue
        if column == "xpts" and upper is not None and value >= upper and value > 0:
            strong_projection = True
            counterpoints.append({
                "code": "STRONG_PROJECTION",
                "sentence": f"His {value:.1f} point projection is still strong for his position; recent blanks do not make that forecast weak.",
                "xpts": value, "benchmark": dict(benchmark),
            })
        if lower is not None and value < lower:
            label_text = "next-Gameweek" if column == "xpts" else "five-Gameweek"
            add("LOW_NEXT_GW_OUTLOOK" if column == "xpts" else "LOW_FIVE_WEEK_OUTLOOK",
                "LOW PROJECTED RETURNS" if column == "xpts" else "WEAK FIVE-WEEK OUTLOOK",
                f"His {label_text} projection of {value:.1f} points is below the lower quartile for eligible players in his position.",
                {"value": value, "benchmark": dict(benchmark)})

    codes = {reason["code"] for reason in reasons}
    favourable = any(row["code"] == "FAVOURABLE_FIXTURE" for row in counterpoints)
    if blocked:
        assessment, advice = "AVAILABILITY_FIRST", "Weigh the expected absence against a fit replacement; require an official update before assuming he is back."
    elif codes & {"DOUBTFUL", "MINUTES_RISK", "BLANK_GAMEWEEK"}:
        assessment, advice = "CONDITIONAL_REVIEW", "Resolve that availability, minutes or fixture concern before deciding on a replacement."
    elif codes and codes.issubset({"RECENT_RETURNS", "RECENT_FORM"}) and (strong_projection or favourable):
        assessment, advice = "PATIENCE_CASE", "The outlook argues against a rushed sale after recent blanks."
    elif codes:
        assessment, advice = "REVIEW_SELL", "Those concerns support reviewing a move, provided the replacement improves your squad."
    else:
        assessment, advice = "MARKET_ONLY", "The available football evidence does not establish a sell recommendation."
    if not verified:
        advice = "Verify current team news before treating this market trend as a sell recommendation."

    return {
        "version": "SELL_EVIDENCE_V1", "selection_basis": "OFFICIAL_EVENT_TRANSFERS_OUT",
        "transfers_out": _number(record.get("transfers_out")),
        "net_transfers": _number(record.get("net_transfers")),
        "reasons": reasons, "counterpoints": counterpoints,
        "missing_evidence": list(dict.fromkeys(missing)),
        "xpts": forecast, "next_5_xpts": horizon,
        "assessment": assessment, "advice": advice,
    }


def sell_narration(
    record: Mapping[str, Any], identity: str, status: Mapping[str, Any],
    *, brief: bool = False, fixture_text: str | None = None,
) -> str:
    analysis = record.get("sell_analysis") or analyse_sell(record, status)
    sentences = [f"{identity} is on the sell watchlist."]
    reasons = analysis["reasons"]
    sentences.extend(row["sentence"] for row in reasons[:1 if brief else 2])
    counterpoints = sorted(
        analysis["counterpoints"],
        key=lambda row: {"CONDITIONAL_PROJECTION": 0, "STRONG_PROJECTION": 1}.get(row["code"], 2),
    )
    if counterpoints:
        sentences.append(counterpoints[0]["sentence"])
    elif analysis["xpts"] is not None and not brief and status.get("health_clear") is True:
        sentences.append(f"The next-Gameweek projection is {analysis['xpts']:.1f} points.")
    if fixture_text and not brief and status.get("has_fixture") is not False:
        sentences.append(f"Next up is {fixture_text}.")
    if not reasons:
        sentences.append("Transfer activity alone is not a reason to sell.")
    sentences.append(analysis["advice"])
    return " ".join(sentences)


def _once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise RuntimeError(f"SELL reasoning notebook contract changed: {old[:90]!r}")
    return source.replace(old, new, 1)


def patch_sell_reasoning_source(source: str) -> str:
    source = "from day3.sell_reasoning import analyse_sell, sell_narration, sell_projection_benchmarks\n" + source
    source = _once(source, "_index = 0\nfor _action, _rows in (",
        '_d3_sell_benchmarks = sell_projection_benchmarks(_d3_desk_model, DAY3_AVAILABILITY.eligible_ids())\n'
        '_index = 0\nfor _action, _rows in (')
    source = _once(source, '        _record = _d3_desk_record(_action, _row, _index)',
        '''        _record = _d3_desk_record(_action, _row, _index)
        if _action == "SELL":
            _record["sell_analysis"] = analyse_sell(
                _record, DAY3_AVAILABILITY.state(_record["player_id"]), _d3_sell_benchmarks,
            )''')
    source = _once(source, '    identity = f"{name} from {club}"\n    if index >= 3:',
        '    identity = f"{name} from {club}"\n    if index >= 3 and role != "SELL":')
    source = _once(source, '    points = float(record["xpts"])',
        '''    if role == "SELL":
        return sell_narration(record, identity, DAY3_AVAILABILITY.state(record["player_id"]),
                              brief=index >= 3, fixture_text=fixture)
    points = float(record["xpts"])''')
    source = _once(source, '"sell": "Largest event transfers out among negative net-transfer players",',
        '"sell": "Market-volume watchlist; explain verified availability, minutes, recent returns and canonical model FDR; weigh positional projection counter-evidence; no assumed replacement gains",')
    return source
