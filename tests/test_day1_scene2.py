"""Scene 2 completion, identity, source and original-card integration regressions."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import unittest

from vortex.day1_scene2 import (build_player, completed_gameweek, original_card_literals,
                               player_script, render_times, select_players, sum_verified)

ROOT = Path(__file__).resolve().parents[1]


class Scene2Contracts(unittest.TestCase):
    def fixtures(self):
        return [dict(id=1,event=9,finished=True,team_h=1,team_a=2,team_h_score=2,team_a_score=1)]

    def test_completed_review_rejects_provisional_postponed_and_missing_scores(self):
        boot=dict(events=[dict(id=9,finished=True,data_checked=True),dict(id=10,finished=False)])
        self.assertEqual(completed_gameweek(boot,self.fixtures()),9)
        for change in (dict(finished=False),dict(team_h_score=None)):
            rows=self.fixtures();rows[0].update(change)
            with self.assertRaises(ValueError):completed_gameweek(boot,rows)
        rows=self.fixtures()+[dict(event=9,finished=False)]
        with self.assertRaises(ValueError):completed_gameweek(boot,rows)
        boot['events'][0]['data_checked']=False
        with self.assertRaises(ValueError):completed_gameweek(boot,self.fixtures())

    def test_double_gameweek_aggregation_and_missing_is_not_zero(self):
        self.assertEqual(sum_verified([dict(expected_goals='0.40'),dict(expected_goals='0.25')],'expected_goals'),.65)
        self.assertIsNone(sum_verified([dict(expected_goals='0.40'),{}],'expected_goals'))
        self.assertEqual(sum_verified([dict(expected_goals='0.00')],'expected_goals'),0)
        self.assertIsNone(sum_verified([],'expected_goals'))

    def test_original_hero_card_is_extracted_without_design_replacement(self):
        literals=original_card_literals()
        self.assertIn('V6.0_SIDE_HERO_SAMPLE',literals['PLAYER_CARD_JS'])
        self.assertIn('window.VXPlayerCard',literals['PLAYER_CARD_JS'])
        self.assertIn('pc-portrait',literals['PLAYER_CARD_CSS'])
        self.assertIn('pc-stat-rows',literals['PLAYER_CARD_CSS'])
        self.assertIn('NEXT 5 FIXTURES',literals['PLAYER_CARD_JS'])
        source=(ROOT/'1_final_day1.py').read_text()
        self.assertIn('GW_REVIEW_SCENE2_MP4 = production_entry(globals())',source)
        self.assertIn('VIDEO / "gw_review.mp4"',source)

    def test_selection_is_distinct_and_uses_more_than_top_points(self):
        players=[dict(id=i,now_cost=100 if i==3 else 60,selected_by_percent=str(80 if i in (3,5) else 2),status='a') for i in range(1,6)]
        live=dict(elements=[dict(id=i,stats=dict(minutes=35 if i==5 else 90,total_points=2 if i in (3,5) else 20-i,
            goals_scored=1 if i==2 else 0,assists=0)) for i in range(1,6)])
        chosen=select_players(dict(elements=players),live)
        self.assertEqual(len({p['id'] for p in chosen}),5)
        self.assertEqual(next(p for p in chosen if p['story']=='PREMIUM UNDER SCRUTINY')['id'],3)
        self.assertEqual(chosen[-1]['id'],5)

    def test_player_mapping_and_summary_reconciliation(self):
        now=datetime.now(timezone.utc).isoformat()
        meta={k:dict(source='official/'+k,retrievedAt=now) for k in ('bootstrap','fixtures','live','summary')}
        identity=dict(id=7,team=1,code=123,first_name='Test',second_name='Player',web_name='Player',element_type=3,
                      now_cost=60,selected_by_percent='2.0',status='a',news='',minutes=90,expected_goals='0.1',expected_assists='0.2',goals_scored=0,assists=1,clean_sheets=0,points_per_game='5.0')
        boot=dict(teams=[dict(id=1,code=3,name='Actual club',short_name='ACT'),dict(id=2,code=4,name='Opponent',short_name='OPP')],
                  element_types=[dict(id=3,singular_name_short='MID')],events=[dict(id=9,deadline_time='2026-10-01T10:00:00Z')])
        stats=dict(total_points=5,minutes=90,goals_scored=0,assists=1)
        history=dict(history=[dict(round=9,**stats,starts=1)])
        player=build_player(identity,stats,history,meta,boot,self.fixtures(),9,11,'GAMEWEEK STANDOUT')
        self.assertEqual(player['club'],'Actual club')
        self.assertIn('t3.png',player['card']['club_badge'])
        self.assertIsNone(player['fields']['expected_goals']['value'])
        self.assertEqual(player['verdict'],'MONITOR')
        self.assertTrue(all('retrievedAt' in item and 'source' in item for item in player['fields'].values()))
        history['history'][0]['total_points']=6
        with self.assertRaisesRegex(ValueError,'mismatch'):
            build_player(identity,stats,history,meta,boot,self.fixtures(),9,11,'GAMEWEEK STANDOUT')

    def test_narration_windows_use_actual_measured_boundaries(self):
        segments=[dict(t0=0,t1=10,kind='chapter',captions=[dict(start=1.125,end=2.25)],cues={}),
                  dict(t0=10,t1=42,kind='player',captions=[],cues=dict(points=19.4))]
        times=render_times(segments)
        self.assertIn(19.4,times)
        self.assertIn(1.125,times)
        self.assertLess(times[-1],42)
        self.assertEqual(times,sorted(set(times)))


if __name__=='__main__':unittest.main()
