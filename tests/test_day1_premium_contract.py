import ast
import json
import re
import unittest
from pathlib import Path
from typing import Any
from vortex.day1_short import patch_cell, results_assets, results_html

SOURCE=Path('1_final_day1.py').read_text()
TREE=ast.parse(SOURCE)
def constant(name):
    return next(ast.literal_eval(n.value) for n in TREE.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in n.targets))
def fixture_namespace():
    logo='data:image/svg+xml,'+__import__('urllib.parse',fromlist=['quote']).quote('<svg xmlns="http://www.w3.org/2000/svg" width="120" height="140"><path fill="#ffd449" d="M10 10h100v80l-50 40-50-40z"/></svg>')
    team={'id':1,'code':1,'name':'Test Club','short_name':'TST'}
    player={'id':1,'code':1,'team':1,'element_type':3,'web_name':'QA Player','first_name':'QA','second_name':'Player','minutes':900,'starts':10,'goals_scored':6,'assists':4,'total_points':65,'now_cost':75,'selected_by_percent':'12.3','form':'6.5','expected_goals':'5.2','expected_assists':'3.1','expected_goal_involvements':'8.3','status':'a'}
    ns={'PLAYER_CARD_CSS':constant('PLAYER_CARD_CSS'),'PLAYER_CARD_JS':constant('PLAYER_CARD_JS'),'vortex_logo_html':f'<img src="{logo}">','EPL_SEASON':2026,'team_meta_by_id':{1:{'id':1,'code':1,'badge':logo}},'team_meta_by_short':{'TST':{'badge':logo}},'_PC_SEASON_LABEL':'2026/27 SEASON','_POSITION_LABEL':{'MID':'MIDFIELDER'},'re':re,'math':__import__('math'),'Any':Any,'_pc_fdr_rows':{},'REVIEW_GW':8,'resolve_player_photo':lambda p:logo}
    for n in TREE.body:
        if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and (n.name.startswith('_pc_') or n.name in ('vx_review_number','vx_review_player_result_state')):
            exec(compile(ast.Module(body=[n],type_ignores=[]),'original-helper','exec'),ns)
    ns['GW_REVIEW']={'bootstrap':{'teams':[team],'elements':[player]},'live':{'elements':[{'id':1,'stats':{'total_points':10,'minutes':90,'bonus':2,'bps':30}}]},'gw':8,'fixtures':[]}
    rows=[{'home':'Home Club','away':'Away Club','home_code':1,'away_code':1,'score':[2,1],'final':True,'kickoff':'2026-10-25T14:00:00Z'} for _ in range(10)]
    return ns,player,rows

class PremiumContractTests(unittest.TestCase):
    def test_review_script_is_not_truncated_and_original_moods_are_used(self):
        cells=[c for c in re.split(r'(?m)(?=^# ={20,}\n# [^\n]*\bCELL\s+\d+[A-Za-z]?\b[^\n]*\n)',SOURCE) if c.strip()]
        review=next(c for c in cells if '# CELL 15 — AUTO' in c)
        restored=patch_cell(review)
        self.assertNotIn('shorten_review',restored)
        self.assertIn('profile = vx_tts_profile(mood)',restored)
        before=next(n for n in ast.parse(review).body if isinstance(n,ast.FunctionDef) and n.name=='vx_review_creator_player_text')
        after=next(n for n in ast.parse(restored).body if isinstance(n,ast.FunctionDef) and n.name=='vx_review_creator_player_text')
        self.assertEqual(ast.dump(before),ast.dump(after))
        for cell in cells:compile(patch_cell(cell),'patched','exec',flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)

    def test_original_hero_data_and_design_are_reused(self):
        ns,p,rows=fixture_namespace()
        cards=results_assets(ns,[{'player':p}])
        self.assertEqual(cards[1]['stats']['goals'],6)
        self.assertEqual(cards[1]['stats']['assists'],4)
        self.assertEqual(cards[1]['price'],'£7.5m')
        html=results_html(ns,8,rows,cards)
        self.assertIn(ns['PLAYER_CARD_CSS'],html)
        self.assertIn(ns['PLAYER_CARD_JS'],html)
        self.assertIn('VXPlayerCard.mount',html)
        self.assertEqual(html.count('class="match"'),10)
        self.assertEqual(html.count('class="kick"'),10)
        self.assertIn('grid-template-columns:1fr 1fr',html)
        self.assertNotIn('opacity:0;',html.split('</style>',1)[0])
