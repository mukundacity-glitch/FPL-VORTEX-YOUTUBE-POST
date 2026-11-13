import React from 'react';
import {Easing, Img, interpolate, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import './value-board.css';

const positions = [
  ['GK', 'Goalkeepers', 'M8 17V8a2 2 0 0 1 4 0v6-9a2 2 0 0 1 4 0v9-7a2 2 0 0 1 4 0v8-4a2 2 0 0 1 4 0v9c0 5-3 8-8 8-4 0-7-2-9-5l-3-5a2 2 0 0 1 3-2l4 4'],
  ['DEF', 'Defenders', 'M16 3 5 7v8c0 6 5 10 11 14 6-4 11-8 11-14V7L16 3Zm0 0v26'],
  ['MID', 'Midfielders', 'M3 6h26v20H3zM16 6v20M3 11h5v10H3m26-10h-5v10h5M20 16a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z'],
  ['FWD', 'Strikers', 'M29 16a13 13 0 1 1-26 0 13 13 0 0 1 26 0ZM16 10l6 4-2 7h-8l-2-7Zm0 0V3m6 11 6-4m-8 11 5 5m-13-5-5 5m3-12-6-4'],
];
const revealEasing = Easing.out(Easing.cubic);

function PitchMarkings() {
  return <svg className="vb-pitch-lines" viewBox="0 0 1920 885" fill="none" aria-hidden="true">
    <path d="M64 4h1792l64 302v575H0V306L64 4Z"/>
    <path d="M460 32h1000l299 840H221L460 32Z M423 140h977l-27-67H566l-22 67
      M576 32l-39 148h846l-40-148 M445 68q40-3 54-36 M1421 32q13 35 52 36
      M847 180q113 137 226 0 M439 872l18-92h1006l18 92 M586 780q60-95 374-95t374 95
      M225 850q36 1 39 22 M1656 872q3-21 39-22"/>
  </svg>;
}

function PlayerCard({player, active}) {
  return <article className={`vb-player${active ? ' vb-player--active' : ''}`} aria-label={player.name}>
    <div className="vb-card-outline"/>
    <div className="vb-photo">
      {player.portrait && <Img src={staticFile(player.portrait.slice(1))} alt=""/>}
    </div>
    {player.clubLogo && <Img className="vb-crest" src={staticFile(player.clubLogo.slice(1))} alt=""/>}
    <div className="vb-player-copy">
      <strong className="vb-name" style={{fontSize: Math.min(31, 220 / Math.max(1, player.name.length * .56))}}>
        {player.name}
      </strong>
      <div className="vb-player-info"><span>£{player.price.toFixed(1)}m</span><b>{player.nextGwXpts.toFixed(2)} xPts</b></div>
    </div>
  </article>;
}

export default function ValueBoard({board}) {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const squad = [...board.starters, ...board.bench];
  const rows = positions.map(([position]) => squad.filter(player => player.position === position));
  if (new Set(squad.map(player => player.id)).size !== 15 ||
      rows.some((row, index) => row.length !== [2, 5, 5, 3][index])) {
    throw new Error('Scene 05 requires 15 verified players in the four official FPL position groups');
  }
  const seconds = frame / fps;
  const cue = (board.narrationCues || []).find(c => seconds >= c.start && seconds < c.end);
  return <main className="vb-pitch" aria-label={`Recommended Gameweek ${board.nextGameweek} squad`}>
    <PitchMarkings/>
    {positions.map(([position, label, icon], index) => {
      const progress = interpolate(seconds, [index * .045, .38 + index * .045], [0, 1],
        {easing: revealEasing, extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
      return <section className={`vb-line vb-line--${position.toLowerCase()}`} key={position}
        style={{opacity: .68 + .32 * progress, transform: `translateY(${(1 - progress) * 9}px)`}}>
        <h2 className="vb-position"><span><svg viewBox="0 0 32 32" aria-hidden="true"><path d={icon}/></svg></span>
          {label} <b>({rows[index].length})</b></h2>
        <div className="vb-players">
          {rows[index].map(player => <PlayerCard key={player.id} player={player} active={player.id === cue?.playerId}/>)}
        </div>
      </section>;
    })}
  </main>;
}
