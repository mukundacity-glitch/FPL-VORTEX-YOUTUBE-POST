# FPL VORTEX Day 1 — automatic finalized-GW production

Day 1's production workflow is still `.github/workflows/day-1.yml`. The scheduler
is a **separate coordinator**, not a replacement for the original 33 cells,
pitch renderer, model, Remotion graphics, Ryan narration, or FFmpeg mixer.

## Safety / setup

Set GitHub repository variable `DAY1_SCHEDULER_ENABLED=true` **only after a
five-scene video has passed actual 3840×2160 video, audio and visual QA on main**.
While this variable is absent or false, the periodic scheduler does not dispatch.
The schedule checks at 00:23, 06:23, 12:23 and 18:23 **UTC** (GitHub cron
execution can be delayed). Manual Day 1 workflow dispatch remains available.

`DAY1_AUTO_PRIVATE_UPLOAD=true` permits the scheduler to request a YouTube
**Private** upload after the final video QA gates. Default is false.
`DAY1_SCHEDULER_MAX_RETRIES` defaults to 3 and is capped at 5.
No automatic public release or public schedule is enabled by either workflow.

Official FPL bootstrap event flags `finished` and `data_checked`, completed
fixture scores, the next game's official `is_next` flag and the next five event
records are all required. A fixed weekday never substitutes for finalization.
Temporary API or metadata failures result in no dispatch. A score update, market
change, player status change or fixture change is represented in the recorded
SHA-256 snapshot version. The idempotency key is the stable
season/review-GW/preview-GW identity; a changing market price by itself does
not generate duplicate videos for the same reviewed week.

A persistent GitHub issue named `FPL VORTEX DAY 1 | <production-identity>`
records attempts, snapshot version, source revision, requested Private-upload
status, workflow URL and completion status. The scheduler's concurrency guard
and action-run check avoid overlapping production; successful runs prevent
duplicate dispatch. Failed runs can retry only within the configured limit.
Manual intervention is required after the retry limit.

The `workflow_run` completion handler marks the issue successful **only if**
the full Day 1 workflow succeeds. The production workflow must have passed
`vortex.day1_final_qa`, the complete five-scene MP4 decoder and screenshot
collection, before it can upload privately. It saves ten representative
screenshots (five scenes + five weekly lineup states), black-frame/silence
scan results, the live 15-player squad and actual media timings.

The controls deliberately do not authorize public publication. Keep the
existing YouTube uploader locked to `privacyStatus=private`; any public
release requires separate approval and an explicit policy change.

## Diagnostics

- Production work: GitHub Actions **Day 1**.
- Scheduling and idempotency: **Day 1 scheduler (finalized FPL only, private upload)**.
- Safe scheduler tests: **Day 1 scheduler contracts (no production)**.
- Official snapshot: `DATA/scene05_value_board.json` and
  `DATA/day1_production_identity.json` when the full run has succeeded.
- Visual/audio scan: `DATA/day1_final_media_scan.json`.
- Evidence frames: `SLIDE/final-scene-*.png`.
- If a production fails, inspect the failing Day 1 run log and ledger issue.
  Never publish a failed or stale episode.

No production is considered verified solely because its code or scheduler is committed.
