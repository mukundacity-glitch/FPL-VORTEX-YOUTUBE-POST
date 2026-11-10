import React from 'react';
import {AbsoluteFill, Composition, Img, OffthreadVideo, Sequence, interpolate, registerRoot, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import './broadcast.css';

const socials = [
  ['youtube', '@FPLVORTEX', <path d="M10 6v12l10-6z" fill="white"/>],
  ['x', '@FPLVORTEXM', <path d="M4 3h5l11 18h-5L4 3Zm16 0L4 21" fill="none" stroke="white" strokeWidth="1.6"/>],
  ['telegram', 't.me/FPLVortexDailyBot', <path d="m2 10 20-8-4 20-6-5-4 3 1-6 9-8-12 7z" fill="#4be5ff"/>],
  ['instagram', '@fplvortex', <><rect x="4" y="4" width="16" height="16" rx="5" fill="none" stroke="white" strokeWidth="2"/><circle cx="12" cy="12" r="3.5" fill="none" stroke="white" strokeWidth="2"/><circle cx="17" cy="7" r="1" fill="white"/></>],
];

function Broadcast({scene, media = false}) {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const sourceHeight = scene.bottom - scene.top;
  const scale = Math.min(1, 868 / sourceHeight);
  const light = interpolate(frame, [0, fps * 1.15], [-35, 112], {extrapolateRight: 'clamp'});
  return <AbsoluteFill className={`canvas ${scene.number === 5 ? "canvas--value-board" : ""}`}>
    {media && <div className="scene-window" style={{width:1920*scale,height:sourceHeight*scale,left:(1920-1920*scale)/2,top:112+(868-sourceHeight*scale)/2}}>
      <OffthreadVideo src={staticFile(`scene-${scene.number}.mp4`)} style={{position:'absolute',top:-scene.top*scale,width:1920*scale,height:1080*scale}}/>
    </div>}
    <header className="rail header">
      <div className="sheen" style={{left:`${light}%`,opacity:light>100?0:.7}}/>
      <div className="brand" aria-label="FPL VORTEX official channel branding"><Img src={scene.logo || staticFile('vortex.jpg')} alt="FPL VORTEX original channel logo"/><strong>FPL<br/>VORTEX</strong></div>
      <div className="heading"><div>FPL VORTEX · DAY 1 · SCENE {String(scene.number).padStart(2,'0')}</div><h1>{scene.title}</h1>{scene.number === 5 && <span className="value-board-kicker">THE BEST £100M SQUAD · NEXT FIVE GAMEWEEKS</span>}</div>
      <b className="gameweek">{scene.label}</b>
    </header>
    <footer className="rail footer">
      <div className="sheen" style={{left:`${light}%`,opacity:light>100?0:.5}}/>
      {socials.map(([platform, handle, mark])=><div className="social" key={platform}>
        <span className={`icon ${platform}`}><svg viewBox="0 0 24 24">{mark}</svg></span>{handle}
      </div>)}
    </footer>
  </AbsoluteFill>;
}

function Episode({scenes}) {
  let from = 0;
  return scenes.map(scene => {
    const start = from;
    from += scene.frames;
    return <Sequence key={scene.title} from={start} durationInFrames={scene.frames} premountFor={30}>
      <Broadcast scene={scene} media/>
    </Sequence>;
  });
}

function Root() {
  return <>
    <Composition id="Day1Broadcast" component={Episode} fps={30} width={1920} height={1080} durationInFrames={1} calculateMetadata={async ({props}) => {
      const scenes = props.scenes ?? await (await fetch(staticFile("scenes.json"))).json();
      return {props:{scenes},durationInFrames:scenes.reduce((sum,scene)=>sum+scene.frames,0)};
    }}/>
    <Composition id="BroadcastRails" component={Broadcast} fps={30} width={1920} height={1080} durationInFrames={36} defaultProps={{scene:{number:1,title:"The Gameweek Brief",label:"",top:0,bottom:1080}}}/>
  </>;
}
registerRoot(Root);
