/* Scene 2 verified retrospective panels; uses original episode manifest, not forecasts. */
(function(global){
"use strict";
const fmt=value=>value===null||value===undefined?"N/A":String(value);
function mountPanels(root,manifest){
  if(!root||!manifest||manifest.players?.length!==15)
    throw Error("Verified 15-player Scene 2 manifest required");
  function panel(attr){return root.querySelector("[data-vx-scene2-"+attr+"]")}
  function text(attr,value){
    const el=panel(attr);if(el)el.textContent=fmt(value);
  }
  function setRank(){
    const movement=manifest.rank_movement||{direction:"unavailable"};
    const dir=movement.direction;
    if(!["green_up","red_down","unchanged","unavailable"].includes(dir))
      throw Error("Unrecognized rank arrow");
    const el=panel("rank-arrow");
    if(el){
      el.textContent=dir==="green_up"?"↑":dir==="red_down"?"↓":dir==="unchanged"?"→":"N/A";
      el.dataset.direction=dir;
      el.setAttribute("aria-label",dir==="green_up"?"Rank improved":dir==="red_down"?"Rank worsened":dir==="unchanged"?"Rank unchanged":"Rank data unavailable");
    }
    text("rank-old",movement.previous);
    text("rank-new",movement.current);
  }
  function setTable(){
    const table=manifest.gameweek_table;
    if(!table)throw Error("Missing original Gameweek table");
    for(const [metric,value] of Object.entries(table)){
      const el=[...root.querySelectorAll("[data-vx-scene2-metric]")].find(n=>n.dataset.vxScene2Metric===metric);
      if(el)el.textContent=fmt(value);
    }
  }
  function setCaptain(){
    const cap=manifest.captaincy;
    if(!cap)throw Error("Missing verified captaincy");
    text("captain-id",cap.captain_id);
    text("vice-id",cap.vice_captain_id);
    text("captain-multiplier","×"+cap.verified_multiplier);
  }
  function setTransfers(){
    const wrap=panel("transfers");
    if(!wrap)return;
    wrap.replaceChildren();
    for(const trade of manifest.transfers||[]){
      if(!["potential","completed"].includes(trade.status))throw Error("Invalid transfer status");
      if(trade.status==="completed"&&!trade.verified)throw Error("Unverified completed transfer");
      const line=document.createElement("div");
      line.className="vx-scene2-transfer";
      const flag=document.createElement("strong");
      flag.textContent=trade.status==="completed"?"COMPLETED":"POSSIBLE MOVE";
      const label=document.createElement("span");
      label.textContent=" "+fmt(trade.name??trade.player_in??trade.player_out);
      line.append(flag,label);
      wrap.append(line);
    }
  }
  function setResults(){
    const wrap=panel("results");
    if(!wrap)return;
    wrap.replaceChildren();
    for(const fixture of manifest.results||[]){
      const row=document.createElement("div");
      row.className="vx-scene2-result";
      row.textContent=fmt(fixture.home)+" "+fmt(fixture.home_score)+"–"+
        fmt(fixture.away_score)+" "+fmt(fixture.away)+" · "+fmt(fixture.status);
      wrap.append(row);
    }
  }
  setRank();setTable();setCaptain();setTransfers();setResults();
  return {refresh(){setRank();setTable();setCaptain();setTransfers();setResults()}};
}
global.VXScene2Panels={mountPanels};
})(typeof window==="undefined"?globalThis:window);
