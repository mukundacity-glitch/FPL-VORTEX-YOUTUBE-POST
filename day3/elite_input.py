"""Read the optional Actions paste as data, sharing the notebook's live parser."""

from __future__ import annotations

import math
import os
import re
from collections.abc import Mapping


INPUT_ENV = "DAY3_ELITE_PAGE_TEXT"


def validate_elite_input(text: str, decision_gameweek: int | None = None) -> None:
    """Reject incomplete/mixed-week pastes rather than replacing them silently."""
    flat = re.sub(r"\s+", " ", text).strip()
    gw = re.search(r"\bGameweek\s+(\d+)\b", flat, re.I)
    sample = re.search(r"\bSampled\s+([\d,]+)\b", flat, re.I)
    chips = re.search(r"\bGW(\d+)\s+Chip\s+Usage\b", flat, re.I)
    if not gw or not sample or not chips:
        raise ValueError("Elite paste needs Gameweek, Sampled and GW chip usage headings. Copy the full fpl.team Top 10k page.")
    source_gw = int(gw[1])
    if not 1 <= source_gw <= 38 or int(chips[1]) != source_gw:
        raise ValueError("Elite paste has invalid or mixed Gameweek headings. Copy one complete page.")
    if not 1 <= int(sample[1].replace(",", "")) <= 10_000:
        raise ValueError("Elite paste has an invalid Top 10k sample size.")
    if decision_gameweek is not None and not max(1, int(decision_gameweek) - 1) <= source_gw <= int(decision_gameweek):
        raise ValueError(f"Elite paste GW{source_gw} is stale/future for decision GW{decision_gameweek}. Paste the current page.")
    template = re.split(r"\b(?:Ownership\s+100%|Top\s*10k\s+Captains)\b", flat, maxsplit=1, flags=re.I)[0]
    cards = re.findall(r"\b[A-Z]{2,4}\s+\([HA]\)\s*(\d+(?:\.\d+)?)%", template, re.I)
    captain = re.search(r"\bTop\s*10k\s+Captains\s+(.*?)\s+GW\d+\s+Chip\s+Usage", flat, re.I)
    cap_rates = re.findall(r"(\d+(?:\.\d+)?)%", captain[1]) if captain else []
    if len(cards) != 15 or len(cap_rates) != 7:
        raise ValueError("Elite paste needs all 15 template players and seven captain cards. Copy the full page.")
    for value in cards + cap_rates:
        _percentage(value)
    parts = re.split(r"\bTotal\s+Chip\s+Usage\b", flat[chips.end():], maxsplit=1, flags=re.I)
    if len(parts) != 2:
        raise ValueError("Elite paste is missing Total Chip Usage.")
    for index, part in enumerate(parts):
        populations = re.findall(r"(Top\s*10k|Overall)\s*-\s*([\d,]+)\s+teams\s+(.*?)(?=(?:Top\s*10k|Overall)\s*-|$)", part, re.I)
        if len(populations) != 2 or len({re.sub(r"\s+", "", p[0]).lower() for p in populations}) != 2:
            raise ValueError("Elite paste needs Top 10k and Overall teams in each chip panel.")
        required = {"wildcard", "freehit", "triplecaptain", "benchboost"}
        if index == 0:
            required |= {"total", "nochip"}
        for _, teams, body in populations:
            if int(teams.replace(",", "")) <= 0:
                raise ValueError("Elite paste chip panel has no sampled teams.")
            metrics = re.findall(r"(Wildcard|Freehit|Triple\s+Captain|Benchboost|Total|No\s+Chip)\s+([\d,]+)\s*-\s*(\d+(?:\.\d+)?)%", body, re.I)
            labels = [re.sub(r"\s+", "", label).lower() for label, _, _ in metrics]
            if not required.issubset(labels) or len(labels) != len(set(labels)):
                raise ValueError("Elite paste chip panel is incomplete or duplicated.")
            for _, _, pct in metrics:
                _percentage(pct)


def _percentage(value: object) -> None:
    number = float(value)
    if not math.isfinite(number) or not 0 <= number <= 100:
        raise ValueError("Elite data percentages must be between 0 and 100.")


