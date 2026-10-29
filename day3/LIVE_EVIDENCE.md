# Day 3 live evidence and narration

The GitHub runner applies `evidence_pipeline.patch_evidence_pipeline` after the
existing presentation patches. The production Drive notebook remains the media
template; its old DEFCON narration function and archived-role minutes branch are
replaced before any cell executes.

## Data contract

Each run uses one fresh canonical official FPL bootstrap/fixture snapshot and
fresh official event-live responses for every completed current-season Gameweek.
Player IDs and fixture IDs are the join keys. Bootstrap season minutes and DC
must reconcile with event history. A player name is never a join key.

Current-club join dates and observed fixtures bound the recent playing-time
sample. Playing-time estimates use up to six completed current-club fixtures,
with recency weights of 0.85 per earlier fixture. Official status and next-round
playing chance adjust that estimate. These are modelling assumptions, not
confirmed future lineups. Current-season model-input refresh failures now stop
the run instead of feeding retained current-season files into narration.

Missing and contradictory availability is rejected. A blank is established from
the official fixture allocation; a missing model row is not a blank. Missing
rates and missing forecasts are never displayed as a real zero. Genuine zeros
retain an evidence-based reason, including confirmed unavailability, a blank,
no recent appearances, or an observed zero action rate. The script does not
infer an injury or a tactical explanation from the number zero.

DC expectation is current-season actions per 90 times expected fixture minutes.
The threshold-award probability uses a Poisson action model integrated over the
minutes distribution, with a maximum of two points per fixture. Doubles sum
fixture forecasts and awards separately. These independent estimates are not
official FPL predictions and are not claimed to be calibrated probabilities.
The verified scoring reference is linked in `live_evidence.RULE_SOURCE`.

Team DC ranks describe workload. Narration separately discusses actual goals
conceded, actual clean sheets and, when available from the same-run fixture
model, estimated clean-sheet probability. All current clubs are narrated.
The existing five-card and team-board animation anchors remain compatible.
No injury, coaching, tactical, xGC or press-conference claim is manufactured
when its source is unavailable. Official FPL news is attributed as such;
independently checked press-conference coverage is not claimed.

## Publication contract

The runner seals all selected, exact TTS narration exports and the final combined
video after the last notebook cell. It exports `Day3_Complete_Narration.txt`,
`day3_live_evidence.json` and `day3_script_evidence.json` beside the slide scripts.
The workflow runs `python -m day3.verify_evidence --output-root ...` before the
existing private YouTube upload.

Verification requires the same implementation version, workflow run, planning
Gameweek, source fingerprint, script contents and video SHA-256. It re-fetches
official availability, identity and fixture evidence. Changed material evidence,
an API outage, a passed planning deadline or a snapshot older than six hours
stops upload and requires regeneration. Six hours is an explicit freshness
ceiling; the material-change check still runs inside that window.

All other workflows, rendering geometry, Ryan voice profiles, transition-title
patches and popup bell mixing remain in place.

## Verification

Run `python -m unittest discover -s day3 -p 'test_*.py' -v`, then validate the
actual downloaded production notebook with `day3/run_notebook.py --validate-only`.
The regression suite covers blanks and doubles, missing forecasts, bad joins,
duplicate names and IDs, official history reconciliation, position/club changes,
confirmed and uncertain availability, minutes/distribution arithmetic, misleading
team-workload conclusions and stale or changed publication artifacts.
