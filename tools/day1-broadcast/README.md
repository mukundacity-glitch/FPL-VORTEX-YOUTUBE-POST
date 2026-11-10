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

## Scene 05 — data-driven Value Board (new)

The optional premium renderer is `ValueBoard.jsx` with `value-board.css`.
It follows the reference pitch layout, keeps large one-fixture player cards,
right-hand fixture radar and five-GW forecast figures, and uses the episode's
original crest and the FPL VORTEX channel-name rail. All player and fixture
numbers come from the supplied payload, never the design mock-up.

To enable the new board, pass a `04_value_board` source report with a matching
`value_board` property generated from the existing 15-player squad optimiser
using `vortex.day1_value_board.build_value_board`. The report must also point
to a freshly rendered narrated `scene-5.mp4` clip: the native board replaces
its old video frames but explicitly keeps its audio track. If no board payload
is supplied, the old media plays as-is; it is not silently discarded.

This is a **renderer component and manifest contract**, not proof that the
canonical 33-cell Day 1 producer currently emits Scene 05. The producer must
supply its live squad, forecasts, original logo, source report and measured
narration cue data before a five-scene premium master is possible. Do not
publish or label a run as five scenes unless the final scene manifest lists
all five. No media files or previously approved scenes are deleted by this UI
change.
