"""Narration facts, chip accounting and actual notebook name-cue regressions."""

from __future__ import annotations

import ast
import asyncio
import copy
import json
from pathlib import Path
import re
import tempfile
import unittest

from day3.creator_narration import (
    ELITE_CUES, creator_elite_narration, creator_review_segments, patch_creator_narration_source,
)
from day3.run_notebook import _prepare_code_cells


def review_fixture(chip: str = "", partial: bool = False, base_id: int = 100):
    positions = ["GK", "DEF", "DEF", "DEF", "MID", "MID", "MID", "MID",
                 "FWD", "FWD", "FWD", "GK", "DEF", "DEF", "MID"]
    players, elements, live, picks = [], [], [], []
    for index, position in enumerate(positions):
        player_id = base_id + index
        multiplier = 3 if index == 4 and chip == "3xc" else 2 if index == 4 else 1 if index < 11 or chip == "bboost" else 0
        points, minutes = (8, 90) if index == 4 else (6, 90) if index == 12 else (0, 0) if index == 13 else (2, 90)
        stats = dict(total_points=points, minutes=minutes, goals_scored=1 if index == 4 else 0,
                     assists=0, clean_sheets=1 if index == 12 else 0, saves=4 if index == 11 else 0,
                     bonus=1 if index == 4 else 0, yellow_cards=0, red_cards=0)
        element = dict(id=player_id, team=index // 3 + 1, web_name=f"Name{player_id}",
                       first_name=f"Name{player_id}", second_name="", now_cost=50, code=player_id + 9000,
                       element_type={"GK":1, "DEF":2, "MID":3, "FWD":4}[position],
                       selected_by_percent="12", total_points=20, form="2")
        player = dict(id=player_id, name=element["web_name"], team_name=f"Club {element['team']}",
                      team=f"C{element['team']}", pos=position, points=points, minutes=minutes,
                      bench=index >= 11, multiplier=multiplier, captain=index == 4, vice=index == 5,
                      squad_position=index + 1, ownership=12, review_state="FINAL")
        players.append(player)
        elements.append(element)
        live.append(dict(id=player_id, stats=stats))
        picks.append(dict(element=player_id, position=index + 1, multiplier=multiplier,
                          is_captain=index == 4, is_vice_captain=index == 5))
    fixtures = [dict(id=team, event=8, team_h=team, team_a=team + 5,
                     started=not partial, minutes=0 if partial else 90, finished=not partial,
                     finished_provisional=not partial,
                     team_h_score=None if partial else 0, team_a_score=None if partial else 0)
                for team in range(1, 6)]
    score = sum(row["stats"]["total_points"] * picks[index]["multiplier"] for index, row in enumerate(live))
    current = dict(points=score, overall_rank=12000, rank=300000, bank=10, value=1000,
                   event_transfers=0, event_transfers_cost=0)
    snapshot = dict(gw=8, status="LIVE/PARTIAL" if partial else "FINAL",
                    bootstrap=dict(elements=elements,
                                   teams=[dict(id=team, name=f"Club {team}", short_name=f"C{team}", code=team)
                                          for team in range(1, 11)],
                                   events=[dict(id=8, average_entry_score=40)]),
                    live=dict(elements=live),
                    picks=dict(picks=picks, active_chip=chip, automatic_subs=[], entry_history=current),
                    history=dict(current=[dict(event=7, overall_rank=11000)],
                                 chips=[dict(event=8, name=chip)] if chip else []),
                    fixtures=fixtures)
    ids = ["headline", "captaincy_intro", "captain_summary", "vice_summary", "starting_xi_intro"]
    segments = [dict(id=key, text="Previous wording.") for key in ids]
    segments[2].update(name=players[4]["name"], focus_player_id=players[4]["id"])
    segments[3].update(name=players[5]["name"], focus_player_id=players[5]["id"])
    for player in players[:11]:
        segments.append(dict(id=f"player_{player['id']}", player_id=player["id"], name=player["name"],
                             kind="starter", text="Previous player wording."))
    segments += [dict(id="process_lesson", text="Old process"), dict(id="bench_intro", text="Old bench")]
    for player in players[11:]:
        segments.append(dict(id=f"player_{player['id']}", player_id=player["id"], name=player["name"],
                             kind="bench", text="Previous bench wording."))
    segments += [dict(id=key, text="Old summary") for key in ("bench_verdict", "transfer_review", "ownership_review")]
    if chip in {"bboost", "3xc", "freehit"}:
        segments.append(dict(id="chip_emphasis", text="Old chip"))
    segments += [dict(id=key, text="Old metric") for key in (
        "metrics_intro", "metric_points", "metric_orank", "metric_gwrank", "metric_captain",
        "metric_bench", "metric_hit", "review_close")]
    return players, snapshot, current, segments


