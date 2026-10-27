from __future__ import annotations

import json
import re
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from contextlib import ExitStack
from pathlib import Path
from typing import Any
from unittest.mock import patch

from day3 import live_evidence
from day3 import run_notebook as runner
from day3.chip_plan import DAY3_CHIP_PLAN_SCENE, DAY3_PLANNED_CHIP_OPTIONS, chip_plan_copy
from day3.publish_private import _one_final_video


class FullWordNarrationAbbreviationPatchTests(unittest.TestCase):
    def test_fast_template_preflight_passes_current_templates_and_rejects_new_abbreviations(self) -> None:
        runner._preflight_narration_templates()

        bad_source = (
            'def player_analysis():\\n    return "The API still gives a playing chance."\\n'
            'def team_analysis():\\n    return "Recorded evidence is available."\\n'
            'def defcon_narration():\\n    return "No tactical conclusion is assumed."\\n'
            'def unrelated_metadata():\\n    return "API documentation is not spoken."\\n'
        )
        with self.assertRaisesRegex(RuntimeError, "API"):
            runner._preflight_narration_templates(bad_source)

    def test_defcon_api_is_expanded_at_validation_and_other_scenes_are_unchanged(self) -> None:
        source = (
            '_full_word_scripts = {"03_defcon": "The API confirms the forecast.", "intro": "API remains."}\n'
            'seen = {}\n'
            'for key, script in _full_word_scripts.items():\n'
            '    seen[key] = script\n'
        )
        patched = runner._patch_full_word_abbreviation_normalization(source)
        namespace: dict[str, Any] = {}
        exec(compile(patched, "<narration-abbreviation-patch-test>", "exec"), namespace)

        loop_marker = "# Normalize the exact DEFCON script being checked and retained for speech."
        self.assertLess(patched.index("for key, script in _full_word_scripts.items():"), patched.index(loop_marker))
        self.assertLess(patched.index(loop_marker), patched.index("seen[key] = script"))
        self.assertEqual(
            namespace["seen"]["03_defcon"],
            "The application programming interface confirms the forecast.",
        )
        self.assertEqual(
            namespace["_full_word_scripts"]["03_defcon"],
            "The application programming interface confirms the forecast.",
        )
        self.assertEqual(namespace["seen"]["intro"], "API remains.")
        self.assertEqual(namespace["_full_word_scripts"]["intro"], "API remains.")

    def test_normalizes_after_late_dictionary_overwrite_before_audit_even_without_matching_loop(self) -> None:
        source = (
            '_full_word_scripts = {"03_defcon": "Earlier API", "intro": "API remains."}\n'
            '# Expand API before the full-word audit so speech uses the spoken form.\n'
            '_full_word_scripts = {"03_defcon": "Final API confirms the forecast.", "intro": "API remains."}\n'
            '_full_word_errors = []\n'
            'audit_text = _full_word_scripts["03_defcon"]\n'
            'scripts = _full_word_scripts\n'
        )
        patched = runner._patch_full_word_abbreviation_normalization(source)
        namespace: dict[str, Any] = {}
        exec(compile(patched, "<narration-audit-boundary-test>", "exec"), namespace)

        self.assertLess(
            patched.index("# Normalize DEFCON narration immediately before the full-word audit."),
            patched.index("_full_word_errors = []"),
        )
        self.assertEqual(
            namespace["audit_text"],
            "Final application programming interface confirms the forecast.",
        )
        self.assertEqual(
            namespace["scripts"]["03_defcon"],
            "Final application programming interface confirms the forecast.",
        )
        self.assertEqual(namespace["scripts"]["intro"], "API remains.")

    def test_stale_marker_cannot_skip_normalization_after_script_dictionary_is_overwritten(self) -> None:
        # This models the production failure: the prior patch marker already exists,
        # but a later dictionary assignment restores API after that earlier patch ran.
        source = (
            '_full_word_scripts = {"03_defcon": "Earlier API"}\n'
            '# Expand API before the full-word audit so speech uses the spoken form.\n'
            'import re as _vx_narration_re\n'
            '_full_word_scripts = {_key: _vx_narration_re.sub(r"\\bAPI\\b", "application programming interface", _value) '
            'if _key == "03_defcon" else _value for _key, _value in _full_word_scripts.items()}\n'
            '_full_word_scripts = {"03_defcon": "Final API confirms the forecast.", "intro": "API remains."}\n'
            'seen = {}\n'
            'for key, script in _full_word_scripts.items():\n'
            '    seen[key] = script\n'
            'scripts = _full_word_scripts\n'
        )
        patched = runner._patch_full_word_abbreviation_normalization(source)
        namespace: dict[str, Any] = {}
        exec(compile(patched, "<narration-abbreviation-stale-marker-test>", "exec"), namespace)

        self.assertEqual(
            namespace["seen"]["03_defcon"],
            "Final application programming interface confirms the forecast.",
        )
        self.assertEqual(
            namespace["scripts"]["03_defcon"],
            "Final application programming interface confirms the forecast.",
        )
        self.assertEqual(namespace["scripts"]["intro"], "API remains.")

    def test_assignment_fallback_handles_validation_without_inline_loop(self) -> None:
        source = (
            '_full_word_scripts = {"03_defcon": "The API confirms the forecast.", "intro": "API remains."}\n'
            'consume(_full_word_scripts)\n'
        )
        patched = runner._patch_full_word_abbreviation_normalization(source)
        namespace: dict[str, Any] = {"consume": lambda value: None}
        exec(compile(patched, "<narration-abbreviation-fallback-test>", "exec"), namespace)

        self.assertLess(
            patched.index("import re as _vx_narration_re"),
            patched.index("consume(_full_word_scripts)"),
        )
        self.assertEqual(
            namespace["_full_word_scripts"]["03_defcon"],
            "The application programming interface confirms the forecast.",
        )
        self.assertEqual(namespace["_full_word_scripts"]["intro"], "API remains.")

    def test_newer_narration_structure_does_not_fail_on_legacy_hook(self) -> None:
        source = 'def narrate():\n    return "Narration is assembled by a helper."\n'
        self.assertEqual(runner._patch_full_word_abbreviation_normalization(source), source)


