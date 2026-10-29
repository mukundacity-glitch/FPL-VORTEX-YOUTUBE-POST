"""Presentation-only Remotion adapter for the existing Day 1 show contract.

The authoritative snapshot, sections, beats, speech and word times pass through
unchanged. Runtime media lives outside the published output folders.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import math
import os
import shutil
import uuid
from pathlib import Path

from .day1_media import _probe, _required_file, _run, _sha256, _stream
from .day1_short import _validate_results_video
from .day1_show import COLORS

PROJECT = Path(__file__).resolve().parents[1] / 'remotion-day1'
FPS = 24
POPUP_INTERVAL = 120


def show_digest(show):
    # The existing Shorts exporter appends output filenames after the master
    # render. Only those output annotations are outside the input contract.
    contract = copy.deepcopy(show)
    for short in contract.get('shorts', []):
        short.pop('file', None)
    return hashlib.sha256(json.dumps(contract, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def popup_schedule(duration, clip_duration):
    """Start on the final video's clock; never add a scene or extend its length."""
    if not math.isfinite(duration) or not math.isfinite(clip_duration) or min(duration, clip_duration) <= 0:
        raise ValueError('Invalid program or popup duration')
    return [{'start': float(at), 'duration': min(clip_duration, POPUP_INTERVAL, duration - at)}
            for at in range(POPUP_INTERVAL, math.ceil(duration), POPUP_INTERVAL)]


def prepare_props(show, stage, asset_dir, *, width, height, start=0, end=None, vertical=False):
    from .day1_show_render import _font_css

    end = float(show['duration']) if end is None else float(end)
    if not 0 <= start < end <= float(show['duration']):
        raise ValueError('Render range must stay inside the original Day 1 timeline')
    stage = Path(stage)
    stage.mkdir(parents=True, exist_ok=True)
    # Only a copy of the presentation data is serialized. No model or text rewrite.
    props = {'show': copy.deepcopy(show), 'start': start, 'end': end,
             'width': width, 'height': height, 'vertical': vertical,
             'fontCss': _font_css(), 'verdictColors': COLORS, 'popup': None}
    popup_report = {'interval_seconds': POPUP_INTERVAL, 'placement': 'bottom footer',
                    'muted': True, 'occurrences': []}
    if not vertical and end > POPUP_INTERVAL:
        popup = _required_file(Path(asset_dir) / 'popup.mp4')
        probe = _probe(popup)
        video = _stream(probe, 'video')
        clip_duration = float(video.get('duration') or probe.get('format', {}).get('duration') or 0)
        occurrences = popup_schedule(float(show['duration']), clip_duration)
        shutil.copyfile(popup, stage / 'popup.mp4')
        props['popup'] = {'src': f'runtime/{stage.name}/popup.mp4',
                          'duration': min(clip_duration, POPUP_INTERVAL),
                          'starts': [event['start'] for event in occurrences]}
        popup_report.update({'name': popup.name, 'sha256': _sha256(popup),
                             'source_duration': clip_duration, 'occurrences': occurrences})
    return props, popup_report


def remotion_command(action, output, props_file, *extra):
    command = [str(PROJECT / 'node_modules/.bin/remotion'), action, 'src/index.ts',
               'Day1Premium', str(Path(output).resolve()), f'--props={Path(props_file).resolve()}',
               '--log=error', *extra]
    browser = os.environ.get('REMOTION_BROWSER_EXECUTABLE')
    if browser:
        command.append(f'--browser-executable={browser}')
    return command


def _render(command):
    import subprocess
    try:
        subprocess.run(command, cwd=PROJECT, check=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError('Day 1 Remotion render failed; no legacy visual fallback was used') from exc


async def capture_show(show, work, audio, output, width=3840, height=2160,
                       start=0, end=None, vertical=False):
    work = Path(work).resolve()
    work.mkdir(parents=True, exist_ok=True)
    if not (PROJECT / 'node_modules/.bin/remotion').is_file():
        raise RuntimeError('Install the pinned Day 1 renderer with npm ci in remotion-day1')
    stage = PROJECT / 'public/runtime' / uuid.uuid4().hex
    asset_dir = Path(os.environ.get('DAY1_ASSET_DIR', '/content/drive/MyDrive/FPL_VORTEX/Assets'))
    baseline = json.dumps(show, sort_keys=True, ensure_ascii=False)
    try:
        # The same fitted audio feeds the existing FFmpeg mux. Check its metadata
        # before an expensive frame render; no re-encoding or new TTS provider.
        await asyncio.to_thread(_run, ['node', str(PROJECT / 'scripts/inspect-media.mjs'),
                                      str(Path(audio).resolve()), str(end or show['duration'])])
        props, popup_report = prepare_props(show, stage, asset_dir, width=width, height=height,
                                            start=start, end=end, vertical=vertical)
        props_file = work / 'remotion-props.json'
        props_file.write_text(json.dumps(props, ensure_ascii=False), encoding='utf-8')
        picture = work / 'picture.mp4'
        duration = math.ceil((props['end'] - start) * FPS - 1e-6) / FPS
        await asyncio.to_thread(_render, remotion_command('render', picture, props_file,
            '--codec=h264', '--crf=18', '--pixel-format=yuv420p', '--concurrency=2', '--muted'))
        _run(['ffmpeg', '-y', '-v', 'error', '-i', str(picture), '-ss', f'{start:.9f}',
              '-i', str(Path(audio).resolve()), '-map', '0:v:0', '-map', '1:a:0',
              '-c:v', 'copy', '-af', f'aresample=48000:async=1:first_pts=0,atrim=duration={props["end"]-start:.9f},apad',
              '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2',
              '-t', f'{duration:.9f}', '-movflags', '+faststart', str(output)])
        _validate_results_video(output, FPS, duration)
        still = work / 'first-frame.png'
        await asyncio.to_thread(_render, remotion_command('still', still, props_file, '--frame=0'))
        if json.dumps(show, sort_keys=True, ensure_ascii=False) != baseline:
            raise RuntimeError('Remotion changed the authoritative Day 1 presentation data')
        report = {'renderer': 'Remotion', 'fps': FPS, 'resolution': [width, height],
                  'data_and_slide_structure_preserved': True,
                  'show_sha256': show_digest(show),
                  'section_ids': [s['id'] for s in show['sections']],
                  'beat_count': len(show['beats']), 'start': start, 'end': props['end'],
                  'footer_popup': popup_report}
        (work / 'remotion-qa.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(f'Day 1 Remotion: {len(show["sections"])} unchanged sections; '
              f'{len(popup_report["occurrences"])} footer popups — PASS', flush=True)
        return [(0, still)]
    finally:
        shutil.rmtree(stage, ignore_errors=True)
