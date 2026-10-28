from __future__ import annotations
import copy,json,math,tempfile,unittest
from pathlib import Path
from day1.roundup import Wording,booking_warning,build_roundup,card,kickoff_label,state,upcoming


def player(pid,team=1,**kw):
    return dict(id=pid,team=team,web_name=f'Player {pid}',first_name='Test',second_name=str(pid),element_type=3,status='a',news='',yellow_cards=0,**kw)


def fixture(fid=1,**kw):
    return dict(id=fid,event=8,team_h=1,team_a=2,kickoff_time='2026-10-25T14:00:00Z',started=False,finished=False,finished_provisional=False,minutes=0,team_h_score=None,team_a_score=None,stats=[],**kw)


class RoundupTests(unittest.TestCase):
    def snapshot(self):
        return {'gw':8,'status':'LIVE/PARTIAL','bootstrap':{'teams':[dict(id=1,name='Home Club',short_name='HOM'),dict(id=2,name='Away Club',short_name='AWA')], 'elements':[player(1),player(2,2)]},'fixtures':[fixture()],'live':{'elements':[]}}

    def roundup(self,snapshot):
        with tempfile.TemporaryDirectory() as d:
            return build_roundup(snapshot,[],9,Wording(Path(d)/'history.json','fixed'))

    def test_pending_match_has_a_real_date_never_a_zero_score(self):
        data=self.roundup(self.snapshot());b=next(b for b in data['beats'] if b['kind']=='fixture')
        self.assertIn('still to come',b['text'])
        self.assertIn('Sunday 25 October at 2:00 PM UK time',b['text'])
        self.assertIsNone(b['match']['home_score'])
        self.assertEqual(b['match']['status'],'TO PLAY')

    def test_live_score_is_explicitly_provisional(self):
        s=self.snapshot();s['fixtures'][0].update(started=True,minutes=45,team_h_score=1,team_a_score=0)
        b=next(b for b in self.roundup(s)['beats'] if b['kind']=='fixture')
        self.assertEqual(b['match']['status'],'LIVE');self.assertIn('Still in progress',b['text'])

    def test_goals_position_cards_and_own_goals_are_not_confused(self):
        s=self.snapshot();s['fixtures'][0].update(started=True,finished=True,minutes=90,team_h_score=0,team_a_score=3,stats=[dict(identifier='goals_scored',h=[],a=[dict(element=2,value=2)]),dict(identifier='own_goals',h=[dict(element=1,value=1)],a=[]),dict(identifier='red_cards',h=[dict(element=1,value=1)],a=[])])
        beats=self.roundup(s)['beats'];scorer=next(b for b in beats if b.get('player_id')==2)
        self.assertIn('midfielder',scorer['text']);self.assertIn('scored twice',scorer['text'])
        own=next(b for b in beats if b.get('player_id')==1)
        self.assertIn('own goal',own['text']);self.assertIn('sent off',own['text']);self.assertNotIn('three-match',own['text'])

    def test_booking_cutoff_counts_club_matches_not_gameweek_number(self):
        p=player(1);p['yellow_cards']=4
        fs=[fixture(i) for i in range(18)]
        for f in fs:f.update(started=True,finished=True,minutes=90,team_h_score=0,team_a_score=0)
        self.assertIn('1-match',booking_warning(p,fs))
        fs.append(dict(fs[0],id=19))
        self.assertEqual(booking_warning(p,fs),'')
        p['yellow_cards']=9
        self.assertIn('2-match',booking_warning(p,fs))

    def test_old_injury_is_not_reported_as_new_match_injury(self):
        s=self.snapshot();s['bootstrap']['elements'][0].update(status='i',news='Knee injury',news_added='2026-09-01T12:00:00Z')
        self.assertFalse(any(b.get('player_id')==1 for b in self.roundup(s)['beats']))
        s['bootstrap']['elements'][0]['news_added']='2026-10-25T18:00:00Z'
        mentions=[m for b in self.roundup(s)['beats'] for m in b.get('mentions',[])]
        self.assertTrue(any(m['player_id']==1 for m in mentions))

    def test_blank_missing_model_and_zero_statistics_stay_distinct(self):
        s=self.snapshot();p=s['bootstrap']['elements'][0];p.update(minutes=90,expected_goals='0.0',expected_assists='0.0',goals_scored=0,assists=0,points_per_game='0.0')
        c=card(p,s,[],9)
        self.assertEqual(c['xg_per90'],0);self.assertIsNone(c['clean_sheet_probability'])
        self.assertEqual(c['fixtures'][0]['fixtures'],[])
        p['minutes']=0;self.assertIsNone(card(p,s,[],9)['xg_per90'])

    def test_double_gameweek_keeps_both_fixtures_and_exact_position_fdr(self):
        s=self.snapshot();s['fixtures']=[dict(fixture(9),event=9),dict(fixture(10),event=9)]
        rows=[dict(fixture_id=fid,home_team_id=1,away_team_id=2,gameweek=9,model_lambda_home=2.16,model_lambda_away=.73,home_clean_sheet_probability=math.exp(-.73),away_clean_sheet_probability=math.exp(-2.16)) for fid in (9,10)]
        p=s['bootstrap']['elements'][0]
        x=upcoming(p,s,rows,9)
        self.assertEqual(len(x[0]['fixtures']),2)
        self.assertAlmostEqual(x[0]['fixtures'][0]['fdr'],1+4*(3.2-2.16)/2.8)
        self.assertIsNone(upcoming(p,s,[],9)[0]['fixtures'][0]['fdr'])

    def test_welcome_does_not_repeat_after_state_reload(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'history.json'
            first=Wording(path,'same');a=first.welcome(8,'Ten matches complete.');first.save()
            second=Wording(path,'same');b=second.welcome(8,'Ten matches complete.');second.save()
            self.assertNotEqual(a,b)

    def test_uk_time_handles_clock_change(self):
        self.assertIn('BST',kickoff_label('2026-10-24T14:00:00Z'))
        self.assertIn('GMT',kickoff_label('2026-10-25T14:00:00Z'))
        self.assertEqual(kickoff_label(None),'KICKOFF TBC')


if __name__=='__main__':unittest.main()
