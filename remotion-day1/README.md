# Day 1 presentation renderer

The workflow passes the existing `day1_show.json` into `Day1Premium`. The renderer changes presentation only: all seven sections, their order, player records, evidence, verdicts, beat times, narration and word boundaries remain authoritative. The immutable notebook and data/decision builders are unchanged.

The landscape export is 3840 × 2160 at 24 fps. The same design adapts to the existing portrait Shorts. Animation is frame-driven; titles and cards dissolve over the existing 0.4-second transition. Bundled Inter and Barlow fonts load before frames are captured.

`vortex/day1_remotion.py` creates temporary input props, renders the picture, and muxes the existing fitted narration. The existing final sound mix, output folders and private upload policy remain in place. `DATA/day1_remotion_qa.json` records the original show's hash, section IDs, beat count and popup occurrences.

## Footer popup

The Day 1 workflow restores the exact `popup.mp4` from the established Drive asset folder alongside the current audio assets. It is required before production starts. The actual file is copied without modification into temporary render assets and its SHA-256 is recorded.

Each occurrence restarts the clip at 2:00, 4:00 and every further two-minute boundary inside the original video. Playback uses its actual video-stream duration, capped at the next occurrence or the program end. It never inserts time or changes a slide. The clip stays inside the bottom footer below the captions, uses `contain` to retain its aspect ratio, and is muted so the existing narration and music mix stay intact. Shorts are shorter than two minutes and keep their portrait layout.

## Local use

```sh
cd remotion-day1
npm ci
npm run lint
npx remotion browser ensure
npm run dev -- --props=/absolute/path/to/remotion-props.json
```

The production adapter writes the props file to its scratch work directory. While previewing, keep the corresponding `public/runtime/<run-id>` media directory available. Runtime assets and outputs are ignored by Git and removed after a successful or failed render. No Google or YouTube credentials enter the Remotion bundle.

Run the existing Day 1 tests and the preservation/popup contracts from the repository root:

```sh
python -m unittest discover -s tests -p 'test_day1*.py' -v
```

A full production render needs the workflow's actual asset folder, official snapshot and fitted Ryan audio. Synthetic test frames are design and timing checks only; they are never substituted for production data or `popup.mp4`.

Remotion rendering references: [CLI render](https://www.remotion.dev/docs/cli/render), [Sequence](https://www.remotion.dev/docs/sequence), [Video](https://www.remotion.dev/docs/media/video).
