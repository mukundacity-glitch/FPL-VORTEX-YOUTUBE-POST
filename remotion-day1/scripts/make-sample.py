"""Deterministic SYNTHETIC fixture. Never used by the production data adapter."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from vortex.day1_review import build_review, build_review_timeline
root = Path(__file__).resolve().parents[2]
package = json.loads((root / 'tests/fixtures/day1_synthetic.json').read_text())
package['performer_scope'] = 'Synthetic preview · verified test fixture · not live FPL data'
# Test-only events exercise every visual action; these are not real-world claims.
for p in package['players']:
    p.update(goals=0, assists=0, clean_sheets=0, saves=0, bonus=0)
    p['fixtures'] = [dict(p['next_fixture'], gw=9+i) for i in range(5)]
for pid, changes in {1:{'clean_sheets':1,'saves':4,'bonus':1},3:{'goals':1,'clean_sheets':1,'bonus':3},4:{'clean_sheets':1},6:{'assists':1},10:{'goals':1,'bonus':2}}.items():
    next(p for p in package['players'] if p['id']==pid).update(changes)
show=build_review(package)
words=[]
for section in show['sections']:
    tokens=section['text'].split();step=(section['duration']-.5)/len(tokens)
    words.extend({'text':token,'start':section['start']+i*step,'duration':step*.85,'section_id':section['id']} for i,token in enumerate(tokens))
build_review_timeline(show,words)
props={'show':show,'start':0,'end':400,'width':1920,'height':1080,'vertical':False,'fontCss':'','verdictColors':{},'popup':None}
(root / 'remotion-day1/sample-props.json').write_text(json.dumps(props,indent=2))
print(f'Synthetic sample: {sum(len(s["text"].split()) for s in show["sections"])} words, 400 seconds, 15 individual reviews')
