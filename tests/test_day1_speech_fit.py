"""Measured Ryan pacing regressions, including the failed production pitch."""
import copy
import io
import json
import shutil
import subprocess
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import AsyncMock, patch

from vortex.day1_show_render import _synthesize_section, synthesize_show


def pitch_section():
    # Run 40792853555 stopped on this 30-second section at tempo 1.247.
    return {
        'id': 'pitch', 'start': 175, 'end': 205, 'duration': 30,
        'text': ('Here is the verified starting eleven, with the bench kept separate. '
                 'Raya in goal. Thomas, Konsa, Justin, De Cuyper in defence. '
                 'Rogers, Mbeumo, Groß, Palmer in midfield. Haaland, Calvert-Lewin up front. '
                 'The armband follows the actual captain selection. '
                 'Any official substitute contribution is already included through its multiplier. '
                 'Now I will go through every starting player, keeping their position on the pitch in view.'),
    }


def boundaries(tempo):
    return [{'text': 'Here', 'start': .1, 'duration': .2},
            {'text': 'view', 'start': 29.6 * tempo - .4, 'duration': .4}]


class SpeechFitTests(unittest.IsolatedAsyncioTestCase):
    async def test_production_pitch_retries_and_uses_the_accepted_audio_and_words(self):
        section = pitch_section()
        original = copy.deepcopy(section)
        first, second = boundaries(1.247), boundaries(.96)
        tts = AsyncMock(side_effect=[(b'discarded', first), (b'accepted', second)])
        payload, profile, tempo, fitted = await _synthesize_section(section, tts)
        self.assertEqual(section, original)
        self.assertEqual([c.args[1]['rate'] for c in tts.await_args_list], ['-15%', '+6%'])
        self.assertTrue(all(c.args[0] == original['text'] for c in tts.await_args_list))
        self.assertEqual(profile, {'rate': '+6%', 'pitch': '-2Hz', 'volume': '+0%'})
        self.assertEqual(payload, b'accepted')
        self.assertAlmostEqual(tempo, .96)
        self.assertAlmostEqual(fitted[-1]['start'], 175 + second[-1]['start'] / tempo)
        self.assertAlmostEqual(fitted[-1]['start'] + fitted[-1]['duration'], 204.6)
        self.assertTrue(all(w['section_id'] == 'pitch' for w in fitted))
        self.assertEqual(second, boundaries(.96))

    async def test_a_fitting_take_is_not_resynthesized(self):
        tts = AsyncMock(return_value=(b'accepted', boundaries(1)))
        payload, profile, tempo, _ = await _synthesize_section(pitch_section(), tts)
        tts.assert_awaited_once()
        self.assertEqual((payload, profile['rate'], tempo), (b'accepted', '-15%', 1))

    async def test_slow_speech_is_corrected_without_leaving_the_rate_limits(self):
        section = pitch_section()
        section['text'] = ' '.join(['review'] * 100)
        tts = AsyncMock(side_effect=[(b'discarded', boundaries(.7)), (b'accepted', boundaries(.95))])
        _, profile, tempo, _ = await _synthesize_section(section, tts)
        self.assertEqual([c.args[1]['rate'] for c in tts.await_args_list], ['+12%', '-15%'])
        self.assertEqual(profile['rate'], '-15%')
        self.assertAlmostEqual(tempo, .95)

    async def test_persistent_bad_fit_still_fails_after_at_most_three_takes(self):
        tts = AsyncMock(return_value=(b'unusable', boundaries(1.247)))
        with self.assertRaisesRegex(RuntimeError, 'tempo range for pitch: 1.247'):
            await _synthesize_section(pitch_section(), tts)
        self.assertEqual([c.args[1]['rate'] for c in tts.await_args_list], ['-15%', '+6%', '+12%'])

    async def test_no_more_attempts_when_the_rate_limit_cannot_help(self):
        tts = AsyncMock(return_value=(b'unusable', boundaries(.7)))
        with self.assertRaisesRegex(RuntimeError, 'tempo range'):
            await _synthesize_section(pitch_section(), tts)
        tts.assert_awaited_once()

    async def test_invalid_timings_and_transport_errors_are_not_pacing_retries(self):
        for invalid in ([], [{'text': 'bad', 'start': float('nan'), 'duration': 1}],
                        [{'text': 'bad', 'start': 0, 'duration': float('inf')}],
                        [{'text': 'bad', 'start': -1, 'duration': 1}],
                        [{'text': 'bad', 'start': 0, 'duration': 0}]):
            with self.subTest(words=invalid):
                tts = AsyncMock(return_value=(b'unusable', invalid))
                with self.assertRaisesRegex(RuntimeError, 'invalid Ryan word timings'):
                    await _synthesize_section(pitch_section(), tts)
                tts.assert_awaited_once()
        tts = AsyncMock(side_effect=RuntimeError('transport unavailable'))
        with self.assertRaisesRegex(RuntimeError, 'transport unavailable'):
            await _synthesize_section(pitch_section(), tts)
        tts.assert_awaited_once()

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg required')
    async def test_ffmpeg_and_captions_use_the_same_corrected_take(self):
        section = pitch_section()
        section.update(start=0, end=30)
        pcm = io.BytesIO()
        with wave.open(pcm, 'wb') as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(24000)
            audio.writeframes(b'\0\0' * (24000 * 29))
        accepted = pcm.getvalue()
        tts = AsyncMock(side_effect=[(b'not-decodable-audio', boundaries(1.247)),
                                    (accepted, boundaries(1))])
        show = {'sections': [section]}
        with tempfile.TemporaryDirectory() as directory:
            with patch('vortex.day1_show_render.build_visual_timeline') as timeline:
                output = await synthesize_show(show, directory, tts)
            self.assertEqual((Path(directory) / 'pitch.mp3').read_bytes(), accepted)
            self.assertEqual(section['tts_profile']['rate'], '+6%')
            self.assertAlmostEqual(section['audio_tempo'], 1)
            fitted = timeline.call_args.args[1]
            self.assertAlmostEqual(fitted[-1]['start'] + fitted[-1]['duration'], 29.6)
            probe = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                                    '-of', 'json', str(output)], check=True, capture_output=True, text=True)
            self.assertAlmostEqual(float(json.loads(probe.stdout)['format']['duration']), 30, delta=.05)


if __name__ == '__main__':
    unittest.main()
