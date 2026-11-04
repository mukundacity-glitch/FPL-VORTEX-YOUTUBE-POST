# FPL VORTEX Day 1 — seven-minute production audit

Scope: **the existing** `.github/workflows/day-1.yml` and `1_final_day1.py`; no new video, workflow, publication schedule or Day 2/Day 3 changes.

## 1. Inspected components

| Priority | Component | Actual finding | Mitigation |
| --- | --- | --- | --- |
| P0 | Day 1 workflow | Existing manual `workflow_dispatch`, 33 notebook cell compiler/runner, existing Drive inputs and Private YouTube upload. The November implementation set `VORTEX_DAY1_VIDEO_TARGET_SECONDS=240`. | Set one measured editorial target (330s), plus a **hard** final-MP4 limit of 420s regardless of scene count. Keep all existing source cells and Private-only safety gates. |
| P0 | Player-card contract | `tests/test_day1_player_card.py` pins original `V6.0_SIDE_HERO_SAMPLE` JSX-in-string styling, position-specific stats, portrait URLs, club badges and hero animation. Eleven starters + four bench are separately validated in `vortex/day1_publish_contract.py`. | **Leave original 1.1MB `1_final_day1.py` unchanged**. Keep current component; make selected existing player scenes richer from their verified player_id and TTS boundaries. Run unchanged card-layout CI. |
| P0 | Dynamic FPL/model math | `vortex/day1_editorial.py` consumes verified 15-person retrospective roster, live context, official players and VORTEX model rows (`next_gw_xpts`, `expected_minutes_next_gw`). Model is not a personal transfer/bank state. | Keep actual VORTEX projections; add transparent **editorial prioritization** only, no replacement projection formula, fabricated figures or fake FTs/bank. |
| P0 | Intro agenda | `vortex/day1_agenda.py` already joins rendered agenda cards with spoken TTS anchors but formerly used inconsistent headings and optional substitutes. | Lock all five user-required on-screen titles and matching spoken anchors for GW review runs; show data-dependent caveat when no target qualifies. |
| P0 | Narration & sync | Existing Edge TTS Ryan with timed WordBoundary offsets, measured audio, `word_timed_vtt`, player reveal timings and original portrait cards. | Select four evidence-led spotlights by availability, verified minutes and existing VORTEX xPts; keep all 15 spoken/visible IDs; refrain from rewriting the reliable renderer. |
| P0 | 4K/media | `vortex/day1_media.py` mixes the original opening, `Background_music.mp3`, and a 6-second `outro.mp3` with ffprobe/ffmpeg. | Preserve source assets, fades, ratios and 3840x2160 output; validate final duration both at workflow and YouTube metadata packaging. |
| P0 | Upload duplicates | `vortex/youtube_private_upload.py` explicitly uploaded a *new* private draft on every manual run despite existing GW tags. | Compute a season-qualified marker from the **official FPL deadline**; scan authenticated YouTube uploads (private included), reuse a matching GW and never override a public video. Fail closed on incomplete owner inventory. |
| P1 | Viewer attraction | Intro previously read more like a general list of fixtures; narrator used repetitive two-sentence player summaries. YouTube package was 'My Review' and 'player by player'. | Open with a genuine verified squad dilemma, focus 3–5 card beats, compare transfer options, deliver conditional resolution; provide a clear, accurate GW-specific title/description. |
| P1 | Motion technology | Original renderer is HTML/CSS/JS inside 33-cell Python source; Remotion is NOT an installed dependency and cannot replace original hero cards without redesign. | Apply Remotion sequencing/caption/animation *principles* where compatible. Do not force a second renderer or add a React toolchain just to use a named skill. |
| P1 | Canva/Figma | Canva has at least one FPL VORTEX design; no Canva brand kit was returned. No Figma file/key was supplied or verified as the actual Day 1 source. | **Original in-repository card is the source of truth**; avoid fake Figma/Canva reconstruction and accidental visual drift. |
| P1 | Analytics | Metricool has the creator's linked YouTube brand, but no verified per-video retention curve was obtained. vidIQ returned **zero authorized YouTube channels** from the connected account. | Use evidence-backed retention hypotheses, not invented retention percentages or conversion rates; read live retention later only after owner connection. |
| P1 | QA | Existing PR QA tests 33 cells, voice sync, official review states, player cards, Playwright card screenshots and Private upload contract. | Extend with updated duration/agenda and season-deduplication tests; run PR QA before merging. |

## 2. Five on-screen chapters / viewer promise

1. **GAMEWEEK REVIEW — THE REAL STORY:** actual returns and review state, not speculative team performance.
2. **SQUAD PRESSURE — WHAT NEEDS FIXING?:** verified flags, minutes and cover; useful dilemma in the first moments.
3. **TRANSFER TARGETS — BUY / HOLD / SELL:** VORTEX model comparison and current FPL market context, with strict no-made-up-budget caveat.
4. **TRANSFER PLANS — ROLL, MOVE OR TAKE A HIT?:** realistic conditional routes, not a fabricated personalized transfer instruction.
5. **THE FINAL VORTEX VERDICT:** clear recommendation conditional on verified availability and editable squad state.

The agenda headings are visual anchors; YouTube chapters still use **actual rendered scene boundary timestamps**. Do not manufacture 5 distinct timestamps from one `gw_review` visual section.

## 3. Runtime and safety acceptance

- **One original** Day 1 16:9 3840x2160 MP4, up to **420.00 seconds inclusive** of the original intro and 6s outro.
- The 330s editorial setting is a **pacing target**, not an inferred final duration. Real ffprobe measurement decides pass/fail. A shorter episode is acceptable if useful.
- All 15 `player_id` identities (11 + 4), correct current club names/crests/photos, original card language, no newly hardcoded football facts.
- TTS WordBoundary aligns player-name audio, reveal animation and captions; mismatches fail production.
- Preserve current original soundtrack, opening, outro, Private-only upload and no automatic public post/schedule.
- Keep dynamic official FPL `bootstrap-static`, fixtures and relevant element-summary checks in the existing source. No model values, odds, injuries, EO or transfer state fabricated.
- YouTube upload idempotent per **season + Gameweek**, including reruns that complete successfully.
- GitHub PR QA reports syntax/unit/card-layout results; full media/render/YouTube proof needs an actual workflow run with configured Drive assets and secrets.

## 4. Deliberately unchanged

- `1_final_day1.py`: canonical 33-cell source, including original card JavaScript and CSS. The GitHub connector could not return its >1 MB UTF-8 body during this review; it was verified through existing source-contract tests, not falsely claimed as a frame-by-frame rendering review.
- `vortex/day1_media.py`: established signed source audio and mixing implementation.
- Day 2, Day 3 and external FPL VORTEX automated graphics tasks.
- Public YouTube publishing and all unrelated social schedules.

## 5. What proves the change

Open the PR, review `Day 1 editorial QA` (including Playwright artifact), merge only after green; then run the **existing** manual Day 1 workflow once to generate its private 4K video, ffprobe report, and Drive output. Do not claim an MP4 preview from a source-only change.
