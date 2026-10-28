"""Speech-first sound mix: continuous bed, one impact, and no pre-hook bumper."""
from __future__ import annotations

import json
import math
import os
import shutil
import struct
import tempfile
import wave
from pathlib import Path

from .day1_media import (_duration, _fps, _probe, _required_file, _run,
                         _sha256, _stream, _write_json_atomic)


def _impact(path):
    rate = 48000
    samples = []
    for i in range(int(rate * .16)):
        t = i / rate
        envelope = min(1, t / .008) * math.exp(-32 * t)
        signal = .13 * envelope * (math.sin(2 * math.pi * 84 * t) + .25 * math.sin(2 * math.pi * 168 * t))
        samples.append(struct.pack('<h', round(signal * 32767)))
    with wave.open(str(path), 'wb') as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b''.join(samples))


def sound_graph(duration, impact_at):
    length = f'{duration:.9f}'
    fmt = 'aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo'
    delay = round(impact_at * 1000)
    return ';'.join([
        f'[0:a]{fmt},loudnorm=I=-18:LRA=7:TP=-1.5,aresample=48000:async=1:first_pts=0,'
        f'apad=whole_dur={length},atrim=duration={length},asplit=2[voice][detector]',
        f'[1:a]{fmt},loudnorm=I=-32:LRA=7:TP=-2,aresample=48000,'
        f'atrim=duration={length},afade=t=in:st=0:d=0.8,'
        f'afade=t=out:st={max(0,duration-1.5):.9f}:d=1.5[bed]',
        '[bed][detector]sidechaincompress=threshold=0.04:ratio=3:attack=30:release=350:'
        'detection=rms:link=maximum:makeup=1:mix=1[ducked]',
        f'[2:a]{fmt},volume=0.3,adelay={delay}:all=1[impact]',
        f'[voice][ducked][impact]amix=inputs=3:duration=first:normalize=0,'
        f'alimiter=limit=0.891251:level=0,aresample=48000:async=1:first_pts=0,'
        f'apad=whole_dur={length},atrim=duration={length}[audio]',
    ])


def integrate_show_media(root, asset_dir, qa, final_mp4, combined_mp3):
    show = json.loads((root / 'DATA/day1_show.json').read_text())
    probe = _probe(final_mp4)
    video = _stream(probe, 'video')
    duration = _duration(probe)
    if not 240 <= duration <= 360 or abs(duration - show['duration']) > .15:
        raise RuntimeError('Premium show must keep its four-to-six-minute spoken timeline')
    impact_at = float(show['impact_at'])
    if not 0 <= impact_at < 15:
        raise RuntimeError('Captain reveal impact must be tied to a word inside the hook')
    music = _required_file(asset_dir / 'Background_music.mp3')
    original_hash = _sha256(final_mp4)
    work = Path(tempfile.mkdtemp(prefix='day1-show-sound-'))
    try:
        impact = work / 'soft-impact.wav'
        _impact(impact)
        staged = work / 'program.mp4'
        _run(['ffmpeg', '-y', '-v', 'error', '-i', str(final_mp4), '-stream_loop', '-1',
              '-i', str(music), '-i', str(impact), '-filter_complex', sound_graph(duration, impact_at),
              '-map', '0:v:0', '-map', '[audio]', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k',
              '-ar', '48000', '-ac', '2', '-t', f'{duration:.9f}', '-movflags', '+faststart', str(staged)])
        mixed = _probe(staged)
        mixed_video = _stream(mixed, 'video')
        _stream(mixed, 'audio')
        if (mixed_video['width'], mixed_video['height']) != (video['width'], video['height']):
            raise RuntimeError('Premium sound mix changed the video dimensions')
        if abs(float(_fps(mixed_video)) - float(_fps(video))) > .001 or abs(_duration(mixed) - duration) > .15:
            raise RuntimeError('Premium sound mix changed the picture timing')
        mp3 = work / 'program.mp3'
        _run(['ffmpeg', '-y', '-v', 'error', '-i', str(staged), '-vn', '-c:a', 'libmp3lame',
              '-b:a', '192k', '-ar', '48000', str(mp3)])
        for source, target in ((staged, final_mp4), (mp3, combined_mp3)):
            temporary = target.with_name(f'.{target.stem}.uploading{target.suffix}')
            shutil.copy2(source, temporary)
            os.replace(temporary, target)
    finally:
        shutil.rmtree(work)
    report = {'applied': True, 'version': 'DAY1-PREMIUM-SPEECH-FIRST-V1',
              'opening': {'duration': 0, 'omitted_for_immediate_spoken_hook': True},
              'background_music': {'name': music.name, 'timeline_start': 0, 'timeline_end': duration,
                                   'target_lufs': -32, 'sha256': _sha256(music)},
              'impact': {'count': 1, 'at': impact_at, 'source': 'locally synthesized soft impact'},
              'voice_target_lufs': -18, 'ducking': True, 'video_reencoded': False,
              'original_program_sha256': original_hash, 'final_sha256': _sha256(final_mp4),
              'final_duration': _duration(_probe(final_mp4)), 'final_file': str(final_mp4),
              'combined_mp3': str(combined_mp3)}
    qa.update({'external_media_integration': report, 'final_duration': report['final_duration'],
               'combined_mp3_duration': _duration(_probe(combined_mp3)),
               'assembly_mode': 'DECISION SHOW + SPEECH-FIRST SOUND', 'premium_show': True})
    _write_json_atomic(root / 'DATA/day1_media_qa.json', report)
    _write_json_atomic(root / 'DATA/final_video_qa.json', qa)
    print('Decision show sound: immediate hook, continuous quiet music, one word-timed impact — PASS')
    return report
