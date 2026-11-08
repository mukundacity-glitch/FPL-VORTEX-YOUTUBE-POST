"""Scene 2 player introduction and landing contract for the REAL Day 1 renderer."""
import ast
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=(ROOT/"1_final_day1.py").read_text(encoding="utf-8")

def script_literal(name):
    tree=ast.parse(SOURCE)
    for node in tree.body:
        if isinstance(node,ast.Assign):
            if any(isinstance(x,ast.Name) and x.id==name for x in node.targets):
                try:
                    value=ast.literal_eval(node.value)
                except (ValueError, TypeError):
                    continue
                if isinstance(value,str) and 'vx-review-engine' in value:
                    return value
    raise AssertionError("Existing Day 1 review engine missing")

class Scene2RendererIntegrationTests(unittest.TestCase):
    def test_uses_original_pitch_and_hero_card_runtime(self):
        js=script_literal("JS")
        self.assertIn("VX.starters.map(p=>pitchCard(p))",js)
        self.assertIn("window.VXPlayerCard.mount(hw, p.card || p)",js)
        self.assertIn("window.VXPlayerCard.mount(flightEl,p.card||p)",js)
        self.assertIn('id="vxHeroFlight"',js) if False else self.assertIn('flight.id="vxHeroFlight"',js)

    def test_player_lands_only_after_speech_and_persists(self):
        js=script_literal("JS")
        self.assertIn("t-end-flightSeconds",js)
        self.assertIn('s.speech_end_at ?? s.t1',js)
        self.assertIn('const flying=VX.segments.find',js)
        self.assertIn("vxSquadSettled",js)
        self.assertIn('s.kind==="starter" || s.kind==="bench"',js)
        self.assertIn('t < VX.metrics_t',js)

    def test_review_preserves_original_table_captain_and_market_desk(self):
        js=script_literal("JS")
        for token in ('#captainReturn','#gwPoints','#overallRank',
                      '#benchPoints','#hitPoints','VX.market_cards',
                      '.reviewPanel .metric','pitchGW'):
            self.assertIn(token,SOURCE,token)

    def test_extracted_review_js_parses_in_node(self):
        js=script_literal("JS").replace("__VX_DATA__","{}")
        js=re.sub(r'^<script[^>]*>\s*','',js).replace("</script>","")
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"scene2-review.js"
            path.write_text(js,encoding="utf-8")
            result=subprocess.run(["node","--check",str(path)],
                                  capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

if __name__=="__main__":
    unittest.main()
