import unittest
from unittest.mock import patch

from vortex.day1_schedule_gate import evaluate
from vortex.day1_scheduler import title, dispatch


def case():
    events = [
        {"id": gw, "is_next": gw == 11, "finished": gw == 10,
         "data_checked": gw == 10, "deadline_time": "2026-11-01T12:00:00Z"}
        for gw in range(10, 16)
    ]
    fixtures = [
        {"id": gw * 100 + i, "event": gw, "team_h": 2 * i + 1,
         "team_a": 2 * i + 2, "finished": gw == 10,
         "team_h_score": 1 if gw == 10 else None,
         "team_a_score": 0 if gw == 10 else None}
        for gw in range(10, 16) for i in range(10)
    ]
    bootstrap = {
        "events": events, "teams": [{"id": i} for i in range(1, 21)],
        "elements": [{"id": i, "now_cost": 45} for i in range(1, 201)],
    }
    return bootstrap, fixtures


class Day1SchedulerTests(unittest.TestCase):
    def test_ready_only_after_official_scores_checked(self):
        bootstrap, fixtures = case()
        report = evaluate(bootstrap, fixtures)
        self.assertTrue(report["ready"])
        self.assertEqual(report["production_identity"], "2026-27-review-GW10-preview-GW11")
        self.assertEqual(report["completed_fixtures"], 10)
        self.assertEqual(report["future_fixtures"], 50)

    def test_provisional_final_is_not_authoritative(self):
        bootstrap, fixtures = case()
        bootstrap["events"][0]["data_checked"] = False
        self.assertFalse(evaluate(bootstrap, fixtures)["ready"])

    def test_incomplete_match_blocks_generation(self):
        bootstrap, fixtures = case()
        fixtures[0]["finished"] = False
        self.assertFalse(evaluate(bootstrap, fixtures)["ready"])

    def test_future_horizon_must_exist(self):
        bootstrap, fixtures = case()
        bootstrap["events"].pop()
        self.assertFalse(evaluate(bootstrap, fixtures)["ready"])

    def test_snapshot_version_changes_on_official_price_update(self):
        bootstrap, fixtures = case()
        original = evaluate(bootstrap, fixtures)["snapshot_version"]
        bootstrap["elements"][0]["now_cost"] = 50
        self.assertNotEqual(original, evaluate(bootstrap, fixtures)["snapshot_version"])

    def test_identity_rejects_user_controlled_input(self):
        with self.assertRaises(ValueError):
            title("fake; gh workflow run")

    @patch("vortex.day1_scheduler.find_issue")
    @patch("vortex.day1_scheduler.runs")
    @patch("vortex.day1_scheduler.upsert")
    @patch("vortex.day1_scheduler.subprocess.run")
    @patch.dict("os.environ", {"GITHUB_REPOSITORY": "owner/repo"}, clear=True)
    def test_successful_prior_run_never_dispatches(self, run, upsert, workflow_runs, issue):
        issue.return_value = None
        workflow_runs.return_value = [
            {"display_title": "FPL VORTEX DAY 1 | 2026-27-review-GW10-preview-GW11",
             "status": "completed", "conclusion": "success", "head_branch": "main"}
        ]
        report = evaluate(*case())
        dispatch(report)
        run.assert_not_called()
        self.assertTrue(upsert.called)


if __name__ == "__main__":
    unittest.main()
