# Day 3 workflow incident, 23 November 2026

## Run #152 and its previous success

[Day 3 #152](https://github.com/mukundacity-glitch/FPL-VORTEX-YOUTUBE-POST/actions/runs/40880508465) was a scheduled run on commit `37c391b1b4bed95ae5b1a6b3872ebff16a9695d0`, started at 13:17:02 UTC (19:02:02 Nepal time) on 29 October. Job `Refresh OUT dropdowns from FPL` succeeded. Job `Run final Day 3` was skipped. There is no failed step, HTTP error, traceback or nonzero step exit in #152. The log says `Day 3 OUT choices: entry 145784, GW8, digest 03d89ca2ddcd11b1, changed=False` and verified 15 choices per OUT input.

[Day 3 #151](https://github.com/mukundacity-glitch/FPL-VORTEX-YOUTUBE-POST/actions/runs/40826436541), the previous scheduled success, used the same commit, `ubuntu-24.04` image `20261025.353.1`, runner `2.338.0`, Python `3.12.15`, checkout/setup-python v7, identical GW8 and the same digest. Neither run exercised rendering or YouTube. The present workflow has manual dispatch only. The change to the old schedule predates this patch.

## Confirmed production failures and fixes

[Day 3 #166](https://github.com/mukundacity-glitch/FPL-VORTEX-YOUTUBE-POST/actions/runs/44726710898/job/136255860063#step:20:1), the latest failed production run, was manually dispatched on `4b3c3b9496855839b366f93a3e09c427a8ebdbaf` at 11:19:52 UTC on 20 November (17:04:52 Nepal time). `Run final Day 3` ran on Ubuntu 24.04 `20261116.133.1`, runner `2.338.2`, Python `3.12.16`. It captured FPL evidence for the GW11 preview at 11:29:10 UTC, then rendered successfully. `Verify Day 3 render evidence`, step 20, failed nearly two hours later at 13:27:14 UTC, with exit code 1. Upload was skipped.

```text
Traceback (most recent call last):
  File "<frozen runpy>", line 198, in _run_module_as_main
  File "<frozen runpy>", line 88, in _run_code
  File "/home/runner/work/FPL-VORTEX-YOUTUBE-POST/FPL-VORTEX-YOUTUBE-POST/day3/verify_evidence.py", line 79, in <module>
    main()
  File "/home/runner/work/FPL-VORTEX-YOUTUBE-POST/FPL-VORTEX-YOUTUBE-POST/day3/verify_evidence.py", line 75, in main
    verify_bundle(arguments.output_root.resolve())
  File "/home/runner/work/FPL-VORTEX-YOUTUBE-POST/FPL-VORTEX-YOUTUBE-POST/day3/verify_evidence.py", line 67, in verify_bundle
    assert_snapshot_current(snapshot, loader)
  File "/home/runner/work/FPL-VORTEX-YOUTUBE-POST/FPL-VORTEX-YOUTUBE-POST/day3/live_evidence.py", line 506, in assert_snapshot_current
    raise RuntimeError("Official availability, identity or fixture evidence changed; regenerate before upload")
RuntimeError: Official availability, identity or fixture evidence changed; regenerate before upload
##[error]Process completed with exit code 1.
```

The exception is reached only after both live requests returned parseable data and the aggregate source checksum mismatched. It is a publication safety guard, with no HTTP error attached. The historical log contains no field-level diff or raw responses and #166 has no artifact. The specific changed player, event or fixture field cannot be recovered from the recorded evidence. Warnings about missing archive lineup CSVs and incomplete top-10K standings did not stop the notebook.

The verifier now distinguishes a changed FPL source with the same preview target from a changed deadline, expired evidence, altered files or network/JSON failures. A confirmed checksum mismatch with the same target clears the runner's Day 3 output and renderer work directories, starts a new notebook process and runs the full gate once more. It requires the original Gameweek and deadline and rechecks current FPL, scripts and MP4. A second mismatch is a hard failure. The workflow archives the diagnostic log on render or verification failure. It only uploads or syncs final video after successful verification.

[Day 3 #163](https://github.com/mukundacity-glitch/FPL-VORTEX-YOUTUBE-POST/actions/runs/44523566184/job/135558141245#step:6:1) failed earlier in `Install system dependencies`, exit 100, when Ubuntu package downloads returned `503 Service Unavailable`. That separate failure now gets APT download retries and network timeouts. An exhausted index refresh fails before installation.

[Day 3 #153](https://github.com/mukundacity-glitch/FPL-VORTEX-YOUTUBE-POST/actions/runs/41835969560/job/126594828742#step:13:1), the first failed production dispatch after #152, stopped at `Restore and validate Day 3 production assets`, exit 1, with `Required production assets missing from Drive: outro.mp4 popup.mp4`. That was a shell asset validation failure. The logs contain no accompanying Drive HTTP error. Current production logs #165 and #166 both passed that step. Removing the required asset check would permit incomplete renders, so it remains enforced.

[Day 3 #165](https://github.com/mukundacity-glitch/FPL-VORTEX-YOUTUBE-POST/actions/runs/44654488252/job/136017249308#step:21:1) passed the render check and failed in the publisher before it made a YouTube request, with `ModuleNotFoundError: No module named 'vortex'`. Main already has the direct-invocation import fix in `4b3c3b9` and the regression test passes. #162 and #164 stopped earlier in notebook narration preflight (full-word and exact-sync, respectively). #165 and #166 advanced beyond those points.

## Last full production success

[Day 3 #148](https://github.com/mukundacity-glitch/FPL-VORTEX-YOUTUBE-POST/actions/runs/40617247753) was the newest successful production dispatch in the retrieved history. It rendered and uploaded a private draft for the GW9 preview from `5cbdc3eec39b2acc6d6bd5fb6f50e6c8f5cd244a`, runner `2.338.0`, Ubuntu image `20261012.334.1`, Python `3.12.15`. #166 exercised the GW11 preview. Both installed pandas `2.3.3`, requests `2.34.2`, Edge TTS `7.2.8` and PyArrow `20.0.0`. NumPy moved from `2.5.4` to `2.5.5`, Playwright from `1.64.1` to `1.65.2`, the Google API client from `2.201.0` to `2.202.0` and google-auth from `2.62.0` to `2.62.2`. These changes did not stop setup or rendering in #166. The latest workflow also includes later evidence/transfer-preview changes and a render-only mode. [Complete code comparison](https://github.com/mukundacity-glitch/FPL-VORTEX-YOUTUBE-POST/compare/5cbdc3eec39b2acc6d6bd5fb6f50e6c8f5cd244a...4b3c3b9496855839b366f93a3e09c427a8ebdbaf)

Checkout, runtime setup, the credential presence check, Google Drive OAuth/read access, notebook restore and the production paths all passed in #166. YouTube auth, channel access and quota were not exercised. Actual secret values and change history are not available from the job logs. The patch preserves the manual trigger, UTC FPL deadline interpretation, one-at-a-time workflow concurrency, read-only GitHub token permission, existing Drive destination and private YouTube publishing.

## Validation

Run the regression tests and workflow syntax check:

```bash
python -m unittest discover -s day3 -p 'test_*.py'
actionlint .github/workflows/day-3.yml
```

The tests cover one rerender, repeat drift, a rescheduled deadline, stale sources, HTTP/network errors and integrity failures. Once FPL marks prior fixtures final, use the existing render-only mode on the repair branch:

```bash
repo=mukundacity-glitch/FPL-VORTEX-YOUTUBE-POST
gh workflow run day-3.yml -R "$repo" --ref fix/day3-render-evidence -f render_only=true -f plan=ROLL
gh run list -R "$repo" --workflow day-3.yml --branch fix/day3-render-evidence --limit 5
```

Verify that `Verify Day 3 render evidence` succeeds, the MP4 artifact exists, and the YouTube and Drive sync steps are skipped in render-only mode. A separately dispatched production run with `render_only=false` can then verify the private draft and thumbnail. At investigation time, the official API still reported nine started GW11 fixtures as provisional, which makes the existing production evidence reader wait. There was no production upload during this investigation.
