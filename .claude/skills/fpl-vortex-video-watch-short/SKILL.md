---
name: fpl-vortex-video-watch-short
description: Analyze a referenced FPL YouTube video using a timestamped transcript and real video frames, cross-check both, extract reusable production patterns, and build a compact original FPL VORTEX Day 1 script/edit plan. Use for /watch, analyze this video, make Day 1 shorter, or turn a reference into a reusable Claude skill. Do not use for generic football news, unsupported video summaries, or automatically publishing to YouTube.
---

# FPL VORTEX — Watch → Verify → Shorten


## USER'S CURRENT DAY 1 CONTRACT — SUPERSEDES PRIOR 180-SECOND SHORT DEFAULTS

**ONE existing Day 1 MP4 per Gameweek. NO second video, no new Shorts workflow.** The legacy skill directory name contains "short", but this is solely for backward compatibility, NOT an instruction to make a separate short video.

- **Runtime:** 5–7 minutes when warranted; **absolute MAXIMUM 420 seconds including existing opening and outro**, confirmed by ffprobe on final 16:9 4K MP4. A shorter meaningful episode is acceptable; never pad or artificially accelerate speech. Any legacy 150–180-second target or 3-minute storyboard is historical reference only.
- **Keep the ORIGINAL player cards as they are in the current Day 1 implementation:** same current portrait/card components, exact typography/layout/animations, current club badges, neon VORTEX identity, data hierarchy and timing. Visually include **all fifteen** 11 starters + 4 bench from the original reviewed squad, but narrate the 3–5 genuinely relevant players in depth instead of fifteen repetitive robotic monologues. Match every card player ID to official FPL data and spoken subject. Do not replace cards with generic slides or fabricated logos.
- **Five fixed headings:** (1) GAMEWEEK REVIEW — THE REAL STORY; (2) SQUAD PRESSURE — WHAT NEEDS FIXING?; (3) TRANSFER TARGETS — BUY / HOLD / SELL; (4) TRANSFER PLANS — ROLL, MOVE OR TAKE A HIT?; (5) THE FINAL VORTEX VERDICT. Spoken agenda must correspond to exactly the scenes displayed.
- **Production story learned from FPL Harry's reference video (https://youtu.be/LOtSsW7j9lY):** open with a real transfer dilemma; identify player problems; compare relevant alternatives with prices, verified fixtures, minutes and xPts where genuine; explain roll/one FT/-4 scenarios without inventing personalized transfers; finish with conditional verdict. Never copy another creator's footage, speech or graphic assets.
- **Skills:** Use all RELEVANT installed FPL, YouTube scripting/editing/SEO/retention, vidIQ and **Remotion** skills (remotion-best-practices, markup, captions, Studio, render) wherever they improve the EXISTING renderer. Evaluate compatibility first. Remotion is optional technical support, not permission to replace the current player-card renderer, audio, assets or automation. No need to use irrelevant skills.
- **Edit the original GitHub production:** .github/workflows/day-1.yml, 1_final_day1.py, vortex/day1_editorial.py and timing/card modules as necessary. Maintain the existing 33-cell source, private-only upload, existing opening, soundtrack and six-second outro; don't edit Day 2/Day 3/other Task automations. Existing Day 1 must regenerate gameweek-correct video on future runs. Retain manual dispatch; any future automatic schedule belongs in the SAME workflow after checking match-completion gate and per-GW duplicate guard.
- **Data integrity:** Live official FPL season, fixtures, clubs, deadline, status, minutes, transfers and previous-GW results; separate VORTEX model xPts/xMins with source/model timestamps and N/A when unavailable. No invented EO, odds, injuries or transfer state. Do not equate a previous completed GW squad with a verified future editable squad.
- **QA:** Player card/voiceover/subtitle alignment, all 15 player IDs & current team logos, five agenda headings, verified statistics, 4K 16:9, actual ffprobe MP4 <=420s, captions, mobile readability, music/opening/outro, private YouTube upload, no duplicate GW video. Render/inspect real frames/audio when accessible. If only instructions/code were changed, explicitly state no actual MP4 was produced.
- **Deliver:** Real repo changes/commits/QA/MP4 link when exists; otherwise exact blocker. No more standalone 3-minute script or second workflow unless explicitly requested.

## Source and activation
Accept a canonical YouTube URL, source video ID, timestamped transcript, frames, current FPL VORTEX Day 1 media/code and a duration goal. Target 5–7 minutes, horizontal 16:9 4K, with a HARD maximum of 420 seconds for the SINGLE existing Day 1 MP4. Make a **45–60 second vertical 9:16 Short** only when requested. Do not copy another creator's script, branding or proprietary graphics.