class LiveEvidencePollingTests(unittest.TestCase):
    def setUp(self) -> None:
        now = datetime.now(timezone.utc)
        self.old_deadline = (now - timedelta(days=1)).isoformat()
        self.next_deadline = (now + timedelta(days=3)).isoformat()
        self.kickoff = (now - timedelta(hours=2)).isoformat()
        self.bootstrap = {
            "events": [
                {"id": 1, "deadline_time": self.old_deadline},
                {"id": 2, "deadline_time": self.next_deadline},
            ],
            "teams": [{"id": 1, "name": "Home FC"}, {"id": 2, "name": "Away FC"}],
            "elements": [{
                "id": 11, "code": 1011, "team": 1, "team_join_date": None,
                "element_type": 3, "status": "a", "chance_of_playing_next_round": 100,
                "minutes": 0, "starts": 0, "defensive_contribution": 0,
                "first_name": "Test", "second_name": "Player", "web_name": "Player",
                "now_cost": 50,
            }],
            "element_types": [{"id": 3, "singular_name_short": "FWD"}],
        }
        self.live_payload = {
            "elements": [{
                "id": 11,
                "stats": {"minutes": 0, "starts": 0, "defensive_contribution": 0},
                "explain": [],
            }]
        }

    def fixture(self, finished: bool, provisional: bool) -> dict[str, Any]:
        return {
            "id": 701, "event": 1, "team_h": 1, "team_a": 2,
            "kickoff_time": self.kickoff, "started": True, "finished": finished,
            "finished_provisional": provisional, "team_h_score": 0, "team_a_score": 0,
            "stats": [],
        }

    def test_capture_reloads_until_fixture_has_verified_final_statistics(self) -> None:
        fixture_states = [
            self.fixture(False, False),  # match is in progress
            self.fixture(True, False),   # match ended, stats are still provisional
            self.fixture(True, True),    # final stats are verified
        ]
        state = {"fixtures": 0}

        def loader(path: str) -> Any:
            if path == "/bootstrap-static/":
                return self.bootstrap
            if path == "/fixtures/":
                index = min(state["fixtures"], len(fixture_states) - 1)
                state["fixtures"] += 1
                return [fixture_states[index]]
            if path == "/event/1/live/":
                return self.live_payload
            raise AssertionError(f"Unexpected FPL path: {path}")

        with patch.object(live_evidence.time, "sleep") as sleep:
            snapshot = live_evidence.capture_evidence(
                {"next_gw": 2, "api_fallback_used": False},
                loader=loader,
                poll_interval_seconds=0,
                max_wait_seconds=30,
            )

        self.assertEqual(state["fixtures"], 3)
        self.assertEqual(snapshot["history_gameweeks"], [1])
        self.assertEqual(snapshot["next_gw"], 2)
        self.assertEqual(sleep.call_count, 2)

    def test_score_locked_gameweek_overrides_stale_fixture_finished_flag(self) -> None:
        # The API can leave fixture.finished=False after the event's official
        # data_checked score lock. Provisional fixture data is accepted only
        # for that locked event, then still reconciled against live/bootstrap stats.
        self.bootstrap["events"][0].update(finished=True, data_checked=True)
        state = {"fixtures": 0}
        stale_fixture = self.fixture(False, True)

        def loader(path: str) -> Any:
            if path == "/bootstrap-static/":
                return self.bootstrap
            if path == "/fixtures/":
                state["fixtures"] += 1
                return [stale_fixture]
            if path == "/event/1/live/":
                return self.live_payload
            raise AssertionError(f"Unexpected FPL path: {path}")

        with patch.object(live_evidence.time, "sleep") as sleep:
            snapshot = live_evidence.capture_evidence(
                {"next_gw": 2, "api_fallback_used": False},
                loader=loader,
                poll_interval_seconds=0,
                max_wait_seconds=0,
            )

        self.assertEqual(state["fixtures"], 1)
        self.assertEqual(snapshot["history_gameweeks"], [1])
        self.assertEqual(snapshot["next_gw"], 2)
        sleep.assert_not_called()

    def test_provisional_fixture_still_waits_without_official_score_lock(self) -> None:
        def loader(path: str) -> Any:
            if path == "/bootstrap-static/":
                return self.bootstrap
            if path == "/fixtures/":
                return [self.fixture(False, True)]
            raise AssertionError(f"Unexpected FPL path: {path}")

        with self.assertRaisesRegex(
            RuntimeError,
            r"fixture #701 \(Home FC vs Away FC;.*No video was rendered from incomplete data",
        ):
            live_evidence.capture_evidence(
                {"next_gw": 2, "api_fallback_used": False},
                loader=loader,
                poll_interval_seconds=0,
                max_wait_seconds=0,
            )

    def test_wait_timeout_reports_the_exact_fixture_and_stops_safely(self) -> None:
        def loader(path: str) -> Any:
            if path == "/bootstrap-static/":
                return self.bootstrap
            if path == "/fixtures/":
                return [self.fixture(False, False)]
            raise AssertionError(f"Unexpected FPL path: {path}")

        with self.assertRaisesRegex(
            RuntimeError,
            r"fixture #701 \(Home FC vs Away FC;.*No video was rendered from incomplete data",
        ):
            live_evidence.capture_evidence(
                {"next_gw": 2, "api_fallback_used": False},
                loader=loader,
                poll_interval_seconds=0,
                max_wait_seconds=0,
            )


class FinalVideoSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.output_root = Path(self.temporary.name)
        self.video_directory = self.output_root / "MP4"
        self.video_directory.mkdir()

    def write_video(self, name: str, content: bytes = b"video") -> Path:
        path = self.video_directory / name
        path.write_bytes(content)
        return path

    def test_shortlist_scene_is_not_a_second_master(self) -> None:
        self.write_video("04_final_shortlists.mp4")
        self.write_video("gw_review.mp4")
        master = self.write_video("FPL_VORTEX_GW6_COMBINED_FINAL_2160P_24FPS.mp4")
        self.assertEqual(_one_final_video(self.output_root), master.resolve())

    def test_shortlist_scene_cannot_replace_a_missing_master(self) -> None:
        self.write_video("04_final_shortlists.mp4")
        with self.assertRaises(RuntimeError):
            _one_final_video(self.output_root)

    def test_empty_master_is_rejected(self) -> None:
        self.write_video("FPL_VORTEX_GW6_COMBINED_FINAL_2160P_24FPS.mp4", b"")
        with self.assertRaises(RuntimeError):
            _one_final_video(self.output_root)

    def test_multiple_masters_are_rejected(self) -> None:
        self.write_video("FPL_VORTEX_GW6_COMBINED_FINAL_2160P_24FPS.mp4")
        self.write_video("FPL_VORTEX_GW6_COMBINED_OLD.mp4")
        with self.assertRaises(RuntimeError):
            _one_final_video(self.output_root)


class DefconGameweekTests(unittest.TestCase):
    def test_partial_review_uses_latest_completed_gameweek(self) -> None:
        self.assertEqual(
            runner._resolve_defcon_history_gameweek([5, 5.0], [1, 2, 3, 4, 5], [1, 2, 3, 4, 5], 7),
            (5, [1, 2, 3, 4, 5]),
        )

    def test_final_review_advances_completed_cutoff(self) -> None:
        self.assertEqual(
            runner._resolve_defcon_history_gameweek([6, 6], [1, 2, 3, 4, 5, 6], [1, 2, 3, 4, 5, 6], 7),
            (6, [1, 2, 3, 4, 5, 6]),
        )

    def test_stale_player_features_are_rejected(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "latest completed GW 6"):
            runner._resolve_defcon_history_gameweek([5, 5], [1, 2, 3, 4, 5, 6], [1, 2, 3, 4, 5, 6], 7)

    def test_mixed_player_cutoffs_cannot_hide_behind_maximum(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "player feature Gameweeks"):
            runner._resolve_defcon_history_gameweek([4, 5], [1, 2, 3, 4, 5], [1, 2, 3, 4, 5], 7)

    def test_missing_model_gameweek_is_rejected_even_with_current_cutoff(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "model history"):
            runner._resolve_defcon_history_gameweek([5], [1, 2, 3, 4, 5], [1, 3, 4, 5], 7)

    def test_no_completed_history_is_rejected(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "no completed"):
            runner._resolve_defcon_history_gameweek([], [], [], 1)

    def test_invalid_gameweek_evidence_is_rejected(self) -> None:
        for invalid in (None, float("nan"), 5.5, True, "unknown", 39):
            with self.subTest(value=invalid), self.assertRaisesRegex(RuntimeError, "invalid Gameweek"):
                runner._resolve_defcon_history_gameweek([invalid], [1, 2, 3, 4, 5], [1, 2, 3, 4, 5], 7)


