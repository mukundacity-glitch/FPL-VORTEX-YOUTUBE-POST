"""Build a standalone HTML harness of the Day 1 GW Review scene from the LIVE source.

Everything (pitch scene, hero slot CSS/JS, player card design) is extracted from
1_final_day1.py, so the audit always tests what the notebook will really render.
Usage: python build_harness.py <output_dir>
"""
import ast, re, json, sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[2]
S = pathlib.Path(sys.argv[1]); S.mkdir(parents=True, exist_ok=True)

def _literals():
    wanted = {"PLAYER_CARD_CSS", "PLAYER_CARD_JS", "EMBEDDED_PITCH_TEMPLATE", "CSS", "JS"}
    found = {}
    for node in ast.walk(ast.parse((ROOT / "1_final_day1.py").read_text(encoding="utf-8"))):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) \
           and node.targets[0].id in wanted:
            try:
                value = ast.literal_eval(node.value)
            except Exception:
                continue
            if node.targets[0].id in {"CSS", "JS"} and "vxHeroWrap" not in value:
                continue
            found[node.targets[0].id] = value
    missing = wanted - set(found)
    if missing:
        raise SystemExit(f"Source is missing expected literals: {sorted(missing)}")
    return found

_L = _literals()
out = str(S / "harness.html")
REVIEW={'history':{'points':63,'overall_rank':224495,'rank':2100000,'event_transfers_cost':0,'value':1012},
 'event':{'id':9,'average_entry_score':52,'highest_score':140},'entry':{'name':'FPL VORTEX','last_deadline_value':1012},'previousRank':230000,
 'chips':[{'name':'wildcard','event':4}],
 'fixtures':[{'opp':o,'side':sd,'teamCode':0} for o,sd in [('WHU','H'),('EVE','A'),('FUL','H'),('BRE','A'),('NEW','H')]],
 'players':[{'name':n,'type':t,'points':pt,'bench':False,'captain':n=='Salah','multiplier':2 if n=='Salah' else 1,'photo':'','teamCode':0,'fixture':'WHU (H)'} for n,t,pt in [('Raya',1,2),('Gabriel',2,6),('Van Dijk',2,1),('Saliba',2,9),('Saka',3,2),('Palmer',3,5),('Salah',3,3),('Bruno Fernandes',3,12),('Haaland',4,2),('Isak',4,4),('Watkins',4,7)]]+
   [{'name':f'Sub{j}','type':3,'points':1,'bench':True,'photo':'','teamCode':0,'fixture':'REVIEW FIXTURE'} for j in range(4)]}
html=_L['EMBEDDED_PITCH_TEMPLATE']
CSS=_L['CSS']; JS=_L['JS']
PCSS=_L['PLAYER_CARD_CSS']; PJS=_L['PLAYER_CARD_JS']
for k,v in {'__PL_BUG_CSS__':'','__VORTEX_LOGO_HTML__':'<div class="vortex-logo" style="font:900 120px Arial;color:#fff">FPL VORTEX</div>','__PL_BUG_HTML__':'<div class="plBug" style="width:150px;height:150px;border-radius:50%;background:#fff;opacity:0"></div>','__SEASON_FULL__':'2026/27','__TEAM_ID__':'1','__REVIEW_DATA_JSON__':json.dumps(REVIEW)}.items(): html=html.replace(k,v)
html=re.sub(r"\(async\(\)=>\{\s*if\(CONFIG\.forceDemo\).*?\}\)\(\);","",html,flags=re.S)
svg="data:image/svg+xml;utf8,"+"<svg xmlns='http://www.w3.org/2000/svg' width='600' height='700'><defs><linearGradient id='g' x1='0' y1='0' x2='1' y2='1'><stop offset='0' stop-color='%23446'/><stop offset='1' stop-color='%23a33'/></linearGradient></defs><rect width='600' height='700' fill='url(%23g)'/><circle cx='300' cy='230' r='120' fill='%23d9b08c'/><rect x='120' y='360' width='360' height='340' rx='80' fill='%23c22'/></svg>"
pos=[('GK',50,88),('DEF',22,68),('DEF',50,68),('DEF',78,68),('MID',12,45),('MID',37,45),('MID',63,45),('MID',88,45),('FWD',25,20),('FWD',50,15),('FWD',75,20)]
names=['Raya','Gabriel','Van Dijk','Saliba','Saka','Palmer','Salah','Bruno Fernandes','Haaland','Isak','Watkins']
def card(i,n,p):
    fx=[{'gw':12+k,'opponent':o,'venue':v,'fdr_value':f,'fixdiff':f,'badge':''} for k,(o,v,f) in enumerate([('WHU','H',2),('EVE','A',3),('FUL','H',2),('BRE','A',3),('NEW','H',2),('CHE','A',4)])]
    return {'id':i,'name':n,'full_name':('Virgil '+n) if n=='Van Dijk' else n,'first_name':'Virgil' if n=='Van Dijk' else n.split()[0],
      'surname':'Van Dijk' if n=='Van Dijk' else (' '.join(n.split()[1:]) or n),'position':p,'position_label':{'GK':'GOALKEEPER','DEF':'DEFENDER','MID':'MIDFIELDER','FWD':'FORWARD'}[p],
      'club':'LIVERPOOL','club_badge':'','player_image':PHOTO,'price':'£6.4m','ownership':'24.3%','avg_minutes_per_start':'88','captain':False,
      'display_stats':[{'icon':'ball','label':'xG PER 90','value':'0.03'},{'icon':'boot','label':'xA PER 90','value':'0.08'},{'icon':'target','label':'GOALS PER 90','value':'0.12'},{'icon':'assist','label':'ASSISTS PER 90','value':'0.08'},{'icon':'shield','label':'CLEAN SHEETS %','value':'52%'},{'icon':'star','label':'POINTS PER MATCH','value':'5.8'}],
      'verdict_sub':'GW 9 | 6 PTS | 90 MIN | WHU H 2-1',
      'fixtures':fx,'season_label':'2026/27'}
