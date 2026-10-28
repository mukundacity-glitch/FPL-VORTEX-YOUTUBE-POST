from __future__ import annotations

import json
import os
import re
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

from day3 import fpl_squad as live_module

from day3.fpl_squad import (
    FPL_API_BASE,
    LiveSquad,
    LiveSquadError,
    parse_player_choice,
    resolve_live_squad,
    validate_transfer_selections,
)
from day3.refresh_day3_choices import replace_out_options

ENTRY_ID = 145784
LIVE_IDS = [1, 173, 31, 332, 115, 40, 427, 124, 154, 411, 346, 623, 165, 112, 289]
PREVIOUS_IDS = [1, 109, 4, 418, 469, 304, 229, 426, 124, 40, 12, 368, 249, 346, 165]
FREE_HIT_IDS = [7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21]


def _meta(player_id: int) -> dict:
    position = 1 if player_id % 7 == 0 else (2 if player_id % 3 == 0 else 3)
    return {
        "id": player_id,
        "web_name": f"Player{player_id}",
        "element_type": position,
        "team": 1 + (player_id % 20),
        "now_cost": 55,
        "status": "a",
    }


def _events() -> list[dict]:
    events = [
        {"id": gw, "finished": True, "is_current": False, "is_next": False}
        for gw in range(1, 8)
    ]
    events.append({"id": 8, "finished": True, "is_current": True, "is_next": False})
    events.append({"id": 9, "finished": False, "is_current": False, "is_next": True})
    return events


def _bootstrap() -> dict:
    ids = sorted(set(LIVE_IDS + PREVIOUS_IDS + FREE_HIT_IDS))
    return {
        "events": _events(),
        "elements": [_meta(pid) for pid in ids],
        "teams": [{"id": tid, "short_name": f"T{tid}"} for tid in range(1, 25)],
    }


def _picks(ids: list[int]) -> dict:
    return {
        "active_chip": None,
        "entry_history": {"event": 8, "bank": 22, "value": 1016},
        "picks": [
            {
                "element": pid,
                "position": index + 1,
                "multiplier": 1 if index < 11 else 0,
                "is_captain": False,
                "is_vice_captain": False,
            }
            for index, pid in enumerate(ids)
        ],
    }


class FakeFetcher:
    def __init__(self, *, picks=None, bootstrap=None, history=None, chips=None):
        self.bootstrap = _bootstrap() if bootstrap is None else bootstrap
        self.history = {"chips": chips or [], "current": [], "past": []} if history is None else history
        self.picks = {8: _picks(LIVE_IDS), 7: _picks(PREVIOUS_IDS)} if picks is None else picks
        self.calls: list[str] = []

    def __call__(self, url: str):
        self.calls.append(url)
        if url == f"{FPL_API_BASE}/bootstrap-static/":
            return self.bootstrap
        if url == f"{FPL_API_BASE}/entry/{ENTRY_ID}/history/":
            return self.history
        match = re.search(r"/entry/(\d+)/event/(\d+)/picks/$", url)
        if match:
            return self.picks.get(int(match.group(2)))
        raise AssertionError(f"Unexpected FPL URL: {url}")