class Top10kTemplateNameTests(unittest.TestCase):
    def test_changing_bench_positions_do_not_become_player_names(self) -> None:
        for labels in (
            "GKP1. MID2. FWD3. MID",
            "GKP 1. DEF 2. MID 3. MID",
            "GKP 1. DEF 2. MID 3. FWD",
            "GK 1. FWD 2. DEF 3. MID",
            "GKP\n1.\nMID\n2.\nFWD\n3.\nMID",
        ):
            with self.subTest(labels=labels):
                self.assertEqual(runner._clean_top10k_template_name(f"{labels} Raya"), "Raya")

    def test_player_kit_labels_are_removed_before_bench_positions(self) -> None:
        self.assertEqual(
            runner._clean_top10k_template_name("Player Kit GKP1. MID2. FWD3. MID Player Kit João Pedro"),
            "João Pedro",
        )

    def test_real_names_preserve_accents_punctuation_and_multiple_words(self) -> None:
        for name in ("João Pedro", "Groß", "Calvert-Lewin", "B.Fernandes", "De Cuyper", "van Hecke", "Midtsjø", "Fwderson"):
            with self.subTest(name=name):
                self.assertEqual(runner._clean_top10k_template_name(name), name)

    def test_split_percentage_text_nodes_are_rejoined(self) -> None:
        self.assertEqual(
            runner._normalize_top10k_visible_text("Raya\r\nLEE (H)\n43\n%\n\nPalmer\n19.89 %"),
            "Raya\nLEE (H)\n43%\nPalmer\n19.89%",
        )

    def test_normalizer_preserves_captain_section_line_boundaries(self) -> None:
        self.assertEqual(
            runner._normalize_top10k_visible_text("Top 10k Captains\n João   Pedro \n17.4%\nGW6 Chip Usage"),
            "Top 10k Captains\nJoão Pedro\n17.4%\nGW6 Chip Usage",
        )


