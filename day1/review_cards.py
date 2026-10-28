# CELL 15A — PLAYER CARD DESIGN
# TRUE-4K PLAYER CARD ONLY • CLEAN REWRITE • NO PITCH / NO DATA MATH
# ============================================================
# Design source: player-stat-panel.html supplied by the user.
# The source was authored at 1920×1080. Its fixed px typography,
# spacing, padding, borders and gaps are scaled ~2× for true 4K use.
# This cell owns ONLY the hero/player-card visual runtime.
# Cell 16 continues to own live player data + card payload creation.
# The pitch, formation, narration, footer and all other slide code are untouched.
# ============================================================

PLAYER_CARD_DESIGN_VERSION = "V5.0_4K_SAMPLE_REWRITE"
PLAYER_CARD_RATIO = "AUTO_SLOT"

PLAYER_CARD_CSS = r"""
<!-- VX_PLAYER_CARD_DESIGN_START -->
<style id="vx-player-card-design">

/* ------------------------------------------------------------
   PLAYER CARD TOKENS — 4K SCALE
   ------------------------------------------------------------ */
.vx-player-card{
  --pc-bg:#0a0e1a;
  --pc-card:#0d1220;
  --pc-card-2:#111a2b;
  --pc-accent:#3ec8ff;
  --pc-accent-2:#138cff;
  --pc-accent-glow:rgba(62,200,255,.34);
  --pc-heading:#e8f7ff;
  --pc-value:#38ef8b;
  --pc-muted:#aebbd0;
  --pc-green:#2ecc71;
  --pc-amber:#f39c12;
  --pc-red:#e74c3c;
  --pc-divider:rgba(255,255,255,.11);

  position:relative;
  width:100%;
  height:100%;
  min-width:0;
  min-height:0;
  overflow:hidden;
  box-sizing:border-box;
  isolation:isolate;
  container-type:size;

  padding:36px;
  border:2px solid var(--pc-accent);
  border-radius:24px;

  background:
    radial-gradient(circle at 16% 18%,rgba(35,125,255,.16),transparent 34%),
    radial-gradient(circle at 88% 10%,rgba(42,210,255,.08),transparent 30%),
    linear-gradient(160deg,#0b1221 0%,#080d18 54%,#07101b 100%);

  box-shadow:
    0 0 24px var(--pc-accent-glow),
    inset 0 0 24px rgba(62,200,255,.05),
    0 28px 54px rgba(0,0,0,.48);

  color:#fff;
  font-family:Inter,"Arial Narrow","Roboto Condensed",Arial,sans-serif;
  text-transform:uppercase;
}

.vx-player-card *,
.vx-player-card *::before,
.vx-player-card *::after{box-sizing:border-box}

.pc-card-grid{
  position:absolute;
  inset:0;
  z-index:0;
  pointer-events:none;
  opacity:.20;
  background-image:
    linear-gradient(rgba(62,200,255,.08) 1px,transparent 1px),
    linear-gradient(90deg,rgba(62,200,255,.06) 1px,transparent 1px);
  background-size:52px 52px;
  mask-image:linear-gradient(180deg,#000 0%,rgba(0,0,0,.65) 54%,transparent 100%);
}

.pc-card-sheen{
  position:absolute;
  inset:0;
  z-index:0;
  pointer-events:none;
  background:linear-gradient(122deg,transparent 0 64%,rgba(42,165,255,.08) 65%,transparent 78%);
}

.pc-card-body{
  position:relative;
  z-index:2;
  width:100%;
  height:100%;
  min-width:0;
  min-height:0;
  display:grid;
  grid-template-rows:auto 500px minmax(0,1fr) 260px auto auto;
  gap:24px;
}

/* ------------------------------------------------------------
   IDENTITY — TWO-COLOR NAME
   Original 1920 sample: 28 / 44 px -> 56 / 88 px at 4K.
   ------------------------------------------------------------ */
.pc-identity{
  position:relative;
  min-width:0;
  min-height:150px;
  padding-right:132px;
}

.pc-name-first,
.pc-name-last,
.pc-club{
  display:block;
  min-width:0;
  max-width:100%;
  white-space:nowrap;
  overflow:hidden;
}

.pc-name-first{
  font-size:56px;
  line-height:.95;
  font-weight:900;
  letter-spacing:2px;
  color:#fff;
  text-shadow:0 4px 12px rgba(0,0,0,.62);
}

.pc-name-last{
  margin-top:2px;
  font-size:88px;
  line-height:.92;
  font-weight:1000;
  letter-spacing:1px;
  background:linear-gradient(90deg,#64edff 0%,#2fc8ff 42%,#228fff 100%);
  -webkit-background-clip:text;
  background-clip:text;
  -webkit-text-fill-color:transparent;
  filter:drop-shadow(0 5px 11px rgba(0,0,0,.55));
}

.pc-club{
  margin-top:12px;
  font-size:34px;
  line-height:1;
  font-weight:750;
  letter-spacing:2px;
  color:var(--pc-muted);
}

.pc-club-crest{
  position:absolute;
  right:4px;
  top:4px;
  width:112px;
  height:112px;
  object-fit:contain;
  filter:drop-shadow(0 8px 12px rgba(0,0,0,.45));
}

/* ------------------------------------------------------------
   PHOTO + INFO
   Fixed photo box. Image is never allowed to overflow/crop.
   ------------------------------------------------------------ */
.pc-photo-info{
  min-width:0;
  min-height:0;
  display:grid;
  grid-template-columns:42% minmax(0,1fr);
  gap:32px;
  align-items:stretch;
}

.pc-portrait-box{
  position:relative;
  width:100%;
  height:100%;
  max-height:100%;
  min-width:0;
  min-height:0;
  overflow:hidden;
  border:2px solid var(--pc-accent);
  border-radius:24px;
  background:
    radial-gradient(circle at 50% 40%,rgba(39,125,200,.38),transparent 58%),
    linear-gradient(150deg,#12243b,#0b1322 68%,#08101b);
  box-shadow:
    0 0 20px var(--pc-accent-glow),
    inset 0 0 26px rgba(52,160,255,.08);
}

.pc-portrait-box::after{
  content:"";
  position:absolute;
  inset:14px;
  border:1px solid rgba(120,220,255,.18);
  border-radius:18px;
  pointer-events:none;
}

.pc-portrait{
  position:absolute;
  inset:0;
  width:100%;
  height:100%;
  max-width:100%;
  max-height:100%;
  object-fit:contain;
  object-position:center bottom;
  padding:10px 10px 0;
  display:block;
  filter:drop-shadow(0 15px 16px rgba(0,0,0,.44));
}

.pc-portrait-fallback{
  position:absolute;
  inset:0;
  display:grid;
  place-items:center;
  padding:28px;
  color:var(--pc-muted);
  font-size:28px;
  font-weight:850;
  letter-spacing:1px;
  text-align:center;
}

.pc-info-stack{
  width:100%;
  height:100%;
  max-height:100%;
  min-width:0;
  min-height:0;
  overflow:hidden;
  display:grid;
  grid-template-rows:repeat(5,minmax(0,1fr));
  gap:14px;
  align-content:stretch;
}

.pc-info-item{
  min-width:0;
  display:grid;
  grid-template-columns:64px minmax(0,1fr);
  gap:20px;
  align-items:center;
  padding:10px 16px;
  border-bottom:2px solid var(--pc-divider);
  background:linear-gradient(90deg,rgba(62,200,255,.045),transparent 72%);
}

.pc-info-item:last-child{border-bottom:0}

.pc-info-icon{
  width:64px;
  height:64px;
  border-radius:50%;
  border:2px solid var(--pc-accent);
  display:grid;
  place-items:center;
  flex:none;
  color:var(--pc-accent);
  font-size:28px;
  font-weight:1000;
  line-height:1;
  box-shadow:inset 0 0 14px rgba(62,200,255,.07);
}

.pc-info-copy{min-width:0}

.pc-info-label{
  min-width:0;
  font-size:26px;
  line-height:1;
  font-weight:800;
  color:var(--pc-heading);
  letter-spacing:2px;
  white-space:nowrap;
  overflow:hidden;
}

.pc-info-value{
  min-width:0;
  margin-top:8px;
  font-size:40px;
  line-height:1;
  font-weight:1000;
  color:var(--pc-value);
  letter-spacing:1px;
  white-space:nowrap;
  overflow:hidden;
  text-shadow:0 0 18px rgba(56,239,139,.17);
}

.pc-info-value.pc-captain-yes{color:#ffd94a}

/* ------------------------------------------------------------
   PER-90 STATS
   Every row owns its own space. No squeeze / overlap.
   ------------------------------------------------------------ */
.pc-stat-rows{
  min-width:0;
  min-height:0;
  display:grid;
  grid-template-rows:repeat(5,minmax(0,1fr));
  overflow:hidden;
  border:2px solid rgba(62,200,255,.28);
  border-radius:20px;
  background:linear-gradient(180deg,rgba(11,20,35,.88),rgba(7,13,24,.92));
}

.pc-stat-row{
  min-width:0;
  display:grid;
  grid-template-columns:64px minmax(0,1fr) 190px;
  gap:20px;
  align-items:center;
  padding:12px 24px;
  border-bottom:2px solid var(--pc-divider);
}

.pc-stat-row:last-child{border-bottom:0}

.pc-stat-icon{
  width:54px;
  height:54px;
  border-radius:14px;
  display:grid;
  place-items:center;
  color:var(--pc-accent);
  border:2px solid rgba(62,200,255,.64);
  background:rgba(16,40,72,.68);
  font-size:26px;
  font-weight:1000;
  box-shadow:inset 0 0 12px rgba(62,200,255,.08);
}

.pc-stat-label{
  min-width:0;
  font-size:32px;
  line-height:1;
  font-weight:900;
  letter-spacing:1px;
  color:var(--pc-heading);
  white-space:nowrap;
  overflow:hidden;
}

.pc-stat-value{
  min-width:0;
  text-align:right;
  font-size:38px;
  line-height:1;
  font-weight:1000;
  letter-spacing:1px;
  color:var(--pc-value);
  white-space:nowrap;
  overflow:hidden;
  text-shadow:0 0 16px rgba(56,239,139,.16);
}

/* ------------------------------------------------------------
   SIX FIXTURES — ONE ROW
   FDR 1-2 GREEN • 3 AMBER • 4-5 RED
   ------------------------------------------------------------ */
.pc-fixture-row{
  min-width:0;
  min-height:0;
  display:grid;
  grid-template-columns:repeat(6,minmax(0,1fr));
  gap:16px;
}

.pc-fixture-card{
  min-width:0;
  min-height:0;
  overflow:hidden;
  border-radius:16px;
  border:2px solid rgba(255,255,255,.22);
  display:grid;
  grid-template-rows:minmax(0,1fr) auto;
  align-items:stretch;
  color:#fff;
  text-align:center;
  box-shadow:0 8px 18px rgba(0,0,0,.30);
}

.pc-fixture-card.fdr-1,
.pc-fixture-card.fdr-2{
  background:linear-gradient(180deg,#229a51,#126d39);
  border-color:#43ea8a;
}
.pc-fixture-card.fdr-3{
  background:linear-gradient(180deg,#b87309,#815004);
  border-color:#ffbf3a;
}
.pc-fixture-card.fdr-4,
.pc-fixture-card.fdr-5{
  background:linear-gradient(180deg,#b9363b,#7d1822);
  border-color:#ff5963;
}
.pc-fixture-card.fdr-none{
  background:linear-gradient(180deg,#33435a,#202b3c);
  border-color:#6d819d;
}

.pc-fixture-main{
  min-width:0;
  min-height:0;
  padding:14px 8px 8px;
  display:flex;
  flex-direction:column;
  align-items:center;
  justify-content:center;
  gap:6px;
}

.pc-fixture-crest{
  width:52px;
  height:52px;
  object-fit:contain;
  filter:drop-shadow(0 3px 5px rgba(0,0,0,.45));
}

.pc-fixture-team{
  min-width:0;
  max-width:100%;
  font-size:36px;
  line-height:1.05;
  font-weight:1000;
  letter-spacing:1px;
  white-space:nowrap;
  overflow:hidden;
}

.pc-fixture-venue{
  margin-top:2px;
  font-size:28px;
  line-height:1;
  font-weight:900;
  white-space:nowrap;
}

.pc-fixture-meta{
  min-width:0;
  padding:12px 6px 14px;
  border-top:2px solid rgba(255,255,255,.20);
  background:rgba(0,0,0,.18);
  display:flex;
  flex-direction:column;
  gap:7px;
  align-items:center;
  justify-content:center;
}

.pc-fixture-gw,
.pc-fixture-fdr{
  min-width:0;
  max-width:100%;
  font-size:27px;
  line-height:1.1;
  font-weight:1000;
  letter-spacing:.5px;
  white-space:nowrap;
  overflow:hidden;
}

/* ------------------------------------------------------------
   LEGEND + FOOTER
   ------------------------------------------------------------ */
.pc-legend{
  min-width:0;
  display:flex;
  align-items:center;
  justify-content:center;
  gap:36px;
  font-size:28px;
  line-height:1;
  font-weight:800;
  letter-spacing:1px;
  color:var(--pc-muted);
  white-space:nowrap;
  overflow:hidden;
}

.pc-legend-item{display:flex;align-items:center;gap:12px;min-width:0}
.pc-legend-dot{width:16px;height:16px;border-radius:50%;flex:none;box-shadow:0 0 10px currentColor}
.pc-legend-dot.easy{background:var(--pc-green);color:var(--pc-green)}
.pc-legend-dot.medium{background:var(--pc-amber);color:var(--pc-amber)}
.pc-legend-dot.hard{background:var(--pc-red);color:var(--pc-red)}

.pc-card-footer{
  min-width:0;
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:24px;
  padding-top:8px;
  border-top:2px solid var(--pc-divider);
  font-size:26px;
  line-height:1;
  font-weight:800;
  letter-spacing:1px;
  color:var(--pc-accent);
  white-space:nowrap;
  overflow:hidden;
}

.pc-card-footer > span{min-width:0;overflow:hidden;white-space:nowrap}

/* Compact only when the actual existing hero slot is unusually short.
   This does not alter the pitch or slide geometry. */
@container (max-height:1500px){
  .pc-card-body{grid-template-rows:auto 420px minmax(0,1fr) 230px auto auto;gap:20px}
  .pc-name-first{font-size:52px}
  .pc-name-last{font-size:80px}
  .pc-club{font-size:30px}
  .pc-info-label{font-size:24px}
  .pc-info-value{font-size:36px}
  .pc-stat-label{font-size:29px}
  .pc-stat-value{font-size:35px}
  .pc-fixture-crest{width:42px;height:42px}
  .pc-fixture-team{font-size:31px}
  .pc-fixture-venue{font-size:24px}
  .pc-fixture-gw,.pc-fixture-fdr{font-size:23px}
  .pc-legend{font-size:25px}
  .pc-card-footer{font-size:24px}
}

</style>
<!-- VX_PLAYER_CARD_DESIGN_END -->
"""

