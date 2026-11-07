/* All animation is derived from the measured narration timeline. */
(() => {
  const {review,segments}=SCENE2;
  const content=document.querySelector('#scene2-content');
  const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
  const esc=value=>String(value??'N/A').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
  const text=value=>value===null||value===undefined?'N/A':String(value);
  const ease=value=>1-Math.pow(1-Math.max(0,Math.min(1,value)),3);
  const cueWords=segments.flatMap(s=>s.captions);
  // Native Cell 16 slot: 1202 + 30 + 12 wide, 1642 + 4 + 3 high.
  const nativeCard={width:1244,height:1649};
  let mounted=null;
  let cardRoot=null;
  document.body.classList.add('video');
  document.querySelectorAll('.controls,.review').forEach(e=>e.style.display='none');
  document.querySelector('.agenda-card:last-child')?.classList.add('active');

  function stat(key,label,value){
    return `<div class="analytics-stat" data-stat="${key}"><span>${label}</span><strong>${esc(text(value))}</strong></div>`;
  }
  function playerMarkup(player){
    const f=Object.fromEntries(Object.entries(player.fields).map(([key,item])=>[key,item.value]));
    const m=player.market;
    const first=m.nextFixture;
    const upcoming=`${first.opponent} (${first.venue})`;
    const recent=`${text(f.recent_starts)} starts · ${text(f.recent_minutes)} minutes · last five completed GWs`;
    const involvement=f.recent_xg==null||f.recent_xa==null?'N/A':(f.recent_xg+f.recent_xa).toFixed(2);
    const movement=`${m.net>0?'+':'−'}${Math.abs(m.net).toLocaleString('en-GB')}`;
    return `<section class="spotlight"><div class="spotlight-hero" aria-label="Original FPL VORTEX Hero Card"></div><div class="analytics">
      <div class="scene-label">${esc(player.story)} · GW${review.nextGameweek} DECISION</div>
      <h2>${esc(player.name)} <span class="accent">/ THE EVIDENCE</span></h2>
      <div class="player-context">${esc(player.club)} • ${esc(player.position)} • £${m.price.toFixed(1)}m • ${m.ownership}% owned</div>
      <div class="stat-grid">${stat('xpts',`xPTS · ${esc(m.projectionSource)}`,m.xpts.toFixed(1))}${stat('movement','NET TRANSFERS',movement)}${stat('next','NEXT OPPONENT',upcoming)}${stat('fdr','OFFICIAL FDR',`${text(first.fdr)} / 5`)}${stat('minutes','EXPECTED MINUTES',m.expectedMinutes==null?'N/A':Math.round(m.expectedMinutes))}${stat('form','FPL FORM',m.form)}${stat('xgi','xG + xA · LAST 5 GW',involvement)}${stat('points',`GW${review.gameweek} POINTS`,f.total_points)}</div>
      <div class="evidence-note"><b>STARTING EVIDENCE</b><br>${esc(recent)} · ${esc(f.status==='a'?'Listed available by FPL':f.news||'FPL availability flag')}</div>
      <div class="verdict ${player.verdict==='MONITOR'?'monitor':''}"><strong>${esc(player.verdict)}</strong><span>${esc(player.reason)}</span></div>
    </div></section>`;
  }
  function mount(segment){
    if(mounted===segment.id)return;
    mounted=segment.id;
    cardRoot=null;
    if(segment.kind==='chapter'){
      content.innerHTML='<section class="chapter"><div class="chapter-label">CHAPTER 01</div><div class="chapter-line"></div><h1>GAMEWEEK <span class="accent">REVIEW</span></h1><h2>THE REAL STORY</h2><p>THE RETURNS. THE SURPRISES. THE DECISIONS THAT MATTER.</p></section>';
    }else if(segment.kind==='overview'){
      content.innerHTML=`<section class="overview"><div class="scene-label">GW${review.gameweek} · FINAL OFFICIAL RESULTS</div><h1 class="scene-heading">THE GAMEWEEK <span class="accent">AT A GLANCE</span></h1><div class="overview-panels">${[['completed','MATCHES COMPLETED'],['goals','TOTAL GOALS'],['topPoints','TOP FPL SCORE']].map(([key,label])=>`<article class="overview-panel" data-value="${review.overview[key].value}"><label>${label}</label><strong>${review.overview[key].value}</strong></article>`).join('')}</div><p class="scene-note">${esc(review.skippedBuyLeader || 'Final results for the completed Gameweek. Transfer decisions use the current official snapshot.')}</p></section>`;
    }else if(segment.kind==='player'){
      const player=review.players.find(p=>p.id===segment.player_id);
      content.innerHTML=playerMarkup(player);
      const host=content.querySelector('.spotlight-hero');
      const shadow=host.attachShadow({mode:'open'});
      // Original component CSS and DOM run in isolation from the broadcast shell.
      const scale=content.clientHeight/nativeCard.height;
      host.style.width=`${nativeCard.width*scale}px`;
      shadow.innerHTML=SCENE2.cardCss+`<div id="card" style="width:${nativeCard.width}px;height:${nativeCard.height}px;transform:scale(${scale});transform-origin:top left"></div>`;
      cardRoot=shadow.querySelector('#card');
      window.VXPlayerCard.mount(cardRoot,player.card);
    }else if(segment.kind==='takeaways'){
      content.innerHTML=`<section class="lessons"><h1 class="scene-heading">THREE GAMEWEEK <span class="accent">LESSONS</span></h1><div class="lesson-grid">${review.takeaways.map(l=>`<article class="lesson"><h3>${esc(l.heading)}</h3><p>${esc(l.explanation)}</p><strong>${esc(l.implication)}</strong></article>`).join('')}</div></section>`;
    }else{
      content.innerHTML='<section class="next-chapter"><div class="scene-label">THE NEXT CHAPTER</div><h1>NEXT: <span class="accent">PLAYERS &amp; FIXTURES</span></h1><div class="chapter-line"></div><p>WHO DESERVES YOUR ATTENTION NOW?</p></section>';
    }
  }
  window.__seek=function(time){
    const t=Math.max(0,Math.min(time,segments.at(-1).t1-.001));
    const segment=segments.find(s=>t>=s.t0&&t<s.t1)||segments.at(-1);
    mount(segment);
    const local=t-segment.t0;
    const remaining=segment.t1-t;
    const initial=ease((t-.15)/.55);
    document.querySelector('.title-row').style.opacity=1-initial;
    document.querySelector('.agendaWrap').style.opacity=1-initial;
    content.style.opacity=initial;
    const match=document.querySelector('#opening-match');
    if(match)match.style.opacity=1-ease(t/.5);
    if(segment.kind==='chapter'){
      const h1=content.querySelector('h1');
      h1.style.opacity=ease((local-1)/.7);
      h1.style.transform=reduced?'none':`translateY(${(1-ease((local-1)/.7))*22}px)`;
      content.querySelector('h2').style.opacity=ease((local-1.7)/.7);
      content.querySelector('p').style.opacity=ease((local-2.5)/.8);
      content.querySelector('.chapter-line').style.transform=`scaleX(${ease((local-.5)/.7)})`;
    }else if(segment.kind==='overview'){
      content.querySelectorAll('.overview-panel').forEach((panel,i)=>{
        const p=ease((local-i*.25)/.7);
        panel.style.opacity=p;
        panel.style.transform=reduced?'none':`translateY(${(1-p)*14}px)`;
        panel.querySelector('strong').textContent=Math.round(Number(panel.dataset.value)*(reduced?1:ease((local-.3-i*.25)/1.1)));
      });
    }else if(segment.kind==='player'){
      const entrance=reduced?1:ease(local/1.3);
      const exit=reduced?1:ease(remaining/.55);
      const hero=content.querySelector('.spotlight-hero');
      const leftCenter=hero.clientWidth/2;
      hero.style.left=`${leftCenter-hero.clientWidth/2}px`;
      hero.style.opacity=entrance*exit;
      hero.style.transform=reduced?'none':`translateY(${(1-entrance)*20}px) scale(${.94+.06*entrance})`;
      const panel=content.querySelector('.analytics');
      const clear=hero.getBoundingClientRect().right<=content.getBoundingClientRect().left+panel.offsetLeft;
      const panelReveal=clear?ease(local/.55):0;
      panel.style.opacity=panelReveal*exit;
      panel.style.transform=reduced?'none':`translateX(${(1-panelReveal)*25}px)`;
      content.querySelectorAll('[data-stat]').forEach(el=>{
        const at=segment.cues[el.dataset.stat];
        el.classList.toggle('active',at!==undefined&&t>=at-.12&&t<at+1.4);
      });
      const verdictAt=segment.cues.verdict??segment.t1-4;
      content.querySelector('.verdict').style.opacity=ease((t-verdictAt+.15)/.4)*exit;
      if(cardRoot)window.VXPlayerCard.fitText(cardRoot);
    }else if(segment.kind==='takeaways'){
      content.querySelectorAll('.lesson').forEach((panel,i)=>panel.style.opacity=ease((local-i*.3)/.7));
    }else{
      content.querySelector('.chapter-line').style.transform=`scaleX(${ease(local/.8)})`;
    }
    const cue=cueWords.find(c=>t>=c.start&&t<c.end);
    document.querySelector('.captions span').textContent=cue?.text||'';
    document.querySelector('.captions').style.display=cue?'block':'none';
  };
  window.__scene2AssetsReady=()=>!cardRoot||[...cardRoot.querySelectorAll('img')].every(i=>i.complete&&i.naturalWidth>0);
  window.__scene2Audit=function(){
    const footer=document.querySelector('.source').getBoundingClientRect();
    const header=document.querySelector('.broadcast>header').getBoundingClientRect();
    const stage=content.getBoundingClientRect();
    const card=cardRoot?.querySelector('.vx-player-card');
    const images=cardRoot?[...cardRoot.querySelectorAll('img')]:[];
    const tab=card?.querySelector('.pc-fixtures-tab')?.getBoundingClientRect();
    const stats=card?[...card.querySelectorAll('.pc-banner,.pc-stat-row,.pc-stat-icon')]:[];
    const cardInternalOverlap=!!tab&&stats.some(e=>e.getBoundingClientRect().bottom>tab.top+1);
    const textNodes=[...content.querySelectorAll('h1,h2,h3,.analytics-stat,.analytics,.verdict,.lesson')];
    return {segment:mounted,playerId:Number(card?.dataset.playerId||0),
      overlapsBranding:stage.top<header.bottom||stage.bottom>footer.top,
      overflowingText:textNodes.filter(e=>e.scrollWidth>e.clientWidth+1||e.scrollHeight>e.clientHeight+1).map(e=>e.textContent),
      cardInternalOverlap,missingImage:images.some(i=>!i.complete||i.naturalWidth===0),
      originalCardVersion:card?window.VXPlayerCard.version:null,
      footerVisible:footer.bottom<=innerHeight,season:document.querySelector('.season-label').textContent};
  };
  window.__ready=true;
  window.__seek(0);
})();