def compose(players, snapshot, current, segments, *, transfers=()):
    return creator_review_segments(
        segments, players, snapshot, gameweek=8, current_history=current, previous_rank=11000,
        transfer_rows=transfers, transfer_count=int(current["event_transfers"]),
        transfer_cost=int(current["event_transfers_cost"]),
        chip_code=snapshot["picks"]["active_chip"], next_gameweek=9, elite_selected=True)


def elite_fixture():
    team = [dict(player_id=400 + index, name=f"Name{400 + index}", ownership=70 - index)
            for index in range(15)]
    captains = [dict(player_id=400 + index, captaincy=50 - index * 5) for index in range(7)]
    metrics = {key: dict(pct=value) for key, value in (
        ("total", 15.3), ("wildcard", 30.2), ("freehit", 2.1), ("triple_captain", 5.4),
        ("bench_boost", 3.7))}
    return dict(ELITE1000_TEMPLATE_TEAM=team, ELITE1000_TEMPLATE_STARTERS=team[:11],
                ELITE1000_TEMPLATE_BENCH=team[11:], ELITE1000_CAPTAINS=captains,
                ELITE1000_SAMPLE_LABEL="1,234", ELITE1000_SOURCE_GW=8,
                ELITE1000_CHIP_USAGE=dict(gameweek=8,
                    gw=dict(top10k=dict(metrics=copy.deepcopy(metrics)),
                            overall=dict(metrics={"total": dict(pct=10.4)})),
                    total=dict(top10k=dict(metrics=copy.deepcopy(metrics)))))