PLAYER_CARD_JS = r"""
<!-- VX_PLAYER_CARD_RUNTIME_START -->
<script id="vx-player-card-runtime">
(() => {
  "use strict";

  const esc = value => String(value ?? "")
    .replaceAll("&","&amp;")
    .replaceAll("<","&lt;")
    .replaceAll(">","&gt;")
    .replaceAll('"',"&quot;")
    .replaceAll("'","&#039;");

  const text = (value, fallback="—") => {
    if (value === null || value === undefined) return fallback;
    const s = String(value).trim();
    return s ? s : fallback;
  };

  const upper = (value, fallback="—") => text(value, fallback).toUpperCase();

  function nameParts(p){
    const explicitFirst = text(p?.first_name, "");
    const explicitLast  = text(p?.surname, "");
    if (explicitFirst || explicitLast){
      return {
        first: explicitFirst || explicitLast || "PLAYER",
        last: explicitLast && explicitFirst ? explicitLast : ""
      };
    }

    const raw = text(p?.full_name, text(p?.name, "PLAYER"))
      .replace(/\s+/g," ")
      .trim();
    const bits = raw.split(" ").filter(Boolean);
    if (bits.length <= 1) return {first:bits[0] || "PLAYER", last:""};
    return {first:bits[0], last:bits.slice(1).join(" ")};
  }

  function captainValue(p){
    return p?.captain ? "YES" : "NO";
  }

  function statIcon(key){
    const k = String(key || "").toLowerCase();
    if (k === "target") return "◎";
    if (k === "boot" || k === "glove") return "↗";
    if (k === "ball") return "●";
    if (k === "shield") return "◇";
    if (k === "spark") return "★";
    return "•";
  }

  function infoRows(p){
    const rows = [
      ["P", "POSITION", upper(p?.position_label, upper(p?.position,"PLAYER")), ""],
      ["£", "PRICE", upper(p?.price,"—"), ""],
      ["O", "OWNERSHIP", upper(p?.ownership,"—"), ""],
      ["M", "AVG MIN / START", upper(p?.avg_minutes_per_start, upper(p?.stats?.avg_minutes_per_start,"—")), ""],
      ["C", "CAPTAIN THIS WEEK", captainValue(p), p?.captain ? "pc-captain-yes" : ""]
    ];

    return rows.map(([icon,label,value,klass]) => `
      <div class="pc-info-item">
        <div class="pc-info-icon">${esc(icon)}</div>
        <div class="pc-info-copy">
          <div class="pc-info-label" data-pc-fit data-pc-max="26" data-pc-min="18">${esc(label)}</div>
          <div class="pc-info-value ${klass}" data-pc-fit data-pc-max="40" data-pc-min="24">${esc(value)}</div>
        </div>
      </div>`).join("");
  }

  function statRows(p){
    const rows = Array.isArray(p?.display_stats) ? p.display_stats.slice(0,5) : [];
    const padded = rows.slice();
    while (padded.length < 5) padded.push({icon:"",label:"—",value:"—"});

    return padded.map(r => `
      <div class="pc-stat-row">
        <div class="pc-stat-icon">${esc(statIcon(r?.icon))}</div>
        <div class="pc-stat-label" data-pc-fit data-pc-max="32" data-pc-min="21">${esc(upper(r?.label))}</div>
        <div class="pc-stat-value" data-pc-fit data-pc-max="38" data-pc-min="24">${esc(upper(r?.value))}</div>
      </div>`).join("");
  }

  function fdrClass(fx){
    const existing = String(fx?.fdr_class || "").toLowerCase();
    if (/^fdr-[1-5]$/.test(existing)) return existing;

    const raw = Number(fx?.fdr_value ?? fx?.fixdiff);
    if (Number.isFinite(raw)){
      const n = Math.max(1, Math.min(5, Math.round(raw)));
      return `fdr-${n}`;
    }
    return "fdr-none";
  }

  function fdrDisplay(fx){
    const raw = fx?.fdr_value ?? fx?.fixdiff;
    const n = Number(raw);
    if (Number.isFinite(n) && n >= 1 && n <= 5) return n.toFixed(2);
    const values = String(raw ?? "").match(/[1-5](?:\.\d+)?/g);
    return values ? values.map(v=>Number(v).toFixed(2)).join(" + ") : "—";
  }

  function fixtureCard(fx, index){
    if (!fx || fx.gw === null || fx.gw === undefined){
      return `<div class="pc-fixture-card fdr-none">
        <div class="pc-fixture-main"><div class="pc-fixture-team">—</div><div class="pc-fixture-venue">—</div></div>
        <div class="pc-fixture-meta"><div class="pc-fixture-gw">GW —</div><div class="pc-fixture-fdr">FDR —</div></div>
      </div>`;
    }

    const venue = text(fx?.venue, "").replace(/[()]/g,"");
    const oppBadge = text(fx?.badge, Array.isArray(fx?.badges) ? fx.badges[0] : "");
    const crestHtml = oppBadge
      ? `<img class="pc-fixture-crest" src="${esc(oppBadge)}" alt="" onerror="this.style.display='none'">`
      : "";
    return `<div class="pc-fixture-card ${fdrClass(fx)}" data-fixture-index="${index}">
      <div class="pc-fixture-main">
        ${crestHtml}
        <div class="pc-fixture-team" data-pc-fit data-pc-max="36" data-pc-min="22">${esc(upper(fx?.opponent,"—"))}</div>
        <div class="pc-fixture-venue" data-pc-fit data-pc-max="28" data-pc-min="19">${venue ? `(${esc(venue.toUpperCase())})` : "—"}</div>
      </div>
      <div class="pc-fixture-meta">
        <div class="pc-fixture-gw" data-pc-fit data-pc-max="27" data-pc-min="18">GW ${esc(text(fx?.gw,"—"))}</div>
        <div class="pc-fixture-fdr" data-pc-fit data-pc-max="27" data-pc-min="18">FDR ${esc(fdrDisplay(fx))}</div>
      </div>
    </div>`;
  }

  function renderPlayerCard(playerData){
    const p = playerData || {};
    const name = nameParts(p);
    const crest = text(p?.club_badge, "");
    const portrait = text(p?.player_image, "");
    const fixtures = Array.isArray(p?.fixtures) ? p.fixtures.slice(0,6) : [];
    while (fixtures.length < 6) fixtures.push(null);

    return `
      <article class="vx-player-card" data-player-id="${esc(p?.id ?? "")}">
        <div class="pc-card-grid"></div>
        <div class="pc-card-sheen"></div>

        <div class="pc-card-body">
          <header class="pc-identity">
            <div class="pc-name-first" data-pc-fit data-pc-max="56" data-pc-min="34">${esc(upper(name.first,"PLAYER"))}</div>
            <div class="pc-name-last" data-pc-fit data-pc-max="88" data-pc-min="46">${esc(upper(name.last,""))}</div>
            <div class="pc-club" data-pc-fit data-pc-max="34" data-pc-min="22">${esc(upper(p?.club, upper(p?.team_name,"CLUB")))}</div>
            ${crest ? `<img class="pc-club-crest" src="${esc(crest)}" alt="">` : ""}
          </header>

          <section class="pc-photo-info">
            <div class="pc-portrait-box">
              ${portrait
                ? `<img class="pc-portrait" src="${esc(portrait)}" alt="" draggable="false">`
                : `<div class="pc-portrait-fallback">PLAYER IMAGE</div>`}
            </div>
            <div class="pc-info-stack">${infoRows(p)}</div>
          </section>

          <section class="pc-stat-rows">${statRows(p)}</section>

          <section class="pc-fixture-row">${fixtures.map(fixtureCard).join("")}</section>

          <div class="pc-legend" aria-label="Fixture difficulty legend">
            <span class="pc-legend-item"><i class="pc-legend-dot easy"></i>GREEN EASY</span>
            <span class="pc-legend-item"><i class="pc-legend-dot medium"></i>AMBER MEDIUM</span>
            <span class="pc-legend-item"><i class="pc-legend-dot hard"></i>RED HARD</span>
          </div>

          <footer class="pc-card-footer">
            <span data-pc-fit data-pc-max="26" data-pc-min="18">STATS: ${esc(upper(p?.season_label,"CURRENT SEASON"))}</span>
            <span data-pc-fit data-pc-max="26" data-pc-min="18">FPL VORTEX</span>
          </footer>
        </div>
      </article>`;
  }

  function elementWidthFits(el){
    if (!el || el.clientWidth <= 0) return true;
    return el.scrollWidth <= el.clientWidth + 1;
  }

  function fitOne(el){
    const max = Number(el?.dataset?.pcMax || 40);
    const min = Number(el?.dataset?.pcMin || 16);
    if (!el || !Number.isFinite(max) || !Number.isFinite(min)) return;

    let lo = Math.max(8, Math.min(min,max));
    let hi = Math.max(lo,max);
    let best = lo;

    el.style.fontSize = `${hi}px`;
    if (elementWidthFits(el)) return;

    for (let i=0; i<12; i++){
      const mid = (lo + hi) / 2;
      el.style.fontSize = `${mid}px`;
      if (elementWidthFits(el)){
        best = mid;
        lo = mid;
      } else {
        hi = mid;
      }
    }
    el.style.fontSize = `${best}px`;
  }

  function fitText(root){
    if (!root) return;
    root.querySelectorAll("[data-pc-fit]").forEach(fitOne);
  }

  function fitSlot(host){
    if (!host) return;
    const card = host.querySelector(":scope > .vx-player-card");
    if (!card) return;
    card.style.width = "100%";
    card.style.height = "100%";
    card.style.maxWidth = "100%";
    card.style.maxHeight = "100%";
  }

  function mount(host, playerData){
    if (!host) throw new Error("PLAYER CARD host missing");
    host.innerHTML = renderPlayerCard(playerData);
    const card = host.querySelector(":scope > .vx-player-card");
    fitSlot(host);
    fitText(card);

    const portrait = card?.querySelector(".pc-portrait");
    if (portrait && !portrait.complete){
      portrait.addEventListener("load", () => fitText(card), {once:true});
    }

    requestAnimationFrame(() => {
      fitSlot(host);
      fitText(card);
    });

    return card;
  }

  window.VXPlayerCard = Object.freeze({
    version:"V5.0_4K_SAMPLE_REWRITE",
    mount,
    render:renderPlayerCard,
    fitText,
    fitSlot
  });
})();
</script>
<!-- VX_PLAYER_CARD_RUNTIME_END -->
"""

print("✅ CELL 15A PLAYER CARD DESIGN READY")
print("✅ Design version:", PLAYER_CARD_DESIGN_VERSION)
print("✅ 4K-scaled type / spacing from supplied player-stat-panel sample")
print("✅ Two-color player name • fixed contained portrait • full ownership")
print("✅ Five padded stat rows • six FDR tiles • readable legend/footer")
print("✅ PLAYER CARD ONLY — pitch / formation / footer / narration untouched")

