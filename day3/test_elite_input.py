"""Paste-box regressions and opt-in checks against the actual Drive notebook."""

from __future__ import annotations

import ast
import asyncio
import copy
import os
from pathlib import Path
import re
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import pandas as pd

from day3.creator_narration import creator_elite_narration
from day3.elite_input import (
    INPUT_ENV, patch_elite_input_source, read_workflow_elite_input,
    validate_elite_input, validate_elite_payload,
)


def page_fixture(gw=8, shift=0):
    """Generated players/rates prove the parser has no player-specific defaults."""
    positions = [1] + [2]*4 + [3]*4 + [4]*2 + [1, 2, 3, 4]
    players = [dict(id=800+shift*100+i, team=1, element_type=pos,
                    web_name=f"Álpha{shift}{i}", first_name=f"Álpha{shift}{i}", second_name="")
               for i, pos in enumerate(positions)]
    team = [f"Player Kit {p['web_name']} BBB (H) {70-i+shift}%" for i, p in enumerate(players)]
    team.insert(11, "GKP1. DEF2. MID3. FWD")
    captains = [f"{p['web_name']}\n{35-i*4+shift}%" for i, p in enumerate(players[:7])]
    lines = [f"Top 10k Gameweek {gw} Sampled 4,321 Updated 1 hour ago Chips 1,234", *team,
             "Top 10k Captains", *captains, f"GW{gw} Chip Usage"]
    metrics = [("Wildcard", 10.5+shift), ("Freehit", 2), ("Triple Captain", 3),
               ("Benchboost", 4), ("Total", 19.5+shift), ("No Chip", 80.5-shift)]
    for scope in ("gw", "total"):
        if scope == "total":
            lines.append("Total Chip Usage")
        for population, count in (("Top 10k", 4321), ("Overall", 12345678)):
            lines.append(f"{population} - {count:,} teams")
            for label, pct in (metrics if scope == "gw" else metrics[:4]):
                lines.append(f"{label} {round(count*pct/100):,} - {pct:g}%")
    return "\n".join(lines), players


class EliteInputTests(unittest.TestCase):
    def test_blank_and_whitespace_mean_auto_not_saved_notebook_sample(self):
        for value in ("", " \r\n\t"):
            with patch.dict(os.environ, {INPUT_ENV: value}):
                source = patch_elite_input_source(1, 'TOP10K_PAGE_TEXT = "old saved sample"\n')
                namespace = {}
                exec(source, namespace)
                self.assertEqual(namespace["TOP10K_PAGE_TEXT"], "")
                self.assertFalse(namespace["DAY3_ELITE_MANUAL_INPUT"])

    def test_paste_is_data_and_line_endings_are_supported(self):
        text, _ = page_fixture()
        text += '\n"; raise RuntimeError("must not execute"); # $(exit 99)'
        with patch.dict(os.environ, {INPUT_ENV: text.replace("\n", "\r\n")}):
            source = patch_elite_input_source(1, 'TOP10K_PAGE_TEXT = "old sample"\n')
            self.assertNotIn(text, source)
            namespace = {}
            exec(source, namespace)
            self.assertEqual(namespace["TOP10K_PAGE_TEXT"], text)
            self.assertTrue(namespace["DAY3_ELITE_MANUAL_INPUT"])

    def test_current_or_latest_review_snapshot_allowed_but_stale_future_rejected(self):
        for gw in (7, 8):
            validate_elite_input(page_fixture(gw)[0], 8)
        for gw in (1, 6, 9):
            with self.subTest(gw=gw), self.assertRaisesRegex(ValueError, "stale/future"):
                validate_elite_input(page_fixture(gw)[0], 8)

    def test_rejects_partial_mixed_week_and_invalid_numbers(self):
        text, _ = page_fixture()
        for invalid in (
            "Gameweek 8 Sampled 100", text.replace("GW8 Chip", "GW9 Chip"),
            text.replace("Sampled 4,321", "Sampled 0"),
            text.replace("Sampled 4,321", "Sampled 14,321"),
            text.replace("BBB (H) 70%", "BBB (H) 101%"),
            text.replace("Álpha00\n35%", "Álpha00\n135%"),
            text.replace("No Chip", "Missing metric", 1),
            text.replace("Overall - 12,345,678 teams", "Wrong cohort", 1),
            text.replace("Total Chip Usage", "Missing panel"),
        ):
            with self.subTest(invalid=invalid[:80]), self.assertRaises(ValueError):
                validate_elite_input(invalid, 8)

    def test_malformed_input_stops_notebook_preflight(self):
        with patch.dict(os.environ, {INPUT_ENV: "incomplete paste"}):
            with self.assertRaisesRegex(ValueError, "Copy the full"):
                patch_elite_input_source(1, 'TOP10K_PAGE_TEXT = "old sample"\n')

    def test_flattened_complete_page_is_valid(self):
        validate_elite_input(re.sub(r"\s+", " ", page_fixture()[0]), 8)

    def test_parsed_payload_rejects_mixed_week_and_invalid_rates(self):
        payload = dict(ELITE1000_TEMPLATE_TEAM=[dict(ownership=60)],
                       ELITE1000_CAPTAINS=[dict(captaincy=40)], ELITE1000_SOURCE_GW=8,
                       ELITE1000_CHIP_USAGE=dict(gameweek=8, **{
                           scope: {pop: dict(metrics=dict(wildcard=dict(pct=10)))
                                   for pop in ("top10k", "overall")}
                           for scope in ("gw", "total")}))
        validate_elite_payload(payload)
        for change in ("week", "ownership", "captaincy", "chip"):
            bad = copy.deepcopy(payload)
            if change == "week": bad["ELITE1000_CHIP_USAGE"]["gameweek"] = 7
            if change == "ownership": bad["ELITE1000_TEMPLATE_TEAM"][0]["ownership"] = 101
            if change == "captaincy": bad["ELITE1000_CAPTAINS"][0]["captaincy"] = float("nan")
            if change == "chip": bad["ELITE1000_CHIP_USAGE"]["gw"]["overall"]["metrics"]["wildcard"]["pct"] = -1
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_elite_payload(bad)


