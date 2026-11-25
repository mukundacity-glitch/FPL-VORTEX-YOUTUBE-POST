import copy
import json
import unittest
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import requests

from day3.frozen_fpl import FrozenFPL
from day3.live_evidence import SourceChanged, assert_snapshot_current, build_evidence
from day3.test_live_evidence import sample_inputs
from day3.verify_evidence import finalize_evidence_bundle, verify_bundle, verify_with_recovery


class FrozenFPLTests(unittest.TestCase):
    def test_official_clients_share_frozen_responses_and_never_fetch_during_render(self):
        snapshot = {"_bootstrap": {"events": [1]}, "fixtures": [], "_event_payloads": {1: {}}}
        frozen = FrozenFPL(snapshot)
        base = "https://fantasy.premierleague.com/api"
        looked_up = []

        def send(_session, request, **kwargs):
            looked_up.append(request.url)
            response = requests.Response()
            response.status_code = 200
            response._content = b'{"picks":[11]}'
            response._content_consumed = True
            return response

        with patch.object(requests.Session, "send", send), frozen.installed():
            self.assertEqual(requests.get(base + "/bootstrap-static/?_vx=1").json(), snapshot["_bootstrap"])
            with urllib.request.urlopen(base + "/fixtures/?_vortex=2") as response:
                self.assertEqual(json.load(response), [])
            url = base + "/entry/99/event/1/picks/"
            self.assertEqual(requests.get(url + "?_vx=3").json(), {"picks": [11]})
            self.assertEqual(len(frozen.seal()), 64)
            self.assertEqual(requests.get(url + "?_vx=4").json(), {"picks": [11]})
            with self.assertRaisesRegex(RuntimeError, "uncaptured official FPL endpoint"):
                requests.get(base + "/entry/100/event/1/picks/")
            with self.assertRaisesRegex(RuntimeError, "uncaptured FPL endpoints"):
                frozen.verify()
        self.assertEqual(looked_up, [url + "?_vx=3"])


class PublishedVideoEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.bootstrap, self.fixtures, live, cutoff = sample_inputs()
        self.bootstrap["elements"][0]["web_name"] = "Alex Same"
        self.bootstrap["elements"][1]["web_name"] = "Jamie Same"
        self.snapshot = build_evidence(self.bootstrap, self.fixtures, live, cutoff)
        self.snapshot["_bootstrap"] = copy.deepcopy(self.bootstrap)
        self.snapshot["frozen_endpoint_hash"] = "a" * 64

    def loader(self, path):
        return self.bootstrap if path == "/bootstrap-static/" else self.fixtures

    def seal(self, root):
        for subdir in ("DATA", "MP4"):
            (root / subdir).mkdir()
        (root / "MP4" / "COMBINED.mp4").write_bytes(b"test-video")
        script = root / "DATA" / "plan.txt"
        script.write_text("Alex Same starts.", encoding="utf-8")
        finalize_evidence_bundle({
            "OUTPUT_ROOT": root, "DAY3_EVIDENCE": self.snapshot,
            "vx_export_narration_scripts": lambda **_: [script],
            "SLIDE_SELECTION": {"05a_my_plan_roll": True},
            "DAY3_MY_PLAN_5A_PACKAGE": {"summary": {"current_squad_ids": [11], "captain_id": 11}},
        })

    def test_unrelated_player_and_score_lock_updates_do_not_restart_render(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self.seal(root)
            self.bootstrap["elements"][1].update(status="i", chance_of_playing_next_round=0, minutes=40)
            self.bootstrap["events"][0].update(data_checked=False)
            verify_bundle(root, self.loader)
            self.bootstrap["elements"][0].update(status="i", chance_of_playing_next_round=0)
            with self.assertRaisesRegex(SourceChanged, r"player 11 \(availability\)"):
                verify_bundle(root, self.loader)

    def test_rescheduled_fixture_and_missing_watched_player_are_identified(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self.seal(root)
            self.fixtures[1]["kickoff_time"] = "2030-01-01T15:00:00Z"
            self.bootstrap["elements"].pop(0)
            with self.assertRaisesRegex(SourceChanged, r"player 11 removed; fixture 2 \(kickoff_time\)"):
                verify_bundle(root, self.loader)

    def test_scope_cannot_be_changed_after_sealing(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self.seal(root)
            path = root / "DATA" / "day3_live_evidence.json"
            record = json.loads(path.read_text())
            record["video_source_state"]["player"].clear()
            path.write_text(json.dumps(record))
            with self.assertRaisesRegex(RuntimeError, "snapshot was changed"):
                verify_bundle(root, self.loader)

    def test_expired_deadline_blocks_before_a_live_request_or_retry(self):
        self.snapshot["deadline"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        loader, rerender = Mock(), Mock()
        with patch("day3.verify_evidence.verify_bundle", side_effect=lambda *a, **k:
                   assert_snapshot_current(self.snapshot, loader)):
            with self.assertRaisesRegex(RuntimeError, "deadline has passed"):
                verify_with_recovery(Path("."), rerender)
        loader.assert_not_called()
        rerender.assert_not_called()

    def test_only_the_relevant_change_triggers_recovery(self):
        with TemporaryDirectory() as first, TemporaryDirectory() as second:
            root = Path(first)
            recovered = Path(second)
            self.seal(root)
            self.bootstrap["elements"][0]["status"] = "i"
            calls = []

            def rerender(target):
                calls.append(target)
                self.snapshot["_bootstrap"] = copy.deepcopy(self.bootstrap)
                self.seal(recovered)
                for file in (recovered / "DATA").iterdir():
                    file.replace(root / "DATA" / file.name)
                self.bootstrap["elements"][1]["status"] = "s"

            with patch("day3.verify_evidence.verify_bundle", side_effect=lambda path, **kwargs:
                       verify_bundle(path, self.loader, **kwargs)):
                verify_with_recovery(root, rerender)
            self.assertEqual(calls, [(self.snapshot["next_gw"], self.snapshot["deadline"])])


if __name__ == "__main__":
    unittest.main()