class NarrationExportTests(unittest.TestCase):
    # Keep the production export contract so tests exercise partial and final exports.
    export_source = r'''
from pathlib import Path
import json, os

VX_EXPORT_SCENES = {
 'gw_review': ('06_Gameweek_Review', 'gw_review_scene_4k'),
 '05a_my_plan_roll': ('05A_Gameweek_Plan_Roll', 'my_plan_5a_roll_scene_4k'),
 '05b_my_plan_transfer': ('05B_Transfer_Plan', 'my_plan_5b_transfer_scene_4k'),
 '05_outro': ('08_Outro', 'outro_scene_4k'),
}

def _vx_export_folder_guard():
    NARRATION_EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    Path(SLIDE_DIR).mkdir(parents=True, exist_ok=True)

def _vx_remove_export_item(path):
    path.unlink()

def vx_export_narration_scripts(available_only=False):
    _vx_export_folder_guard()
    selected = list(globals().get('SELECTED_SCENES', []))
    if not selected:
        raise RuntimeError('Run Cell 0 to select slides before exporting narration')
    shared_path = VX_INTERNAL_DATA_DIR / 'other_scenes_narration.json'
    shared = json.loads(shared_path.read_text(encoding='utf-8')) if shared_path.is_file() else {}
    packages = {'gw_review': 'gw_review_package.json',
                '05a_my_plan_roll': 'my_plan_5a_roll_package.json',
                '05b_my_plan_transfer': 'my_plan_5b_transfer_package.json'}
    texts, missing = {}, []
    for key in selected:
        if key not in VX_EXPORT_SCENES:
            raise RuntimeError('Unknown selected slide: ' + key)
        text = None
        if key in packages:
            path = VX_INTERNAL_DATA_DIR / packages[key]
            if path.is_file():
                package = json.loads(path.read_text(encoding='utf-8'))
                segments = package.get('segments', [])
                if segments and all(isinstance(s.get('text'), str) and s['text'].strip() for s in segments):
                    text = '\n\n'.join(s['text'] for s in segments)
        else:
            text = shared.get(key, {}).get('script')
        if not isinstance(text, str) or not text.strip():
            missing.append(key)
            continue
        texts['Slide_' + VX_EXPORT_SCENES[key][0] + '.txt'] = text
    if missing and not available_only:
        raise RuntimeError('Narration not generated for: ' + ', '.join(missing))
    for filename, text in texts.items():
        target = NARRATION_EXPORT_DIR / filename
        pending = target.with_name('.' + filename + '.pending')
        try:
            pending.write_text(text, encoding='utf-8')
            if pending.read_text(encoding='utf-8') != text:
                raise RuntimeError('Narration write verification failed: ' + filename)
            os.replace(pending, target)
        finally:
            pending.unlink(missing_ok=True)
    keep = {'Slide_' + VX_EXPORT_SCENES[key][0] + '.txt' for key in selected}
    for path in list(NARRATION_EXPORT_DIR.iterdir()):
        if path.name not in keep:
            _vx_remove_export_item(path)
    return sorted(str(NARRATION_EXPORT_DIR / name) for name in texts)

def vx_finish_clean_exports():
    files = vx_export_narration_scripts(available_only=not bool(globals().get('VX_GENERATE_AUDIO', True)))
    keep = {VX_EXPORT_SCENES[key][1] + '.png' for key in SELECTED_SCENES}
    for path in list(Path(SLIDE_DIR).iterdir()):
        if path.name not in keep:
            _vx_remove_export_item(path)
    return files
'''

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.data_directory = self.root / "work" / "data"
        self.data_directory.mkdir(parents=True)
        self.export_directory = self.root / "output" / "DATA"
        self.slide_directory = self.root / "output" / "SLIDE"
        self.namespace: dict[str, Any] = {
            "VX_INTERNAL_DATA_DIR": self.data_directory,
            "NARRATION_EXPORT_DIR": self.export_directory,
            "SLIDE_DIR": self.slide_directory,
            "SELECTED_SCENES": [DAY3_CHIP_PLAN_SCENE],
        }
        exec(runner._patch_narration_exports(self.export_source), self.namespace)

    def write_package(self, filename: str, package: dict[str, Any]) -> None:
        (self.data_directory / filename).write_text(json.dumps(package), encoding="utf-8")

    def test_partial_export_waits_for_chip_renderer_and_keeps_review(self) -> None:
        self.namespace["SELECTED_SCENES"] = ["gw_review", DAY3_CHIP_PLAN_SCENE]
        self.write_package("gw_review_package.json", {"segments": [{"text": "Review narration."}]})
        files = self.namespace["vx_export_narration_scripts"](available_only=True)
        self.assertEqual(files, [str(self.export_directory / "Slide_06_Gameweek_Review.txt")])
        self.assertEqual(Path(files[0]).read_text(encoding="utf-8"), "Review narration.")

    def test_final_export_rejects_missing_chip_before_replacing_scripts(self) -> None:
        self.export_directory.mkdir(parents=True)
        existing = self.export_directory / "existing.txt"
        existing.write_text("Previous export", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "Narration not generated for: 05c_my_plan_chip"):
            self.namespace["vx_export_narration_scripts"]()
        self.assertEqual(existing.read_text(encoding="utf-8"), "Previous export")

    def test_all_planned_chips_export_the_exact_rendered_tts_text(self) -> None:
        for chip in DAY3_PLANNED_CHIP_OPTIONS:
            with self.subTest(chip=chip):
                text = chip_plan_copy(chip, 7)
                self.write_package("my_plan_chip_render.json", {"text": text, "passed": True})
                files = self.namespace["vx_export_narration_scripts"]()
                self.assertEqual(files, [str(self.export_directory / "Slide_05C_My_Plan_Chip.txt")])
                self.assertEqual(Path(files[0]).read_text(encoding="utf-8"), text)

    def test_review_roll_transfer_and_shared_narration_stay_exact(self) -> None:
        self.namespace["SELECTED_SCENES"] = [
            "gw_review", "05a_my_plan_roll", "05b_my_plan_transfer", "05_outro",
        ]
        for filename in (
            "gw_review_package.json", "my_plan_5a_roll_package.json", "my_plan_5b_transfer_package.json",
        ):
            self.write_package(filename, {"segments": [{"text": "First."}, {"text": "Second!"}]})
        self.write_package("other_scenes_narration.json", {"05_outro": {"script": "Goodbye!"}})
        files = self.namespace["vx_export_narration_scripts"]()
        self.assertEqual(len(files), 4)
        for filename in files:
            expected = "Goodbye!" if Path(filename).name == "Slide_08_Outro.txt" else "First.\n\nSecond!"
            self.assertEqual(Path(filename).read_text(encoding="utf-8"), expected)

    def test_final_cleanup_preserves_the_selected_chip_png(self) -> None:
        self.slide_directory.mkdir(parents=True)
        chip_png = self.slide_directory / "my_plan_chip_scene_4k.png"
        chip_png.write_bytes(b"selected chip PNG")
        unselected = self.slide_directory / "my_plan_5a_roll_scene_4k.png"
        unselected.write_bytes(b"unselected PNG")
        self.write_package("my_plan_chip_render.json", {"text": "Exact chip narration."})
        self.namespace["vx_finish_clean_exports"]()
        self.assertTrue(chip_png.exists())
        self.assertFalse(unselected.exists())

    def test_unknown_selected_scenes_still_fail_partial_export(self) -> None:
        self.namespace["SELECTED_SCENES"] = ["unknown_scene"]
        with self.assertRaisesRegex(RuntimeError, "Unknown selected slide: unknown_scene"):
            self.namespace["vx_export_narration_scripts"](available_only=True)

    def test_empty_chip_narration_still_fails_final_export(self) -> None:
        for text in (None, "", "   "):
            with self.subTest(text=text):
                self.write_package("my_plan_chip_render.json", {"text": text})
                with self.assertRaisesRegex(RuntimeError, "Narration not generated for: 05c_my_plan_chip"):
                    self.namespace["vx_export_narration_scripts"]()

    def test_changed_export_schema_fails_during_preflight(self) -> None:
        source = self.export_source.replace(" '05b_my_plan_transfer':", " 'renamed_transfer':", 1)
        with self.assertRaisesRegex(RuntimeError, "planned chip export registration"):
            runner._patch_narration_exports(source)


