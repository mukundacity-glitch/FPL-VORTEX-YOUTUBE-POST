# FPL VORTEX Day 1 broadcast treatment

The Day 1 GitHub workflow installs the renderer, then runs the existing scene
pipeline. Assembly builds a new rail manifest from the freshly rendered clips,
the verified review and planning gameweeks, and the original channel logo.
The animation, narration and analytical panels come from the native scene
exports. A stale or provisional review blocks the premium master.

For local Studio playback, place the actual episode source exports in
`public/scene-1.mp4` through `public/scene-5.mp4` when all five are produced. Place a generated manifest
from the same episode in `public/scenes.json`. The Studio timeline uses 30 fps,
so a Studio-only manifest should use frame counts measured at 30 fps. The
production assembler calculates frame counts at its configured output fps.

Run `npm ci` and `npm run studio` and select **Day1Broadcast**. Use
`npx remotion render index.jsx Day1Broadcast FPL_VORTEX_Day1.mp4` for a local
export. **BroadcastRails** previews the shared framing. Geometry defaults are
presentation settings in `vortex/day1_broadcast.py`.

## Scene 05 — live optimized Value Board

The canonical `.github/workflows/day-1.yml` run now invokes
`python -m vortex.day1_value_render` immediately after all 33 existing
Day 1 cells have produced their four-scene current-gameweek program, but
before the approved music/outro integration.

The live data path is official FPL `bootstrap-static`, `fixtures` and
player `element-summary` history. `vortex/day1_value_live.py` weighs
FPL form, season points, injury flags, recent minutes, upcoming FDR,
market transfers and ownership; a constrained MILP selects exactly
2 GK / 5 DEF / 5 MID / 3 FWD, max three per club, under £100m.
Forecasts are **VORTEX research estimates**, not official future points.

`vortex/day1_value_board.py` builds the legal starting XI, captain,
vice-captain and bench sequence for **each** of the next five GWs.
`ValueBoard.jsx` swaps the green-pitch XI on Ryan's narrated GW cues.
The right rail shows the next fixture list, five weekly projections and
the highest-owned selected players with net market movement. The
original FPL VORTEX channel crest and name remain in the header, with
the four social handles in the footer.

`vortex/day1_value_render.py` preserves original Scenes 01–04 and
renders a real fifth scene with natural Ryan audio. It verifies GW
consistency with the finalized review, image dimensions, timing,
budget, squad and MP4 decoding, then updates the current-run QA
manifest. Only the approved final Day 1 media mixer and **Private**
YouTube uploader may process the verified output.

A real freshly rendered MP4 requires a successful **manual** GitHub
Actions > **Day 1** run. This documentation does not assert that such
a run has already occurred. If the official FPL snapshot is invalid,
there is no legal squad, or a render fails, the workflow stops instead
of publishing a stale four-scene file.

The cleanup routine removes only the temporary
`tools/day1-broadcast/public/value-assets` cache between runs.
Existing original scene code, saved assets and day-2 pipelines remain.
