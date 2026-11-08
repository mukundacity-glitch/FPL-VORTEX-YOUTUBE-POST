# Scene 2 renderer integration — non-destructive handoff

This branch adds `vortex/day1_scene2_restore.py` and
`vortex/day1_scene2_runtime.js`. They **do not** replace
`1_final_day1.py`, the original HTML pitch, or the original `VXPlayerCard`.

## Timeline and narrative

1. Reuse the approved chapter and original GW results (historical snapshot).
2. Reveal the existing HTML football pitch and its **verified** formation slots.
3. Narrate each of the original starting 11, then the reserve GK and remaining
   substitutes in the original bench order.
4. During each player's spoken segment, the real `VXPlayerCard` appears on
   the **left**, with actual gameweek points exposed at their cue.
5. Only **after the spoken segment**, animate the same card into the original
   pitch/bench slot. It stays visible for the remainder of the review.
6. After all players, revisit captain and vice-captain (effective multiplier,
   chip state and vice substitution must be taken from the final picks).
7. Show original Gameweek dashboard, green-up/red-down rank movement, and
   verified completed transfers separately from possible future moves.
8. End with all 15 cards visible, then transition to Scene 3.
9. Keep existing Jackson, Evanilson, João Pedro and Calvert-Lewin content as
   distinct **future outlook** segments where those are already in Scene 2.
   Their forecast values must never replace GW9 retrospective points.

## Existing renderer hookup required

Use the verified original episode snapshot. Build the animation manifest by
calling `build_scene2_manifest(...)` with exactly 11 starters and four bench
players, their actual `slot` values, **15 measured narration cues**, the
historical Gameweek metrics and official score data. If any values are
unavailable, fail rather than generating invented roster identities.

The animation script expects three non-overlapping positioned host elements
inside the existing scene root:

- `data-vx-scene2-pitch`: wraps the original HTML football pitch, with the
  original player slots carrying `data-vx-slot="<saved original slot>"`.
- `data-vx-scene2-spotlight`: left Hero Card host.
- `data-vx-scene2-flight`: an overlay for the card moving into the pitch.

Optional hosts: `data-vx-scene2-name`, `data-vx-scene2-points`.

Load `vortex/day1_scene2_runtime.js` **after** original
`window.VXPlayerCard` setup:

```javascript
const review = VXScene2Review.mountScene2(sceneRoot, manifest, cardsByPlayerId);
// On every seek / Remotion frame update:
review.seek(frame / fps);
```

The existing `VXPlayerCard` asset payloads (portrait, club, stats,
typography, typography-fit hooks) must come from the same original snapshot.

**Important:** The manifest and runtime are not yet wired into the large
`1_final_day1.py` source. This branch is intentionally a WIP, and no
rendered MP4 or completed TTS output exists for these changes.

## Review checklist before production

- Confirm the 15-player roster and slot order against the official GW9 picks.
- Confirm captain, vice-captain, auto-subs, chips and **net** score arithmetic.
- Confirm original green/red rank-arrow definitions and source values.
- Confirm full data table columns and historical transfers.
- Verify Hero Card left slot does not overlap header/footer and its flight
  ends at the correct original formation position.
- Verify every narration cue matches the onscreen player and points.
- Validate seek determinism at arbitrary timestamps, not only sequential playback.
- Render 1920x1080 / 30 fps MP4 and inspect the actual output.
- Do not touch approved opening or Scene 3.

## Tests

```bash
python -m unittest tests.test_day1_scene2_restore -v
```

The test module uses synthetic data for **unit validation only**. No
synthetic data is authorized for the actual viewer-facing video.
