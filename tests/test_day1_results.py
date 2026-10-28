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

class ShortProductionTests(unittest.TestCase):
    def test_selection_and_forecast_removal(self):
        from vortex.day1_short import patch_cell
        from pathlib import Path
        import re, ast
        cells=[p for p in re.split(r'(?m)(?=^# ={20,}\n# [^\n]*\bCELL\s+\d+[A-Za-z]?\b[^\n]*\n)',Path('1_final_day1.py').read_text()) if p.strip()]
        patched=[patch_cell(c) for c in cells]
        for c in patched: compile(c,'cell','exec',flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
        controls=next(c for c in patched if 'SLIDE_SELECTION = {' in c)
        for name in ('SLIDE_03_FDR','SLIDE_04_PROJECTED_GOALS','SLIDE_05_CLEAN_SHEETS','SLIDE_06_OUTRO'):
            self.assertIn(name+' = False',controls)
        self.assertFalse(any('build_weekly_frame(globals())' in c for c in patched))
        self.assertFalse(any('agenda_1_at=18.0' in c for c in patched))
        self.assertTrue(any('await render_results(globals())' in c for c in patched))

    def test_card_count_does_not_invent_a_suspension(self):
        from vortex.day1_short import warning
        self.assertEqual(warning({'web_name':'A','status':'a','yellow_cards':4}), '')
        text=warning({'web_name':'A','status':'a','yellow_cards':5})
        self.assertIn('does not confirm a ban',text)
        self.assertIn('flagged as suspended',warning({'web_name':'A','status':'s'}))
