# FPL VORTEX AUTO

## Shared fixture calculations

Day 1, Day 2, Day 3 and WC/FH use `vortex/fixture_forecast.py` and the
WC/FH model vendored from `FPL-VORTEX-AGENT` commit
`31e088378736a0f622eb51e7da6b3e2ab18ba55b`. The evidence coverage gates,
projected-goal equations, Poisson clean-sheet probabilities and continuous FDR
formulas are shared. GK/DEF use defence FDR; MID/FWD use attack FDR. Day 2 no
longer uses official FPL difficulty or a separate opponent-strength blend for
its fixture values. Its numbers retain decimals while existing CSS buckets,
card geometry and scene order remain intact.

The Day 1 and Day 3 legacy goal builders and duplicate FDR function definitions
are removed from their execution source. Clean-sheet odds are read directly
from the same WC/FH fixture record, with a strict goal-snapshot identity check.
Day 2 removes the old FPL-strength normalization as well as its difficulty inputs.

Existing Gameweek windows, graphics, narration structure and workflow schedules
are preserved. These are forecasts: runs using newer match evidence or different
Gameweek windows can show different totals. The common input/cache directory is
`FPL_VORTEX/MODEL_INPUTS/canonical_fixtures`; optional `team_context_raw.csv` and
`team_news_overrides.csv` must be placed there so every workflow reads the same
overrides. `VORTEX_FIXTURE_INPUT_ROOT` can override that directory for local tests.
Weekly Phase 3 retains its uncertainty method and schema while taking all goal
components from the shared model before downstream Poisson/FDR calculations.

Validation: `python -m unittest discover -s tests -p 'test_*.py' -v`,
`python -m unittest discover -s day2 -p 'test_*.py' -v`,
`python -m unittest discover -s day3 -p 'test_*.py' -q`, and
`python -m unittest discover -s wc_fh -p 'test_*.py' -q`.

## Day 1 and Day 2 video workflows

Day 1 produces exactly two video sections:

1. Intro and match roundup (maximum 180 seconds). Every official fixture in the
   reviewed Gameweek appears individually. Completed scores, scorers/positions,
   own goals, yellow/red cards and recent availability flags come from the
   same official FPL snapshot. Pending matches show the official kickoff in UK
   time; live scores are explicitly provisional. Each spoken player name opens
   a purple player card using measured Ryan WordBoundary times.
2. The existing player-by-player squad review and its closing outro (maximum
   240 seconds). The approved pitch, formation, bench and review-card geometry
   remain. The closing message is inside this section, not a third MP4.

Standalone FDR, projected-goal, clean-sheet, transfer/decision-engine and outro
scenes were removed from Day 1. Only the shared WC/FH fixture model runs for
card FDR and team CS forecasts; official player rates are descriptive statistics.
Missing values show as unavailable, not invented zeros. Blank and double
Gameweeks remain explicit. Review cards display continuous FDR to two decimals
while retaining their existing color classes.

Welcome copy varies using persisted wording history under
`MODEL_INPUTS/canonical_fixtures/day1_narration_history.json`. It is kept outside
the output-reset directory. Speech is conversational, and duration is checked
from the generated audio. If a roundup exceeds its limit, optional assist-only
mentions yield to scores, scorers, discipline and availability coverage; an
over-length edition cannot publish. Red-card ban lengths are not guessed.
Booking warnings use club match cutoffs, not Gameweek numbers: five cautions
within 19 league matches, ten within 32, and fifteen within the season.

Day 1's workflow trigger, the shared watcher schedule, Day 2, Day 3 and WC/FH
are unchanged. No separate opening clip is prepended. The existing background
and final six-second music treatment remain, and the final assembly has exactly
two chapters. YouTube uploads remain private.

- Workflow: `.github/workflows/day-1.yml`
- Source: `1_final_day1.py`
- Runtime, narration, rendering and music integration: `day1/`
- YouTube package/upload: `vortex/youtube_studio_package.py` and `vortex/youtube_private_upload.py`
- Output root: `My Drive/FPL_VORTEX/FIRST VIDEO`

Day 2 is isolated from Day 1:

- Workflow: `.github/workflows/day-2.yml`
- Day 2 automation code/config: `day2/`
- Colab source: Drive file `DAY2_FINAL.ipynb` (configured by file/path in `day2/config.json`)
- Output root: `My Drive/FPL_VORTEX/Day_2`
- Actions artifacts: `day2-video-output-*` and `day2-video-log-*`
- YouTube uploads are explicitly `private`; automatic Public, Unlisted, and scheduled publishing are disabled.

