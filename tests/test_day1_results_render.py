"""Exercise the actual FFmpeg path that failed in Day 1 run 75."""
import json
import math
import shutil
import struct
import subprocess
import tempfile
import unittest
import zlib
from fractions import Fraction
from pathlib import Path

from vortex.day1_short import (
    _encode_results_segment,
    _join_results_segments,
    _validate_results_video,
)


def write_png(path, color):
    def chunk(kind, data):
        return (struct.pack('>I', len(data)) + kind + data
                + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff))

    row = b'\0' + bytes(color) * 320
    path.write_bytes(
        b'\x89PNG\r\n\x1a\n'
        + chunk(b'IHDR', struct.pack('>IIBBBBB', 320, 180, 8, 2, 0, 0, 0))
        + chunk(b'IDAT', zlib.compress(row * 180))
        + chunk(b'IEND', b'')
    )


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),
                     'FFmpeg and ffprobe are required')
class ResultsRenderTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='day1 results ')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.images = []
        for index, color in enumerate(((255, 0, 0), (0, 255, 0),
                                       (0, 0, 255), (255, 255, 0))):
            image = self.root / f'{index}.png'
            write_png(image, color)
            self.images.append(image)
        self.audio = self.root / 'narration.mp3'
        subprocess.run(
            ['ffmpeg', '-y', '-v', 'error', '-f', 'lavfi', '-i',
             'sine=frequency=440:sample_rate=24000:duration=3.072',
             '-c:a', 'libmp3lame', str(self.audio)], check=True,
        )

    def probe(self, path):
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_streams', '-of', 'json', str(path)],
            capture_output=True, text=True, check=True,
        )
        return {s['codec_type']: s for s in json.loads(result.stdout)['streams']}

    def test_sparse_keyframes_fill_the_entire_narration_at_24fps(self):
        clip = self.root / 'segment.mp4'
        duration = _encode_results_segment(self.images, self.audio, clip, 3.152, 24)
        streams = self.probe(clip)
        self.assertEqual(Fraction(streams['video']['avg_frame_rate']), 24)
        self.assertEqual(int(streams['video']['nb_frames']), math.ceil(3.152 * 24))
        self.assertGreater(float(streams['video']['duration']), 3.072)
        self.assertAlmostEqual(float(streams['video']['duration']), duration, places=5)
        self.assertLess(abs(float(streams['audio']['duration']) - duration), 1 / 24)
        self.assertEqual(streams['audio']['sample_rate'], '48000')

    def test_joined_intro_keeps_all_frames_and_matching_audio(self):
        clips = []
        duration = 0
        frames = 0
        for index, seconds in enumerate((3.152, 2.696, 7.76)):
            clip = self.root / f'segment-{index}.mp4'
            duration += _encode_results_segment(self.images, self.audio, clip, seconds, 24)
            frames += math.ceil(seconds * 24)
            clips.append(clip)
        output = self.root / '00_intro.mp4'
        _join_results_segments(clips, output, 24, duration)
        streams = self.probe(output)
        self.assertEqual(Fraction(streams['video']['avg_frame_rate']), 24)
        self.assertEqual(int(streams['video']['nb_frames']), frames)
        self.assertAlmostEqual(float(streams['video']['duration']), duration, places=5)
        self.assertLess(abs(float(streams['audio']['duration']) - duration), 2 / 24)

    def test_seven_frame_clip_is_rejected_before_final_assembly(self):
        # The old encoder produced a 24fps video stream lasting ~0.29s while
        # retaining several seconds of audio. Its nominal FPS alone passed.
        clip = self.root / 'truncated.mp4'
        subprocess.run(
            ['ffmpeg', '-y', '-v', 'error', '-loop', '1', '-i', str(self.images[0]),
             '-t', str(7 / 24), '-r', '24', '-vf', 'format=yuv420p',
             '-c:v', 'libx264', '-preset', 'ultrafast', str(clip)], check=True,
        )
        broken = self.root / 'old-segment.mp4'
        subprocess.run(
            ['ffmpeg', '-y', '-v', 'error', '-i', str(clip), '-i', str(self.audio),
             '-c:v', 'copy', '-c:a', 'aac', str(broken)], check=True,
        )
        self.assertEqual(Fraction(self.probe(broken)['video']['avg_frame_rate']), 24)
        with self.assertRaisesRegex(RuntimeError, 'video duration'):
            _validate_results_video(broken, 24, 3.152)


if __name__ == '__main__':
    unittest.main()
