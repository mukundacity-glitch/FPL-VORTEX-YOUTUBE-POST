import unittest
from datetime import datetime, timezone
from email.message import Message
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError

from vortex.day1_preflight import NotReady, drive_credentials, fetch_json, require_final_review, verify_environment
from vortex.youtube_private_upload import _youtube_service


class Day1PreflightTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 23, 3, 29, tzinfo=timezone.utc)
        self.events = [
            dict(id=10, deadline_time="2026-11-06T18:30:00Z", finished=True, data_checked=True),
            dict(id=11, deadline_time="2026-11-21T11:00:00Z", is_current=True,
                 finished=False, data_checked=False),
            dict(id=12, deadline_time="2026-11-27T18:30:00Z", is_next=True),
        ]
        self.bootstrap = dict(events=self.events, elements=[{"id": 1}],
                              teams=[{"id": 1}], element_types=[{"id": 1}])
        self.fixtures = [
            dict(id=i, event=11, started=True, minutes=90, finished=False,
                 finished_provisional=True, team_h_score=0, team_a_score=0)
            for i in range(1, 10)
        ]
        self.fixtures += [
            dict(id=10, event=11, started=None, minutes=0, finished=False,
                 finished_provisional=False, team_h_score=None, team_a_score=None,
                 kickoff_time="2026-11-23T20:00:00Z"),
            dict(id=11, event=12, started=False),
        ]

    def check(self):
        return require_final_review(self.bootstrap, self.fixtures, now=self.now)

    def test_incident_nine_of_ten_prevents_render(self):
        with self.assertRaisesRegex(NotReady, r"GW11.*9/10.*data_checked=False.*20:00:00Z"):
            self.check()

    def test_full_time_without_score_lock_still_waits(self):
        self.fixtures[9].update(started=True, minutes=90, team_h_score=0,
                                team_a_score=0, finished_provisional=True)
        with self.assertRaisesRegex(NotReady, r"10/10.*data_checked=False"):
            self.check()

    def test_settled_zero_goal_week_passes_without_ten_match_requirement(self):
        self.events[1].update(finished=True, data_checked=True)
        self.fixtures.pop(9)
        for fixture in self.fixtures[:-1]:
            fixture["finished"] = True
        self.assertEqual(self.check()[:2], (11, 12))
        self.events[2]["is_next"] = None
        self.assertEqual(self.check()[:2], (11, 12))

    def test_missing_fixtures_or_no_preview_is_explicit(self):
        self.fixtures = [self.fixtures[-1]]
        with self.assertRaisesRegex(NotReady, r"GW11.*0/0"):
            self.check()
        self.events.pop()
        with self.assertRaisesRegex(NotReady, "No upcoming official Gameweek"):
            self.check()

    def test_retry_respects_retry_after_then_handles_server_failure(self):
        headers = Message()
        headers["Retry-After"] = "7"
        failures = [
            HTTPError("https://example.invalid", 429, "quota", headers, BytesIO()),
            HTTPError("https://example.invalid", 503, "unavailable", Message(), BytesIO()),
            BytesIO(b'{"events": []}'),
        ]
        with patch("vortex.day1_preflight.urlopen", side_effect=failures), patch(
            "vortex.day1_preflight.time.sleep"
        ) as sleep:
            self.assertEqual(fetch_json("/bootstrap-static/"), {"events": []})
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [7, 4])

    def test_nonretryable_error_has_status_and_endpoint(self):
        error = HTTPError("https://example.invalid", 403, "forbidden", Message(), BytesIO())
        with patch("vortex.day1_preflight.urlopen", side_effect=error) as open_url:
            with self.assertRaisesRegex(RuntimeError, r"/fixtures/.*HTTP 403"):
                fetch_json("/fixtures/")
        open_url.assert_called_once()

    def test_missing_credentials_do_not_make_a_network_request(self):
        with patch.dict("os.environ", {}, clear=True), patch("vortex.day1_preflight.urlopen") as open_url:
            with self.assertRaisesRegex(RuntimeError, "GOOGLE_OAUTH_REFRESH_TOKEN"):
                drive_credentials()
            with self.assertRaisesRegex(RuntimeError, "YOUTUBE_OAUTH_REFRESH_TOKEN"):
                _youtube_service()
        open_url.assert_not_called()

    def test_rejected_drive_token_reports_reason_without_printing_token(self):
        error = HTTPError("https://oauth2.googleapis.com/token", 400, "Bad Request", Message(),
                          BytesIO(b'{"error":"invalid_grant","error_description":"do not log"}'))
        values = dict(GOOGLE_OAUTH_CLIENT_ID="test.apps.googleusercontent.com",
                      GOOGLE_OAUTH_CLIENT_SECRET="test", GOOGLE_OAUTH_REFRESH_TOKEN="test")
        with patch.dict("os.environ", values, clear=True), patch(
            "vortex.day1_preflight.urlopen", side_effect=error,
        ) as open_url:
            with self.assertRaisesRegex(RuntimeError, r"HTTP 400 \(invalid_grant\)") as captured:
                drive_credentials()
        self.assertNotIn("do not log", str(captured.exception))
        open_url.assert_called_once()

    def test_preview_date_rollover_or_reschedule_blocks_publish(self):
        initial = dict(VORTEX_DAY1_REVIEW_GW="11", VORTEX_DAY1_PREVIEW_GW="12",
                       VORTEX_DAY1_PREVIEW_DEADLINE="2026-11-27T18:30:00+00:00")
        with patch.dict("os.environ", initial, clear=True):
            verify_environment(11, 12, datetime.fromisoformat(initial["VORTEX_DAY1_PREVIEW_DEADLINE"]))
            with self.assertRaisesRegex(NotReady, "identity changed"):
                verify_environment(12, 13, datetime(2026, 11, 29, tzinfo=timezone.utc))
