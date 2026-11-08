/* Original VXPlayerCard -> original football pitch. Seekable scene2 adapter. */
(function (global) {
"use strict";
const ease=x=>{x=Math.max(0,Math.min(1,x));return 1-(1-x)**3};
function mountScene2(root,manifest,cardsById) {
  if(!root||manifest?.players?.length!==15) throw Error("15 verified players required");
  if(!global.VXPlayerCard?.mount) throw Error("Existing VXPlayerCard is required");
  const find=(selector,context=root)=>{
    const item=context.querySelector(selector);
    if(!item)throw Error("Missing Scene 2 element: "+selector);
    return item;
  };
  const pitch=find("[data-vx-scene2-pitch]");
  const hero=find("[data-vx-scene2-spotlight]");
  const flight=find("[data-vx-scene2-flight]");
  const pName=root.querySelector("[data-vx-scene2-name]");
  const pPoints=root.querySelector("[data-vx-scene2-points]");
  const cards=new Map();
  for(const beat of manifest.players){
    const slot=[...pitch.querySelectorAll("[data-vx-slot]")].find(n=>n.dataset.vxSlot===String(beat.slot));
    if(!slot)throw Error("Original pitch slot missing: "+beat.slot);
    const payload=cardsById[beat.player_id];
    if(!payload)throw Error("Existing Hero Card data missing: "+beat.player_id);
    const compact=document.createElement("div");
    compact.className="vx-scene2-pitch-card";
    compact.style.cssText="width:100%;height:100%;visibility:hidden;opacity:0";
    global.VXPlayerCard.mount(compact,payload);
    slot.append(compact);
    cards.set(beat.player_id,{slot,compact,payload,beat});
  }
  if(cards.size!==15)throw Error("Repeated player IDs");
  const left=document.createElement("div"), moving=document.createElement("div");
  left.style.cssText="position:absolute;inset:0;transform-origin:top left";
  moving.style.cssText="position:absolute;transform-origin:top left;pointer-events:none";
  hero.append(left);flight.append(moving);
  let leftId=null,movingId=null;
  function rebind(element,oldId,newId){
    if(oldId===newId)return oldId;
    element.replaceChildren();
    if(newId!=null)global.VXPlayerCard.mount(element,cards.get(newId).payload);
    return newId;
  }
  function seek(time){
    if(!Number.isFinite(time)||time<0)throw Error("Invalid video time");
    const active=manifest.players.find(b=>time>=b.narration_start&&time<b.narration_end);
    const returning=manifest.players.find(b=>time>=b.pitch_flight_start&&time<b.pitch_arrival);
    leftId=rebind(left,leftId,active?.player_id??null);
    movingId=rebind(moving,movingId,returning?.player_id??null);
    hero.style.visibility=active?"visible":"hidden";
    flight.style.visibility=returning?"visible":"hidden";
    left.style.opacity=active?String(ease((time-active.left_hero_enter)/0.45)):"0";
    let settled=0;
    for(const beat of manifest.players){
      const card=cards.get(beat.player_id).compact;
      const visible=time>=beat.pitch_arrival;
      card.style.visibility=visible?"visible":"hidden";
      card.style.opacity=visible?"1":"0";
      if(visible)settled++;
    }
    if(returning){
      const target=cards.get(returning.player_id).slot.getBoundingClientRect();
      const source=hero.getBoundingClientRect(),host=flight.getBoundingClientRect();
      const u=ease((time-returning.pitch_flight_start)/(returning.pitch_arrival-returning.pitch_flight_start));
      const x=source.left-host.left+(target.left-source.left)*u;
      const y=source.top-host.top+(target.top-source.top)*u;
      const w=Math.max(1,source.width),h=Math.max(1,source.height);
      moving.style.width=w+"px";moving.style.height=h+"px";
      moving.style.transform="translate("+x+"px,"+y+"px) scale("+(1+(target.width/w-1)*u)+","+(1+(target.height/h-1)*u)+")";
      moving.style.opacity=String(u>0.94?(1-u)/0.06:1);
    }
    if(pName)pName.textContent=active?.name??"";
    if(pPoints)pPoints.textContent=active&&time>=active.points_reveal?active.actual_points+" PTS":"";
    root.dataset.vxScene2Settled=String(settled);
    root.dataset.vxScene2ActivePlayer=active?String(active.player_id):"";
    return {settled,activePlayerId:active?.player_id??null};
  }
  return {seek,destroy(){left.remove();moving.remove();for(const v of cards.values())v.compact.remove()}};
}
global.VXScene2Review={mountScene2};
})(typeof window==="undefined"?globalThis:window);