class PitchRevealTests(unittest.TestCase):
    def setUp(self) -> None:
        self.segments = [
            {"player_id": 1, "kind": "starter", "hero_off": 10.0},
            {"player_id": 229, "kind": "starter", "hero_off": 20.0},
            {"player_id": 2, "kind": "bench", "hero_off": 5.0},
        ]

    def test_pitch_stays_empty_through_first_hero_exit(self) -> None:
        for time in (0.0, 9.9, 10.0):
            self.assertEqual(runner._expected_pitch_player_count(self.segments, time, .42), 0)

    def test_cubic_entrance_is_visible_before_linear_halfway_cutoff(self) -> None:
        # At 25% elapsed, ease-out opacity is .578125, already above the DOM's .5.
        self.assertEqual(runner._expected_pitch_player_count(self.segments, 10.105, .42), 1)

    def test_dom_visibility_threshold_is_strict(self) -> None:
        self.assertEqual(runner._expected_pitch_player_count(self.segments, 10.08, .42), 0)
        self.assertEqual(runner._expected_pitch_player_count(self.segments, 10.09, .42), 1)

    def test_later_starter_and_bench_do_not_reveal_early(self) -> None:
        self.assertEqual(runner._expected_pitch_player_count(self.segments, 20.0, .42), 1)
        self.assertEqual(runner._expected_pitch_player_count(self.segments, 20.105, .42), 2)
        self.assertEqual(runner._expected_pitch_player_count(self.segments, 100.0, .42), 2)

    def test_changed_renderer_fails_preflight(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "Pitch reveal audit"):
            runner._patch_pitch_reveal_audit("expected = 0")


class BenchingNarrationTests(unittest.TestCase):
    # Production's three factual sentence templates, with explicit test inputs.
    source = '''
def narrate(name, team, defender=True, multiple=False):
    lead = f"{name} from {team} leads the group."
    matchup, fdr, xpts = "Arsenal at home", 3.5, 4.2
    line = f"{lead} {matchup} is rated {fdr:.1f}, with a {xpts:.1f}-point projection."
    per_fixture = " per fixture" if multiple else ""
    if defender:
        cs = 43.0
        line += f" {team} have a {cs:.0f} percent clean-sheet chance{per_fixture}."
    else:
        goals = 1.7
        horizon = " across those fixtures" if multiple else ""
        line += f" {team} are expected to score {goals:.1f} goals{horizon}."
    return line
'''

    def setUp(self) -> None:
        namespace = {}
        exec(runner._patch_benching_narration(self.source), namespace)
        self.narrate = namespace["narrate"]

    def assert_no_duplicate_sentences(self, text: str) -> None:
        sentences = [part.strip().casefold() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]
        self.assertEqual(len(sentences), len(set(sentences)))

    def test_clubmate_defenders_keep_equal_probabilities_without_duplicate_prose(self) -> None:
        text = self.narrate("Senesi", "Bournemouth") + " " + self.narrate("Truffert", "Bournemouth")
        self.assert_no_duplicate_sentences(text)
        self.assertEqual(text.count("43 percent clean-sheet chance"), 2)
        for name in ("Senesi", "Truffert"):
            self.assertEqual(text.count(f"{name} from Bournemouth"), 1)
            self.assertIn(f"For {name}, Bournemouth have a 43 percent", text)

    def test_clubmate_attackers_keep_equal_goal_projections(self) -> None:
        text = self.narrate("Kluivert", "Bournemouth", False) + " " + self.narrate("Semenyo", "Bournemouth", False)
        self.assert_no_duplicate_sentences(text)
        self.assertEqual(text.count("expected to score 1.7 goals"), 2)

    def test_multiple_fixture_qualifiers_are_preserved(self) -> None:
        self.assertIn("43 percent clean-sheet chance per fixture.", self.narrate("Senesi", "Bournemouth", multiple=True))
        self.assertIn("1.7 goals across those fixtures.", self.narrate("Kluivert", "Bournemouth", False, True))

    def test_changed_templates_fail_preflight(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "Benching narration"):
            runner._patch_benching_narration(self.source.replace("clean-sheet chance", "defensive outlook"))


