import asyncio as _vx_asyncio
import importlib as _vx_importlib
import inspect as _vx_inspect
import sys as _vx_sys
import json, re, subprocess, unicodedata, math
VOICE="en-GB-RyanNeural"
MOODS={key: {"rate":"+0%","pitch":"+0Hz","volume":"+0%"} for key in ("intro","analysis","key_stat","warning","outro")}
def vx_tts_profile(mood="analysis"):
    return dict(MOODS[mood])
# running Colab never has to disconnect merely because its package is older.
import asyncio as _vx_asyncio
import importlib as _vx_importlib
import inspect as _vx_inspect
import sys as _vx_sys

def _vx_edge_tts_supports_boundary_option(module):
    try:
        return "boundary" in _vx_inspect.signature(module.Communicate).parameters
    except (TypeError, ValueError, AttributeError):
        return False

def vx_load_edge_tts():
    """Load edge-tts once; install it only when the package is absent."""
    try:
        return _vx_importlib.import_module("edge_tts")
    except ImportError:
        subprocess.run(
            [_vx_sys.executable, "-m", "pip", "install", "-q", "edge-tts"],
            check=True,
        )
        _vx_importlib.invalidate_caches()
        return _vx_importlib.import_module("edge_tts")

async def vx_edge_tts_stream(text, profile, attempts=3):
    """Return MP3 bytes plus WordBoundary timing across edge-tts versions."""
    module = vx_load_edge_tts()
    failures = []
    supports_boundary = _vx_edge_tts_supports_boundary_option(module)

    for attempt in range(1, int(attempts) + 1):
        audio = bytearray()
        words = []
        try:
            kwargs = {
                "rate": str(profile["rate"]),
                "pitch": str(profile["pitch"]),
                "volume": str(profile["volume"]),
            }
            if supports_boundary:
                kwargs["boundary"] = "WordBoundary"

            communicate = module.Communicate(str(text), VOICE, **kwargs)
            async for chunk in communicate.stream():
                if chunk.get("type") == "audio":
                    audio.extend(chunk.get("data", b""))
                elif chunk.get("type") == "WordBoundary":
                    words.append({
                        "text": str(chunk.get("text", "")),
                        "start": float(chunk.get("offset", 0)) / 10_000_000,
                        "duration": float(chunk.get("duration", 0)) / 10_000_000,
                    })

            if audio and words:
                return bytes(audio), words
            raise RuntimeError(
                f"empty TTS payload (audio_bytes={len(audio)}, word_boundaries={len(words)})"
            )
        except Exception as exc:
            failures.append(f"attempt {attempt}: {type(exc).__name__}: {exc}")
            if attempt < int(attempts):
                print(f"⚠️ Ryan TTS retry {attempt}/{attempts - 1}: {type(exc).__name__}")
                await _vx_asyncio.sleep(1.5 * attempt)

    raise RuntimeError(
        "Ryan TTS failed after package-compatible setup and retries: "
        + " | ".join(failures)
    )


def vx_media_duration(path):
    r=subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(path)],capture_output=True,text=True,check=True)
    return float(r.stdout.strip())


def vx_norm_text(value):
    text=unicodedata.normalize("NFKD",str(value or ""))
    text="".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+"," ",text.lower()).strip()

def vx_phrase_span(words, phrase, *, required=False, context=""):
    """Return exact Ryan WordBoundary start/span for a spoken phrase."""
    target=vx_norm_text(phrase).split()
    if not target:
        if required:
            raise RuntimeError(f"Empty sync phrase in {context or 'animation sync'}.")
        return None

    flat=[]
    for boundary_index,w in enumerate(words or []):
        for token in vx_norm_text(w.get("text","")).split():
            flat.append((token,boundary_index))

    tokens=[token for token,_ in flat]
    for i in range(len(tokens)-len(target)+1):
        if tokens[i:i+len(target)] != target:
            continue
        first_boundary=flat[i][1]
        last_boundary=flat[i+len(target)-1][1]
        first=words[first_boundary]
        last=words[last_boundary]
        start=float(first["start"])
        end=float(last["start"])+float(last.get("duration",0.0))
        return start,max(0.01,end-start)

    if required:
        label=f" in {context}" if context else ""
        raise RuntimeError(
            f"Ryan exact-sync phrase not found{label}: {phrase!r}. "
            f"Received {len(words or [])} WordBoundary events."
        )
    return None

