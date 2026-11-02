from __future__ import annotations
import re
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vortex.day1_editorial import (
    build_editorial_review, validate_narration, review_voice_profile,
    word_timed_vtt, measured_audio_report,
)


def evidence(*, partial=False, scarce=False):
    roster=[]; ctx={}; segments=[dict(id='headline',text='review placeholder')]
    for n in range(15):
        player_id=n+1
        p={
            'id': player_id,'name':f'Example {player_id}',
            'pos':['GK','DEF','MID','FWD'][n % 4],
            'review_state':'PENDING' if partial and n==2 else 'FINAL',
            'next_fixture':{'gw':12,'opp_name':'An Example Team','is_home':n%2==0},
            'model_projection':({'next_gw_xpts':4.4,'expected_minutes_next_gw':77} if not scarce else {}),
            'team_id':n%5+1,
        }
        roster.append(p)
        ctx[player_id]={
            'full_name':p['name'],'status':'d' if n==0 else 'a',
            'stats':({'minutes':0} if partial and n==2 else {'total_points':n%11,'minutes':88,
                      'goals_scored':1 if n==1 else 0, 'assists':0,'clean_sheets':0,'saves':0}),
            'point_breakdown':{'defensive_contribution':2 if n==4 else 0},
        }
        segments.append({'id':f'player_{player_id}','player_id':player_id,'name':p['name'],
                         'spoken_name':p['name'],'text':'Temporary original commentary.'})
    segments.insert(12,{'id':'bench_intro','text':'The bench.'})
    segments.append({'id':'metrics_intro','text':'The metrics.'})
    for key in ('metric_captain','hero_review','quietest_review','availability_review','review_close'):
        segments.append({'id':key,'text':f'Temporary report {key}.'})
    return segments,roster,ctx

class EditorialTests(unittest.TestCase):
    def test_builds_dynamic_review_and_preserves_player_order(self):
        segments,roster,ctx=evidence()
        scripts,meta=build_editorial_review(segments,roster[:11],roster[11:],ctx,
                                            review_gw=11,next_gw=12,review_status='FINAL')
        self.assertEqual([x['player_id'] for x in scripts if x.get('player_id')],list(range(1,16)))
        self.assertEqual(meta['review_gw'],11)
        self.assertFalse(meta['current_transfer_state_verified'])
        combined=' '.join(s['text'] for s in scripts)
        self.assertIn('An Example Team',combined)
        self.assertIn('Expected points are forecasts, not guaranteed returns',combined)
        self.assertNotIn('£2.2m',combined)
        self.assertNotIn('Gibbs-White',combined)
        self.assertGreater(meta['draft_words'],750)
        self.assertLess(meta['draft_words'],1350)
        self.assertEqual(len(segments),23,'source segments stay unmodified')

    def test_missing_next_fixture_or_projected_number_is_omitted(self):
        segments,roster,ctx=evidence(scarce=True)
        roster[0]['next_fixture']={}
        scripts,_=build_editorial_review(segments,roster[:11],roster[11:],ctx,
                                         review_gw=11,next_gw=12,review_status='FINAL')
        first=next(x for x in scripts if x.get('player_id')==1)
        self.assertIn('no verified next fixture',first['text'])
        self.assertNotIn('0.0 expected',first['text'])

    def test_live_result_is_not_presented_as_final(self):
        segments,roster,ctx=evidence(partial=True)
        scripts,_=build_editorial_review(segments,roster[:11],roster[11:],ctx,
                                         review_gw=11,next_gw=12,review_status='LIVE/PARTIAL')
        pending=next(x for x in scripts if x.get('player_id')==3)
        self.assertIn('not verified yet',pending['text'])
        self.assertNotRegex(pending['text'],r'\bzero points\b|\b0 points\b')

    def test_incoherent_gameweek_and_broken_roster_fail_closed(self):
        segments,roster,ctx=evidence()
        with self.assertRaisesRegex(ValueError,'Gameweeks'):
            build_editorial_review(segments,roster[:11],roster[11:],ctx,
                                   review_gw=12,next_gw=11,review_status='FINAL')
        with self.assertRaisesRegex(ValueError,'fifteen-player'):
            build_editorial_review(segments,roster[:11],roster[11:14],ctx,
                                   review_gw=11,next_gw=12,review_status='FINAL')

    def test_banned_hype_and_stage_directions_fail(self):
        for bad in ('ultimate asset','[00:40 scene change]','[PLAYER 1]','must-buy'):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError,'narration|certainty|phrase|Stage'):
                validate_narration([{'id':'intro','text':'We have '+bad}],player_ids=[])

    def test_conversational_voice_profiles_use_supported_controls(self):
        p=review_voice_profile('analysis')
        self.assertEqual(set(p),{'rate','pitch','volume'})
        self.assertNotEqual(review_voice_profile('intro'),review_voice_profile('warning'))
        self.assertEqual(p['rate'],'-3%')

    def test_captions_follow_word_boundaries(self):
        one=dict(id='a',t0=0.,t1=3.,duration=3.,words=[
            {'text':'The','start':0.1,'duration':.2},
            {'text':'minutes','start':.4,'duration':.4},
            {'text':'matter','start':1.,'duration':.3},
            {'text':'here','start':1.5,'duration':.4}])
        two=dict(id='b',t0=3.,t1=4.,duration=1.,words=[{'text':'Wait','start':.1,'duration':.3}])
        vtt=word_timed_vtt([one,two],max_words=3)
        self.assertIn('00:00:00.100 --> 00:00:01.300',vtt)
        self.assertIn('00:00:03.100 --> 00:00:03.400',vtt)
        self.assertTrue(vtt.startswith('WEBVTT'))
        with self.assertRaisesRegex(ValueError,'boundaries'):
            word_timed_vtt([{'id':'x','words':[],'t0':0,'t1':3}])

    def test_measured_duration_not_word_count_proxy(self):
        report=measured_audio_report([{'text':'Speech '*100}],450.,target_seconds=480)
        self.assertEqual(report['audio_seconds'],450.0)
        self.assertTrue(report['within_target'])
        self.assertFalse(measured_audio_report([{'text':'Speech '*100}],320.,target_seconds=480)['within_target'])

if __name__=='__main__':unittest.main()