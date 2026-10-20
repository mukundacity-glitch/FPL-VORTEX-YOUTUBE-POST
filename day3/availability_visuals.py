from __future__ import annotations

import functools
import json
import re
from typing import Any


STATUS_CSS = r"""
<style id="vx-player-status-css">
.vx-player-card .vx-player-status{position:absolute!important;right:16px!important;top:16px!important;z-index:40!important;display:flex!important;align-items:center!important;gap:7px!important;max-width:48%!important;padding:7px 11px!important;border-radius:9px!important;font:800 clamp(18px,2.6cqw,30px)/1.2 Arial,sans-serif!important;color:white!important;white-space:normal!important;pointer-events:none}
.vx-player-status[data-color=red]{--vx-status-fill:#bd0037;--vx-status-ink:white;background:#bd0037!important;color:#fff!important}
.vx-player-status[data-color=yellow]{--vx-status-fill:#ffe04c;--vx-status-ink:#160d26;background:#ffe04c!important;color:#160d26!important}
.vx-player-status[data-color=grey]{--vx-status-fill:#596578;--vx-status-ink:white;background:#596578!important;color:#fff!important}
.vx-player-status svg{width:1.2em!important;height:1.2em!important;flex:none!important}
.vx-player-status-icon{position:absolute!important;z-index:35!important;display:grid!important;place-items:center!important;width:32px!important;height:32px!important;border-radius:7px!important;pointer-events:none}
.vx-player-status-icon[data-color=yellow]{--vx-status-fill:#ffe04c;--vx-status-ink:#160d26}
.vx-player-status-icon[data-color=grey]{--vx-status-fill:#596578}
.vx-player-status-icon svg{width:27px!important;height:27px!important}
</style>
"""
STATUS_JS = r"""
<script id="vx-player-status-runtime">
(() => {
  const states=__STATES__;
  const escape=value=>String(value??"").replace(/[&<>"']/g,char=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
  const icon='<svg viewBox="0 0 24 24" role="img" aria-label="FPL availability warning"><path d="M12 2L23 22H1Z" fill="var(--vx-status-fill,#bd0037)"/><path d="M12 8v7m0 3v.1" stroke="var(--vx-status-ink,white)" stroke-width="2.4" stroke-linecap="round"/></svg>';
  window.VX_PLAYER_AVAILABILITY=states;
  window.vxAvailabilityBadge=id=>{
    const state=states[String(id)];
    if(!state||state.color==="none")return "";
    const title="Current status: "+state.reason+(state.news ? " "+state.news : "");
    return '<span class="vx-player-status" data-color="'+escape(state.color)+'" role="status" title="'+escape(title)+'">'+icon+'<span>'+escape(state.label)+'</span></span>';
  };
  let queued=false;
  const update=()=>{
    queued=false;
    for(const host of document.querySelectorAll("[data-player-id]")){
      const state=states[String(host.dataset.playerId)];
      if(!state||state.color==="none"||host.classList.contains("vx-player-card")||host.querySelector(".vx-player-card"))continue;
      const photo=host.querySelector(".d3Def20Photo,.d3DeskPhoto,.d3BenchPhoto,.playerPhoto,.miniPhoto");
      if(!photo)continue;
      let badge=host.querySelector(":scope > .vx-player-status-icon");
      if(!badge){
        badge=document.createElement("span");badge.className="vx-player-status-icon";
        badge.innerHTML=icon;badge.dataset.color=state.color;badge.setAttribute("role","status");
        badge.title="Current status: "+state.reason+(state.news ? " "+state.news : "");
        host.appendChild(badge);
      }
      if(getComputedStyle(host).position==="static")host.style.position="relative";
      const box=photo.getBoundingClientRect(), parent=host.getBoundingClientRect();
      badge.style.left=Math.max(0,box.right-parent.left-28)+"px";
      badge.style.top=Math.max(0,box.top-parent.top)+"px";
    }
  };
  const schedule=()=>{if(!queued){queued=true;requestAnimationFrame(update);}};
  document.addEventListener("DOMContentLoaded",()=>{
    update();new MutationObserver(schedule).observe(document.body,{childList:true,subtree:true});
  },{once:true});
  window.addEventListener("resize",schedule);
})();
</script>
"""


def decorate_availability_html(source: str, registry: dict[str, Any]) -> str:
    source = re.sub(r'<(?:script|style) id="vx-player-status-[^"]+">.*?</(?:script|style)>', "", source, flags=re.S)
    payload = json.dumps(registry, ensure_ascii=True, allow_nan=False).replace("<", "\\u003c")
    insertion = STATUS_CSS + STATUS_JS.replace("__STATES__", payload)
    return source.replace("<head>", "<head>" + insertion, 1)


def install_availability_presentation(namespace: dict[str, Any]) -> None:
    original = namespace.get("vx_polish_branding")
    context = namespace.get("DAY3_AVAILABILITY")
    if not callable(original) or context is None or getattr(original, "_availability_wrapped", False):
        return

    @functools.wraps(original)
    def wrapped(*args: Any, **kwargs: Any) -> str:
        return decorate_availability_html(original(*args, **kwargs), context.public_registry())

    setattr(wrapped, "_availability_wrapped", True)
    namespace["vx_polish_branding"] = wrapped