class ResolveLiveSquadTests(unittest.TestCase):
    def test_resolves_latest_published_squad_and_next_gameweek(self):
        fetcher = FakeFetcher()
        squad = resolve_live_squad(ENTRY_ID, fetcher=fetcher)
        self.assertEqual(sorted(squad.squad_ids), sorted(LIVE_IDS))
        self.assertEqual(squad.base_gw, 8)
        self.assertEqual(squad.latest_visible_gw, 8)
        self.assertEqual(squad.planning_gw, 9)
        self.assertEqual(squad.free_hit_gws_skipped, ())
        self.assertEqual(len(squad.choices), 15)
        self.assertEqual(len(set(squad.choices)), 15)
        self.assertTrue(all(re.match(r"^\d+ \| .+ \| (GK|DEF|MID|FWD)$", c) for c in squad.choices))

    def test_free_hit_walks_back_to_permanent_squad(self):
        fetcher = FakeFetcher(
            picks={8: _picks(FREE_HIT_IDS), 7: _picks(PREVIOUS_IDS)},
            chips=[{"event": 8, "name": "Free Hit"}],
        )
        squad = resolve_live_squad(ENTRY_ID, fetcher=fetcher)
        self.assertEqual(sorted(squad.squad_ids), sorted(PREVIOUS_IDS))
        self.assertEqual(squad.base_gw, 7)
        self.assertEqual(squad.latest_visible_gw, 8)
        self.assertEqual(squad.free_hit_gws_skipped, (8,))

    def test_active_chip_field_alone_also_triggers_walk_back(self):
        free_hit_picks = _picks(FREE_HIT_IDS)
        free_hit_picks["active_chip"] = "freehit"
        fetcher = FakeFetcher(picks={8: free_hit_picks, 7: _picks(PREVIOUS_IDS)})
        squad = resolve_live_squad(ENTRY_ID, fetcher=fetcher)
        self.assertEqual(squad.base_gw, 7)

    def test_free_hit_without_earlier_squad_fails(self):
        fetcher = FakeFetcher(
            picks={8: _picks(FREE_HIT_IDS)},
            chips=[{"event": 8, "name": "freehit"}],
        )
        with self.assertRaisesRegex(LiveSquadError, "no earlier permanent squad"):
            resolve_live_squad(ENTRY_ID, fetcher=fetcher)

    def test_future_gameweek_not_found_falls_back_to_current_squad(self):
        fetcher = FakeFetcher(picks={8: _picks(LIVE_IDS), 9: None})
        squad = resolve_live_squad(ENTRY_ID, fetcher=fetcher)
        self.assertEqual(squad.base_gw, 8)
        self.assertEqual(squad.planning_gw, 9)

    def test_incomplete_picks_are_rejected_not_used_as_a_squad(self):
        short = _picks(LIVE_IDS)
        short["picks"] = short["picks"][:14]
        fetcher = FakeFetcher(picks={8: short, 7: _picks(PREVIOUS_IDS)})
        squad = resolve_live_squad(ENTRY_ID, fetcher=fetcher)
        self.assertEqual(squad.base_gw, 7)

    def test_api_outage_fails_instead_of_returning_a_stale_squad(self):
        class DownFetcher(FakeFetcher):
            def __call__(self, url):
                super().__call__(url)
                return None

        with self.assertRaisesRegex(LiveSquadError, "bootstrap-static response is unavailable"):
            resolve_live_squad(ENTRY_ID, fetcher=DownFetcher())

    def test_picks_outage_fails_even_with_a_valid_bootstrap(self):
        class DownFetcher(FakeFetcher):
            def __call__(self, url):
                if "/picks/" in url:
                    return None
                return super().__call__(url)

        with self.assertRaisesRegex(LiveSquadError, "No public 15-player FPL squad"):
            resolve_live_squad(ENTRY_ID, fetcher=DownFetcher())

    def test_missing_entry_history_fails(self):
        class NoHistory(FakeFetcher):
            def __call__(self, url):
                if "/history/" in url:
                    return None
                return super().__call__(url)

        with self.assertRaisesRegex(LiveSquadError, "entry history response is unavailable"):
            resolve_live_squad(ENTRY_ID, fetcher=NoHistory())

    def test_no_public_picks_fails(self):
        with self.assertRaisesRegex(LiveSquadError, "No public 15-player FPL squad"):
            resolve_live_squad(ENTRY_ID, fetcher=FakeFetcher(picks={}))

    def test_snapshot_roundtrip_preserves_digest(self):
        squad = resolve_live_squad(ENTRY_ID, fetcher=FakeFetcher())
        restored = LiveSquad.from_dict(json.loads(json.dumps(squad.to_dict())))
        self.assertEqual(restored, squad)
        tampered = squad.to_dict()
        tampered["players"] = tampered["players"][:14]
        with self.assertRaisesRegex(LiveSquadError, "15 unique players"):
            LiveSquad.from_dict(tampered)
        bad_digest = squad.to_dict()
        bad_digest["squad_digest"] = "deadbeef"
        with self.assertRaisesRegex(LiveSquadError, "digest mismatch"):
            LiveSquad.from_dict(bad_digest)


