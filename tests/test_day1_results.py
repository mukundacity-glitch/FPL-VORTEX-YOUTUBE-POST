import unittest
from vortex.day1_results import build_results

class Day1ResultsTests(unittest.TestCase):
    def test_events_stay_with_their_fixture_and_pending_scores_are_not_final(self):
        boot = {'teams':[{'id':1,'name':'Home','code':1},{'id':2,'name':'Away','code':2}],
                'elements':[{'id':7,'web_name':'Player','team':1,'code':77}]}
        fixtures = [{'id':10,'event':8,'team_h':1,'team_a':2,'finished':True,'team_h_score':1,'team_a_score':0,
                     'stats':[{'identifier':'goals_scored','h':[{'element':7,'value':1}],'a':[]}]},
                    {'id':11,'event':8,'team_h':2,'team_a':1,'finished':False,'team_h_score':0,'team_a_score':0,'stats':[]}]
        result = build_results(boot, fixtures, 8)
        self.assertEqual(result[0]['returns'][0]['name'], 'Player')
        self.assertEqual(result[0]['score'], [1,0])
        self.assertIsNone(result[1]['score'])
        self.assertFalse(result[1]['final'])