PHOTO=svg  # synthetic portrait; no real photo is needed for layout checks
starters=[]; segs=[]; t=4.0
for i,((p,x,y),n) in enumerate(zip(pos,names),1):
    c=card(i,n,p)
    starters.append({'id':i,'name':n,'pos':p,'pitch_x':x,'pitch_y':y,'points':[2,6,1,9,2,5,3,12,2,4,7][i-1],'captain':i==7,'vice':False,'photo':'','code':0,'team_code':0,'fixture':{'opp':'WHU','ha':'H','score':''},'card':c})
    dur=17.5
    segs.append({'id':f'player_{i}','player_id':i,'kind':'starter','t0':t,'t1':t+dur,'speech_end_at':t+dur-1,'reveal_at':t+1.0,'hero_on':t+1.0,'hero_exit_at':t+dur,'hero_off':t+dur+.34})
    t+=dur
bench_t=t
bench=[]
for j in range(4):
    bench.append({'id':20+j,'name':f'Sub{j}','pos':'MID','points':1,'photo':'','code':0,'team_code':0,'fixture':{'opp':'WHU','ha':'H'}})
    segs.append({'id':f'player_{20+j}','player_id':20+j,'kind':'bench','t0':t+3,'t1':t+3+12,'speech_end_at':t+3+11,'reveal_at':t+4})
    t+=12
metrics_t=t+4
VX={'gw':9,'starters':starters,'bench':bench,'segments':segs,'total':metrics_t+60,'narration_end':metrics_t+55,'timeline':{},'bench_t':bench_t,'metrics_t':metrics_t,'metric_times':{}}
# Post-review market cards reuse the same measured scene and side slot.
VX['market_cards'] = []
for index, action in enumerate(('BUY', 'HOLD', 'SELL')):
    sid = 'market_' + action.lower()
    payload = card(100 + index, 'Market Player ' + str(index + 1), 'MID')
    payload['verdict_sub'] = action + ' WATCHLIST • EVENT MARKET'
    payload['display_stats'] = [
      {'icon':'people','label':'TRANSFERS IN','value':'1,234,567'},
      {'icon':'people','label':'TRANSFERS OUT','value':'987,654'},
      {'icon':'star','label':'RECENT FORM','value':'3.4'},
      {'icon':'clock','label':'SEASON MINUTES','value':'1,020'},
      {'icon':'star','label':'SEASON POINTS','value':'64'},
      {'icon':'star','label':'POINTS PER MATCH','value':'5.8'}]
    start = metrics_t + 12 + index * 12
    segs.append({'id':sid,'t0':start,'t1':start+12,'speech_end_at':start+11.5})
    VX['market_cards'].append({'segment_id':sid,'action':action,'card':payload})
html=html.replace('</head>',PCSS+'\n'+CSS+'\n</head>')
html=html.replace('</body>',PJS+'\n'+JS.replace('__VX_DATA__',json.dumps(VX))+'\n</body>')
pathlib.Path(out).write_text(html,encoding='utf-8')
json.dump(VX,open(str(S/'vx.json'),'w'))
print('harness written',len(html),'mini cards in template:',html.count('class="mini'))