class ValidateSelectionsTests(unittest.TestCase):
    def setUp(self):
        self.squad = resolve_live_squad(ENTRY_ID, fetcher=FakeFetcher())

    def test_valid_pairs_are_normalized(self):
        outs, ins = validate_transfer_selections(
            self.squad,
            ["1 | Raya | GK", "173 | Thomas | DEF"],
            ["109 | Verbruggen | GK", "4 | Gabriel | DEF"],
        )
        self.assertEqual(outs, [1, 173])
        self.assertEqual(ins, [109, 4])

    def test_names_and_bare_ids_both_resolve(self):
        self.assertEqual(parse_player_choice("1 | Raya | GK", self.squad), 1)
        self.assertEqual(parse_player_choice("173", self.squad), 173)
        self.assertEqual(parse_player_choice("Player427", self.squad), 427)
        with self.assertRaises(LiveSquadError):
            parse_player_choice("unknown player", self.squad)

    def test_stale_out_player_is_rejected_with_the_live_squad(self):
        with self.assertRaisesRegex(LiveSquadError, "not in your live FPL squad"):
            validate_transfer_selections(self.squad, ["109 | Verbruggen | GK"], ["700"])
        with self.assertRaisesRegex(LiveSquadError, "Live 15:"):
            validate_transfer_selections(self.squad, ["999"], ["700"])

    def test_in_player_already_owned_is_rejected(self):
        with self.assertRaisesRegex(LiveSquadError, "already in your live FPL squad"):
            validate_transfer_selections(self.squad, ["1"], ["173"])

    def test_pair_rules_are_enforced(self):
        with self.assertRaisesRegex(LiveSquadError, "1–5 complete OUT/IN pairs"):
            validate_transfer_selections(self.squad, "1,173", "109")
        with self.assertRaisesRegex(LiveSquadError, "1–5 complete OUT/IN pairs"):
            validate_transfer_selections(self.squad, "1,173,31,332,115,40", "109,4,418,469,304,229")
        with self.assertRaisesRegex(LiveSquadError, "more than once"):
            validate_transfer_selections(self.squad, "1,1", "109,4")
        with self.assertRaisesRegex(LiveSquadError, "both OUT and IN"):
            validate_transfer_selections(self.squad, "1", "1")

    def test_none_selections_are_rejected_for_manual_mode(self):
        with self.assertRaises(LiveSquadError):
            validate_transfer_selections(self.squad, "NONE", "NONE")


class WorkflowChoiceTests(unittest.TestCase):
    def _sample_workflow(self) -> str:
        blocks = []
        for index in range(1, 6):
            blocks.append(
                f"      player_out_{index}:\n"
                '        description: "Manual Transfer only"\n'
                "        required: true\n"
                '        default: "NONE"\n'
                "        type: choice\n"
                "        options:\n"
                '          - "NONE"\n'
                '          - "1 | Raya | GK"\n'
            )
        return "on:\n  workflow_dispatch:\n    inputs:\n" + "".join(blocks)

    def test_replace_all_five_blocks_and_is_idempotent(self):
        squad = resolve_live_squad(ENTRY_ID, fetcher=FakeFetcher())
        original = self._sample_workflow()
        updated = replace_out_options(original, squad.choices)
        self.assertEqual(updated.count("Generated from the official FPL API"), 5)
        for choice in squad.choices:
            self.assertEqual(updated.count(f'- "{choice}"'), 5)
        self.assertEqual(updated.count('- "NONE"'), 5)
        self.assertNotIn('- "1 | Raya | GK"', updated)
        self.assertEqual(replace_out_options(updated, squad.choices), updated)

    def test_requires_exactly_fifteen_unique_choices(self):
        with self.assertRaisesRegex(LiveSquadError, "15 unique live squad choices"):
            replace_out_options(self._sample_workflow(), ["1"] * 15)
        with self.assertRaisesRegex(LiveSquadError, "15 unique live squad choices"):
            replace_out_options(self._sample_workflow(), ["1"])

    def test_missing_input_blocks_fail(self):
        squad = resolve_live_squad(ENTRY_ID, fetcher=FakeFetcher())
        truncated = self._sample_workflow().replace("      player_out_5:", "      player_out_skip:")
        with self.assertRaisesRegex(LiveSquadError, "Expected five"):
            replace_out_options(truncated, squad.choices)

    def test_checked_in_workflow_uses_api_generated_live_squad(self):
        workflow = Path(__file__).resolve().parents[1] / ".github/workflows/day-3.yml"
        text = workflow.read_text(encoding="utf-8")
        blocks = re.findall(
            r"(?ms)^      player_out_[1-5]:.*?^        options:\n(.*?)(?=^      \w|\Z)",
            text,
        )
        self.assertEqual(len(blocks), 5)
        option_lists = [
            re.findall(r'^          - "(.+)"$', block, re.M) for block in blocks
        ]
        for options in option_lists:
            self.assertEqual(options[0], "NONE")
            self.assertEqual(len(options), 16)
        expected = option_lists[0][1:]
        self.assertEqual(len(set(expected)), 15)
        self.assertTrue(all(option_lists[i][1:] == expected for i in range(5)))
        self.assertEqual(replace_out_options(text, expected), text)
        for player_id in LIVE_IDS:
            self.assertTrue(any(option.startswith(f"{player_id} | ") for option in expected))