class RyanProfileTests(unittest.TestCase):
    source = '''VOICE = "en-GB-RyanNeural"
# Ryan delivery — keep the project's intended/original speaking profile.
# Mood labels remain useful for manifests and scene semantics, but they must not
# speed Ryan up or slow him down simply to force a target video duration.
# Punctuation and script structure provide emphasis; TTS speed stays constant.
RYAN_BASE_PROFILE = {"rate": "+12%", "pitch": "-5Hz", "volume": "+0%"}

MOODS = {
    "intro":    dict(RYAN_BASE_PROFILE),
    "analysis": dict(RYAN_BASE_PROFILE),
    "key_stat": dict(RYAN_BASE_PROFILE),
    "warning":  dict(RYAN_BASE_PROFILE),
    "outro":    dict(RYAN_BASE_PROFILE),
}

def vx_tts_profile(mood="analysis"):
    if mood not in MOODS:
        raise KeyError(f"Unknown TTS mood: {mood}")
    return dict(MOODS[mood])

'''

    def setUp(self) -> None:
        self.namespace: dict[str, Any] = {}
        exec(runner._patch_tts_profile(self.source), self.namespace)

    def test_all_moods_match_day2_effective_production_profiles(self) -> None:
        expected = {
            "intro": {"rate": "+13%", "pitch": "-4Hz", "volume": "+0%"},
            "analysis": {"rate": "+17%", "pitch": "-4Hz", "volume": "+0%"},
            "key_stat": {"rate": "+18%", "pitch": "+0Hz", "volume": "+0%"},
            "warning": {"rate": "+11%", "pitch": "-4Hz", "volume": "+0%"},
            "outro": {"rate": "+11%", "pitch": "-4Hz", "volume": "+0%"},
        }
        self.assertEqual(self.namespace["VOICE"], "en-GB-RyanNeural")
        self.assertEqual(self.namespace["MOODS"], expected)
        for mood, profile in expected.items():
            with self.subTest(mood=mood):
                self.assertEqual(self.namespace["vx_tts_profile"](mood), profile)

    def test_callers_cannot_mutate_shared_profiles(self) -> None:
        profile = self.namespace["vx_tts_profile"]("analysis")
        profile["rate"] = "+99%"
        self.assertEqual(self.namespace["vx_tts_profile"]("analysis")["rate"], "+17%")
        self.namespace["MOODS"]["intro"]["pitch"] = "+99Hz"
        self.assertEqual(self.namespace["MOODS"]["analysis"]["pitch"], "-4Hz")
        self.assertEqual(self.namespace["RYAN_BASE_PROFILE"]["pitch"], "-4Hz")

    def test_unknown_mood_remains_an_error(self) -> None:
        with self.assertRaises(KeyError):
            self.namespace["vx_tts_profile"]("unknown")

    def test_patch_preserves_surrounding_synthesis_and_timing_code(self) -> None:
        prefix = "# synthesis transport and word boundaries before profile\n"
        suffix = "\n# audio synthesis and measured duration after profile\n"
        updated = runner._patch_tts_profile(prefix + self.source + suffix)
        self.assertTrue(updated.startswith(prefix))
        self.assertTrue(updated.endswith(suffix))
        self.assertEqual(updated.replace(
            '''# Match Day 2's effective production profiles, including its runtime rate overrides.
# Keep volume flat; synthesis still supplies the timing used by every scene.
RYAN_BASE_PROFILE = {"rate": "+17%", "pitch": "-4Hz", "volume": "+0%"}

MOODS = {
    "intro":    dict(RYAN_BASE_PROFILE, rate="+13%"),
    "analysis": dict(RYAN_BASE_PROFILE),
    "key_stat": dict(RYAN_BASE_PROFILE, rate="+18%", pitch="+0Hz"),
    "warning":  dict(RYAN_BASE_PROFILE, rate="+11%"),
    "outro":    dict(RYAN_BASE_PROFILE, rate="+11%"),
}''',
            '''# Ryan delivery — keep the project's intended/original speaking profile.
# Mood labels remain useful for manifests and scene semantics, but they must not
# speed Ryan up or slow him down simply to force a target video duration.
# Punctuation and script structure provide emphasis; TTS speed stays constant.
RYAN_BASE_PROFILE = {"rate": "+12%", "pitch": "-5Hz", "volume": "+0%"}

MOODS = {
    "intro":    dict(RYAN_BASE_PROFILE),
    "analysis": dict(RYAN_BASE_PROFILE),
    "key_stat": dict(RYAN_BASE_PROFILE),
    "warning":  dict(RYAN_BASE_PROFILE),
    "outro":    dict(RYAN_BASE_PROFILE),
}''',
            1,
        ), prefix + self.source + suffix)

    def test_changed_or_duplicate_notebook_profile_is_rejected(self) -> None:
        for invalid in (
            self.source.replace('"rate": "+12%"', '"rate": "+99%"'),
            self.source + self.source,
        ):
            with self.subTest(source_length=len(invalid)):
                with self.assertRaisesRegex(RuntimeError, "TTS profile"):
                    runner._patch_tts_profile(invalid)


class NotebookPreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.notebook_path = self.root / "notebook.ipynb"
        self.patch_stack = ExitStack()
        self.addCleanup(self.patch_stack.close)
        for function_name in (
            "_patch_control_cell",
            "_patch_narration_exports",
            "_patch_outro_social_icon",
            "_patch_tts_profile",
            "patch_narration_pacing_source",
            "patch_popup_audio_source",
            "patch_evidence_pipeline",
            "_patch_transition_titles",
            "_patch_player_card_sample",
            "_patch_narration_tone",
            "_patch_pitch_card_entrance",
            "_patch_pitch_reveal_audit",
            "_patch_benching_narration",
            "_patch_full_word_abbreviation_normalization",
            "_patch_pitch_player_names",
            "_patch_shared_card_scene_checks",
            "_patch_defcon_team_numeric_fit",
            "_patch_defcon_render_preflight",
            "_patch_defcon_gameweek_contract",
            "_patch_defcon_card_motion",
            "_patch_elite_template_parser",
            "patch_transfer_desk_source",
            "patch_transfer_desk_audio_source",
            "patch_transfer_desk_animation_source",
            "remove_shortlist_cell",
        ):
            self.patch_stack.enter_context(patch.object(runner, function_name, side_effect=lambda *args: args[-1]))

    def write_notebook(self, overrides: dict[int, str]) -> None:
        cells = [
            {"cell_type": "code", "source": overrides.get(index, "pass\n")}
            for index in range(37)
        ]
        self.notebook_path.write_text(json.dumps({"cells": cells}), encoding="utf-8")

    def test_late_syntax_error_prevents_all_execution(self) -> None:
        marker = self.root / "executed.txt"
        self.write_notebook({
            0: f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n",
            36: "def unfinished(\n",
        })
        with patch.object(runner.InteractiveShell, "instance") as create_shell:
            with self.assertRaises(SyntaxError):
                runner.run_notebook(self.notebook_path)
        self.assertFalse(marker.exists())
        create_shell.assert_not_called()

    def test_preflight_supports_notebook_commands_and_async_cells(self) -> None:
        self.write_notebook({
            0: "import asyncio\nawait asyncio.sleep(0)\n",
            2: "!echo notebook-command\n",
        })
        self.assertEqual(len(runner._prepare_code_cells(self.notebook_path)), 37)


class DefconNumericRegressionTests(unittest.TestCase):
    def test_renderer_fits_after_timeline_ready_but_before_clip_audit(self) -> None:
        original = (
            "        await vx_apply_render_scale(page, W, H, DESIGN_W, DESIGN_H)\n\n"
            '        if key == "03_defcon":\n'
            "            # Audit the states the viewer will actually see\n"
        )
        updated = runner._patch_defcon_render_preflight(original)
        self.assertIn(
            'if key == "03_defcon":\n'
            '            await page.evaluate("() => { window.__vxDefconRenderScaleReady = true; }")\n'
            "            await vx_prepare_capture(page)\n"
            "            # Audit",
            updated,
        )
        self.assertEqual(updated.count("await vx_prepare_capture(page)"), 1)

    def test_renderer_patch_refuses_an_unknown_notebook(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "expected one renderer entry point"):
            runner._patch_defcon_render_preflight("pass\n")

    def test_forecast_fit_runs_before_premium_layout_validation(self) -> None:
        source = (
            "  const assertDefconBoardFit=()=>{};\n"
            "  const prepare=window.vxPrepareCapture;\n"
            "  window.vxPrepareCapture=async(...args)=>{\n"
            "    await window.vxDefconCardsReady;\n"
            "    const result=prepare ? await prepare(...args) : (window.vxLayoutReport ? window.vxLayoutReport() : {passed:true});\n"
            "    assertDefconBoardFit();\n"
            "    return result;\n"
            "  };\n"
        )
        updated = runner._patch_defcon_team_numeric_fit(source)
        self.assertLess(
            updated.index("fitDefconTeamForecasts();"),
            updated.index("result = prepare ? await prepare(...args)"),
        )
        self.assertIn("await document.fonts.ready;", updated)
        self.assertIn("window.__ready === true", updated)
        self.assertIn("window.__vxDefconRenderScaleReady === true", updated)
        self.assertIn("!window.__vxDefconTeamNumbersFitted", updated)
        self.assertIn("window.__vxDefconTeamNumbersFitted = true", updated)
        self.assertIn("window.__seek(0);", updated)
        self.assertIn("finally {", updated)
        self.assertIn("captured in a closure", updated)


if __name__ == "__main__":
    unittest.main()