class CreatorNarrationTests(unittest.TestCase):
    def test_review_keeps_ids_names_and_uses_bench_clean_sheet_facts(self):
        players, snapshot, current, segments = review_fixture()
        rewritten, audit = compose(players, snapshot, current, segments)
        self.assertEqual([row["id"] for row in rewritten], [row["id"] for row in segments])
        for segment in rewritten:
            if segment.get("player_id"):
                self.assertRegex(segment["text"], rf"\b{segment['name']}\b")
        texts = {row["id"]: row["text"] for row in rewritten}
        self.assertIn("FPL", texts["headline"])
        self.assertIn("1 clean sheet", texts["player_112"])
        self.assertIn("4 saves", texts["player_111"])
        self.assertEqual(audit["bench"]["unused_clean_sheets"], 1)
        self.assertIn("1 clean sheet", texts["metric_bench"])
        self.assertLess(sum(len(row["text"].split()) for row in rewritten), 650)
        self.assertEqual(len({row["text"] for row in rewritten}), len(rewritten))

    def test_returns_change_without_player_specific_rules(self):
        players, snapshot, current, segments = review_fixture(base_id=900)
        snapshot["live"]["elements"][11]["stats"].update(clean_sheets=1, minutes=90, total_points=6)
        _, audit = compose(players, snapshot, current, segments)
        self.assertEqual(audit["bench"]["unused_clean_sheets"], 2)

    def test_automatic_sub_points_are_not_called_unused(self):
        players, snapshot, current, segments = review_fixture()
        players[12]["multiplier"] = 1
        snapshot["picks"]["automatic_subs"] = [dict(element_in=112, element_out=101)]
        rewritten, audit = compose(players, snapshot, current, segments)
        text = next(row["text"] for row in rewritten if row["id"] == "player_112")
        self.assertIn("came in for you", text)
        self.assertEqual(audit["bench"]["counted_points"], 6)
        self.assertEqual(audit["bench"]["unused_clean_sheets"], 0)

    def test_bench_boost_counts_returns_without_regret_language(self):
        players, snapshot, current, segments = review_fixture("bboost")
        rewritten, audit = compose(players, snapshot, current, segments)
        self.assertEqual(audit["bench"]["unused_points"], 0)
        self.assertEqual(audit["bench"]["counted_points"], 10)
        text = " ".join(row["text"] for row in rewritten)
        self.assertIn("through your Bench Boost", text)
        self.assertNotIn("missed", text)
        self.assertNotIn("left 6 points", text)

    def test_captain_and_triple_captain_multipliers_use_official_values(self):
        for chip, expected, extra in (("", 16, 8), ("3xc", 24, 16)):
            players, snapshot, current, segments = review_fixture(chip)
            _, audit = compose(players, snapshot, current, segments)
            self.assertEqual(audit["captain_counted_points"], expected)
            self.assertEqual(audit["captain_extra_points"], extra)

    def test_live_pending_and_double_gameweek_results_stay_provisional(self):
        players, snapshot, current, segments = review_fixture(partial=True)
        rewritten, _ = compose(players, snapshot, current, segments)
        self.assertNotIn("did not play", " ".join(row["text"] for row in rewritten))
        snapshot["fixtures"][2].update(started=True, finished=True, minutes=90,
                                        team_h_score=0, team_a_score=0)
        snapshot["fixtures"].append(dict(event=8, team_h=3, team_a=10, started=False))
        rewritten, audit = compose(players, snapshot, current, segments)
        self.assertEqual(audit["player_states"]["106"], "PARTIAL")
        text = next(row["text"] for row in rewritten if row["id"] == "player_106")
        self.assertIn("still has a fixture", text)
        self.assertIn("so far", text)

    def test_missing_stats_never_become_a_zero_or_no_clean_sheet_claim(self):
        players, snapshot, current, segments = review_fixture()
        snapshot["live"]["elements"] = snapshot["live"]["elements"][:-1]
        rewritten, audit = compose(players, snapshot, current, segments)
        self.assertFalse(audit["bench"]["complete"])
        text = {row["id"]: row["text"] for row in rewritten}
        self.assertIn("official return needs an update", text["player_114"])
        self.assertIn("needs complete official returns", text["metric_bench"])

    def test_zero_appearance_and_negative_points_are_reported_without_guessing(self):
        players, snapshot, current, segments = review_fixture()
        snapshot["live"]["elements"][0]["stats"].update(total_points=-1, red_cards=1)
        rewritten, _ = compose(players, snapshot, current, segments)
        text = {row["id"]: row["text"] for row in rewritten}
        self.assertIn("minus 1 point", text["player_100"])
        self.assertIn("1 red card", text["player_100"])
        self.assertIn("did not play", text["player_113"])

    def test_unawarded_clean_sheet_and_forward_clean_sheet_do_not_get_credited(self):
        players, snapshot, current, segments = review_fixture()
        snapshot["live"]["elements"][12]["stats"].update(minutes=45)
        snapshot["live"]["elements"][8]["stats"].update(clean_sheets=1)
        rewritten, audit = compose(players, snapshot, current, segments)
        self.assertEqual(audit["bench"]["unused_clean_sheets"], 0)
        for player_id in (108, 112):
            self.assertNotIn("clean sheet", next(row["text"] for row in rewritten if row["id"] == f"player_{player_id}"))

    def test_transfer_comparison_labels_player_returns_and_hits(self):
        players, snapshot, current, segments = review_fixture()
        current.update(event_transfers=1, event_transfers_cost=4)
        rewritten, _ = compose(players, snapshot, current, segments,
                               transfers=[dict(element_in=104, element_out=101)])
        line = next(row["text"] for row in rewritten if row["id"] == "transfer_review")
        self.assertIn("arrivals scored 8", line)
        self.assertIn("departures 2", line)
        self.assertIn("after your hit is 2 points", line)
        self.assertIn("bench roles can change the team impact", line)

    def test_transfer_chains_cancel_the_intermediate_player(self):
        players, snapshot, current, segments = review_fixture()
        current.update(event_transfers=2)
        rewritten, _ = compose(players, snapshot, current, segments, transfers=[
            dict(element_in=105, element_out=101), dict(element_in=104, element_out=105)])
        line = next(row["text"] for row in rewritten if row["id"] == "transfer_review")
        self.assertIn("arrivals scored 8", line)
        self.assertIn("departures 2", line)

    def test_creator_text_avoids_stock_phrases_and_duplicate_result_recaps(self):
        players, snapshot, current, segments = review_fixture()
        rewritten, _ = compose(players, snapshot, current, segments)
        text = " ".join(row["text"] for row in rewritten)
        for phrase in ("That included", "Ownership added another layer", "final picture",
                       "green arrow", "missed bench return"):
            self.assertNotIn(phrase, text)
        for row in rewritten:
            if row["id"].startswith("player_"):
                self.assertLess(len(row["text"].split()), 36)

    def test_elite_text_uses_the_published_sample_and_retains_five_cues(self):
        namespace = elite_fixture()
        text = creator_elite_narration(namespace, lambda pid: f"Name{pid}")
        self.assertIn("1,234 sampled managers", text)
        self.assertIn("70 percent ownership", text)
        self.assertIn("50 percent of captain selections", text)
        self.assertIn("15.3 percent", text)
        self.assertIn("10.4 percent overall", text)
        self.assertLess(len(text.split()), 220)
        positions = [text.index(cue) for cue in ELITE_CUES]
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn("that supports patience", text)

    def test_elite_data_changes_and_missing_rates_do_not_get_zero_filled(self):
        namespace = elite_fixture()
        namespace["ELITE1000_CAPTAINS"][6]["captaincy"] = 80
        namespace["ELITE1000_CHIP_USAGE"]["gw"]["top10k"]["metrics"]["total"]["pct"] = None
        text = creator_elite_narration(namespace, lambda pid: f"Name{pid}")
        self.assertIn("Name406 takes 80 percent", text)
        self.assertIn("an unavailable rate", text)

    def test_rewrites_preserve_the_input_data_and_reject_unknown_contracts(self):
        players, snapshot, current, segments = review_fixture()
        before = copy.deepcopy((players, snapshot, current, segments))
        _, audit = compose(players, snapshot, current, segments)
        self.assertEqual((players, snapshot, current, segments), before)
        json.dumps(audit, allow_nan=False)
        with self.assertRaisesRegex(RuntimeError, "notebook contract changed"):
            patch_creator_narration_source(29, "pass\n")


