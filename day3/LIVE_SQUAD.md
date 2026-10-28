# Live FPL squad: the single source of truth for Player OUT

Day 3 must plan transfers from the 15 players that are actually on the FPL
entry — not from a remembered list. Before this fix, the five `player_out_*`
dispatch inputs in `.github/workflows/day-3.yml` were a hardcoded snapshot of a
much older squad, and `FPL_ENTRY_ID` existed in the workflow env but was never
used by checked-in runner code. Even when the notebook's AUTO model resolved the
real squad, a MANUAL selection from a stale dropdown could put somebody else's
players on the transfer-plan slide.

## Public FPL API only

[`fpl_squad.py`](fpl_squad.py) resolves the squad from public endpoints; no
login, cookie, or session token is involved:

| Endpoint | Purpose |
| --- | --- |
| `/api/bootstrap-static/` | events (current / next Gameweek), player names, positions, clubs, prices |
| `/api/entry/<id>/history/` | chip usage, used to detect a Free Hit |
| `/api/entry/<id>/event/<gw>/picks/` | the submitted 15 for one Gameweek |

`/api/my-team/<id>/` is **not** used: without an FPL session it returns
`{"detail":"Authentication credentials were not provided."}`.

The resolver walks Gameweeks backwards from the current/next event until it
finds a published 15-player picks payload. A picks payload for a future
Gameweek normally returns `Not found.` and is skipped. If the visible squad was
played with a Free Hit chip (from `active_chip` or entry history), the resolver
keeps walking back to the last permanent 15 and records the skipped Gameweeks.
A picks payload that is not exactly 15 unique players is rejected. If bootstrap,
history, or every picks call fails, resolution raises `LiveSquadError`: there is
**no** cached, hardcoded, or "last known good" squad fallback.

`LiveSquad.choices` produces deterministic `ID | web_name | POS` strings sorted
by position and name. `squad_digest` is a short hash of the sorted 15 IDs.

## Three layers of enforcement

1. **Dispatch dropdowns are generated.** GitHub `workflow_dispatch` choice
   options are static YAML — the form cannot call an API when it opens.
   [`refresh_day3_choices.py`](refresh_day3_choices.py) rewrites all five OUT
   option lists from `LiveSquad.choices`.
   [`refresh-day3-choices.yml`](../.github/workflows/refresh-day3-choices.yml)
   runs it every three hours on the default branch and commits only when the 15
   players change, so the OUT choices the user sees are the live squad. It can
   also be dispatched manually with an optional entry ID. It never touches the
   IN lists, which are the full player pool rather than team-specific choices.

2. **Every run re-validates against the API.** The `Resolve live FPL squad and
   verify Player OUT picks` step in `day-3.yml` runs before system dependencies
   and the render. It resolves the squad, prints the 15, and for
   `TRANSFER — MANUAL` calls `validate_transfer_selections()`: every OUT ID must
   be in the live 15, every IN ID must not be, pairs must be 1–5 and unique. A
   stale choice fails with a message that includes the live 15 and a request to
   refresh the dropdowns. The step writes `$RUNNER_TEMP/day3-live-squad.json`
   and exports `DAY3_LIVE_SQUAD_JSON`, `DAY3_LIVE_SQUAD_GW` and
   `DAY3_LIVE_SQUAD_IDS` for the notebook run.

3. **The notebook is guarded end to end.** [`run_notebook.py`](run_notebook.py)
   patches three cells:

   - **Cell 1 (control):** `FPL_ID` is replaced with `FPL_ENTRY_ID` so the
     notebook and the workflow resolve the same entry. A live-squad contract is
     injected before `MY_PLAN_SCENARIOS`: it loads the workflow's snapshot
     (falling back to the live resolver for standalone runs), checks the entry
     ID matches, exports `DAY3_LIVE_SQUAD`, `DAY3_LIVE_SQUAD_IDS` and
     `DAY3_LIVE_SQUAD_GW`, and re-validates manual OUT/IN IDs against those 15.
   - **Cell 19 (Phase 11):** immediately before the squad feature merge, the
     runner asserts `phase11_current_squad_state` is exactly the live 15. This
     is the frame that becomes `SLIDE_CURRENT_SQUAD`, which feeds both the
     Transfer Desk HOLD/SELL cards and the video's 5A/5B base squad. A stale
     Drive `current_squad_state.json` or a resolver mismatch now fails the run
     instead of publishing another manager's team.
   - **Cell 30 (MY PLAN 5B):** inside the manual transfer branch, the runner
     asserts `SLIDE_CURRENT_SQUAD` is still the live 15, every OUT is owned and
     no IN is already owned — right before the scene builds its OUT/IN cards.

   For `TRANSFER — AUTO`, `ROLL` and `NEITHER`, the manual OUT/IN lists are
   ignored; the automatic engine's candidate pool still comes from the guarded
   live 15.

The `--validate-only` preflight compiles every patched cell, so a changed
notebook anchor fails before any render or upload.

## Running locally

```bash
python -m day3.fpl_squad --entry-id 145784
python -m day3.fpl_squad --entry-id 145784 --out-json /tmp/day3-live-squad.json
python -m day3.refresh_day3_choices --entry-id 145784 --dry-run
python -m unittest discover -s day3 -p 'test_*.py' -v
```

If `FPL_ENTRY_ID` changes, update it in `day-3.yml`'s workflow `env` and pass
`--entry-id` to the refresh workflow (or dispatch it with the new ID). The
notebook's `FPL_ID` is overridden from that env at run time, so no Drive
notebook edit is required.

No secret is read, printed, or stored by the resolver. Player IDs, names, clubs
and prices are public FPL data.
