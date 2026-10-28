"""Real FFmpeg checks for captioned rendering, scratch manifests and sound."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from vortex.day1_media import integrate_media
from vortex.day1_show import build_show
from vortex.day1_show_render import encode_frames
from test_day1_results_render import write_png


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg is required')
class ShowMediaTests(unittest.TestCase):
    def test_keyframe_encoding_keeps_manifests_outside_the_video_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            work, videos = root / 'work', root / 'MP4'
            work.mkdir(); videos.mkdir()
            a, b = work / 'a.png', work / 'b.png'
            write_png(a, (10, 20, 40)); write_png(b, (40, 120, 80))
            audio = work / 'voice.mp3'
            subprocess.run(['ffmpeg', '-y', '-v', 'error', '-f', 'lavfi', '-i',
                            'sine=frequency=440:duration=2', str(audio)], check=True)
            output = videos / '00_intro.mp4'
            encode_frames([(0, a), (.5, b), (1.9, b)], audio, output, 2)
            self.assertEqual([p.name for p in videos.iterdir()], ['00_intro.mp4'])
            self.assertTrue((work / 'frames.ffconcat').is_file())

    def test_finished_show_starts_with_speech_and_keeps_its_video_clock(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ['MP4', 'MP3', 'DATA', 'assets']:
                (root / name).mkdir()
            video = root / 'MP4/FPL_VORTEX_GW9_COMBINED.mp4'
            audio = root / 'MP3/FPL_VORTEX_GW9_COMBINED.mp3'
            music = root / 'assets/Background_music.mp3'
            subprocess.run(['ffmpeg', '-y', '-v', 'error', '-f', 'lavfi', '-i',
                            'color=c=0x07101b:s=160x90:r=24:d=290', '-f', 'lavfi', '-i',
                            'sine=frequency=440:sample_rate=48000:duration=290',
                            '-c:v', 'libx264', '-preset', 'ultrafast', '-threads', '2',
                            '-c:a', 'aac', '-ar', '48000', '-ac', '2', str(video)], check=True)
            subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', str(video), '-vn', str(audio)], check=True)
            subprocess.run(['ffmpeg', '-y', '-v', 'error', '-f', 'lavfi', '-i',
                            'sine=frequency=120:duration=3', str(music)], check=True)
            qa = {'passed': True, 'final_file': str(video), 'combined_mp3': str(audio),
                  'video_output': [160, 90], 'output_contract': {'passed': True}}
            (root / 'DATA/final_video_qa.json').write_text(json.dumps(qa))
            (root / 'DATA/day1_show.json').write_text(json.dumps({'duration': 290, 'impact_at': 2}))
            report = integrate_media(root, root / 'assets')
            self.assertEqual(report['opening']['duration'], 0)
            self.assertEqual(report['background_music']['timeline_start'], 0)
            self.assertEqual(report['impact']['count'], 1)
            self.assertFalse(report['video_reencoded'])
            self.assertAlmostEqual(report['final_duration'], 290, delta=.15)
            self.assertEqual(integrate_media(root, root / 'assets')['final_sha256'], report['final_sha256'])


if __name__ == '__main__':
    unittest.main()