def check_notebook_creator_narration(path: Path) -> None:
    cells = dict(_prepare_code_cells(path))
    for chip, partial, vice_takes_over, neither_plays in (
        ("", False, False, False), ("bboost", False, False, False),
        ("3xc", False, False, False), ("freehit", False, False, False),
        ("wildcard", False, False, False), ("", True, False, False),
        ("", False, True, False), ("", False, False, True),
    ):
        players, snapshot, current, _ = review_fixture(chip, partial)
        if vice_takes_over or neither_plays:
            snapshot["picks"]["picks"][4]["multiplier"] = 0
            snapshot["live"]["elements"][4]["stats"].update(minutes=0, total_points=0, goals_scored=0, bonus=0)
            snapshot["picks"]["picks"][5]["multiplier"] = 0 if neither_plays else 2
            if neither_plays:
                snapshot["live"]["elements"][5]["stats"].update(minutes=0, total_points=0)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            names = {int(row["id"]): row["web_name"] for row in snapshot["bootstrap"]["elements"]}
            async def synthesize(target, text, profile):
                Path(target).write_bytes(b"validation-only-audio")
                words = [dict(text=token, start=index * .1, duration=.1)
                         for index, token in enumerate(text.split())]
                return dict(audio=str(target), duration=len(words) * .1 + .3, words=words)
            namespace = dict(
                VX_GENERATE_AUDIO=True, SLIDE_SELECTION={"gw_review":True, "05_elite_1000_trends":True},
                AUDIO_WORK_DIR=root / "audio", DATA_DIR=root / "data", PROJECT_ROOT=root,
                GW_REVIEW=snapshot, REVIEW_GW=8, NEXT_GW=9, VOICE="validation", MOODS={},
                vx_tts_profile=lambda mood: {}, vx_edge_tts_stream=lambda: None,
                vx_full_word_narration=lambda text, **kwargs: text,
                vx_full_word_display=lambda text, **kwargs: text,
                vx_narration_player=lambda pid: names[int(pid)],
                vx_narration_team=lambda name: str(name),
                vx_synthesize_audio=synthesize,
            )
            code = compile(cells[29], "actual-review-cell", "exec", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
            asyncio.run(eval(code, namespace))
            package = namespace["GW_REVIEW_PACKAGE"]
            assert package["narration_style"] == "creator_review_v1"
            assert len([row for row in package["segments"] if row.get("player_id")]) == 15
            assert all(row.get("name_time") is not None for row in package["segments"])
            assert len({row["text"] for row in package["segments"]}) == len(package["segments"])
            assert "FPL" in package["segments"][0]["text"]
            if chip == "bboost":
                assert package["narration_audit"]["bench"]["unused_points"] == 0

    tree = ast.parse(cells[32])
    wrapper = next(node for node in ast.walk(tree)
                   if isinstance(node, ast.FunctionDef) and node.name == "_d3_elite1000_narration")
    anchors = next(node for node in ast.walk(tree)
                   if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and
                       target.id == "_d3_sync_anchors" for target in node.targets))
    namespace = elite_fixture()
    namespace.update(creator_elite_narration=creator_elite_narration,
                     vx_narration_player=lambda pid: f"Name{pid}")
    exec(compile(ast.Module(body=[wrapper], type_ignores=[]), "actual-elite-wrapper", "exec"), namespace)
    text = namespace["_d3_elite1000_narration"]()
    namespace["scripts"] = {"05_elite_1000_trends": text}
    exec(compile(ast.Module(body=[anchors], type_ignores=[]), "actual-elite-anchors", "exec"), namespace)
    cues = namespace["_d3_sync_anchors"]["05_elite_1000_trends"]
    assert cues == list(ELITE_CUES)
    assert [text.index(cue) for cue in cues] == sorted(text.index(cue) for cue in cues)
    assert '"05_elite_1000_trends"' in cells[32] or "'05_elite_1000_trends'" in cells[32]
    print("Actual review cell passed all chips, live results, captain fallback, 15 player name cues; "
          "Elite narration and all five animation anchors passed.")


if __name__ == "__main__":
    unittest.main()
