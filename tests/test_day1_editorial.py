from __future__ import annotations
import re
import sys
from collections import Counter
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
        self.assertGreater(meta['draft_words'],650)
        self.assertLess(meta['draft_words'],1125)
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

    def test_repetitive_sentence_and_singular_points_are_handled(self):
        repeated = [
            {'id':str(i),'text':f'Player {i} recorded an individual return. The next decision depends on verified minutes and role.'}
            for i in range(4)
        ]
        with self.assertRaisesRegex(ValueError, 'repeated sentences'):
            validate_narration(repeated, player_ids=[])
        segments, roster, ctx = evidence()
        scripts, _ = build_editorial_review(segments, roster[:11], roster[11:], ctx,
                                            review_gw=11, next_gw=12, review_status='FINAL')
        second = next(x for x in scripts if x.get('player_id') == 2)
        self.assertIn('1 point.', second['text'])
        self.assertNotIn('1 points', second['text'])

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


def rich_evidence(partial=False):
    """Realistic spread: results, minutes, flags, form, fixture runs, price, ownership."""
    pts=[2,6,1,9,2,5,3,12,2,4,7,1,2,6,3]
    mins=[90,90,90,90,64,90,90,90,45,90,90,0,90,88,90]
    positions=['GK','DEF','DEF','DEF','DEF','MID','MID','MID','MID','FWD','FWD','GK','DEF','MID','FWD']
    segments=[dict(id='headline',text='review placeholder')]; roster=[]; ctx={}
    for n in range(15):
        pid=n+1
        p={'id':pid,'name':f'Example {pid}','pos':positions[n],
           'review_state':'LIVE' if partial and n==7 else 'FINAL','ownership':5.0+n,
           'next_fixture':{'gw':12,'opp_name':f'Club {n%5}','is_home':n%2==0},
           'model_projection':{'next_gw_xpts':3.0+n/5,'expected_minutes_next_gw':88},'team_id':n%7+1}
        roster.append(p)
        ctx[pid]={'full_name':p['name'],'status':'d' if n==5 else 'a','current_price':4.5+n/2,'club':('Alpha','Alpha','Beta','Gamma','Delta')[n%5] if n<10 else f'Club {n}',
                  'stats':{'total_points':pts[n],'minutes':mins[n],'goals_scored':1 if n in (3,7) else 0,
                           'assists':1 if n in (1,9) else 0,'clean_sheets':1 if n in (1,2,4) else 0,
                           'saves':4 if n==0 else 0,'bonus':3 if n==7 else (1 if n in (3,9) else 0)},
                  'point_breakdown':{'defensive_contribution':0},
                  'last_three':{'complete':True,'total_points':pts[n]+9},
                  'next_three':[{'opponent':'x','fdr':f} for f in ((2,3,2),(3,3,4),(2,2,3))[n%3]]}
        segments.append({'id':f'player_{pid}','player_id':pid,'name':p['name'],'text':f'original {pid}'})
    segments.insert(12,{'id':'bench_intro','text':'The bench.'})
    segments.append({'id':'metrics_intro','text':'The metrics.'})
    for key in ('metric_captain','hero_review','quietest_review','availability_review','review_close'):
        segments.append({'id':key,'text':f'Temporary report {key}.'})
    return segments,roster,ctx


