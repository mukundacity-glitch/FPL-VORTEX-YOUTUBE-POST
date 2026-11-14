from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PIL import Image

from vortex.day1_final_scenes import SCENE_KEYS, capture_scene_evidence, scene_timeline
from vortex.youtube_studio_package import _vx23_metadata


class FinalSceneTests(unittest.TestCase):
    def setUp(self):
        self.qa = {"scene_keys": list(SCENE_KEYS), "sections": [
            {"key": key, "duration": seconds}
            for key, seconds in zip(SCENE_KEYS, (25, 90, 80, 85, 45))
        ]}

    def test_chapters_include_all_five_scenes_at_their_measured_starts(self):
        timeline = scene_timeline(self.qa, 325)
        metadata = _vx23_metadata(11, 10, "FINAL", timeline)
        self.assertEqual(metadata["chapters"], [
            "0:00 The Gameweek Brief", "0:25 GW10 Review — The Real Story",
            "1:55 The Numbers Behind the Points", "3:15 Players & Fixtures and Market Outlook",
            "4:40 The Value Board",
        ])

    def test_missing_sections_and_wrong_video_length_fail(self):
        with self.assertRaisesRegex(RuntimeError, "duration does not match"):
            scene_timeline(self.qa, 160)
        self.qa["sections"].pop(2)
        with self.assertRaisesRegex(RuntimeError, "all five scenes"):
            scene_timeline(self.qa, 325)

    def test_identical_frames_fail(self):
        def write_frame(command, **kwargs):
            Image.new("L", (3840, 2160), 128).save(command[-1])

        timeline = scene_timeline(self.qa, 325)
        with TemporaryDirectory() as folder, patch(
            "vortex.day1_final_scenes.subprocess.run", side_effect=write_frame
        ):
            with self.assertRaisesRegex(RuntimeError, "duplicates another scene"):
                capture_scene_evidence(Path("final.mp4"), timeline, Path(folder))
