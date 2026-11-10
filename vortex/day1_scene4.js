(() => {
  const {scene, cues, captions, cardCss, metricCues} = S4;
  const stage = document.querySelector('.vx-s4-stage');
  const caption = document.querySelector('.vx-s4-caption');
  const esc = value => String(value ?? 'N/A').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('"', '&quot;');
  const fmt = (value, digits = 0) => value == null ? 'N/A' : value.toLocaleString('en-GB', {
    minimumFractionDigits: digits, maximumFractionDigits: digits
  });
  const signed = (value, digits = 0) => value == null ? 'N/A' : (value > 0 ? '+' : '') + fmt(value, digits);
  const img = (url, cls) => url ? `<img class="${cls}" src="${esc(url)}" alt="">` : '';
  const cell = (id, label, value, band = '') => `<div class="vx-s4-cell" data-metric="${id}" data-band="${band}">
    <span>${esc(label)}</span><b>${esc(value)}</b></div>`;
  const group = (title, items, columns) => `<section class="vx-s4-section">
    <h3>${esc(title)}</h3><div class="vx-s4-grid" style="--columns:${columns}">${items.map(item => cell(...item)).join('')}</div></section>`;
  const nativeCss = `<style>
    .pc-club{white-space:normal;overflow-wrap:anywhere}
    [data-metric]{outline:5px solid rgb(54 224 255 / var(--active,0));outline-offset:-5px}
    .pc-fixture-fdr[data-band="easy"]{background:#73e5a6;color:#170e20}
    .pc-fixture-fdr[data-band="medium"]{background:#7bc7fc;color:#170e20}
    .pc-fixture-fdr[data-band="hard"]{background:#f7add7;color:#170e20}
    .pc-fixture-fdr[data-band="very-hard"]{background:#bc1938;color:white}
    .pc-fixture-fdr[data-band="missing"]{background:#514262;color:white}
    </style>`;
  const fixtureId = t => `fixtures.${t.gw}.${t.id}`;
  const fixtureWeek = (p, week) => {
    const slots = p.tiles.filter(t => t.gw === week);
    return `<div class="vx-s4-week"><strong>GW${week}</strong>${slots.length ?
      slots.map(t => cell(fixtureId(t), `${t.opponent} (${t.venue})`, t.rating, t.band)).join('') :
      cell('', 'Blank', '—', 'missing')}</div>`;
  };

  const rosterCard = p => {
    const next = p.tiles.filter(t => t.gw === scene.gw);
    const ratings = next.map(t => t.rating).join(' / ') || 'N/A';
    return `<article class="vx-s4-tile" data-player="${p.id}">
      <div class="vx-s4-photo">${img(p.card.player_image, 'vx-s4-portrait')}${img(p.card.club_badge, 'vx-s4-crest')}</div>
      <strong class="vx-s4-roster-name" data-metric="identity.player">${esc(p.name)}</strong>
      <div class="vx-s4-roster-values">
        ${cell('identity.price', 'Price', p.card.price)}
        ${cell('forecast.nextGwXpts', `GW${scene.gw} xPts`, fmt(p.weeks[0], 2))}
        ${cell(next.length === 1 ? fixtureId(next[0]) : '', 'FDR', ratings, next.length === 1 ? next[0].band : 'missing')}
      </div></article>`;
  };

  const dashboard = p => {
    const r = p.recent;
    return `<div class="vx-s4-identity" data-metric="identity.player"><h2>${esc(p.full_name || p.name)}</h2>
      <p>${esc(p.team.full_name || p.team.name)} · ${esc(p.position)} · <span data-metric="identity.price">${esc(p.card.price)}</span> · OWN ${esc(p.card.ownership)}</p></div>
      <section class="vx-s4-section"><h3>NEXT ${scene.weeks.length} FIXTURES <small>FDR 1 EASIEST / 5 HARDEST</small></h3>
      <div class="vx-s4-grid vx-s4-weeks" style="--columns:${scene.weeks.length}">${scene.weeks.map(week => fixtureWeek(p, week)).join('')}</div></section>
      ${group(`VORTEX MODEL FORECAST · ${scene.model_mode.toUpperCase()}`, [
        ['forecast.nextGwXpts', 'Next GW xPts', fmt(p.weeks[0], 2)],
        ['forecast.fiveGwXpts', `${scene.weeks.length}-GW xPts`, fmt(p.total, 2)],
        ['forecast.valuePerMillion', 'xPts / £1m', fmt(p.value, 2)]
      ], 3)}
      ${group('RECORDED PERFORMANCE' + (p.sample_matches == null ? '' : ` · ${p.sample_matches} MATCHES · ${p.sample_window}`), [
        ['performance.starts', 'Starts', r.starts == null ? 'N/A' : `${fmt(r.starts)}/${p.sample_matches}`],
        ['performance.minutes', 'Minutes', fmt(r.minutes)],
        ['performance.actualPoints', 'Actual pts', fmt(r.total_points)],
        ['performance.goals', 'Goals', fmt(r.goals_scored)],
        ['performance.assists', 'Assists', fmt(r.assists)],
        ['performance.xG', 'xG', fmt(r.expected_goals, 2)],
        ['performance.xA', 'xA', fmt(r.expected_assists, 2)],
        ['performance.xGI', 'xGI', fmt(r.expected_goal_involvements, 2)],
        ['performance.shots', 'Shots', fmt(r.shots)],
        ['performance.bigChances', 'Big chances', fmt(r.big_chances)]
      ], 5)}
      ${p.defence ? group('DEFENSIVE EVIDENCE · ' + (p.sample_window || 'RECORDED SAMPLE'), [
        ['defensive.cleanSheets', 'Team clean sheets', fmt(p.defence.clean_sheets)],
        ['defensive.xGC', 'Team xGC', fmt(p.defence.team_xgc, 2)],
        ['defensive.cleanSheetChance', 'Model CS chance', p.defence.cs_probabilities.map(v => v == null ? 'N/A' : fmt(100*v, 1)+'%').join(' / ') || 'N/A'],
        ['defensive.contributionPoints', 'Def. contrib. pts', fmt(r.defensive_contribution_points)]
      ], 4) : ''}
      ${group('TRANSFER SNAPSHOT · ' + scene.stamp, [
        ['transfers.in', 'In', fmt(p.incoming)], ['transfers.out', 'Out', fmt(p.outgoing)],
        ['transfers.net', 'Net', signed(p.net)],
        ['transfers.priceChange', 'Price change', p.price_move == null ? 'N/A' : `${p.price_move < 0 ? '−' : p.price_move > 0 ? '+' : ''}£${fmt(Math.abs(p.price_move)/10, 1)}m`],
        ['transfers.ownershipMovement', 'Owners ' + (p.owner_window || 'change'), signed(p.owner_change)]
      ], 5)}
      <div class="vx-s4-verdict" data-metric="verdict"><b>${esc(p.verdict)}</b><div>${esc(p.reason)}
      <small>Team news · ${esc(p.team_news || 'Unavailable')}</small></div></div>`;
  };

  stage.innerHTML = `<aside class="vx-s4-intro"><small>THE NEXT GAMEWEEKS</small><strong>Which picks justify a transfer?</strong>
    <span>Model forecast · recorded performance · transfer activity</span></aside>
    <div class="vx-s4-hero"></div><div class="vx-s4-detail"></div>
    <aside class="vx-s4-roster"><h2>PLAYER ROSTER</h2><div class="vx-s4-board">${scene.board.map(rosterCard).join('')}</div></aside>`;
  const intro = stage.querySelector('.vx-s4-intro');
  const slots = [...stage.querySelectorAll('.vx-s4-tile')];
  const host = stage.querySelector('.vx-s4-hero');
  const stats = stage.querySelector('.vx-s4-detail');
  const roster = stage.querySelector('.vx-s4-roster');
  const players = new Map(scene.board.map(p => [p.id, p]));
  const smooth = x => {
    const clamped = Math.min(1, Math.max(0, x));
    return clamped * clamped * (3 - 2 * clamped);
  };
  const glow = (cue, t) => smooth((t - cue.start) / .2) * (1 - smooth((t - cue.end) / .28));
  const emphasize = (cue, t) => cue.emphasis == null || t < cue.emphasis ? 0 :
    smooth((t - cue.emphasis) / .12) * (1 - smooth((t - cue.emphasis - .12) / .28));
  let mounted;

  window.__seek = t => {
    const i = Math.max(0, cues.findLastIndex(c => c.at <= t));
    const cue = cues[i];
    const playerId = cue.key.startsWith('hero-') ? Number(cue.key.slice(5)) : null;
    const p = players.get(playerId);
    const opening = cue.key === 'opening';
    const summary = cue.key === 'summary';
    const entrance = smooth((t - cue.at) / .38);
    const exit = smooth((t - (cue.settle_at ?? Infinity)) / .32);
    stage.classList.toggle('vx-s4-summary', summary);
    intro.style.opacity = opening ? 1 : 0;
    roster.style.opacity = opening ? 0 : (summary ? .35 + .65 * entrance : 1);
    if (p && mounted !== playerId) {
      const shadow = host.shadowRoot || host.attachShadow({mode:'open'});
      shadow.innerHTML = cardCss + nativeCss + '<div class="vx-s4-native" style="width:1244px;height:1649px;transform:scale(.375);transform-origin:0 0"></div>';
      const native = window.VXPlayerCard.mount(shadow.lastElementChild, p.card);
      native.querySelectorAll('[data-fixture-index]').forEach((node, index) => {
        const f = p.card.fixtures[index];
        if (!f) return;
        const value = node.querySelector('.pc-fixture-fdr');
        value.textContent = f.rating;
        value.dataset.band = f.band;
        node.dataset.metric = fixtureId(f);
      });
      native.querySelector('.pc-banner-price').dataset.metric = 'identity.price';
      stats.innerHTML = dashboard(p);
      const knownMetrics = new Set([...stats.querySelectorAll('[data-metric]')].map(el => el.dataset.metric));
      const missing = metricCues.find(c => c.playerId === playerId && !knownMetrics.has(c.metricId));
      if (missing) throw new Error(`Unresolved Scene 4 metric: ${missing.metricId} for player ${playerId}`);
      mounted = playerId;
    }
    host.style.opacity = stats.style.opacity = p ? (.25 + .75 * entrance) * (1 - .22 * exit) : 0;
    host.style.transform = stats.style.transform = `translateY(${(1 - entrance)*8}px)`;
    const active = metricCues.filter(c => c.playerId === playerId && t >= c.start && t < c.end + .28);
    const apply = root => root?.querySelectorAll('[data-metric]').forEach(el => {
      const id = el.dataset.metric;
      const cue = active.find(c => c.metricId === id);
      el.style.setProperty('--active', cue ? glow(cue, t) : 0);
      el.style.setProperty('--emphasis', cue ? emphasize(cue, t) : 0);
    });
    slots.forEach(tile => {
      const isPlayer = Number(tile.dataset.player) === playerId;
      tile.style.setProperty('--roster-focus', isPlayer ? entrance : 0);
      tile.style.opacity = p && !isPlayer ? .84 : 1;
      apply(isPlayer ? tile : null);
      if (!isPlayer) tile.querySelectorAll('[data-metric]').forEach(el => {
        el.style.removeProperty('--active');
        el.style.removeProperty('--emphasis');
      });
    });
    apply(stats);
    apply(host.shadowRoot);
    caption.textContent = captions.find(c => t >= c.start && t < c.end)?.text || '';
  };
  window.__seek(0);
  window.__ready = true;
})();
