(() => {
  const {scene, cues, captions, card_css} = S3;
  const root = document.querySelector('.vx-s3');
  const stage = root.querySelector('.vx-s3-stage');
  const caption = root.querySelector('.vx-s3-caption');
  const scanner = root.querySelector('.vx-s3-scanner');
  const handoff = root.querySelector('.vx-s3-handoff');
  const esc = x => String(x ?? 'N/A').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
  const crest = team => team.badge ? `<img class="vx-s3-crest" src="${esc(team.badge)}" alt="">` : '';
  const fixture = (tile, side) => `<div class="vx-s3-fdr-cell" data-band="${tile[side].band}"><span>${esc(tile.opponent)} · ${tile.venue}</span><b>${tile[side].rating}</b></div>`;
  const empty = '<span class="vx-s3-empty">N/A</span>';
  const week = (tiles, side) => tiles.length ? tiles.map(t => fixture(t,side)).join('') : '<span class="vx-s3-empty">BLANK</span>';
  const row = (r, swing=false) => `<div class="vx-s3-row ${r===scene.rows[0]&&!swing?'vx-s3-lead':''}"><div>${crest(r.team)}${esc(r.team.short)}</div>${r.weeks.map(tiles=>`<div class="vx-s3-week">${week(tiles,'attack')}</div>`).join('')}</div>`;
  const heatmap = rows => `<div class="vx-s3-fdr-table"><div class="vx-s3-row vx-s3-axis"><span>CLUB</span>${scene.horizon.map(g=>`<span>GW${g}</span>`).join('')}</div>${rows.map(r=>row(r,rows!==scene.rows)).join('')||empty}</div>`;
  const header = (k,title,subtitle='') => `<div class="vx-s3-kicker">${k}</div><h1>${title}</h1>${subtitle?'<p class="vx-s3-deck">'+subtitle+'</p>':''}`;
  const metrics = (p,defs) => defs.map(([key,label])=>`<div><b>${esc(p.recent?.[key])}</b><span>${label}</span></div>`).join('');
  const minutesPoints = [['minutes','MINUTES'],['total_points','POINTS']];
  const attackStats = [...minutesPoints,['goals_scored','GOALS'],['assists','ASSISTS']];
  const nextTiles = p => p.next.map(t=>fixture(t,p.side)).join('')||empty;
  const playerLane = p => `<article class="vx-s3-lane">${crest(p.team)}<h2>${esc(p.name)}</h2><p>${esc(p.team.name)}</p>
    <div class="vx-s3-next">${nextTiles(p)}</div><div class="vx-s3-metrics">${metrics(p,attackStats)}</div></article>`;
  const hero = p => `<div class="vx-s3-hero-grid"><article class="vx-s3-lane">
    <div class="vx-s3-club">${crest(p.team)}${esc(p.team.name)} · ${p.card.position}</div><h2>${esc(p.name)}</h2>
    <div class="vx-s3-kicker">NEXT OPPONENT · VORTEX ${p.side.toUpperCase()} FDR</div>
    <div class="vx-s3-next">${nextTiles(p)}</div>
    <div class="vx-s3-kicker">RECORDED · LAST FIVE GAMEWEEKS · ${esc(p.recent?.matches)} MATCHES</div>
    <div class="vx-s3-metrics">${metrics(p,p.side==='attack'?attackStats:[...minutesPoints,['clean_sheets','CLEAN SHEETS'],[p.card.position==='GK'?'saves':'assists',p.card.position==='GK'?'SAVES':'ASSISTS']])}</div>
    ${p.xpts==null?'':`<div class="vx-s3-kicker">VORTEX FORECAST · ${p.xpts.toFixed(1)} xPTS</div>`}<div class="vx-s3-verdict">${p.assessment} <small>· ${esc(p.status)}</small></div></article><div class="vx-s3-hero-host"></div></div>`;
  const watch = (label,p,reason) => `<article class="vx-s3-lane"><div class="vx-s3-kicker">${label}</div>${p?
    `${crest(p.team)}<h2>${esc(p.name)}</h2><div class="vx-s3-next">${nextTiles(p)}</div><p>${esc(reason)}</p>`:empty}</article>`;
  const {attack,defence} = scene.watch;
  const risk = scene.risk[0];
  const panels = {
    opening: `<div class="vx-s3-hero-title">${header('CHAPTER 03 · PLAYERS &amp; FIXTURES','THE ROAD<br><em>AHEAD</em>','THE NEXT FIVE GAMEWEEKS · FIXTURE INTELLIGENCE')}</div>`,
    fixtures: header('THE COMPLETE SCHEDULE',`GAMEWEEK ${scene.gw} <em>FIXTURES</em>`, 'Kickoff times in New York')+
      `<div class="vx-s3-fixtures" style="--fixture-rows:${Math.max(1,Math.ceil(scene.fixtures.length/2))}">${scene.fixtures.map(f=>
        `<article class="vx-s3-fixture"><small>${esc(f.kickoff)}</small><div>${crest(f.home)}<b>${esc(f.home.name)}</b><span>VS</span><b>${esc(f.away.name)}</b>${crest(f.away)}</div></article>`).join('')||empty}</div>`,
    heatmap: header('VORTEX ATTACKING FDR','FIVE-GAMEWEEK <em>MAP</em>','Lower values indicate easier fixtures · home (H) · away (A)')+heatmap(scene.rows)+
      '<div class="vx-s3-legend"><i data-band="easy">1.0–2.5</i><i data-band="medium">2.6–3.0</i><i data-band="hard">3.1–4.0</i><i data-band="very-hard">4.1–5.0</i></div>',
    attack: header('MINUTES · ROLE · OPPONENT','ATTACKING <em>OPPORTUNITIES</em>','Recorded returns across the last five Gameweeks')+
      `<div class="vx-s3-lanes">${scene.picks.attack.map(playerLane).join('')||empty}</div>`,
    risk: header('OFFICIAL FPL STATUS','AVAILABILITY <em>&amp; MINUTES</em>',esc(scene.stamp))+
      `<div class="vx-s3-risks">${scene.risk.map(p=>`<article class="vx-s3-risk" data-warning="${p.status!=='Available'}">${crest(p.team)}<div><h2>${esc(p.name)}</h2><p>${esc(p.news || p.team.name)}</p></div><strong>${esc(p.status==='Available'?'LIMITED OR UNKNOWN MINUTES':p.status.toUpperCase())}</strong><div class="vx-s3-metrics">${metrics(p,[['minutes','RECENT MINUTES']])}</div></article>`).join('')||empty}</div>`,
    swings: header('FIRST TWO VS LAST TWO GAMEWEEKS','FIXTURE <em>SWINGS</em>','Arrows indicate changes in fixture difficulty')+
      `<div class="vx-s3-swings"><article><h2>↘ FIXTURES IMPROVING</h2>${heatmap(scene.improving)}</article><article><h2>↗ FIXTURES HARDENING</h2>${heatmap(scene.hardening)}</article></div>`,
    watchlist: header('THE THREE THINGS TO CHECK','PLAYER <em>WATCHLIST</em>')+
      `<div class="vx-s3-lanes">${watch('ATTACKING OPPORTUNITY',attack,'Favourable next attacking matchup. Confirm the starting role.')}${watch('DEFENSIVE OPPORTUNITY',defence,'Favourable next defensive matchup. Check minutes and the defensive setup.')}${watch('MINUTES / RISK WATCH',risk,risk?.status==='Available'?'Check recent minutes and the starting role.':`Official status: ${risk?.status}. Check the latest team update.`)}</div>`,
    conclusion: header('THE ROAD AHEAD','THREE THINGS <em>THAT MATTER</em>')+
      `<div class="vx-s3-lanes">${[
        ['BEST FIXTURE RUN',scene.easiest?.team.name,'Lowest complete five-Gameweek attacking FDR'],
        ['BEST INDIVIDUAL MATCHUP',attack?.name,attack?.next.map(t=>`${t.name} (${t.venue})`).join(' · ')],
        ['BIGGEST QUESTION',risk?.name,risk?.status==='Available'?'Confirm recent minutes':risk?.status]
      ].map(([label,name,detail])=>`<article class="vx-s3-lane"><div class="vx-s3-kicker">${label}</div><h2>${esc(name)}</h2><p>${esc(detail)}</p></article>`).join('')}</div>`,
    transition: `<div class="vx-s3-hero-title vx-s3-axes">${header('CHAPTER 04','NUMBERS &amp;<br><em>MARKET OUTLOOK</em>')}</div>`
  };
  for (const [side, group] of Object.entries(scene.picks)) {
    group.forEach((p,i)=>{ panels[`${side}-${i}`] = header(side.toUpperCase()+' WATCH','PLAYER <em>SPOTLIGHT</em>')+hero(p); });
  }
  stage.innerHTML = cues.map(({key})=>`<section class="vx-s3-beat" data-beat="${key}" hidden>${panels[key]}</section>`).join('');
  const sections = [...stage.children];
  const reveal = (section,selector,t,delay,stagger) => section.querySelectorAll(selector).forEach((node,i)=>{
    const p=Math.min(1,Math.max(0,(t-delay-i*stagger)/.5));
    node.style.opacity=p;
    node.style.translate=`0 ${(1-p)*14}px`;
  });
  let active = -1;
  const hosts = new Map();
  window.__seek = time => {
    const found = cues.findLastIndex(c=>c.at<=time);
    const index = Math.max(0,found);
    const section = sections[index];
    const key = cues[index].key;
    const local = time-cues[index].at;
    if(index!==active) {
      if(active>=0) sections[active].hidden=true;
      section.hidden=false;
      const host=section.querySelector('.vx-s3-hero-host');
      if(host&&!hosts.has(host)){
        const [side,i]=key.split('-');
        const shadow=host.attachShadow({mode:'open'});
        shadow.innerHTML=card_css+'<div class="heroMount" style="width:1244px;height:1649px;transform:scale(.345);transform-origin:0 0"></div>';
        const mount=shadow.querySelector('.heroMount');
        window.VXPlayerCard.mount(mount,scene.picks[side][Number(i)].card);
        hosts.set(host,mount);
      }
      if(host) window.VXPlayerCard.fitText(hosts.get(host));
      active=index;
    }
    if(handoff) handoff.style.opacity=Math.max(0,1-time/.7);
    const scan=Math.min(1,Math.max(0,(local-.30)/.85));
    scanner.style.left=`${5+90*scan}%`;
    scanner.style.opacity=scan===1?0:Math.sin(Math.PI*scan)*.9;
    reveal(section,'.vx-s3-fixture,.vx-s3-risk,.vx-s3-lanes>.vx-s3-lane',local,.15,.14);
    reveal(section,'.vx-s3-fdr-table .vx-s3-week',local,.20,.035);
    reveal(section,'.vx-s3-hero-host,.vx-s3-hero-title',local,.06,0);
    reveal(section,'.vx-s3-hero-grid .vx-s3-next',local,1,0);
    reveal(section,'.vx-s3-hero-grid .vx-s3-metrics>div',local,2,.16);
    const next=cues[index+1]?.at;
    if(next!==undefined) section.style.opacity=Math.min(1,Math.max(0,(next-time)/.29));
    const verdict=section.querySelector('.vx-s3-verdict');
    if(verdict) verdict.style.opacity=Math.min(1,Math.max(0,(local-(next-cues[index].at-3))/.45));
    caption.textContent=captions.find(c=>time>=c.start&&time<c.end)?.text||'';
  };
  window.__seek(0);
  window.__ready=true;
})();