def vx_phrase_time(words, phrase, fallback=0.0, *, required=False, context=""):
    span=vx_phrase_span(words,phrase,required=required,context=context)
    return float(span[0]) if span is not None else fallback

print("✅ Shared production helpers ready")


# ============================================================
# FIX 2 — SHARED 4K BRANDING / READABILITY POLISH
# ONE helper is reused by every presentation HTML.
# It changes presentation only — never data/model calculations.
# ============================================================

VX_BRAND_POLISH_CSS = r"""
<style id="vx-brand-polish">
:root{
  --vx-brand-gold:#ffd447;
  --vx-brand-cyan:#35e6ff;
  --vx-brand-white:#f7fbff;
}

/* Two-colour channel lockup */
.channelName{
  display:flex!important;
  align-items:baseline!important;
  gap:20px!important;
  font-size:104px!important;
  line-height:.94!important;
  font-weight:1000!important;
  letter-spacing:1.5px!important;
  color:var(--vx-brand-white)!important;
  text-shadow:none!important;
}
.channelName .vx-brand-fpl,
.vx-brand-inline .vx-brand-fpl,
.pc-footer-brand .vx-brand-fpl{
  color:var(--vx-brand-gold)!important;
  text-shadow:0 5px 20px rgba(255,212,71,.22)!important;
}
.channelName .vx-brand-vortex,
.vx-brand-inline .vx-brand-vortex,
.pc-footer-brand .vx-brand-vortex{
  color:var(--vx-brand-cyan)!important;
  font-style:italic!important;
  letter-spacing:2px!important;
  text-shadow:0 0 24px rgba(53,230,255,.20)!important;
}
.channelSub{
  font-size:34px!important;
  font-weight:950!important;
  letter-spacing:5.5px!important;
  color:#d4e2ec!important;
}

/* Bigger, cleaner channel logo on every slide family */
.logoBox{
  width:790px!important;
  height:285px!important;
}
.logoBox .vortex-logo{
  max-width:770px!important;
  max-height:275px!important;
  filter:
    drop-shadow(0 12px 28px rgba(0,0,0,.46))
    drop-shadow(0 0 24px rgba(53,230,255,.12))!important;
}
.outroScene .logoBox{
  width:720px!important;
  height:250px!important;
}
.outroScene .logoBox .vortex-logo{
  max-width:700px!important;
  max-height:240px!important;
}
.outroScene .channelName{
  font-size:96px!important;
}
.outroScene .channelSub{
  font-size:30px!important;
  letter-spacing:5px!important;
}

.brand.brandImage{
  width:1320px!important;
  height:380px!important;
}
.brand.brandImage .vortex-logo{
  max-width:1280px!important;
  max-height:360px!important;
  filter:
    drop-shadow(0 14px 22px rgba(0,0,0,.48))
    drop-shadow(0 0 22px rgba(255,212,71,.10))!important;
}

.logo-area{
  width:900px!important;
  height:180px!important;
  overflow:visible!important;
}
.logo-area .vortex-logo{
  max-width:820px!important;
  max-height:178px!important;
  filter:
    drop-shadow(0 8px 20px rgba(0,0,0,.42))
    drop-shadow(0 0 26px rgba(53,230,255,.12))!important;
}

/* Global small-text readability uplift; large headings retain their own sizes */
.footer{
  font-size:38px!important;
}
.footerLeft strong{
  font-size:45px!important;
}
.footerRight .updated{
  font-size:36px!important;
}
.footerRight .season{
  font-size:31px!important;
}
.footerSocial{
  font-size:40px!important;
}
.footer-section{
  font-size:35px!important;
}
.header-kicker{
  font-size:40px!important;
}
.header-season{
  font-size:34px!important;
}
.subtitle{
  font-size:34px!important;
  line-height:1.16!important;
}

.panelTitle .smallTitle{
  font-size:28px!important;
}
.metricLabel{
  font-size:36px!important;
}
.metricSub{
  font-size:29px!important;
}
.chipName{
  font-size:25px!important;
}
.chipStatus{
  font-size:22px!important;
}
.pitchHeader .gw{
  font-size:56px!important;
}
.pitchHeader .team{
  font-size:31px!important;
}
.playerName{
  font-size:34px!important;
}
.playerMeta{
  font-size:30px!important;
}
.tinyScore{
  font-size:18px!important;
}
.points{
  font-size:48px!important;
}
.miniName{
  font-size:33px!important;
}
.miniMeta{
  font-size:30px!important;
}
.miniPts{
  font-size:44px!important;
}

/* Outro phone/1080p legibility */
.outroScene .panelTag{
  font-size:34px!important;
}
.outroScene .todayPanel .lineText{
  font-size:48px!important;
}
.outroScene .todayPanel .lineSub{
  font-size:42px!important;
}
.outroScene .todayPanel .takeawaySub{
  font-size:38px!important;
}
.outroScene .tomorrowPanel .tom-sub{
  font-size:33px!important;
}
.outroScene .tomorrowPanel .lineText{
  font-size:54px!important;
}


/* Unified footer-note readability across every slide family */
.footer,
.vortex-footer{
  font-size:38px!important;
  line-height:1.05!important;
}
.footerLeft,
.footerRight,
.footerSocial,
.footer-section,
.social-group{
  font-size:38px!important;
  line-height:1.05!important;
  font-weight:950!important;
}
.footer-label{
  font-size:33px!important;
  font-weight:950!important;
}
.footer-value{
  font-size:38px!important;
  font-weight:1000!important;
}
.footerLeft strong{
  font-size:45px!important;
}
.footerRight .updated{
  font-size:36px!important;
}
.footerRight .season{
  font-size:31px!important;
}

/* Player hero-card footer branding */
.pc-footer-brand{
  font-size:clamp(8px,1.35cqw,20px)!important;
  letter-spacing:.02em!important;
}
.pc-footer-copy,
.pc-footer-season{
  font-size:clamp(7px,1.05cqw,16px)!important;
}
</style>
"""

