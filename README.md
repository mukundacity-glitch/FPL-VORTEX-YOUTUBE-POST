# FPL VORTEX AUTO

## Actions workflows

Open a workflow and select **Run workflow** on `main`.

| Workflow | Purpose |
| --- | --- |
| [Day 1](https://github.com/mukundacity-glitch/FPL-VORTEX-YOUTUBE-POST/actions/workflows/day-1.yml) | Five-scene gameweek review and value board. |
| [Day 2](https://github.com/mukundacity-glitch/FPL-VORTEX-YOUTUBE-POST/actions/workflows/day-2.yml) | Day 2 video production. |
| [Day 3](https://github.com/mukundacity-glitch/FPL-VORTEX-YOUTUBE-POST/actions/workflows/day-3.yml) | Transfer and chip plan video. |
| [WC-FH](https://github.com/mukundacity-glitch/FPL-VORTEX-YOUTUBE-POST/actions/workflows/wc-fh.yml) | Wildcard and Free Hit videos. |
| [XG-DEFCON](https://github.com/mukundacity-glitch/FPL-VORTEX-YOUTUBE-POST/actions/workflows/xg-defcon.yml) | xG and DEFCON video with public YouTube publishing. |

Day 1 and Day 2 include automated QA jobs for relevant code changes. For a
manual Scene 2 restoration check, select **Run Scene 2 restoration tests only**
in Day 1.

## Day 1 five-scene live production (Scene 05 integrated)

The manual **Day 1** GitHub Actions workflow now keeps all 33 existing Day 1
cells and their first four video scenes. Before the approved background/outro
mix, it automatically generates Scene 05 using a fresh official FPL API snapshot
(`bootstrap-static`, `fixtures`, selected `element-summary` history),
a constrained £100m / 15-player squad optimiser and five-GW projected lineups.

- `vortex/day1_value_live.py`: injury/availability, minutes, ownership, net
  transfers, FDR and estimated xPts; MILP selects 2 GK / 5 DEF / 5 MID /
  3 FWD, with <=3 per club, low-cost GK and DEF coverage.
- `vortex/day1_value_board.py`: legal XI, captain, vice and bench order
  independently optimized across the next five GWs.
- `tools/day1-broadcast/ValueBoard.jsx`: green pitch, portrait/crest safe
  spacing, readable fixture badges, 10-match radar, weekly projections and
  ownership/momentum panel, with original FPL VORTEX lion logo and handles.
- `vortex/day1_value_render.py`: natural Ryan narration, pre-music Scene 05
  encoding, 4K five-scene splice, timing and asset/data evidence files.
- `tests/test_day1_value_board.py`, `tests/test_day1_value_live.py`,
  `tests/test_day1_broadcast.py`: validation gates.

**Production conditions:** The previously rendered Scenes 01–04 must pass their
existing QA; the official next GW must match the finalized review; valid prices,
fixtures and eligible players must yield a legal squad. If a gate fails, the
workflow stops rather than uploading an old video as a fresh five-scene master.

The five-scene MP4 is not produced merely by merging source code: run GitHub
Actions > **Day 1** > **Run workflow** and review the resulting MP4 artifact,
`DATA/scene05_value_board.json`, `DATA/scene05_narration.json`, and
`DATA/final_video_qa.json`. The existing YouTube upload remains **Private
only**, never automatically Public. This change does not delete original
Scene 01–04 source logic, assets, or review content.

## Day 1 and Day 2 video workflows

Day 1 remains the existing implementation on `main`:

- Workflow: `.github/workflows/day-1.yml`
- Source: `1_final_day1.py`
- Media integration: `vortex/day1_media.py`
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

### Day 1 decision-led 4K video — seven minutes preferred (natural voice)

The existing **Day 1** workflow preserves all 33 original source cells and fifteen original V6.0 hero-card players (11 starters + four bench). The dynamic `vortex/day1_editorial.py` narration now spotlights the four biggest *verified* decisions using actual official availability/minutes and **the repository's own VORTEX xPts/xMinutes model**. All other player cards remain in their existing reveal sequence.

- `.github/workflows/day-1.yml` sets a **330-second editorial pacing preference** and **420-second preferred total runtime** including the existing intro/outro. Durations are measured and logged, **not used to reject a valid longer video**. Eleven non-spotlight cards use short factual voiceover while four key players receive deeper commentary. Ryan's TTS rate is never increased to force the duration.
- Five fixed agenda headings are wired through the existing spoken/visual system; no new standalone Shorts workflow is added.
- `vortex/youtube_studio_package.py` verifies valid measured duration, 4K, SEO metadata and the **Private-only** policy; it logs an advisory rather than rejecting an otherwise-valid video when it exceeds seven minutes.
- `vortex/youtube_private_upload.py` checks the owned YouTube upload history for the same **official season and Gameweek** and prevents duplicate uploads on manual reruns; previously published public videos are never overwritten.
- **No new scheduler or automatic public YouTube publication was added.** Start the existing manual `Day 1` action after verifying the FPL event; its in-run content updates from live sources.
- Inspect the implementation and release evidence in [Day 1 audit](docs/DAY1_SEVEN_MINUTE_AUDIT.md). A real MP4 preview exists only after the production workflow has rendered it, not simply because source or tests were updated.

### Run Day 1 manually

1. Open the repository **Actions** tab.
2. Select **Day 1**.
3. Choose **Run workflow** on `main`.

No Day 2 input or file is required for Day 1.

### Run Day 2 manually

Open [Day 2 in Actions](https://github.com/mukundacity-glitch/FPL-VORTEX-YOUTUBE-POST/actions/workflows/day-2.yml),
select `main`, and choose **Run workflow**. A successful production run uploads
a private YouTube video with subscriber notifications and automatic publishing
disabled.

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

### Completed DEFCON history versus live review

The notebook's canonical FPL snapshot distinguishes `review_gw` (which may be `LIVE/PARTIAL`) from `review_ready_gws` (fully completed events). When the forecast is GW7 and GW6 is still partial, the review can show GW6 while DEFCON's completed history ends at GW5.

The Day 3 runner validates every player's DEFCON cutoff and the complete model-history list against `review_ready_gws`. Player and team cumulative totals use that same history, and the board labels its completed cutoff explicitly. A stale/mixed player cutoff or missing model-history event still stops the run. Once GW6 becomes review-ready, DEFCON must advance to GW6. The patch does not change the model formulas or the live review's gameweek selection.

After applying a runner fix, start a new **Day 3** workflow on `main`. Re-running a failed job retains the old run's source commit.