def check_notebook_elite_input(path: Path) -> None:
    """Run the real data parser and HTML/speech consumers; no render or upload."""
    from day3.run_notebook import _prepare_code_cells
    with patch.dict(os.environ, {INPUT_ENV: ""}):
        cells = dict(_prepare_code_cells(path))
    source = cells[26].split('# Visual helpers —', 1)[0]
    bridge = next(node for node in ast.parse(cells[19]).body
                  if isinstance(node, ast.FunctionDef) and node.name == "_vx_phase11_parse_top10k_page")
    tree = ast.parse(cells[26])
    html_functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                      and node.name in {"_e1k_team_player_html", "_e1k_chip_card"}]
    for shift in (0, 1):
        text, players = page_fixture(shift=shift)
        for flattened in (False, True):
            pasted = re.sub(r"\s+", " ", text) if flattened else text
            with patch.dict(os.environ, {INPUT_ENV: pasted}), tempfile.TemporaryDirectory() as directory:
                namespace = dict(re=re, pd=pd, NEXT_GW=9,
                    players=pd.DataFrame(players),
                    fixtures=pd.DataFrame([dict(event=8, team_h=1, team_a=2)]),
                    team_meta_by_id={1:dict(short="AAA", name="Club AAA"), 2:dict(short="BBB", name="Club BBB")},
                    scene_template=None, vortex_logo_html=None, youtube_icon=None, x_icon=None,
                    data_updated=None, vx_polish_branding=None, resolve_player_photo=None,
                    vx_team_jersey_data_uri=None, export_4k_png=None, HTML_WORK_DIR=directory,
                    SLIDE_DIR=directory, DATA_DIR=directory, SLIDE_SELECTION={},
                    TOP10K_PAGE_TEXT=read_workflow_elite_input(), TOP10K_PAGE_SOURCE="MANUAL_OVERRIDE",
                    TOP10K_PAGE_SOURCE_GW=8, DAY3_ELITE_MANUAL_INPUT=True)
                exec(compile(ast.Module(body=[bridge], type_ignores=[]), "actual-page-bridge", "exec"), namespace)
                asyncio.run(eval(compile(source, "actual-elite-parser", "exec",
                                         flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT), namespace))
                team = namespace["ELITE1000_TEMPLATE_TEAM"]
                assert len(team) == 15 and {p["player_id"] for p in team} == {p["id"] for p in players}
                assert team[0]["ownership"] == 70+shift
                assert namespace["ELITE1000_CAPTAINS"][0]["captaincy"] == 35+shift
                assert namespace["ELITE1000_CHIP_USAGE"]["gw"]["top10k"]["metrics"]["wildcard"]["pct"] == 10.5+shift
                assert namespace["ELITE1000_SOURCE_MODE"] == "MANUAL_OVERRIDE"
                assert namespace["ELITE1000_SAMPLE_LABEL"] == "4,321"
                names = {p["id"]:p["web_name"] for p in players}
                namespace["vx_narration_player"] = lambda pid: names[pid]
                speech = creator_elite_narration(namespace, namespace["vx_narration_player"])
                assert players[0]["web_name"] in speech and str(70+shift) in speech
                namespace.update(_e1k_badge=lambda *args: "", _e1k_player_media=lambda *args: "")
                exec(compile(ast.Module(body=html_functions, type_ignores=[]), "actual-elite-html", "exec"), namespace)
                html = namespace["_e1k_team_player_html"](team[0])
                assert players[0]["web_name"] in html and f'{70+shift}%' in html
                namespace["_e1k_chip_style"] = {"wildcard": ("Wildcard", "test")}
                chip_html = namespace["_e1k_chip_card"]("wildcard", "gw", "top10k")
                assert f'{10.5+shift:g}%' in chip_html
                assert f'{10.5+shift:g} percent' in speech

    # A stale explicit paste must fail before the live-fetch fallback can run.
    namespace["TOP10K_PAGE_TEXT"] = page_fixture(3)[0]
    try:
        asyncio.run(eval(compile(source, "stale-elite-parser", "exec",
                                 flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT), namespace))
    except ValueError as exc:
        assert "stale/future" in str(exc)
    else:
        raise AssertionError("A stale explicit paste was accepted/replaced")
    # With no paste, the existing automatic HTTP path still populates the slide.
    text, _ = page_fixture(shift=1)
    namespace.update(TOP10K_PAGE_TEXT="", TOP10K_PAGE_SOURCE="AUTO_FETCH",
                     DAY3_ELITE_MANUAL_INPUT=False)
    with patch("requests.get", return_value=SimpleNamespace(text=text, raise_for_status=lambda: None)) as fetch:
        asyncio.run(eval(compile(source, "auto-elite-parser", "exec",
                                 flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT), namespace))
        fetch.assert_called_once()
    assert namespace["ELITE1000_SOURCE_MODE"].startswith("AUTO_HTTP:")
    assert namespace["ELITE1000_TEMPLATE_TEAM"][0]["ownership"] == 71
    print("Actual notebook Elite paste checks passed: changing IDs/stats, multiline/flattened, shared slide/speech, stale rejection.")


if __name__ == "__main__":
    unittest.main()
