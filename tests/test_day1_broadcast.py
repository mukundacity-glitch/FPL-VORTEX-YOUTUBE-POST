import unittest

from vortex.day1_broadcast import scene_manifest


class Day1BroadcastTests(unittest.TestCase):
    reports = [
        {"key": key, "duration": duration}
        for key, duration in zip(
            ("00_intro", "gw_review", "02_fdr", "03_projected_goals"),
            (38.5, 180, 85.5, 240),
        )
    ]

    def test_current_labels_and_media_durations(self):
        for review in (10, 24):
            scenes = scene_manifest(
                self.reports, review, review + 1, 24, "logo",
                review_status="FINAL", latest_completed=review,
            )
            self.assertEqual([s["label"] for s in scenes],
                             [f"GW{review+1}", f"GW{review}", f"GW{review+1}", f"GW{review+1}"])
            self.assertEqual([s["frames"] for s in scenes], [924, 4320, 2052, 5760])
            self.assertEqual([s["number"] for s in scenes], [1, 2, 3, 4])

    def test_five_scene_manifest_only_when_fifth_report_exists(self):
        board = {"nextGameweek": 11, "starters": [{} for _ in range(11)],
                 "bench": [{} for _ in range(4)]}
        reports = self.reports + [{"key": "04_value_board", "duration": 60,
                                   "value_board": board}]
        scenes = scene_manifest(reports, 10, 11, 24, "logo",
                                review_status="FINAL", latest_completed=10)
        self.assertEqual([s["number"] for s in scenes], [1, 2, 3, 4, 5])
        self.assertEqual(scenes[4]["valueBoard"], board)
        self.assertEqual(scenes[4]["label"], "GW11")
        with self.assertRaisesRegex(ValueError, "gameweek disagree"):
            scene_manifest(self.reports + [{"key": "04_value_board", "duration": 60,
                                           "value_board": dict(board, nextGameweek=12)}],
                           10, 11, 24, "logo", review_status="FINAL", latest_completed=10)

    def test_stale_and_provisional_reviews_fail(self):
        for review, status in ((9, "FINAL"), (10, "LIVE/PARTIAL")):
            with self.assertRaises(ValueError):
                scene_manifest(
                    self.reports, review, 11, 24, "logo",
                    review_status=status, latest_completed=10,
                )
