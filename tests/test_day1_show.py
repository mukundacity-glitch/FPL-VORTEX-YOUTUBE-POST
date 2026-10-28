"""Production evidence, pacing and metadata regressions for the decision show."""
import copy
import json
import math
import unittest
from pathlib import Path

from vortex.day1_show import BANNED, build_show, production_brief, package_snapshot
from vortex.day1_show_render import build_visual_timeline, fit_word_timing, show_html, word_time, caption_ass
from vortex.day1_show_media import sound_graph
from vortex.youtube_studio_package import _vx23_metadata

FIXTURE = Path(__file__).parent / 'fixtures/day1_synthetic.json'


def fixture():
    return json.loads(FIXTURE.read_text())


def timed_words(show):
    words = []
    for s in show['sections']:
        tokens = s['text'].split()
        step = (s['duration'] - .5) / len(tokens)
        words += [{'text': text, 'start': s['start'] + i * step, 'duration': step * .8,
                   'section_id': s['id']} for i, text in enumerate(tokens)]
    return words


class DecisionShowTests(unittest.TestCase):
    def test_official_snapshot_adapter_reconciles_points_before_creating_a_story(self):
        p = fixture()
        teams = [{'id': i, 'code': i, 'short_name': f'T{i}', 'name': f'Club {i}'} for i in range(1, 17)]
        elements, picks, live, fixtures = [], [], [], []
        for player in p['players']:
            pid = player['id']
            elements.append({'id': pid, 'team': pid, 'web_name': player['name'],
                             'element_type': {'GK': 1, 'DEF': 2, 'MID': 3, 'FWD': 4}[player['pos']],
                             'status': player['status'], 'news': player['news'], 'now_cost': 70,
                             'starts': 7, 'minutes': 600, 'total_points': 200 if pid == 10 else 30 + pid})
            picks.append({'element': pid, 'position': player['squad_position'],
                          'is_captain': player['captain'], 'is_vice_captain': player['vice'],
                          'multiplier': player['multiplier']})
            live.append({'id': pid, 'stats': {'total_points': player['points'], 'minutes': player['minutes']}})
            fixtures.append({'event': 9, 'team_h': pid, 'team_a': 16, 'kickoff_time': '2026-11-01T15:00:00Z'})
        gross = sum(x['points'] * x['multiplier'] for x in p['players'])
        snapshot = {'gw': 8, 'status': 'FINAL', 'fixtures': fixtures,
                    'bootstrap': {'teams': teams, 'elements': elements,
                                  'events': [{'id': 8, 'average_entry_score': 40}, {'id': 9, 'is_next': True}]},
                    'live': {'elements': live}, 'picks': {'picks': picks, 'entry_history': {'points': gross}}}
        ns = {'GW_REVIEW': snapshot, 'NEXT_GW': 9, 'resolve_player_photo': lambda p: ''}
        packaged = package_snapshot(ns)
        self.assertEqual(packaged['metrics']['gw_points'], gross)
        self.assertEqual(packaged['players'][0]['next_fixture']['ha'], 'H')
        self.assertEqual(packaged['players'][12]['news'], 'Muscle injury - Unknown return date')
        snapshot['picks']['entry_history']['points'] += 1
        with self.assertRaisesRegex(RuntimeError, 'do not reconcile'):
            package_snapshot(ns)

    def test_verified_story_does_not_invent_the_example_bench_haul(self):
        show = build_show(fixture())
        self.assertEqual(show['accuracy']['gw_points'], 40)
        self.assertEqual(show['accuracy']['captain_points'], -2)
        self.assertEqual(show['accuracy']['actual_bench_regret_id'], 14)
        text = ' '.join(s['text'] for s in show['sections'])
        self.assertIn('Bench Defender scored 7 on my unused bench', text)
        self.assertIn('Starting Hero was already in my starting eleven', text)
        self.assertNotIn('42 points', text)
        self.assertNotIn('Starting Hero scored 14 on my unused bench', text)
        self.assertEqual([(d['player']['id'], d['verdict']) for d in show['decisions']],
                         [(9, 'HOLD'), (14, 'START'), (13, 'WAIT FOR TEAM NEWS')])
        self.assertEqual(show['decisions'][1]['replacement']['id'], 2)

    def test_finalisation_and_missing_captain_fail_closed(self):
        p = fixture()
        p['status'] = 'LIVE/PARTIAL'
        with self.assertRaisesRegex(RuntimeError, 'final official'):
            build_show(p)
        p = fixture()
        for player in p['players']:
            player['captain'] = False
        with self.assertRaisesRegex(RuntimeError, 'captain selection'):
            build_show(p)

    def test_bench_boost_and_autosubs_are_not_unused_bench_regrets(self):
        p = fixture()
        for player in p['players']:
            if player['bench']:
                player['multiplier'] = 1
        show = build_show(p)
        self.assertIsNone(show['accuracy']['actual_bench_regret_id'])
        self.assertNotIn('unused bench', show['sections'][0]['text'])

    def test_transferred_armband_uses_effective_captain_multiplier(self):
        p = fixture()
        for player in p['players']:
            if player['id'] == 9:
                player['points'] = 0
                player['multiplier'] = 0
            elif player['id'] == 10:
                player['multiplier'] = 2
        show = build_show(p)
        self.assertEqual(show['accuracy']['captain_points'], 16)
        self.assertIn('armband passed to Forward Alternative', show['sections'][0]['text'])
        self.assertNotIn('Minus 2', show['sections'][0]['text'])

    def test_injured_bench_player_is_never_given_a_start_verdict(self):
        p = fixture()
        next(x for x in p['players'] if x['id'] == 14)['status'] = 'd'
        show = build_show(p)
        self.assertNotEqual(show['decisions'][1]['player']['id'], 14)

    def test_gameweeks_titles_and_script_are_dynamic(self):
        p = fixture()
        p['gw'], p['preview_gw'] = 10, 11
        for player in p['players']:
            player['next_fixture']['gw'] = 11
            for f in player['fixtures']:
                f['gw'] = 11
        show = build_show(p)
        self.assertIn('GW11', show['title_options'][0])
        self.assertEqual(show['duration'], 290)
        self.assertEqual([s['start'] for s in show['sections']], [0, 15, 45, 105, 165, 225, 270])
        self.assertTrue(all(len(t) < 60 for t in show['title_options']))
        self.assertEqual(len(show['title_options']), 5)
        self.assertTrue(all(len(t.split()) <= 4 for t in show['thumbnail_text_options']))
        text = ' '.join(s['text'] for s in show['sections']).casefold()
        self.assertFalse(any(x in text for x in BANNED))
        self.assertNotIn('gameweek 9', text)
        self.assertIn('unknown return date', text)

    def test_word_timing_visual_cadence_and_sentence_safe_shorts(self):
        show = build_show(fixture())
        words = timed_words(show)
        build_visual_timeline(show, words)
        self.assertTrue(all(3 <= b['end'] - b['start'] <= 6 for b in show['beats']))
        self.assertTrue(all(len(b['phrase'].split()) <= 5 for b in show['beats']))
        self.assertTrue(all(b['transition'] == .4 for b in show['beats']))
        self.assertEqual(show['impact_at'], word_time(words, 'captain'))
        self.assertEqual(len(show['shorts']), 3)
        self.assertTrue(all(15 <= s['end'] - s['start'] <= 35.5 for s in show['shorts']))
        self.assertTrue(all(h['at'] in [w['start'] for w in words] for h in show['highlights']))
        ass = caption_ass(show)
        self.assertEqual(ass.count('Dialogue:'), len(words))
        self.assertIn('PlayResX: 1920', ass)
        self.assertIn('PlayResY: 1920', caption_ass(show, 105, 135, True))

    def test_audio_tempo_scales_word_times_with_the_narration(self):
        section = {'id': 'hook', 'start': 0, 'end': 15, 'duration': 15}
        raw = [{'text': 'Captain', 'start': 0, 'duration': .4},
               {'text': 'decision', 'start': 13, 'duration': .6}]
        tempo, fitted = fit_word_timing(section, raw)
        self.assertAlmostEqual(fitted[-1]['start'] + fitted[-1]['duration'], 14.6)
        self.assertAlmostEqual(fitted[-1]['start'], 13 / tempo)
        with self.assertRaisesRegex(RuntimeError, 'tempo range'):
            fit_word_timing(section, [{'text': 'too short', 'start': 0, 'duration': 1}])

    def test_metadata_is_about_decisions_and_has_word_timed_chapters(self):
        show = build_show(fixture())
        qa = {'sections': [{'key': '00_intro', 'duration': 290}],
              'external_media_integration': {'applied': True, 'opening': {'duration': 0}}}
        metadata = _vx23_metadata(9, 8, 'FINAL', qa, show)
        self.assertNotIn('Results & My Squad', metadata['title'])
        self.assertNotIn('scorers and assists', metadata['description'])
        self.assertEqual(metadata['chapters'][0], '0:00 The captain problem')
        self.assertTrue(metadata['chapters'][2].startswith('0:45 '))
        self.assertEqual(metadata['recommended_visibility'], 'Private')

    def test_brief_includes_all_ten_outputs_and_no_claim_of_analytics_access(self):
        show = build_show(fixture())
        text = production_brief(show)
        for label in ['A.', 'B.', 'C.', 'D–E.', 'F.', 'G.', 'H.', 'I.', 'J.']:
            self.assertIn(label, text)
        self.assertEqual(show['analytics_review']['status'], 'manual_review_after_publication')
        self.assertIn('Private videos and Shorts', text)
        graph = sound_graph(290, 2)
        self.assertIn('I=-32', graph)
        self.assertIn('sidechaincompress', graph)
        self.assertIn('adelay=2000', graph)
        self.assertNotIn('concat=', graph)


if __name__ == '__main__':
    unittest.main()
