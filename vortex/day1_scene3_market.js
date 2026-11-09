(() => {
  const {scene,cues,captions}=S3;
  const root=document.querySelector('.vx-s3');
  const stage=root.querySelector('.vx-s3-stage');
  const caption=root.querySelector('.vx-s3-caption');
  const handoff=root.querySelector('.vx-s3-handoff');
  const esc=x=>String(x??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');
  const crest=t=>t.badge?`<img class="vx-s3-crest" src="${esc(t.badge)}" alt="">`:'';
  const pct=p=>p===null?'N/A':(p*100).toFixed(0)+'%';
  const snapshots=[...new Set(scene.targets.map(r=>r.snapshot).filter(Boolean))].sort();
  const asOf=snapshots.length===1?snapshots[0]:snapshots.length?''+snapshots[0]+' – '+snapshots.at(-1):'Unavailable';
  stage.innerHTML=`<div class="vx-s3-kicker">VORTEX MATCHUP BOARD · GW${scene.gw}</div>
    <h1>TOP FIVE <em>FIXTURES TO TARGET</em></h1>
    <p class="vx-s3-deck">Ranked by Vortex attacking FDR · lower is easier</p>
    <div class="vx-s3-market-table">
      <div class="vx-s3-market-row vx-s3-market-head"><span>RANK</span><span>TARGET TEAM</span><span>OPPONENT</span><span>ATTACK FDR</span><span>WIN CHANCE</span><span>CLEAN SHEET</span></div>
      ${scene.targets.map((r,i)=>`<div class="vx-s3-market-row" data-target="${i}">
        <strong>${String(i+1).padStart(2,'0')}</strong>
        <div>${crest(r.team)}<b>${esc(r.team.name)}</b></div>
        <div>${crest(r.opponent)}<b>${esc(r.opponent.name)}</b><small>${r.venue}</small></div>
        <span class="vx-s3-market-rating" data-band="${r.band}">${r.rating}</span>
        <strong class="vx-s3-market-win">${pct(r.win)}</strong>
        <strong class="vx-s3-market-cs">${pct(r.clean_sheet)}</strong>
      </div>`).join('')||'<p>No verified fixture ratings available.</p>'}
    </div>
    <div class="vx-s3-market-meta"><span>MARKET ESTIMATES · ${esc(scene.market_source)}</span><span>ODDS SNAPSHOT · ${esc(asOf)}</span></div>`;
  const rows=[...stage.querySelectorAll('[data-target]')];
  window.__seek=t=>{
    const at=cues.findLastIndex(c=>c.at<=t);
    const current=cues[Math.max(0,at)];
    const selected=current.key.startsWith('target-')?Number(current.key.slice(7)):-1;
    rows.forEach((row,i)=>{
      row.classList.toggle('vx-s3-market-active',i===selected);
      row.style.opacity=selected<0||i===selected?1:.70;
    });
    if(handoff) handoff.style.opacity=Math.max(0,1-t/.55);
    caption.textContent=captions.find(c=>t>=c.start&&t<c.end)?.text||'';
  };
  window.__seek(0);
  window.__ready=true;
})();
