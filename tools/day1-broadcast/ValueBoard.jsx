import React from 'react';
import {Img, interpolate, useCurrentFrame, useVideoConfig} from 'remotion';
import './value-board.css';

// Everything displayed here comes from a validated episode payload.
// Never use screenshot numbers, player names, fixture abbreviations or club assets as data.
const POSITIONS = ['GK', 'DEF', 'MID', 'FWD'];
const fmt = (value, digits=1) => Number.isFinite(value) ? Number(value).toFixed(digits) : 'N/A';
const money = value => Number.isFinite(value) ? `£${fmt(value)}m` : 'N/A';
const list = value => Array.isArray(value) ? value : [];
const url = value => typeof value === 'string' && /^(https?:|data:|\/)/.test(value) ? value : '';

function Crest({player}) {
  const src = url(player.clubLogo);
  return src ? <Img className="vb-crest" src={src} alt=""/> : null;
}

function Fixture({fixture}) {
  const rating = Number(fixture?.fdr);
  const band = !Number.isFinite(rating) || rating<1 || rating>5 ? 'missing' :
    rating<=2.5 ? 'easy' : rating<=3 ? 'medium' : rating<=4 ? 'hard' : 'very-hard';
  return <span className={`vb-fixture vb-fixture--${band}`} title={fixture?.opponentFullName || ''}>
    <b>{fixture?.opponentShortName || 'TBC'}</b><em>{fixture?.venue || '—'}</em>
    <strong>{fmt(rating)}</strong>
  </span>;
}

function PlayerCard({player, frame, fps, active}) {
  const photo = url(player.portrait);
  const cue = active === player.id;
  const pulse = cue ? interpolate(frame % Math.max(1, fps), [0, Math.max(1, fps)/2, Math.max(1, fps)], [0, 1, 0]) : 0;
  return <article className={`vb-player ${cue?'vb-player--active':''}`} style={{'--vb-pulse':pulse}} aria-label={player.fullName || player.name}>
    <div className="vb-photo">
      {photo && <Img src={photo} alt="" className="vb-headshot"/>}
      <Crest player={player}/>
      {player.captain && <span className="vb-captain">C</span>}
      {player.viceCaptain && <span className="vb-captain vb-captain--vice">VC</span>}
    </div>
    <strong className="vb-name">{player.name || player.fullName || 'Unavailable'}</strong>
    <div className="vb-player-info"><span>{money(player.price)}</span><b>{fmt(player.nextGwXpts,2)} xPts</b></div>
    <div className="vb-mini-fixtures">{list(player.fixtures).filter(f=>f.gw===player.nextGameweek).slice(0,1).map((f,i)=><Fixture key={f.id || i} fixture={f}/>)}{!list(player.fixtures).some(f=>f.gw===player.nextGameweek) && <span className="vb-next-empty">NEXT: BLANK / TBC</span>}</div>
  </article>;
}

function Pitch({board, frame, fps, active}) {
  const starters = list(board.starters);
  return <section className="vb-pitch-panel">
    <div className="vb-pitch-top"><strong>OPTIMIZED STARTING XI</strong><span>{board.formation || '—'} FORMATION · NEXT GAMEWEEK</span></div>
    <div className="vb-pitch">
      <div className="vb-field-markings"><div className="vb-center-circle"/><div className="vb-goal-area vb-goal-area--top"/><div className="vb-goal-area vb-goal-area--bottom"/></div>
      {POSITIONS.map(pos=><div className={`vb-line vb-line--${pos.toLowerCase()}`} key={pos}>
        {starters.filter(p=>p.position===pos).map(p=><PlayerCard key={p.id} player={{...p,nextGameweek:board.nextGameweek}} frame={frame} fps={fps} active={active}/>)}
      </div>)}
    </div>
    <div className="vb-bench"><div className="vb-bench-title">BENCH <small>GK · FIRST · SECOND · THIRD</small></div>
      <div className="vb-bench-grid">{list(board.bench).map((p,i)=><PlayerCard key={p.id || i} player={{...p,nextGameweek:board.nextGameweek}} frame={frame} fps={fps} active={active}/>)}</div>
    </div>
  </section>;
}