class WorkflowLiveSquadStepTests(unittest.TestCase):
    """The Day 3 workflow's early validation step must stay runnable."""

    STEP_NAME = "Resolve live FPL squad and verify Player OUT picks"

    def _step_code(self) -> str:
        workflow = Path(__file__).resolve().parents[1] / ".github/workflows/day-3.yml"
        text = workflow.read_text(encoding="utf-8")
        self.assertIn(f"- name: {self.STEP_NAME}", text)
        section = text[text.index(f"- name: {self.STEP_NAME}") :].split(
            "\n      - name:"
        )[0]
        match = re.search(r"python - <<'PY'\n(.*?)\n\s*PY", section, re.S)
        self.assertIsNotNone(match, "workflow step must contain a Python heredoc")
        return textwrap.dedent(match.group(1))

    def test_embedded_python_compiles(self):
        compile(self._step_code(), "<day-3-live-squad-step>", "exec")

    def test_step_validates_manual_pairs_and_writes_the_snapshot(self):
        squad = resolve_live_squad(ENTRY_ID, fetcher=FakeFetcher())
        code = self._step_code()
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            env_path = root_path / "github_env"
            env_path.write_text("", encoding="utf-8")
            environment = {
                "FPL_ENTRY_ID": str(ENTRY_ID),
                "DAY3_PLAN": "TRANSFER",
                "DAY3_TRANSFER_MODE": "MANUAL",
                "DAY3_OUT_1": "1 | Player1 | GK",
                "DAY3_IN_1": "109 | Verbruggen | GK",
                "DAY3_OUT_2": "NONE",
                "DAY3_IN_2": "NONE",
                "DAY3_OUT_3": "NONE",
                "DAY3_IN_3": "NONE",
                "DAY3_OUT_4": "NONE",
                "DAY3_IN_4": "NONE",
                "DAY3_OUT_5": "NONE",
                "DAY3_IN_5": "NONE",
                "GITHUB_ENV": str(env_path),
                "RUNNER_TEMP": root,
            }
            with patch.dict(os.environ, environment, clear=True):
                with patch.object(live_module, "resolve_live_squad", return_value=squad):
                    exec(compile(code, "<day-3-live-squad-step>", "exec"), {"__name__": "__main__"})
            exported = env_path.read_text(encoding="utf-8")
            self.assertIn("DAY3_LIVE_SQUAD_JSON=", exported)
            self.assertIn("DAY3_LIVE_SQUAD_GW=8", exported)
            snapshot = root_path / "day3-live-squad.json"
            self.assertTrue(snapshot.is_file())
            self.assertEqual(
                LiveSquad.from_dict(json.loads(snapshot.read_text(encoding="utf-8"))),
                squad,
            )

    def test_step_rejects_a_stale_out_choice_before_the_render(self):
        squad = resolve_live_squad(ENTRY_ID, fetcher=FakeFetcher())
        code = self._step_code()
        with tempfile.TemporaryDirectory() as root:
            environment = {
                "FPL_ENTRY_ID": str(ENTRY_ID),
                "DAY3_PLAN": "TRANSFER",
                "DAY3_TRANSFER_MODE": "MANUAL",
                "DAY3_OUT_1": "109 | Verbruggen | GK",
                "DAY3_IN_1": "700 | NewPlayer | GK",
                "GITHUB_ENV": str(Path(root) / "github_env"),
                "RUNNER_TEMP": root,
            }
            with patch.dict(os.environ, environment, clear=True):
                with patch.object(live_module, "resolve_live_squad", return_value=squad):
                    with self.assertRaisesRegex(LiveSquadError, "not in your live FPL squad"):
                        exec(compile(code, "<day-3-live-squad-step>", "exec"), {"__name__": "__main__"})


if __name__ == "__main__":
    unittest.main()
