import sys, json, asyncio, os
from playwright.async_api import async_playwright

"""Overlap audit: the hero card must never cover scene text, nor leave the screen.

Usage: python audit.py <output_dir>   (run build_harness.py with the same dir first)
"""
import pathlib
S = str(pathlib.Path(sys.argv[1]))
html = S + "/harness.html"
tag = "audit"
vx = json.load(open(S + '/vx.json'))

# Every visible text box on screen, split into "inside the hero card" and "outside".
COLLECT = r"""
() => {
  const hero = document.querySelector('#vxHeroWrap');
  const card = hero.querySelector('.vx-player-card');
  const accOpacity = el => {
    let o = 1;
    for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
      const cs = getComputedStyle(n);
      if (cs.display === 'none' || cs.visibility === 'hidden') return 0;
      o *= parseFloat(cs.opacity);
    }
    return o;
  };
  const out = {inside: [], outside: [], overflow: [], cardBox: null, heroBox: null};
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const n = walker.currentNode;
    const t = n.textContent.trim();
    const el = n.parentElement;
    if (!t || !el || /^(SCRIPT|STYLE|NOSCRIPT)$/.test(el.tagName)) continue;
    if (accOpacity(el) < 0.05) continue;
    const r = document.createRange(); r.selectNodeContents(n);
    for (const b of r.getClientRects()) {
      if (b.width < 1 || b.height < 1) continue;
      const rec = {t: t.slice(0, 28), x: b.left, y: b.top, w: b.width, h: b.height};
      (hero.contains(el) ? out.inside : out.outside).push(rec);
    }
  }
  if (card) {
    const cb = card.getBoundingClientRect();
    out.cardBox = {x: cb.left, y: cb.top, w: cb.width, h: cb.height};
    card.querySelectorAll('[data-pc-fit]').forEach(e => {
      const prev = e.style.textOverflow; e.style.textOverflow = 'clip';
      if (e.scrollWidth > e.clientWidth) out.overflow.push(e.textContent.trim().slice(0, 30));
      e.style.textOverflow = prev;
    });
  }
  out.tiny = [];
  if (card) card.querySelectorAll('[data-pc-fit]').forEach(e => {
    const fitted = parseFloat(getComputedStyle(e).fontSize);
    const keep = e.style.fontSize; e.style.fontSize = '';
    const natural = parseFloat(getComputedStyle(e).fontSize); e.style.fontSize = keep;
    if (natural > 0 && fitted / natural < 0.6) out.tiny.push(e.textContent.trim().slice(0, 24) + ' x' + (fitted / natural).toFixed(2));
  });
  const hb = hero.getBoundingClientRect();
  out.heroBox = {x: hb.left, y: hb.top, w: hb.width, h: hb.height};
  return out;
}
"""

def inter(a, b):
    w = min(a['x'] + a['w'], b['x'] + b['w']) - max(a['x'], b['x'])
    h = min(a['y'] + a['h'], b['y'] + b['h']) - max(a['y'], b['y'])
    return (w * h) if (w > 0 and h > 0) else 0

def check(label, res, vw=1920, vh=1080):
    problems = []
    cb = res['cardBox']
    for a in res['inside']:
        # every hero text box must sit inside the card
        if a['x'] < cb['x'] - 1 or a['y'] < cb['y'] - 1 or a['x'] + a['w'] > cb['x'] + cb['w'] + 1 or a['y'] + a['h'] > cb['y'] + cb['h'] + 1:
            problems.append(f"text outside card: {a['t']!r}")
        for b in res['outside']:
            if inter(a, b) > 1:
                problems.append(f"OVERLAP {a['t']!r} x {b['t']!r}")
    for b in res['outside']:
        if inter(cb, b) > 1:
            problems.append(f"card box covers outside text {b['t']!r}")
    if res.get('tiny') and not label.startswith('stress'):
        problems.append(f"collapsed text: {res['tiny']}")
    if res['overflow']:
        problems.append(f"fit overflow: {res['overflow']}")
    if cb['x'] < 0 or cb['y'] < 0 or cb['x'] + cb['w'] > vw or cb['y'] + cb['h'] > vh:
        problems.append('card leaves the screen')
    print(('PASS' if not problems else 'FAIL'), label, f"card=({cb['x']:.0f},{cb['y']:.0f},{cb['w']:.0f}x{cb['h']:.0f})", problems[:4])
    return not problems

PHOTO = "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='600' height='700'><rect width='600' height='700' fill='%23446'/><circle cx='300' cy='230' r='120' fill='%23d9b08c'/></svg>"


