from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path
from typing import Any


@lru_cache(maxsize=1)
def visual_css() -> str:
    assets = Path(__file__).with_name("assets")
    display = base64.b64encode((assets / "BarlowCondensed-SemiBold.ttf").read_bytes()).decode("ascii")
    body = base64.b64encode((assets / "Inter.ttf").read_bytes()).decode("ascii")
    return f"""
@font-face{{font-family:VortexDisplay;src:url(data:font/ttf;base64,{display}) format('truetype');font-weight:100 900;font-display:block}}
@font-face{{font-family:VortexBody;src:url(data:font/ttf;base64,{body}) format('truetype');font-weight:100 900;font-display:block}}
html body .vx-topHeader{{left:58px!important;right:58px!important;top:22px!important;height:164px!important}}
html body .vx-brandLock{{width:1160px!important;max-width:1160px!important;height:164px!important;gap:24px!important;flex:0 0 1160px!important}}
html body .vx-logoBox{{width:180px!important;flex:0 0 180px!important;height:154px!important}}
html body .vx-logoBox .vortex-logo{{max-width:174px!important;max-height:150px!important;object-fit:contain!important}}
html body .vx-brandWords{{min-width:0!important;width:956px!important;max-width:956px!important}}
html body .vx-channelName{{font-family:VortexDisplay!important;font-size:100px!important;line-height:1.04!important;font-weight:600!important;letter-spacing:.25px!important;color:#F9F8F2!important;text-shadow:none!important}}
html body .vx-channelSub{{font-family:VortexBody!important;font-size:30px!important;line-height:1.2!important;font-weight:650!important;font-style:normal!important;letter-spacing:.2px!important;color:#A8CED3!important;white-space:normal!important;overflow-wrap:break-word!important;margin-top:8px!important}}
html body .vx-channelName *,html body .vx-channelSub *{{font-family:inherit!important}}
html body .rankName,html body .idText strong,html body .name,html body .rankMetric strong,html body .metricValue{{line-height:1.08!important}}

html body .vx-topHeader{{
    border-bottom:2px solid rgba(168,206,211,.24)!important;
    border-image:linear-gradient(90deg,#D2AD62 0%,rgba(210,173,98,.42) 24%,rgba(168,206,211,.24) 64%,transparent) 1!important;
}}
html body .sceneTitle h1{{
    font-family:VortexDisplay!important;
    font-size:108px!important;
    font-weight:600!important;
    line-height:1.06!important;
    letter-spacing:.2px!important;
    color:#F9F8F2!important;
    text-shadow:0 3px 16px rgba(0,5,13,.35)!important;
}}
html body .sceneSub{{
    font-family:VortexBody!important;
    font-size:34px!important;
    font-weight:620!important;
    line-height:1.22!important;
    color:#C1D5D8!important;
    max-width:100%!important;
    white-space:normal!important;
    text-wrap:pretty;
}}
html body .vx-gwPill{{
    font-family:VortexDisplay!important;
    font-weight:600!important;
    line-height:1.1!important;
    white-space:nowrap!important;
    background:linear-gradient(110deg,#F8E7B7,#D2AD62)!important;
    border:1px solid #F5E9CA!important;
    color:#102233!important;
    box-shadow:0 6px 18px rgba(0,0,0,.19)!important;
}}
html body .sceneTitle h1 .accentGold,html body .sceneTitle h1 .goldAccent{{color:#E9C985!important}}

/* Refine existing text reveals, including the exposure slide's inline animations.
   The notebook still owns the keyframes, durations and narration cue delays. */
html body .sceneTitle h1,
html body .sceneSub,
html body [style*="animation:vxFadeUp "]{{
    animation-timing-function:cubic-bezier(.22,.61,.36,1)!important;
}}
"""


FIT_TEXT = r"""async () => {
    await document.fonts.load('600 48px VortexDisplay');
    await document.fonts.load('700 32px VortexBody');
    await document.fonts.ready;
    for (const element of document.querySelectorAll('body *:not(svg):not(path)')) {
        const family = getComputedStyle(element).fontFamily;
        const display = /Bebas|Arial Narrow|Impact|VortexDisplay/i.test(family);
        element.style.setProperty('font-family', display ? 'VortexDisplay' : 'VortexBody', 'important');
        element.style.setProperty('font-synthesis', 'none', 'important');
    }
    await document.fonts.ready;
    for (const element of document.querySelectorAll('.sceneTitle h1,.titleBar h1,.mainHeading,.outroHero h1')) {
        const parent = element.parentElement;
        const available = parent.getBoundingClientRect().width;
        if (available > 0) element.style.setProperty('max-width', available + 'px', 'important');
        let size = parseFloat(getComputedStyle(element).fontSize);
        while (element.scrollWidth > element.clientWidth + 1 && size > 56) {
            size -= 1;
            element.style.setProperty('font-size', size + 'px', 'important');
        }
    }
    let fitted = 0;
    for (const element of document.querySelectorAll('body *')) {
        if (!element.textContent.trim() || element.children.length || element.clientWidth <= 0) continue;
        const style = getComputedStyle(element);
        if (style.whiteSpace !== 'nowrap' || element.scrollWidth <= element.clientWidth + 1) continue;
        const original = parseFloat(style.fontSize);
        const minimum = Math.min(original, 28);
        let size = original;
        while (element.scrollWidth > element.clientWidth + 1 && size > minimum) {
            size -= 1;
            element.style.setProperty('font-size', size + 'px', 'important');
        }
        fitted += 1;
    }
    return {fitted, fonts: document.fonts.status};
}"""


def install_visual_polish(namespace: dict[str, Any]) -> None:
    original = namespace.get("_vx_wait_for_page_assets")
    if original is None or getattr(original, "_day2_visual_polish", False):
        return

    async def wait_with_visual_polish(page: Any, *args: Any, **kwargs: Any) -> Any:
        # This hook runs before every existing PNG/video capture and safe-frame check.
        if not await page.locator("#day2-visual-polish").count():
            style = await page.add_style_tag(content=visual_css())
            await style.evaluate("element => element.id = 'day2-visual-polish'")
        result = await original(page, *args, **kwargs)
        await page.evaluate(FIT_TEXT)
        return result

    setattr(wait_with_visual_polish, "_day2_visual_polish", True)
    namespace["_vx_wait_for_page_assets"] = wait_with_visual_polish
