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

    def test_stale_and_provisional_reviews_fail(self):
        for review, status in ((9, "FINAL"), (10, "LIVE/PARTIAL")):
            with self.assertRaises(ValueError):
                scene_manifest(
                    self.reports, review, 11, 24, "logo",
                    review_status=status, latest_completed=10,
                )