def variant(**kw):
    base = {
        'id': 99, 'name': 'Test', 'full_name': 'Test Player', 'first_name': 'Test', 'surname': 'Player',
        'position': 'MID', 'position_label': 'MIDFIELDER', 'club': 'LIVERPOOL', 'club_badge': '',
        'player_image': PHOTO, 'price': '£6.4m', 'ownership': '24.3%',
        'captain': False, 'vice': False, 'verdict_sub': 'GW 9 | 6 PTS | 90 MIN | WHU H 2-1', 'season_label': '2026/27',
        'display_stats': [{'icon': 'ball', 'label': 'xG PER 90', 'value': '0.03'}] * 6,
        'fixtures': [{'gw': 12 + i, 'opponent': 'WHU', 'venue': 'H', 'fdr_value': 2 + i % 3, 'badge': ''} for i in range(6)],
    }
    base.update(kw)
    return base

async def main():
    ok = True
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=os.environ.get("CHROMIUM_EXECUTABLE"))
        pg = await b.new_page(viewport={'width': 1920, 'height': 1080})
        errs = []
        pg.on('pageerror', lambda e: errs.append(str(e)))
        await pg.goto('file://' + html)
        await pg.wait_for_function('window.__ready===true', timeout=20000)

        # 1) every starter's real hero moment (hero fully in, mid-explanation)
        for s in vx['segments']:
            if s.get('kind') != 'starter':
                continue
            t = s['hero_on'] + 3.0
            await pg.evaluate('t=>window.__auditLayout(t)', t)
            await pg.wait_for_timeout(350)
            res = await pg.evaluate(COLLECT)
            ok &= check(f"starter {s['id']} t={t:.1f}", res)

        # 2) pop-in and pop-out frames still never cover outside text
        seg = vx['segments'][2]
        for label, t in (('pop-in 40%', seg['hero_on'] + 0.13), ('pop-out 50%', seg['hero_exit_at'] + 0.17)):
            await pg.evaluate('t=>window.__auditLayout(t)', t)
            await pg.wait_for_timeout(350)
            res = await pg.evaluate(COLLECT)
            ok &= check(label, res)

        # Market cards remain readable after metrics and restore the review on rewind.
        for item in vx.get('market_cards', []):
            seg = next(s for s in vx['segments'] if s['id'] == item['segment_id'])
            for offset in (.13, 3, 11.84):
                await pg.evaluate('t=>window.__auditLayout(t)', seg['t0'] + offset)
                await pg.wait_for_timeout(150)
                res = await pg.evaluate(COLLECT)
                ok &= check('market ' + item['action'] + ' ' + str(offset), res)
                actual = await pg.evaluate("document.querySelector('#vxHeroWrap .vx-player-card')?.dataset.playerId")
                ok &= actual == str(item['card']['id'])
            if item['action'] == 'BUY':
                await pg.evaluate('t=>window.__seek(t)', seg['t0'] + 3)
                await pg.screenshot(path=S + '/market_buy.png')
        state = await pg.evaluate('t=>window.__auditLayout(t)', vx['metrics_t'] + 2)
        ok &= state['hero'] == 0 and state['table'] > .99

        # 3) stress payloads mounted into the live hero slot
        await pg.evaluate('t=>window.__auditLayout(t)', vx['segments'][2]['hero_on'] + 3.0)
        stress = {
            'long name + long club': variant(first_name='Trent', surname='Alexander-Arnold', club="NOTTINGHAM FOREST", position='DEF', position_label='DEFENDER'),
            'very long single name': variant(first_name='', surname='Gabriel Teodoro Martinelli', club='ARSENAL'),
            'no photo, no crest': variant(player_image='', club_badge=''),
            'goalkeeper + captain': variant(position='GK', position_label='GOALKEEPER', captain=True),
            'double gameweek + blank': variant(fixtures=[
                {'gw': 12, 'opponent': 'ARS+CHE', 'venue': 'H+A', 'fdr_value': 4, 'badges': ['', '']},
                {'gw': 13, 'opponent': 'BLANK', 'venue': '', 'fdr_value': None},
                None, None, None, None]),
            'missing stats': variant(display_stats=[{'icon': 'star', 'label': '—', 'value': '—'}] * 3, price='', ownership=''),
            'awaiting result': variant(verdict_sub='GW 9 | AWAITING RESULT'),
            'long result chip': variant(verdict_sub='GW 9 | 13 PTS SO FAR | 90 MIN | MANCHESTER CITY H 2-1', captain=True),
        }
        for label, payload in stress.items():
            await pg.evaluate("pl=>{const hw=document.querySelector('#vxHeroWrap'); window.VXPlayerCard.mount(hw, pl); hw.dataset.pid='x'; }", payload)
            await pg.wait_for_timeout(500)
            res = await pg.evaluate(COLLECT)
            ok &= check('stress: ' + label, res)
            await pg.screenshot(path=f"{S}/{tag}_stress_{label.split(' ')[0].replace('+','')}.png")
        print('page errors:', errs[:3])
        ok &= not errs
        await b.close()
    print('ALL PASS' if ok else 'FAILURES PRESENT')
    sys.exit(0 if ok else 1)

asyncio.run(main())