The Day 2 workflow reads shared model inputs and the existing Day 1 media assets, but it never publishes to the Day 1 output path and never edits the Day 1 workflow or scripts. The Day 1 opening/music contract is reproduced in `day2/media.py`: opening first with its original audio, background music beginning at the Day 2 `slide_00` program start at the same `12/255` gain, and `outro.mp3` for the final 6 seconds. The Day 2 notebook keeps the canonical VORTEX logo/lion-head treatment and its Scene 7 subscribe CTA.

### Run Day 1 manually

1. Open the repository **Actions** tab.
2. Select **Day 1**.
3. Choose **Run workflow** on `main`.

No Day 2 input or file is required for Day 1.

### Run Day 2 manually

GitHub only exposes a `workflow_dispatch` workflow from the repository's default branch. After reviewing and manually merging `feature/day2-video-workflow` into `main`:

1. Open **Actions**.
2. Select **Day 2**.
3. Choose **Run workflow**.
4. Set:
   - `upload_to_youtube`: `true` to allow a Private upload, or `false` to build only.
   - `dry_run`: `true` to build/render and validate metadata while skipping YouTube upload.
   - `video_date`: the date used in the title, for example `2026-09-03`.
   - `render_quality`: `FINAL` for a 3840x2160 YouTube-ready render; `DRAFT` for fast validation.
5. Start the run.

A real YouTube upload is refused unless `render_quality=FINAL`. Every upload request is created with `privacyStatus=private`, `notifySubscribers=false`, and no automatic scheduling/publication.

### Edit Day 2 metadata and assets

Edit `day2/metadata.json` for the default:

- video date
- topic/title template
- description/summary
- hashtags/tags

Edit `day2/config.json` only when the Day 2 Colab file, output location, or shared asset folder changes.

The media filenames intentionally match Day 1 and are read from the same established Drive asset folder:

- `opening.mp4`
- `Background_music.mp3`
- `outro.mp3`

The workflow copies those assets into runner-local Day 2 storage; it does not modify the Drive asset folder.

### GitHub secrets

Day 2 reuses the existing repository secret names established by Day 1:

- `GOOGLE_OAUTH_CLIENT_ID`
- `GOOGLE_OAUTH_CLIENT_SECRET`
- `GOOGLE_OAUTH_REFRESH_TOKEN`
- `YOUTUBE_OAUTH_CLIENT_ID`
- `YOUTUBE_OAUTH_CLIENT_SECRET`
- `YOUTUBE_OAUTH_REFRESH_TOKEN`
- `YOUTUBE_CHANNEL_ID`

The YouTube client ID/secret may fall back to the Google OAuth client ID/secret exactly as Day 1 does. `YOUTUBE_OAUTH_REFRESH_TOKEN` must authorize YouTube upload/read access for the same channel identified by `YOUTUBE_CHANNEL_ID`.

No credential value is written to logs, source, artifacts, or metadata files.

## Day 3 workflow and authentication

[`day-3.yml`](.github/workflows/day-3.yml) is a manually dispatched workflow. It downloads the production notebook from Drive, restores the model inputs and media assets, runs the patched notebook in FINAL / FULL_VIDEO mode, uploads one private YouTube draft with its thumbnail, syncs the output to Drive, and exposes the finished video as an Actions artifact.

The **Elite Ownership** field under **Run workflow** starts blank. Paste the full visible text from `https://fpl.team/top/`, including Gameweek, sample size, template XI and bench, seven captains, and current/total chip panels for Top 10k and Overall. Line breaks and flattened text are supported. The paste supplies the slide and its narration for that run; player IDs come from official FPL data. It does not replace official effective ownership calculated from manager picks.

Leave the field blank to fetch the page live. The runner ignores the Drive notebook's saved example text. An explicit incomplete paste fails validation; a paste outside the decision Gameweek or its preceding review Gameweek stops with a request for current data, rather than silently switching sources. The slide and narration retain the actual source Gameweek and sample size. This input does not edit the Drive notebook.

The authentication components are:

| Component | Credentials | Request flow and storage |
| --- | --- | --- |
| GitHub checkout | GitHub's job `GITHUB_TOKEN` | The workflow grants `contents: read`; `actions/checkout` uses the token to fetch the repo. This token is separate from the Google credentials. |
| Drive setup in `day-3.yml` | `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `GOOGLE_OAUTH_REFRESH_TOKEN` | POST a form with `grant_type=refresh_token` to `https://oauth2.googleapis.com/token`. Download the notebook with `Authorization: Bearer <access_token>`. Store the client credentials, refresh token, access token, and expiry in `$RUNNER_TEMP/rclone/rclone.conf`, with mode `0600`. |
| Drive asset/state transfer | The same temporary rclone configuration | `vortex-drive` accesses My Drive and `day1-assets` uses the configured asset folder as its root. Only the configuration path is written to `GITHUB_ENV`. rclone uses the refresh token when the access token expires. The configuration is outside the output/artifact paths. |
| Colab compatibility in [`day3/run_notebook.py`](day3/run_notebook.py) | Runner environment variables | `google.colab.userdata.get(name)` reads the corresponding environment value. The Drive mount shim creates local directories; the earlier rclone restore provides their contents. |
| YouTube in [`day3/publish_private.py`](day3/publish_private.py) | `YOUTUBE_OAUTH_REFRESH_TOKEN`, YouTube client ID/secret, `YOUTUBE_CHANNEL_ID` | `Credentials(token=None, ...)` refreshes through Google's token endpoint. The client ID/secret individually fall back to their `GOOGLE_OAUTH_*` counterparts when absent; the YouTube refresh token has no fallback. The API client retains the access token in memory. |
| Official FPL data | No FPL login credentials | Public bootstrap, fixtures, entry/picks, and event-live reads use HTTP requests. OAuth tokens for Drive/YouTube are not FPL session tokens. |