def read_workflow_elite_input() -> str:
    text = os.environ.get(INPUT_ENV, "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if text:
        validate_elite_input(text)
    return text


def validate_elite_payload(namespace: Mapping) -> None:
    """Check parsed values before graphics and speech consume the same payload."""
    team = namespace["ELITE1000_TEMPLATE_TEAM"]
    captains = namespace["ELITE1000_CAPTAINS"]
    chips = namespace["ELITE1000_CHIP_USAGE"]
    if int(chips["gameweek"]) != int(namespace["ELITE1000_SOURCE_GW"]):
        raise ValueError("Elite ownership and chip data have different Gameweeks.")
    for row in team:
        _percentage(row["ownership"])
    for row in captains:
        _percentage(row["captaincy"])
    for scope in ("gw", "total"):
        for population in ("top10k", "overall"):
            for metric in chips[scope][population]["metrics"].values():
                _percentage(metric["pct"])


def _replace(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise RuntimeError("Elite workflow input: notebook source changed; expected one integration point.")
    return source.replace(old, new, 1)


def patch_elite_input_source(cell_index: int, source: str) -> str:
    if cell_index == 1:
        # Preflight runs before any notebook cells, network requests or rendering.
        read_workflow_elite_input()
        pattern = r"^TOP10K_PAGE_TEXT\s*=.*$"
        if len(re.findall(pattern, source, re.M)) != 1:
            raise RuntimeError("Elite workflow input: expected one Colab paste field.")
        return re.sub(pattern, lambda _: (
            "from day3.elite_input import read_workflow_elite_input\n"
            "TOP10K_PAGE_TEXT = read_workflow_elite_input()\n"
            "DAY3_ELITE_MANUAL_INPUT = bool(TOP10K_PAGE_TEXT)"
        ), source, flags=re.M)
    if cell_index == 19:
        return _replace(source,
            '_vx_top10k_manual = str(globals().get("TOP10K_PAGE_TEXT", "") or "").strip()',
            'from day3.elite_input import validate_elite_input\n'
            'if globals().get("DAY3_ELITE_MANUAL_INPUT", False):\n'
            '    validate_elite_input(TOP10K_PAGE_TEXT, int(NEXT_GW))\n'
            '_vx_top10k_manual = str(globals().get("TOP10K_PAGE_TEXT", "") or "").strip()')
    if cell_index != 26:
        return source
    source = _replace(source,
        '_e1k_source_mode = str(TOP10K_PAGE_SOURCE or "")',
        '_e1k_source_mode = str(TOP10K_PAGE_SOURCE or "")\n'
        'from day3.elite_input import validate_elite_input, validate_elite_payload\n'
        'if globals().get("DAY3_ELITE_MANUAL_INPUT", False):\n'
        '    validate_elite_input(_e1k_source_text, int(NEXT_GW))\n'
        '    if not _e1k_has_slide_sections(_e1k_source_text):\n'
        '        raise ValueError("Elite paste is incomplete. Copy the full fpl.team Top 10k page.")')
    source = _replace(source, "    return rows[:7]\n", '''    if len(rows) != 7 and flat_match:
        # GitHub's string field may flatten copied line breaks. Plain visible
        # NAME + percentage pairs also work without image alt text/badge labels.
        rows = [(_clean_top10k_template_name(name), pct, "")
                for name, pct in _e1k_re.findall(r"(.+?)\\s+(\\d+(?:\\.\\d+)?)%", flat_match.group(1))]
    return rows[:7]
''')
    # Keep fractional chip percentages instead of truncating the pasted values.
    source = _replace(source, r'(\d+)%",', r'(\d+(?:\.\d+)?)%",')
    source = _replace(source, '"pct": int(_pct),', '"pct": float(_pct),')
    source = _replace(source, '{int(metric["pct"])}%', '{float(metric["pct"]):g}%')
    source = _replace(source, 'ELITE1000_TRIGGER_PLAYERS =', 'validate_elite_payload(globals())\n\nELITE1000_TRIGGER_PLAYERS =')
    return source