def vx_polish_branding(html):
    """Apply the shared logo/type polish to one complete slide HTML string."""
    text = str(html)

    # Exact two-colour channel-name treatment where the visible lockup exists.
    text = text.replace(
        '<div class="channelName">FPL VORTEX</div>',
        '<div class="channelName"><span class="vx-brand-fpl">FPL</span>'
        '<span class="vx-brand-vortex">VORTEX</span></div>',
    )
    text = text.replace(
        '<div class="pc-footer-brand">FPL VORTEX</div>',
        '<div class="pc-footer-brand vx-brand-inline">'
        '<span class="vx-brand-fpl">FPL</span> '
        '<span class="vx-brand-vortex">VORTEX</span></div>',
    )
    text = text.replace(
        '<strong>FPL VORTEX</strong>',
        '<strong class="vx-brand-inline"><span class="vx-brand-fpl">FPL</span> '
        '<span class="vx-brand-vortex">VORTEX</span></strong>',
    )
    text = text.replace(
        'FPL VORTEX • 2026/27',
        '<span class="vx-brand-inline"><span class="vx-brand-fpl">FPL</span> '
        '<span class="vx-brand-vortex">VORTEX</span></span> • 2026/27',
    )
    text = text.replace(
        'FPL VORTEX &nbsp;|&nbsp;',
        '<span class="vx-brand-inline"><span class="vx-brand-fpl">FPL</span> '
        '<span class="vx-brand-vortex">VORTEX</span></span> &nbsp;|&nbsp;',
    )

    if 'id="vx-brand-polish"' not in text:
        if "</head>" not in text:
            raise RuntimeError("Brand polish requires a complete HTML document with </head>.")
        text = text.replace("</head>", VX_BRAND_POLISH_CSS + "\n</head>", 1)

    return text

print("✅ FIX 2 shared branding polish ready")
print("✅ Logo + typography presentation only — model/data logic unchanged")
