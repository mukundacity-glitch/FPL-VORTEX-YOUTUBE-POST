"""Evidence/pacing regressions for the production pitch review, not CSS snapshots."""
import copy
import json
import tempfile
import unittest
import wave
from pathlib import Path
from vortex.day1_review import build_review, build_review_timeline, enrich_review_package, normalize_player
from vortex.day1_show import BANNED
from vortex.day1_show_media import event_soundtrack, sound_graph
from vortex.day1_show_render import build_visual_timeline, fit_word_timing

FIXTURE = Path(__file__).parent / 'fixtures/day1_synthetic.json'


def fixture():
    return json.loads(FIXTURE.read_text())


def words_for(show):
    result=[]
    for s in show['sections']:
        tokens=s['text'].split(); step=(s['duration']-.5)/len(tokens)
        result.extend({'text':text,'start':s['start']+i*step,'duration':step*.8,'section_id':s['id']} for i,text in enumerate(tokens))
    return result


class PitchReviewTests(unittest.TestCase):
    def test_all_nine_scenes_and_all_fifteen_players_are_timed(self):
        package=fixture(); original=copy.deepcopy(package); show=build_review(package)
        self.assertEqual(package,original)
        self.assertEqual(show['package'],package)
        self.assertEqual(show['duration'],400)
        self.assertEqual([s['start'] for s in show['scenes']],[0,18,50,100,145,175,205,350,380])
        reviews=[s for s in show['sections'] if s['scene']=='reviews']
        benches=[s for s in show['sections'] if s['scene']=='bench']
        self.assertEqual(len(reviews),11);self.assertEqual(len(benches),4)
        self.assertEqual({s['player_id'] for s in reviews+benches},{p['id'] for p in package['players']})
        self.assertTrue(all(10<=s['duration']<=16 for s in reviews))
        self.assertTrue(all(s['duration']==15 for s in show['sections'] if s['id'] in ('top_1','top_2','top_3','worst_1','worst_2','worst_3')))
        self.assertEqual(show['formation'],[4,4,2])
        text=' '.join(s['text'] for s in show['sections'])
        self.assertTrue(700<=len(text.split())<=950)
        self.assertFalse(any(p in text.casefold() for p in BANNED))
        self.assertIn('league data pending',show['performer_scope'])
        self.assertTrue(all(a['end']==b['start'] for a,b in zip(show['sections'],show['sections'][1:])))

    def test_bench_regret_and_captain_use_actual_multipliers(self):
        package=fixture(); show=build_review(package)
        self.assertEqual(show['accuracy']['captain_points'],-2)
        self.assertEqual(show['accuracy']['actual_bench_regret_id'],14)
        self.assertFalse(next(p for p in show['players'] if p['id']==3)['isBench'])
        for p in package['players']:
            if p['bench']: p['multiplier']=1
        show=build_review(package)
        self.assertIsNone(show['accuracy']['actual_bench_regret_id'])
        self.assertFalse(any(p['action']=='bench-haul' for p in show['players']))
        for p in package['players']:
            if p['id']==9: p.update(points=0,multiplier=0)
            if p['id']==10: p['multiplier']=2
        show=build_review(package)
        self.assertEqual(show['accuracy']['captain_points'],16)
        self.assertIn('captain contribution: 16',show['sections'][0]['text'])

    def test_missing_event_fields_are_not_invented(self):
        player=normalize_player(fixture()['players'][0],[])
        self.assertNotIn('goals',player)
        self.assertEqual(player['event_summary'],'Data pending')
        self.assertEqual(player['action'],'points')
        p=fixture();p['players'][12].update(status='d',news='Waiting for assessment')
        show=build_review(p)
        player=next(x for x in show['players'] if x['id']==13)
        self.assertEqual(player['verdict'],'WAIT FOR TEAM NEWS')
        self.assertNotIn('thigh',' '.join(s['text'] for s in show['sections']))

    def test_timing_routes_new_show_without_changing_existing_voice_gate(self):
        show=build_review(fixture());words=words_for(show)
        build_visual_timeline(show,words)
        self.assertEqual(show['words'],words)
        self.assertGreater(len(show['beats']),50)
        self.assertTrue(all(15<=s['end']-s['start']<=35 for s in show['shorts']))
        self.assertTrue(0<=show['impact_at']<18)
        self.assertLessEqual(len(show['sound_cues']),15)
        self.assertEqual(show['sound_cues'][0]['kind'],'impact')
        section=show['sections'][0]
        with self.assertRaisesRegex(RuntimeError,'tempo range'):
            fit_word_timing(section,[{'text':'too short','start':0,'duration':1}])

    def test_league_performers_come_from_same_snapshot_not_the_example_script(self):
        p=fixture(); teams=[{'id':i,'code':i,'short_name':f'T{i}','name':f'Club {i}'} for i in range(1,17)]
        elements=[];live=[]
        for player in p['players']:
            pid=player['id']
            elements.append({'id':pid,'team':pid,'web_name':player['name'],'element_type':{'GK':1,'DEF':2,'MID':3,'FWD':4}[player['pos']], 'status':player['status'],'news':player['news'],'now_cost':70})
            live.append({'id':pid,'stats':{'total_points':player['points'],'minutes':player['minutes'],'goals_scored':1 if pid==3 else 0}})
        elements.append({'id':99,'team':16,'web_name':'Verified league hero','element_type':3,'status':'a','now_cost':85})
        live.append({'id':99,'stats':{'total_points':22,'minutes':90,'goals_scored':3}})
        ns={'GW_REVIEW':{'bootstrap':{'teams':teams,'elements':elements},'live':{'elements':live},'fixtures':[{'id':1,'event':8,'finished':True,'team_h':16,'team_a':3,'team_h_score':3,'team_a_score':1}]},'resolve_player_photo':lambda p:''}
        enriched=enrich_review_package(ns,p)
        self.assertEqual(enriched['top_ids'][0],99)
        self.assertEqual(enriched['matches'][0]['home_score'],3)
        self.assertIsNone(enriched['players'][0]['bonus'])
        show=build_review(enriched)
        self.assertEqual(show['top_ids'][0],99)
        self.assertEqual(next(s for s in show['sections'] if s['id']=='top_1')['player_id'],99)
        self.assertEqual(len([s for s in show['sections'] if s['scene']=='reviews']),11)

    def test_audio_cues_keep_sidechain_ducking_and_are_local(self):
        self.assertIn('sidechaincompress',sound_graph(400,2,True))
        self.assertIn('adelay=0',sound_graph(400,2,True))
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'fx.wav'
            event_soundtrack(path,2,[{'at':.2,'kind':'whoosh'},{'at':.6,'kind':'crowd'}])
            with wave.open(str(path),'rb') as media:
                self.assertEqual(media.getnframes(),96000)
                self.assertEqual(media.getframerate(),48000)
                self.assertNotEqual(set(media.readframes(96000)),{0})


if __name__=='__main__': unittest.main()
