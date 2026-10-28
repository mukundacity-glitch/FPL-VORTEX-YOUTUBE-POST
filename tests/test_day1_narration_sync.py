from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from day1.media import speak_roundup, frame_times, compact_roundup
from day1.production_helpers import vx_phrase_time


class NarrationSyncTests(unittest.IsolatedAsyncioTestCase):
    def namespace(self, words):
        async def speech(text, profile):
            return b'audio', words
        return {'vx_full_word_narration': lambda text, **kwargs: text,
                'vx_edge_tts_stream': speech, 'vx_phrase_time': vx_phrase_time}

    async def test_each_grouped_name_keeps_its_measured_popup_time(self):
        words = [dict(text=t, start=s, duration=.2) for t,s in
                 [('Yellow',0),('cards',.2),('for',.4),('João',.8),('Pedro',1.1),('and',1.5),('Van',2.3),('de',2.6),('Ven',2.9)]]
        package = {'beats':[{'id':'bookings', 'kind':'players', 'text':'Yellow cards for João Pedro and Van de Ven.',
                            'mentions':[{'player_id':1,'spoken_name':'João Pedro'}, {'player_id':2,'spoken_name':'Van de Ven'}]}]}
        with tempfile.TemporaryDirectory() as d, patch('day1.media.duration',return_value=3.5), patch('day1.media.join_audio'):
            await speak_roundup(package,self.namespace(words),Path(d)/'segments')
        self.assertEqual([m['name_time'] for m in package['beats'][0]['mentions']],[.8,2.3])
        self.assertAlmostEqual(package['duration'],3.26)

    async def test_missing_spoken_name_blocks_rendering(self):
        p={'beats':[{'id':'player','kind':'player','text':'Wrong name.', 'player_id':1,'spoken_name':'João Pedro'}]}
        with tempfile.TemporaryDirectory() as d, patch('day1.media.duration',return_value=2):
            with self.assertRaisesRegex(RuntimeError,'exact-sync phrase'):
                await speak_roundup(p,self.namespace([dict(text='Wrong',start=0,duration=1)]),Path(d)/'segments')

    async def test_intro_cannot_exceed_three_minutes(self):
        p={'beats':[{'id':'welcome','text':'Welcome.'}]}
        with tempfile.TemporaryDirectory() as d, patch('day1.media.duration',return_value=182), patch('day1.media.join_audio') as join:
            with self.assertRaisesRegex(RuntimeError,'180s'):
                await speak_roundup(p,self.namespace([dict(text='Welcome',start=0,duration=181)]),Path(d)/'segments')
            join.assert_not_called()

    def test_card_motion_is_sampled_at_output_frame_rate(self):
        times=frame_times(10,24,[(2,2.5)])
        self.assertIn(2,times)
        self.assertIn(2+1/24,times)
        self.assertIn(2.5,times)
        self.assertEqual(times[-1],239/24)

    def test_compact_edition_keeps_every_required_incident(self):
        package={'beats':[{'id':key,'facts':facts} for key,facts in [
            ('goal',{'goals_scored':1,'assists':1}),('yellow',{'yellow_cards':1}),
            ('red',{'red_cards':1}),('injury',{'availability':True}),('assist',{'assists':1})]]}
        result=compact_roundup(package)
        self.assertEqual([b['id'] for b in result['beats']],['goal','yellow','red','injury'])
        self.assertEqual(len(package['beats']),5)

    def test_new_is_not_the_newcastle_club_code(self):
        source=Path(__file__).resolve().parents[1]/'day1'/'spoken_names.py'
        ns={'teams':[{'id':1,'code':4,'name':'Newcastle','short_name':'NEW'}],
            'players':[{'id':1,'web_name':'Jamie','first_name':'Jamie','second_name':'Test'}]}
        exec(compile(source.read_text(),str(source),'exec'),ns)
        self.assertEqual(ns['vx_full_word_narration']('New injury flags for Jamie.'),'New injury flags for Jamie.')
        self.assertEqual(ns['vx_full_word_narration']('NEW next week.'),'Newcastle next week.')


if __name__=='__main__':
    unittest.main()
