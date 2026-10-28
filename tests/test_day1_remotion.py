"""Presentation boundaries: original data and clock, real required popup asset."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vortex.day1_remotion import popup_schedule, prepare_props, show_digest
from vortex.day1_show import build_show
from vortex.day1_show_render import build_visual_timeline


class RemotionContractTests(unittest.TestCase):
    def test_short_output_filenames_do_not_mask_changes_to_presentation_data(self):
        show = {'sections': [{'id': 'hook', 'text': 'Original words'}],
                'shorts': [{'start': 45, 'end': 73}]}
        expected = show_digest(show)
        show['shorts'][0]['file'] = '/output/MP4/day1_short_1.mp4'
        self.assertEqual(show_digest(show), expected)
        show['sections'][0]['text'] = 'Different words'
        self.assertNotEqual(show_digest(show), expected)

    def test_popup_starts_on_two_minute_boundaries_without_extending_the_show(self):
        self.assertEqual(popup_schedule(290, 8), [
            {'start': 120, 'duration': 8}, {'start': 240, 'duration': 8}])
        self.assertEqual(popup_schedule(125, 8), [{'start': 120, 'duration': 5}])
        self.assertEqual(popup_schedule(120, 8), [])
        self.assertEqual(popup_schedule(240, 8), [{'start': 120, 'duration': 8}])
        self.assertEqual(popup_schedule(360, 180), [
            {'start': 120, 'duration': 120}, {'start': 240, 'duration': 120}])
        for invalid in (0, -1, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                popup_schedule(290, invalid)

    def test_presentation_preserves_every_original_section_beat_word_and_player(self):
        package = json.loads((Path(__file__).parent / 'fixtures/day1_synthetic.json').read_text())
        show = build_show(package)
        words = []
        for section in show['sections']:
            tokens = section['text'].split()
            step = (section['duration'] - .5) / len(tokens)
            words.extend({'text': text, 'start': section['start'] + i * step,
                          'duration': step * .8, 'section_id': section['id']}
                         for i, text in enumerate(tokens))
        build_visual_timeline(show, words)
        baseline = copy.deepcopy(show)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'popup.mp4'
            source.write_bytes(b'exact-source-bytes')
            with patch('vortex.day1_remotion._probe', return_value={
                'streams': [{'codec_type': 'video', 'duration': '8'}]}):
                props, report = prepare_props(show, root / 'stage', root, width=3840, height=2160)
            self.assertEqual(show, baseline)
            self.assertEqual(props['show'], baseline)
            self.assertEqual(props['show']['package'], package)
            self.assertEqual(props['popup']['starts'], [120, 240])
            self.assertEqual((root / 'stage/popup.mp4').read_bytes(), source.read_bytes())
            self.assertEqual(report['sha256'], hashlib.sha256(source.read_bytes()).hexdigest())
            self.assertEqual((props['start'], props['end']), (0, 290))
            portrait, report = prepare_props(show, root / 'portrait', root,
                width=1080, height=1920, start=105, end=133.125, vertical=True)
            self.assertEqual(portrait['show'], baseline)
            self.assertEqual(portrait['start'], 105)
            self.assertIsNone(portrait['popup'])
            self.assertEqual(report['occurrences'], [])

    def test_missing_popup_fails_before_rendering_a_long_show(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(FileNotFoundError, 'popup.mp4'):
                prepare_props({'duration': 290}, root / 'stage', root, width=3840, height=2160)

    def test_ranges_cannot_reorder_or_extend_the_original_timeline(self):
        for start, end in ((-1, 1), (2, 1), (0, 291)):
            with self.assertRaises(ValueError):
                prepare_props({'duration': 290}, Path('unused'), Path('unused'),
                    width=3840, height=2160, start=start, end=end)


if __name__ == '__main__':
    unittest.main()
