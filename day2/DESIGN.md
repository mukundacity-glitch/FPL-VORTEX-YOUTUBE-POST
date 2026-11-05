# FPL VORTEX — Day 2 Broadcast Design Contract

The Day 2 episode is a 4K FPL strategy analysis for managers optimizing rank. It is **not** a generic football news video. The visual's only job is to help the viewer identify the safer minutes, better upside, exposure risks and corresponding action.

## Art direction

Use an editorial broadcast aesthetic: midnight scoreboard ink, champagne-white headlines, restrained cyan data labels, and aged-gold Gameweek indicators. This intentionally softens the previous high-glow neon without sacrificing the brand's dark analysis setting.

| Token | Hex | Responsibility |
|---|---|---|
| Scoreboard ink | `#102233` | high-contrast label text on gold |
| Champagne-white | `#F9F8F2` | editorial headings |
| Cyan-soft | `#A8CED3` | secondary header labels |
| Cyan-quiet | `#C1D5D8` | subtitle reading text |
| Aged gold | `#D2AD62` | GW labels and decision moments |
| Gold-light | `#F8E7B7` | restrained highlight |

Display type is existing **Barlow Condensed Semibold**; smaller factual labels and narration copy use existing **Inter**. Type size and wrapping should be legible in the native 3840×2160 frame and scaled mobile previews.

## What must not be redesigned

The original Day 2 player cards, official club badges, portraits, fixtures, model values, animation keyframes, reveal timing, TTS voice and shared intro/outro media are owned by their existing notebook scenes. Styling here only targets page/brand header classes, subtitles and Gameweek indicators in `day2/visuals.py`. Avoid content-agnostic card overrides.

## Data and editorial behavior

Gameweek comes exclusively from the official FPL event marked `is_next`; if ambiguous, fail before any render. Player selections and rankings stay VORTEX model-led and dynamically retrieved, with every named recommendation tied to official FPL player IDs. AllAboutFPL supplies **separately attributed author opinions** from current, dated articles; it does not replace forecasts, override model filters, or become unattributed VORTEX advice.

The speaker sounds personally engaged and conversational: an original first-person Ryan script comments on what the author is considering, explains whether minutes/fixture/xPts support it, and states that forecasts are uncertain. Under no circumstances imply that an expert's chip decision applies to all managers.

The video's private title and description carry the verified target GW and model-selected player shortlist. Source URLs appear only when a recent, same-GW author comment is incorporated. No old hard-coded GW10 advice can be reused for future Gameweeks.

## Release verification

Run `tests/test_day2_editorial_release.py` and the Day 2 logo QA, confirm original player-card output by a full video render, inspect scene screenshots and live audio sync, and confirm private-only YouTube upload before calling the episode production-ready. A passing parser test is not proof of a finished video.
