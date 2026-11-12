# Day 1: The Gameweek Brief

The fixture-led intro is replaced by one 35–40 second football analysis opening.
Default production still contains only the opening and the existing Gameweek
Review. Optional legacy forecast scenes remain off; Day 2/3 are unchanged.

## Exact implementation files

- `1_final_day1.py`: canonical HTTP retrieval provenance; intro/review connection;
  natural Ryan speech; measured timeline/VTT; renderer cache invalidation; review
  scoreboard at frame zero; integrated-opening policy in final QA.
- `vortex/day1_brief.py`: source/freshness validation, presenter calculations,
  missing model handling, current five-card agenda, measured cue validation.
- `vortex/day1_brief.html`: responsive broadcast opening and review section;
  deterministic motion/captions, keyboard controls, reduced-motion mode.
- `vortex/day1_media.py`: retains music mixing and private-output contract, skips
  prepending `opening.mp4` when final QA identifies the integrated opening.
- `.github/workflows/day-1.yml`: production and QA jobs cover data and browser
  contracts alongside existing review/player-card/publication safeguards.

## Caption-ready voiceover

The points are only the start. Which performances matter next?

This is Fantasy Premier League Vortex.

Welcome to The Gameweek Brief, for Gameweek [next official GW].

First, the Gameweek review: points, rank, and our decisions.

Players and fixtures: the roles and minutes to trust.

Numbers behind the points: opportunity beyond a single return.

Transfer priorities: who to keep, consider, or avoid.

Captaincy and final eleven: options where the evidence supports them.

Let’s review the Gameweek, and decide what matters next.

## Timing and artifacts

Preferred ident order: analytical hook → brand → title → five agenda cards →
review. Actual timings come from WordBoundary events, not estimated timestamps.
The opening must measure 35–40 seconds. A real Ryan test of the production wording
measured 39.0 seconds at +0%, with the review handoff beginning at 35.025 seconds. Overlong audio stops with an instruction
to shorten text; Ryan is never accelerated. A short scoreboard hold may pad a
shorter read to the target. A production run writes:

- `DATA/day1_brief_sources.json`: sanitized field-level metadata, generation time.
- `DATA/day1_brief_script.json`: actual spoken text and measured word offsets.
- `DATA/day1_brief_timing.json`: actual scene timing.
- `DATA/day1_brief_master.vtt`: caption-ready measured intro cues.
- `html/gameweek_brief.html`: responsive inspection page in the work directory.

The final rendered intro uses the current review HTML in a same-origin `srcdoc`
frame during its final transition; the next assembled scene is that review at
frame zero. The original 15-player card design and measured review captions stay.

## Data rules and limitations

Official results come from the existing canonical FPL snapshot and its real
endpoint retrieval timestamps. Finals require fixture completion, FPL score lock
and the existing entry/live reconciliation. Provisional results stay provisional.
Displayed official GW points, applied player total and applied total less transfer
cost are separately labelled; captaincy uses official multipliers and bench points
are explicitly raw. Missing ranks or points are unavailable, never zero-filled.

The new intro does not refit or invent forecasts. Optional model envelopes require
source, timestamp, matching horizon and methodology version. Until a field has
that provenance, xPts / xMinutes / attack FDR / defence FDR remain unavailable.
No current XI, FT, bank, injuries or transfer plan is inferred from last GW picks.
No historical pre-deadline evidence is invented to justify a result after the fact.
No scoring-rule constants are introduced: contribution and bonus fields use
upstream actual values. News and future model claims require their own sources.

This repository has no existing web framework/router, TypeScript build or browser
application deployment. The responsive page is an HTML export in the existing
video pipeline; no unrelated website route/service is created.

## Validation / release

Run the existing Day 1 unittest suites, plus `test_day1_brief.py` and
`test_day1_brief_browser.py` (Playwright/Chromium). CI retains the original hero-card
layout audit and all old safeguards. The two source assertions updated for this
intentional replacement now assert the new renderer binding and first-frame
scoreboard visibility; no test or safeguard was deleted.

Changes are reviewed on a branch. Production rendering still requires the normal
Drive assets/model inputs and existing workflow credentials. No public upload,
new automation, schedule, or modification of an existing YouTube video is added.
Rollback: revert the change commit, which restores the prior intro and media policy.
