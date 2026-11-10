# FPL VORTEX — The Gameweek Brief

Scope: the Day 1 opening and its responsive inspection page. The existing
V6.0 player-card component and other days keep their established visual identity.

Audience: FPL managers reviewing a result before making the next decision.
The opening should identify the programme, set expectations and reach the
presenter’s actual review within 35–40 seconds.

## Runtime tokens

`vortex/day1_brief.html` owns the CSS variables used by this opening:

| Token | Value | Purpose |
| --- | --- | --- |
| night | #100d20 | Midnight purple broadcast background |
| black | #07070d | Review background |
| panel | #191629 | Agenda surface |
| line | #343044 | Restrained separators |
| cyan | #70e0ee | Active agenda / navigation |
| white | #f6f5fa | Primary copy |
| muted | #bbb6cb | Secondary copy |
| green | #a7e9b8 | Positive signals only |
| amber | #f1c487 | Source status / caution |

Display: Arial Narrow / Liberation Sans Narrow, deliberately condensed programme
title. Body: Open Sans / Arial. Utility: monospace for Gameweeks and source stamps.
No remotely hosted font is required to render a valid episode.

## Composition and behaviour

One wide review card above four compact agenda cards ties the episode to its
central purpose. Cyan indicates the topic being spoken, not a prediction.
The source stamp remains distinct from the generation time. Each datum retains
its original endpoint timestamp; source-less fields cannot say verified.

Motion is deterministic, driven by measured Ryan word boundaries. The final
transition reveals the actual current review HTML at its first frame. The existing
renderer captures caption boundaries and transition frames as well as entrances.
No second opening video is prepended. Reduced motion disables interactive playback
and takes the viewer directly to the review. Keyboard users can activate agenda
buttons and reach the review; all statuses include text.

## Day 1 episode presentation

The broadcast framing in `tools/day1-broadcast` uses a 1920×1080 design grid.
Across Scenes 1–4, match the reference proportions with a 97 px header and
86 px social footer, a violet rim, midnight plum surfaces, white titles and
gold gameweek badges. Keep social marks at 54 px high and the YouTube mark
wider to preserve its shape. Use one short violet sweep at each scene entrance.
The underlying scene sequence, metric colours and narration timing belong to
the approved source exports.