## Mandatory /watch gate
1. Invoke `/watch` if installed, requesting the complete timestamped transcript plus actual sampled video frames (opening, FPL data comparison, recommendation, ending and visual transitions). Validate returned video ID.
2. Otherwise obtain captions/audio transcription and extract representative frames from the *actual* source media using an authorized tool or FFmpeg; label acquisition method and timestamps.
3. If either modality is unavailable, explicitly state **transcript/frame comparison not performed**. Never invent statements, frames, exact timecodes or opinions from the title. A thumbnail is NOT video-frame analysis.

## Cross-modal evidence ledger
For each key claim record `time_start`, `time_end`, `spoken_claim`, `frame_time`, `observed_visual`, `status`, `confidence`. Status is `both_verified`, `speech_only`, `visual_only`, `contradicted` or `unavailable`. Cross-check what is said against what is on screen: headline promise, player identity, statistics, graphics, comparison structure, cuts and closing CTA. A competitor opinion is not an FPL fact.

## Extract production methods
Identify only demonstrated techniques: hook in first 15 seconds, evidence before a verdict, like-for-like comparison, explicit risk/conditional advice, clean data cards, and concise close. Record the observation/timestamp for each technique. Unobserved principles must be labelled **proposed VORTEX experiment**.

## Convert to FPL VORTEX Day 1
Inspect `mukundacity-glitch/FPL-VORTEX-YOUTUBE-POST` before modifying anything:
- `.github/workflows/day-1.yml` is the manual Day 1 workflow;
- `1_final_day1.py` contains the original 33 notebook-style cells;
- `vortex/day1_editorial.py` constructs narrated FPL player review;
- private YouTube upload scripts must retain privacy and subscriber settings.
Avoid changes to Day 2, Day 3 and scheduled Tasks 1/2. Preserve the complete 33-cell source until tested.

### Historical 180-second reference ONLY — not an active Day 1 workflow
| Time | Scene |
|---|---|
| 0:00–0:07 | One actionable FPL question; hook, current club badges. |
| 0:07–0:20 | Verify season, next GW and deadline; establish why decision matters. |
| 0:20–0:48 | Option A: price, home/away fixture, availability, minutes. |
| 0:48–1:16 | Option B: like-for-like verified comparison. |
| 1:16–1:46 | Tradeoff: transfer/hit cost, fixtures ahead, risk. |
| 1:46–2:18 | BUY/HOLD/SELL/MONITOR verdict conditioned on team news. |
| 2:18–2:50 | Deadline check and one-screen recap; no invented data. |
| 2:50–3:00 | FPL VORTEX outro, like + bell when actual media exists. |

Keep spoken text ~350–420 words including transitions, mobile-readable subtitles and disciplined edit continuity. Existing Day 1 validation currently targets **480 seconds**; reducing only the validation threshold will NOT shorten the rendered video. Re-author the narration/scene selection and regression-test before switching the private upload to a shorter MP4.

## FPL data integrity
Verify official FPL bootstrap-static, fixtures and element-summary as available; verify team, player ID, season/GW, availability, minutes, price and fixtures H/A. Distinguish ownership % from EO and model xPts from official ep_next. Never manufacture market odds, injuries, press quotes, player identities or numeric forecasts. Use N/A, timestamps and the disclosure “Expected points and captaincy recommendations are forecasts, not guaranteed returns.”

## Deliverables and QA
Deliver (a) sources and acquisition status, (b) timestamped transcript/frame ledger if available, (c) 3–5 observed or explicitly experimental methods, (d) original <=180s spoken script with [ON SCREEN] for every beat, (e) EDL with real source timecodes only when measured, and (f) explicit tests and privacy status. Confirm video ID, continuity, data validity, accurate crests, legible title/subtitles, runtime and whether a real MP4 was rendered. Do not claim editing or publication that did not occur.

## Source reference status
Reference: `https://youtu.be/LOtSsW7j9lY`, FPL Harry, “MY FPL GW10 TRANSFER PLANS — GABRIEL vs BOURNEMOUTH PLAYERS,” 2026/27, published 2026-11-02, podcast mirror length 21:25. **Update (2026-11-04):** English timestamped captions were retrieved, and an independent timestamped visual-scene report was returned by vidIQ video-watch. No raw individual video-frame file was downloaded, so pixel-level frame fidelity remains unverified. Observed matching moments include: 05:15 problem players versus three-row panel, 08:27 Gabriel versus defender cards, 10:27 Bournemouth midfield panel, and 13:56 roll/one FT/-4 comparison board. Important conflict: one watch report labels João Pedro as BHA while the transcript treats him as Chelsea; verify all teams through official FPL before reuse. Do not copy the reference video's dated predictions into current VORTEX advice.
