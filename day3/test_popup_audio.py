from __future__ import annotations

import array
import math
import shutil
import subprocess
import unittest

from day3.popup_audio import popup_audio_filters, patch_popup_audio_source


class PopupAudioTests(unittest.TestCase):
    def test_silent_popup_needs_no_audio_stream(self) -> None:
        self.assertEqual(popup_audio_filters(1, [{"start": 2}], 1, False),
                         ["[a_without_popup]anull[a_master]"])
        self.assertEqual(popup_audio_filters(1, [], 1, True),
                         ["[a_without_popup]anull[a_master]"])

    def test_invalid_timing_is_rejected(self) -> None:
        for duration in (0, -1, math.inf, math.nan):
            with self.subTest(duration=duration), self.assertRaises(ValueError):
                popup_audio_filters(1, [{"start": 0}], duration, True)
        for start in (-1, math.inf, math.nan):
            with self.subTest(start=start), self.assertRaises(ValueError):
                popup_audio_filters(1, [{"start": start}], 1, True)
        with self.assertRaisesRegex(RuntimeError, "source contract changed"):
            patch_popup_audio_source("pass\n")

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg is required")
    def test_real_mix_preserves_master_and_repeats_chime_at_video_times(self) -> None:
        for starts in ([0.5], [0.5, 2.25]):
            with self.subTest(starts=starts):
                filters = ["[0:a]anull[a_without_popup]"] + popup_audio_filters(
                    1, [{"start": start} for start in starts], 0.5, True,
                )
                result = subprocess.run(
                    ["ffmpeg", "-nostdin", "-v", "error",
                     "-f", "lavfi", "-i", "aevalsrc=0.03*sin(2*PI*220*t):s=48000:d=4",
                     "-f", "lavfi", "-i", "aevalsrc=0.3*sin(2*PI*1568*t):s=48000:d=0.5",
                     "-filter_complex", ";".join(filters), "-map", "[a_master]",
                     "-ac", "1", "-ar", "48000", "-f", "f32le", "-"],
                    capture_output=True, check=True, timeout=30,
                )
                samples = array.array("f")
                samples.frombytes(result.stdout)
                self.assertEqual(len(samples), 4 * 48000)

                def rms(start: float, end: float) -> float:
                    window = samples[round(start * 48000):round(end * 48000)]
                    return math.sqrt(sum(value * value for value in window) / len(window))

                self.assertAlmostEqual(rms(0.1, 0.4), 0.03 / math.sqrt(2), delta=0.001)
                self.assertAlmostEqual(rms(3.0, 3.8), 0.03 / math.sqrt(2), delta=0.001)
                for start in starts:
                    self.assertGreater(rms(start + 0.05, start + 0.4), 0.2)
                if len(starts) == 1:
                    self.assertLess(rms(2.3, 2.6), 0.025)


if __name__ == "__main__":
    unittest.main()