The YouTube credentials request `youtube.upload` and `youtube.readonly`. `_verify_channel()` calls `channels.list(mine=True)` and rejects a channel other than `YOUTUBE_CHANNEL_ID`. `_upload_video()` explicitly sets `privacyStatus=private` and `notifySubscribers=false`; `_verify_private()` checks the resulting status. Upload metadata and reports contain video/channel information, not OAuth credentials. The repository uses preauthorized refresh tokens; it does not implement an interactive OAuth consent/callback flow or store Google passwords.

References: [GitHub workflow token authentication](https://docs.github.com/en/actions/tutorials/authenticate-with-github_token), [Google refresh tokens and offline access](https://developers.google.com/identity/protocols/oauth2/web-server#offline), and [rclone Drive configuration](https://rclone.org/drive/).

### Live FPL squad and Player OUT choices

The five **Player OUT** dropdowns and the OUT players on the transfer-plan slide
both come from the official public FPL API, not from a stored player list.
[`day3/fpl_squad.py`](day3/fpl_squad.py) resolves entry `FPL_ENTRY_ID` (currently
`145784`) from `bootstrap-static`, entry history and the latest published
`event/<gw>/picks`, walking back past a Free Hit squad to the last permanent 15.
It uses no FPL login; `/api/my-team/<id>/` requires authentication and is never
called. An API outage fails the run — there is no stale squad fallback.

Because GitHub dispatch `choice` options are static YAML,
[`Refresh Day 3 OUT choices`](.github/workflows/refresh-day3-choices.yml)
regenerates all five OUT lists from the live 15 every three hours and commits
only when the squad changes. You can also run it manually before a dispatch.
Every Day 3 run re-resolves the squad in the `Resolve live FPL squad and verify
Player OUT picks` step and rejects any OUT that is not in your real team (or any
IN that already is) before the expensive render starts.

The same resolved squad is passed into the notebook. `FPL_ID` follows
`FPL_ENTRY_ID`, Phase 11's `current_squad_state` must equal the live 15, and the
MY PLAN 5B transfer scene may only draw OUT cards from those 15. See
[`day3/LIVE_SQUAD.md`](day3/LIVE_SQUAD.md) for the full contract, the endpoints
and the local commands.

### Completed DEFCON history versus live review

The notebook's canonical FPL snapshot distinguishes `review_gw` (which may be `LIVE/PARTIAL`) from `review_ready_gws` (fully completed events). When the forecast is GW7 and GW6 is still partial, the review can show GW6 while DEFCON's completed history ends at GW5.

The Day 3 runner validates every player's DEFCON cutoff and the complete model-history list against `review_ready_gws`. Player and team cumulative totals use that same history, and the board labels its completed cutoff explicitly. A stale/mixed player cutoff or missing model-history event still stops the run. Once GW6 becomes review-ready, DEFCON must advance to GW6. The patch does not change the model formulas or the live review's gameweek selection.

Live evidence is strict by default: it waits for verified final FPL statistics and fails rather than publishing incomplete data. `DAY3_ACCEPT_PROVISIONAL`, `DAY3_ALLOW_PARTIAL_GAMEWEEK`, and `DAY3_EVIDENCE_MAX_WAIT_MINUTES` are explicit operator overrides for stale FPL fixture flags or an API outage; see [`day3/LIVE_EVIDENCE.md`](day3/LIVE_EVIDENCE.md). Cell 18's DEFCON animation anchors are rebuilt from the same full-word narration used for speech, so the live-evidence narration cannot drift from the exact-sync preflight.

After applying a runner fix, start a new **Day 3** workflow on `main`. Re-running a failed job retains the old run's source commit.


### Automatic watcher

`Gameweek State Watcher` checks official FPL state every two days (approximately 48 hours). Day 1 and Day 2 remain separate workflows. When the review state advances, the watcher can trigger each workflow independently; Day 2 remains Private-only on YouTube and keeps its own Drive output root.
