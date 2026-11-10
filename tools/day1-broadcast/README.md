# FPL VORTEX Day 1 broadcast treatment

The Day 1 GitHub workflow installs the renderer, then runs the existing scene
pipeline. Assembly builds a new rail manifest from the freshly rendered clips,
the verified review and planning gameweeks, and the original channel logo.
The animation, narration and analytical panels come from the native scene
exports. A stale or provisional review blocks the premium master.

For local Studio playback, place the four source exports in
`public/scene-1.mp4` through `public/scene-4.mp4`. Place a generated manifest
from the same episode in `public/scenes.json`. The Studio timeline uses 30 fps,
so a Studio-only manifest should use frame counts measured at 30 fps. The
production assembler calculates frame counts at its configured output fps.

Run `npm ci` and `npm run studio` and select **Day1Broadcast**. Use
`npx remotion render index.jsx Day1Broadcast FPL_VORTEX_Day1.mp4` for a local
export. **BroadcastRails** previews the shared framing. Geometry defaults are
presentation settings in `vortex/day1_broadcast.py`.
