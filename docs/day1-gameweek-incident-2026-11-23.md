# Day 1 production incident, 23 November 2026

## Confirmed failure

[Production run #165](https://github.com/mukundacity-glitch/FPL-VORTEX-YOUTUBE-POST/actions/runs/45105102199) was manually dispatched on `main` at `2026-11-23T03:17:31Z` (09:02:31 Nepal time). [Job 137464453176, step 18](https://github.com/mukundacity-glitch/FPL-VORTEX-YOUTUBE-POST/actions/runs/45105102199/job/137464453176#step:18:1), `Execute Day 1 cells once in order`, was the first failure. It failed in block 27 of 33, `CELL 14B — ORIGINAL WEEKLY FDR / PROJECTED GOALS / CLEAN SHEET DESIGN`. The notebook chose GW11 after the first verified fixture, which is valid for the provisional review, and then called a Player Hero analysis that accepts only the latest `finished=true`, `data_checked=true` event with finalized fixtures. The five-scene Value Board also requires the preceding review to be final. An older review paired with the new preview would violate that contract.

Relevant runner output, with timestamps shortened and ANSI colours removed.

```text
03:26:30.9718881Z AUTO REVIEW GW: 11 (LIVE/PARTIAL)
03:26:30.9719150Z LATEST REVIEW-READY GW: 10
03:26:37.7129704Z ✅ GW REVIEW STATUS: LIVE/PARTIAL
03:26:37.7130130Z ✅ GW REVIEW FIXTURES: 9/10 verified complete
03:26:37.7131142Z ✅ Review GW source: event.is_current, first_verified_fixture_complete
03:29:55.4834595Z ✅ Next GW: 12
Traceback (most recent call last):
  File "/opt/hostedtoolcache/Python/3.11.18/x64/lib/python3.11/site-packages/IPython/core/interactiveshell.py", line 3821, in run_code
    await eval(code_obj, self.user_global_ns, self.user_ns)
  File "<ipython-input-1-e4ccfc404220>", line 4092, in <module>
    VX_PLAYER_HERO = day1_player_hero.analyze(
  File "/home/runner/work/FPL-VORTEX-YOUTUBE-POST/FPL-VORTEX-YOUTUBE-POST/vortex/day1_player_hero.py", line 105, in analyze
    raise ValueError("Hero analysis requires the latest completed and checked FPL gameweek")
ValueError: Hero analysis requires the latest completed and checked FPL gameweek

The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File "<stdin>", line 126, in <module>
RuntimeError: Day 1 block 27 failed: CELL 14B — ORIGINAL WEEKLY FDR / PROJECTED GOALS / CLEAN SHEET DESIGN
##[error]Process completed with exit code 1.
```

Archived job output contains the Python exception, with no HTTP error or raw response attached to that exception. A separate live replay returned HTTP 200 for `/bootstrap-static/`, `/fixtures/` and `/event/11/live/`. Bootstrap showed GW10 `finished=true,data_checked=true`, GW11 `is_current=true,finished=false,data_checked=false` and GW12 `is_next=true`. GW11 fixture 103 had kickoff `2026-11-23T20:00:00Z` (24 November, 01:45 Nepal time), `finished=false`, `finished_provisional=false` and both scores missing. The other nine had provisional full-time results. FPL documents the 2026/27 score-lock target of 09:00 UK time on the day after the last match. For this fixture that is 24 November, 14:45 Nepal time. Each run should rely on the official status and fixture evidence. [Premier League explanation](https://fantasy.premierleague.com/help/new)

## Comparison

| Run | Trigger and commit | Observed outcome |
| --- | --- | --- |
| [#165](https://github.com/mukundacity-glitch/FPL-VORTEX-YOUTUBE-POST/actions/runs/45105102199) | Manual, `4b3c3b9496855839b366f93a3e09c427a8ebdbaf` | GW11 live with 9/10 complete. First failure in Cell 14B before Scene 05, media packaging, Drive publication and YouTube. |
| [#151](https://github.com/mukundacity-glitch/FPL-VORTEX-YOUTUBE-POST/actions/runs/43657475232) | Manual, `38a6b8ee4c671769d95a021019f59017f4127898` | GW10 final with 10/10. The 33 cells passed and YouTube returned `PRIVATE 4K upload: PASS`. |
| [#157](https://github.com/mukundacity-glitch/FPL-VORTEX-YOUTUBE-POST/actions/runs/44723369449) and [#164](https://github.com/mukundacity-glitch/FPL-VORTEX-YOUTUBE-POST/actions/runs/44919674036) | Push and pull request | Successful checks. `run-day-1` is manual-only and did not run. |
| [#144](https://github.com/mukundacity-glitch/FPL-VORTEX-YOUTUBE-POST/actions/runs/43603759590) | Manual, `b2a4cc47dec9b545db75e213df4d41097ddfda6a` | Separate Cell 21 failure in the clean-room check for `helper_source:analyze:team_a_difficulty` and `team_h_difficulty`. Subsequent GW10 runs passed that check. |

Both #151 and #165 used `1_final_day1.py` SHA-256 `bf40d1b01786b66208f208023c5d00d3262a763270b87a3e7cf6a01866ef6495` and FPL Core revision `de0427dd1cf0cae731eabd2b3c8579c83d789199`. Between their repository commits, all changed files were Day 3 or Wildcard/Free Hit. Top-level production dependencies matched except `google-auth` (`2.62.2` to `2.63.1`); observed transitive changes were `certifi`, `charset-normalizer` and `wcwidth`. The failing branch is a deterministic comparison of Gameweek data. The available history supports one failure of this specific type, with recurrence whenever a manual dispatch reaches the same provisional state.

## Classification

| Suspect | Classification and evidence |
| --- | --- |
| Provisional Gameweek passed to completed-Gameweek Player Hero | **CONFIRMED ROOT CAUSE**. GW11 was still being played and GW10 remained the latest completed and checked event. |
| Readiness checked only after rendering started | **CONTRIBUTING ISSUE**. A provisional snapshot reached Cell 14B after Drive restore and initial rendering. Valid final data is now checked before the production job. |
| End-of-season horizons | **CONTRIBUTING ISSUE for future runs**. Scene 05 explicitly rejected GW35–38. The ported Value Board tests prove only the remaining official rounds are forecast. Day 1 also needs a preceding review and an upcoming preview, so the season opener or a closed season needs a different editorial format. |
| Cron delay, dropped run, timezone or a fixed date/GW | **RULED OUT for #165**. The actual run was manually dispatched and consumed current official fixture and event flags. `day-1.yml` defines no schedule. GitHub may delay or drop scheduled events in workflows that have a schedule. [GitHub Actions schedule docs](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule) |
| FPL 429/5xx/schema drift, empty files, zero fixtures or goals | **RULED OUT as the first error in #165**. The log has nine completed fixtures and a successfully rendered review scene. The direct replay returned valid JSON and HTTP 200. A zero score counts as a result. |
| Private YouTube OAuth, quota, upload metadata, Unicode limits, duplicate video or pagination | **RULED OUT for #165**. All YouTube upload operations were skipped. The early secret shape check passed, which says nothing about the current validity of the OAuth grant. |
| Drive OAuth, permissions, missing inputs, runner paths and checkout | **RULED OUT as the first error**. OAuth, required Drive restore, Git checkout, notebook loading and Scene 02 rendering passed. No later Drive publication ran. |
| Node 20 action deprecation | **CONTRIBUTING ISSUE for runner maintenance only**. GitHub forced `setup-node@v4` onto Node 24 in both runs and the action succeeded. Day 1 now uses the v7 actions. The Remotion Node 22 runtime is preserved. |
| Missing Odds API key or expert advice | **RULED OUT for #165**. Odds is optional and the official/research-only editorial path continued to Cell 14B. |

## Dependencies and service behaviour

| Service/path | Requests, credentials and handling |
| --- | --- |
| FPL public API | `GET /api/bootstrap-static/`, `/api/fixtures/`, `/api/event/{gw}/live/`, `/api/entry/{id}/`, `/api/entry/{id}/history/`, `/api/entry/{id}/event/{gw}/picks/`, `/api/element-summary/{id}/`. No OAuth. No contractual public rate limit was verified. The preflight and Value Board use bounded exponential retry for 429, 500, 502, 503 and 504 plus network timeouts, respect usable Retry-After, and fail explicitly on other HTTP errors or invalid JSON. Notebook requests retain their existing immutable per-endpoint cache and retries. An optional history lookup falls back visibly to season minutes, including a circuit break after three consecutive failures. |
| OAuth / Google Drive | `POST https://oauth2.googleapis.com/token`, form-encoded `grant_type=refresh_token`; the `GOOGLE_OAUTH_*` secrets authorize `rclone` with Drive scope and access to existing approved assets and output folders. The credentials mode checks `drive/v3/about`. Google documents that Drive can return 403 or 429 for throttling and that Testing consent can expire the refresh token after seven days. Project-specific quota and secret grants can only be verified through the authenticated project. [Drive limits](https://developers.google.com/workspace/drive/api/guides/limits) · [Google OAuth](https://developers.google.com/identity/protocols/oauth2/) |
| YouTube Data API v3 | `channels.list(mine=true)`, `playlistItems.list` paginated, `videos.list` for authorized inventory and final status, and `POST /upload/youtube/v3/videos` using resumable private upload, no notifications. Upload/read grants are `youtube.upload` and `youtube.readonly`, with `YOUTUBE_CHANNEL_ID` checked against the owner. The client retries transient failures. A quota or limit rejection reports HTTP status and the reason. Default buckets are 100 video inserts per day and 10,000 daily units for other calls excluding search. Daily reset is midnight Pacific. Project, user and channel limits can differ. [Insert API](https://developers.google.com/youtube/data/reference/rest/v3/videos/insert) · [Quota](https://developers.google.com/youtube/data/determine_quota_cost) · [Resumable protocol](https://developers.google.com/youtube/data/guides/using_resumable_upload_protocol) |
| Data archive and media | GitHub sparse checkout of `lukegiuseppin/fpl:data` provides the seasonal history at the notebook's existing archive symlink. Restore scripts validate approved Google Drive media and recover the crest from the opening if necessary. Photos and crests use public Premier League/FPL endpoints with existing fallbacks. AllAboutFPL uses public RSS and WordPress posts API and omits unverified opinions. Optional Odds API v4 uses `ODDS_API_KEY`; quota depends on the subscription and it was disabled/unconfigured in #165. No Google Sheets path exists in Day 1. |
| Rendering / Actions | Python and FFmpeg build media and packages, Playwright captures original visuals, pinned npm via `npm ci` runs Remotion, and `edge-tts==7.3.1` streams Ryan narration with word timing. Edge has no contractual quota identified for this client. A handshake check and bounded transport retries fail visibly. GitHub's token uses `contents: read` for checkout; the verified MP4 and job log are hosted artifacts. [Setup Python](https://github.com/actions/setup-python) · [Setup Node](https://github.com/actions/setup-node) |

## Validation and recovery

Local validation passed 201 Day 1 tests with the browser-dependent layout case excluded because Chromium hit a sandbox socket permission restriction. A replay of GW10 using official historical fixture and live-data payloads and the previous preview pointer reconciled 313 Player Hero candidates. The current live dry-run blocked GW11 with 9/10 full-time, zero finalized fixtures, and the next kickoff. The revised private production job requires a dispatch after official settlement.

```bash
python -m pip install -r requirements-day1.txt
python -m pip check
python -m unittest discover -s tests -p 'test_day1_preflight.py' -v
python -m unittest discover -s tests -p 'test_day1_season_dedup.py' -v
python -m unittest discover -s tests -p 'test_day1_value_*.py' -v
python -m vortex.day1_preflight

repo=mukundacity-glitch/FPL-VORTEX-YOUTUBE-POST
ref=fix/day1-official-gameweek-readiness
gh workflow run day-1.yml -R "$repo" --ref "$ref" -f mode=validate
gh workflow run day-1.yml -R "$repo" --ref "$ref" -f mode=credentials
gh run list -R "$repo" --workflow day-1.yml --event workflow_dispatch --limit 5
```

`validate` makes public FPL requests only. An in-progress Gameweek yields a specific failure summary and skips production. `credentials` checks OAuth without uploading or publishing. Missing secrets, invalid Drive grant, unavailable fixtures, zero scores, a changed preview deadline, 429/503 retry and same-revision duplicate prevention are covered by offline tests. After selecting the intended production ref and getting a green validation run, dispatch using `-f mode=publish` for the real Private draft. Verify the five-scene MP4 and the Drive/YouTube receipt, then compare the Studio ID with a second run of the same commit and Gameweek. A reuse must say `already_uploaded`, preserve the video ID and avoid `videos.insert`.

Before a new `videos.insert`, the production job records intent in `FPL_VORTEX/DAY1_UPLOAD_JOURNAL` outside the synchronized output folder. The same season, preview GW and render revision will reuse a known Private video or block if a prior upload could have succeeded and ownership is ambiguous. If YouTube rejected a request and Studio confirms no corresponding upload or in-progress session exists, clear only that revision's stale intent file to retry. A cleanly verified different render revision remains intentionally eligible for its own Private draft. Google quotas, asset permission changes, 4K transcode completion, runner availability and provider changes require live evidence. A completed upload is checked by Video ID and Private status. YouTube may still be processing 4K.