class VarietyTests(unittest.TestCase):
    def build(self, partial):
        segments,roster,ctx=rich_evidence(partial)
        return build_editorial_review(segments,roster[:11],roster[11:],ctx,review_gw=11,next_gw=12,
                                      review_status='LIVE/PARTIAL' if partial else 'FINAL')[0]

    def test_no_stock_sentence_is_spoken_more_than_twice(self):
        for partial in (False,True):
            with self.subTest(partial=partial):
                scripts=self.build(partial)
                sentences=[re.sub(r'\s+',' ',part.lower().strip())
                           for s in scripts for part in re.split(r'(?<=[.!?])\s+',s['text'])
                           if len(part.split())>=4]
                worst=max(Counter(sentences).values())
                self.assertLessEqual(worst,2)
                skeletons=Counter(re.sub(r'\d+(?:\.\d+)?','#',re.sub(r'Example \d+','N',x)) for x in sentences)
                self.assertLessEqual(max(skeletons.values()),4,'one sentence shape dominates the script')

    def test_provisional_is_not_announced_up_front_and_is_said_once_plainly(self):
        scripts=self.build(True)
        self.assertNotIn('provisional',scripts[0]['text'].lower())
        combined=' '.join(s['text'] for s in scripts).lower()
        self.assertNotIn('provisional',combined)
        close=next(s for s in scripts if s['id']=='review_close')['text']
        self.assertEqual(close.count('still unfinished'),1)
        live=next(s for s in scripts if s.get('player_id')==8)['text']
        self.assertIn('so far',live)
        self.assertNotIn('finished on',live,'a live result must not read as final')
        final_close=next(s for s in self.build(False) if s['id']=='review_close')['text']
        self.assertNotIn('unfinished',final_close)

    def test_length_stays_inside_the_video_length_gate_and_players_stay_short(self):
        scripts=self.build(False)
        words=sum(len(re.findall(r"[\w'’-]+",s['text'])) for s in scripts)
        # Real runs add ~110 words of metric commentary from Cell 15; at the
        # measured ~136 words/minute this keeps the video near its 480 s target.
        self.assertGreater(words,820)
        self.assertLess(words,1000)
        for s in scripts:
            if s.get('player_id') is not None:
                self.assertLessEqual(len(re.findall(r"[\w'’-]+",s['text'])),90)

    def test_squad_data_beat_uses_only_verified_fields_and_is_omitted_when_missing(self):
        scripts=self.build(False)
        beat=next(s for s in scripts if s['id']=='editorial_squad_data')['text']
        self.assertIn('most widely owned',beat)
        self.assertIn('of the fifteen come from',beat)
        self.assertIn('most expensive pick',beat)
        segments,roster,ctx=evidence(scarce=True)
        for p in roster: p.pop('ownership',None)
        for c in ctx.values(): c.pop('current_price',None); c.pop('club',None)
        scripts,_=build_editorial_review(segments,roster[:11],roster[11:],ctx,review_gw=11,next_gw=12,review_status='FINAL')
        self.assertNotIn('editorial_squad_data',[s['id'] for s in scripts])

    def test_verified_formation_and_points_lead_is_reused_but_placeholders_are_not(self):
        segments,roster,ctx=rich_evidence()
        segments[0]['text']="Let's review Gameweek 11: a 3-4-3 and 63 points."
        scripts,_=build_editorial_review(segments,roster[:11],roster[11:],ctx,review_gw=11,next_gw=12,review_status='FINAL')
        self.assertTrue(scripts[0]['text'].startswith("Let's review Gameweek 11: a 3-4-3 and 63 points. The points count"))
        segments,roster,ctx=rich_evidence()
        scripts,_=build_editorial_review(segments,roster[:11],roster[11:],ctx,review_gw=11,next_gw=12,review_status='FINAL')
        self.assertTrue(scripts[0]['text'].startswith('Gameweek 11: the points count'))

    def test_voice_varies_between_players_but_keeps_safe_bounds(self):
        profiles={tuple(review_voice_profile('analysis',v).items()) for v in range(1,16)}
        self.assertGreater(len(profiles),3)
        for v in range(0,40):
            p=review_voice_profile('analysis',v)
            self.assertTrue(-8<=int(p['rate'].rstrip('%'))<=3)
            self.assertTrue(-5<=int(p['pitch'].removesuffix('Hz'))<=0)
        self.assertEqual(review_voice_profile('analysis'),review_voice_profile('analysis',0))
        self.assertEqual(review_voice_profile('outro',7),review_voice_profile('outro'))

if __name__=='__main__':unittest.main()