function FixturesPanel({board}) {
  const fixtures = list(board.nextFixtures);
  return <section className="vb-fixtures-panel">
    <div className="vb-panel-heading"><strong>GW{board.nextGameweek} · FIXTURE RADAR</strong><small>HOME / AWAY · KICKOFF</small></div>
    <div className="vb-match-list">{fixtures.length ? fixtures.slice(0,10).map((f,i)=><div className="vb-match" key={f.id || i}>
      <span className="vb-match-clubs"><b>{f.homeShort || 'TBC'}</b><em>vs</em><b>{f.awayShort || 'TBC'}</b></span>
      <span className="vb-match-time">{f.kickoffLabel || 'TBC'}</span>
      {Number.isFinite(f.projectedHomeGoals) && Number.isFinite(f.projectedAwayGoals) ?
        <strong className="vb-match-goals">{fmt(f.projectedHomeGoals,2)} : {fmt(f.projectedAwayGoals,2)}</strong> :
        <span className="vb-match-unavailable">xG N/A</span>}
    </div>) : <div className="vb-empty">Fixture data unavailable</div>}</div>
    <div className="vb-budget">
      <small>FIVE-GAMEWEEK VALUE BOARD</small>
      <div><strong>{money(board.totalCost)}</strong><span> / £100.0m budget</span></div>
      <div className="vb-budget-metrics"><span><b>{money(board.bank)}</b><small>Remaining</small></span>
      <span><b>{fmt(board.fiveGwXpts,1)}</b><small>Five-GW xPts</small></span></div>
    </div>
  </section>;
}

function ProjectionPanel({board, activeGameweek}) {
  return <section className="vb-projections-panel">
    <div className="vb-panel-heading"><strong>FIVE-GW OUTLOOK</strong><small>MODEL PROJECTIONS</small></div>
    <div className="vb-projections">{list(board.projections).slice(0,5).map((p,i)=><div className={`vb-projection ${p.gameweek===activeGameweek?"vb-projection--active":""}`} key={p.gameweek || i}>
      <span>GW{p.gameweek}</span><div className="vb-projection-track"><i style={{width:`${Math.max(0,Math.min(100,(p.xpts || 0)/Math.max(1,board.maxProjection || 1)*100))}%`}}/></div>
      <b>{fmt(p.xpts,1)}</b></div>)}</div>
    <div className="vb-market"><strong>MARKET · MOST OWNED PICKS</strong>
      {[...list(board.starters),...list(board.bench)].filter(p=>Number.isFinite(p.ownership)).sort((a,b)=>b.ownership-a.ownership).slice(0,4).map(p=><div className="vb-market-row" key={p.id}><span>{p.name}</span><b>{fmt(p.ownership,1)}%</b><em className={p.netTransfers>=0?"vb-market-rise":"vb-market-fall"}>{p.netTransfers>=0?"▲":"▼"} {Math.abs(p.netTransfers || 0).toLocaleString("en-GB")}</em></div>)}
    </div>
    <div className="vb-model-note">{board.modelLabel || 'Research estimates · Verify before deadline'}</div>
  </section>;
}

export default function ValueBoard({board}) {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  if (!board || !Array.isArray(board.starters) || board.starters.length!==11 || !Array.isArray(board.bench) || board.bench.length!==4) {
    throw new Error('Scene 05 requires a verified 11-player starting XI and four bench players');
  }
  const seconds = frame/fps;
  const cue = list(board.narrationCues).find(c=>seconds>=c.start && seconds<c.end);
  const active = cue?.playerId;
  const activeGameweek = cue?.gameweek || board.nextGameweek;
  const plan = list(board.weeklyPlans).find(p=>p.gameweek===activeGameweek);
  const byId = new Map([...board.starters,...board.bench].map(p=>[p.id,p]));
  const activeBoard = plan ? {
    ...board,
    nextGameweek: activeGameweek,
    formation: plan.formation,
    starters: plan.starters.map(id=>({...byId.get(id),
      nextGwXpts:byId.get(id)?.weekly?.[activeGameweek],
      captain:id===plan.captainId,viceCaptain:id===plan.viceCaptainId})),
    bench: plan.bench.map(id=>({...byId.get(id),
      nextGwXpts:byId.get(id)?.weekly?.[activeGameweek],
      captain:false,viceCaptain:false}))
  } : board;
  return <main className="vb-layout">
    <Pitch board={activeBoard} frame={frame} fps={fps} active={active}/>
    <FixturesPanel board={board}/>
    <ProjectionPanel board={board} activeGameweek={activeGameweek}/>
  </main>;
}
