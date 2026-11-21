import json
from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PIL import Image

from vortex.day1_final_scenes import SCENE_KEYS, capture_scene_evidence, scene_timeline
from vortex.youtube_studio_package import _vx23_metadata, _vx23_probe_video


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
            "1:55 The Numbers Behind the Points", "3:15 Market Outlook",
            "4:40 The Value Board",
        ])

    def test_missing_sections_and_wrong_video_length_fail(self):
        with self.assertRaisesRegex(RuntimeError, "duration does not match"):
            scene_timeline(self.qa, 160)
        self.qa["sections"].pop(2)
        with self.assertRaisesRegex(RuntimeError, "all five scenes"):
            scene_timeline(self.qa, 325)

    @staticmethod
    def _probe_result(*, with_audio=True, rate="30/1"):
        streams = [{
            "codec_type": "video",
            "codec_name": "h264",
            "width": 3840,
            "height": 2160,
            "avg_frame_rate": rate,
        }]
        if with_audio:
            streams.append({"codec_type": "audio", "codec_name": "aac"})
        return SimpleNamespace(stdout=json.dumps({
            "streams": streams, "format": {"duration": "325.0"}
        }))

    def test_final_mp4_probe_requires_audible_stream_metadata(self):
        with patch("vortex.youtube_studio_package.subprocess.run",
                   return_value=self._probe_result(with_audio=False)):
            with self.assertRaisesRegex(RuntimeError, "audio"):
                _vx23_probe_video(Path("day1.mp4"))

    def test_final_mp4_probe_accepts_video_and_audio_tracks(self):
        with patch("vortex.youtube_studio_package.subprocess.run",
                   return_value=self._probe_result()) as run:
            probe = _vx23_probe_video(Path("day1.mp4"))
        self.assertEqual(probe["width"], 3840)
        self.assertEqual(probe["height"], 2160)
        self.assertEqual(probe["audio_codec"], "aac")
        self.assertEqual(probe["fps"], 30.0)
        self.assertNotIn("-select_streams", run.call_args.args[0])

    def test_final_mp4_probe_rejects_invalid_frame_rate(self):
        with patch("vortex.youtube_studio_package.subprocess.run",
                   return_value=self._probe_result(rate="0/1")):
            with self.assertRaisesRegex(RuntimeError, "frame rate"):
                _vx23_probe_video(Path("day1.mp4"))

    def test_youtube_metadata_rejects_nonconsecutive_gameweeks(self):
        timeline = scene_timeline(self.qa, 325)
        with self.assertRaisesRegex(RuntimeError, "consecutive"):
            _vx23_metadata(11, 9, "FINAL", timeline)
        self.assertEqual(_vx23_metadata(38, 37, "FINAL", timeline)["preview_gw"], 38)

    def test_identical_frames_fail(self):
        def write_frame(command, **kwargs):
            Image.new("L", (3840, 2160), 128).save(command[-1])

        timeline = scene_timeline(self.qa, 325)
        with TemporaryDirectory() as folder, patch(
            "vortex.day1_final_scenes.subprocess.run", side_effect=write_frame
        ):
            with self.assertRaisesRegex(RuntimeError, "duplicates another scene"):
                capture_scene_evidence(Path("final.mp4"), timeline, Path(folder))
