"""Measured speech and seekable HTML rendering for the two Day 1 sections."""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import shutil
import subprocess
import copy
from pathlib import Path

VOICE_TARGET_LUFS = -18.0
VOICE_TRUE_PEAK_DBTP = -1.5
MUSIC_BASE_LUFS = -28.0
MUSIC_TRUE_PEAK_DBTP = -2.0


def run(args):
    result = subprocess.run([str(a) for a in args], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"{args[0]} failed: {result.stderr[-4000:]}")
    return result.stdout


def probe(path):
    return json.loads(run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", path]))


def duration(path):
    return float(probe(path)["format"]["duration"])


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


class EditorialLimitError(RuntimeError):
    pass


def compact_roundup(package):
    """Optional assist-only mentions yield to the requested scores/cards/injury coverage."""
    result = copy.deepcopy(package)
    result["beats"] = [b for b in result["beats"] if not (
        b.get("facts") and set(b["facts"]) == {"assists"}
        or b.get("mentions") and all(set(m["facts"]) == {"assists"} for m in b["mentions"])
    )]
    result["compact_edition"] = True
    return result


def join_audio(beats, output):
    inputs, filters, labels = [], [], []
    for i, b in enumerate(beats):
        inputs += ["-i", b["audio"]]
        filters.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo,atrim=duration={b['t1']-b['t0']:.6f},adelay={round(b['t0']*1000)}:all=1[a{i}]")
        labels.append(f"[a{i}]")
    filters.append("".join(labels) + f"amix=inputs={len(labels)}:normalize=0:duration=longest,apad,atrim=duration={beats[-1]['t1']:.6f}[out]")
    run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(filters), "-map", "[out]", "-c:a", "libmp3lame", "-b:a", "192k", output])


async def speak_roundup(package, namespace, audio_dir, limit=180):
    audio_dir = Path(audio_dir)
    audio_dir.mkdir(parents=True, exist_ok=True)
    beats = package["beats"]
    # Conversational pace. A long edition is compacted as copy, never sped up or cut mid-sentence.
    for b in beats:
        b["text"] = namespace["vx_full_word_narration"](b["text"], context="Day 1 match roundup")
        if b.get("player_id"):
            b["spoken_name"] = namespace["vx_full_word_narration"](b["spoken_name"], context="roundup player")
        path = audio_dir / (b["id"] + ".mp3")
        metadata = path.with_suffix(".json")
        profile = {"rate": "+5%", "pitch": "+0Hz", "volume": "+0%"}
        signature = hashlib.sha256(json.dumps([b["text"], profile]).encode()).hexdigest()
        try:
            saved = json.loads(metadata.read_text())
            if saved["signature"] != signature or saved["sha256"] != sha(path):
                raise ValueError("Changed speech")
            words = saved["words"]
        except (OSError, ValueError, KeyError):
            audio, words = await namespace["vx_edge_tts_stream"](b["text"], profile)
            path.write_bytes(audio)
            metadata.write_text(json.dumps({"signature": signature, "words": words, "sha256": sha(path)}))
        if not words:
            raise RuntimeError("Speech returned no word boundaries")
        b.update(audio=str(path), words=words, duration=duration(path))
        b["name_time"] = namespace["vx_phrase_time"](words, b["spoken_name"], required=True, context=b["id"]) if b.get("player_id") else 0.0
        for mention in b.get("mentions", []):
            mention["spoken_name"] = namespace["vx_full_word_narration"](mention["spoken_name"], context="roundup player")
            mention["name_time"] = namespace["vx_phrase_time"](words, mention["spoken_name"], required=True, context=b["id"])
    cursor = 0.0
    for b in beats:
        b["t0"] = cursor
        spoken_end = max(w["start"] + w["duration"] for w in b["words"])
        # Trim only measured encoder silence. Keep the complete last word and natural gap.
        cursor += min(b["duration"], spoken_end + .16)
        b["t1"] = cursor
    package["duration"] = cursor
    if cursor > limit:
        raise EditorialLimitError(f"Match roundup is {cursor:.1f}s, exceeding the {limit}s editorial limit. No over-length video was published.")
    join_audio(beats, audio_dir.parent / "00_intro.mp3")
    return audio_dir.parent / "00_intro.mp3"


def frame_times(duration_seconds, fps, windows):
    """Full-rate motion windows, sparse holds; all timestamps lie on the output grid."""
    frames = math.ceil(duration_seconds * fps)
    indices = {0, frames - 1}
    indices.update(range(0, frames, max(1, fps)))
    for start, end in windows:
        indices.update(range(max(0, math.floor(start * fps)), min(frames, math.ceil(end * fps) + 1)))
    return sorted(i / fps for i in indices)


async def render(html, audio, output, seconds, width, height, fps, windows, preview, audit_times=()):
    from playwright.async_api import async_playwright
    output, preview = Path(output), Path(preview)
    folder = output.parent / ("." + output.stem + "-frames")
    folder.mkdir(parents=True, exist_ok=True)
    times = frame_times(seconds, fps, windows)
    grid_duration = math.ceil(seconds * fps) / fps
    errors = []
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
            page = await browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=1)
            page.on("pageerror", lambda e: errors.append(str(e)))
            await page.goto(Path(html).resolve().as_uri(), wait_until="load", timeout=60000)
            await page.add_style_tag(content=f"html,body{{width:{width}px!important;height:{height}px!important;display:block!important}} body>div.scene,body>#scaleShell{{transform:scale({width/3840})!important;transform-origin:0 0!important;margin:0!important}}")
            await page.evaluate("() => document.fonts.ready")
            await page.wait_for_function("window.__ready === true && typeof window.__seek === 'function'", timeout=60000)
            for t in audit_times:
                if await page.evaluate("typeof window.__auditLayout === 'function'"):
                    audit = await page.evaluate("t=>window.__auditLayout(t)", t)
                    if audit.get("violations"):
                        raise RuntimeError(f"Review layout failed: {audit['violations']}")
            lines = ["ffconcat version 1.0"]
            for i, t in enumerate(times):
                await page.evaluate("t=>window.__seek(t)", t)
                path = folder / f"{i:06d}.jpg"
                await page.screenshot(path=str(path), type="jpeg", quality=94, animations="disabled")
                end = times[i + 1] if i + 1 < len(times) else grid_duration
                lines.extend([f"file '{path.name}'", f"duration {end-t:.9f}"])
                if i % 200 == 0:
                    print(f"{output.stem}: frame {i+1}/{len(times)}", flush=True)
            lines.append(f"file '{len(times)-1:06d}.jpg'")
            await page.evaluate("t=>window.__seek(t)", min(seconds - .05, max(.5, seconds / 2)))
            await page.screenshot(path=str(preview), type="png")
            await browser.close()
        if errors:
            raise RuntimeError("Browser errors: " + "; ".join(errors))
        concat = folder / "frames.ffconcat"
        concat.write_text("\n".join(lines) + "\n")
        temporary = output.with_name("." + output.stem + ".encoding.mp4")
        run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", concat, "-i", audio, "-map", "0:v", "-map", "1:a", "-vf", f"fps={fps},format=yuv420p", "-af", "apad", "-t", f"{grid_duration:.6f}", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", "-movflags", "+faststart", temporary])
        info = probe(temporary)
        video = next(s for s in info["streams"] if s["codec_type"] == "video")
        if [video["width"], video["height"]] != [width, height] or abs(float(info["format"]["duration"]) - grid_duration) > .12:
            raise RuntimeError("Rendered video does not match the requested canvas or timing")
        temporary.replace(output)
        return {"duration": grid_duration, "file": str(output), "sampled_frames": len(times), "sha256": sha(output)}
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def assemble(sections, final, audio, asset_dir, qa_file, dimensions, fps, review_gw):
    """Join exactly two sections and apply the existing soft background/outro music."""
    final, audio, asset_dir = Path(final), Path(audio), Path(asset_dir)
    if [s["key"] for s in sections] != ["00_intro", "gw_review"]:
        raise ValueError("Day 1 must contain exactly intro, then Gameweek review")
    total = sum(s["duration"] for s in sections)
    manifest = final.with_suffix(".ffconcat")
    # Internal paths are generated by this program, not external filenames.
    manifest.write_text("ffconcat version 1.0\n" + "".join("file '" + str(Path(s["file"]).resolve()).replace("'", "'\\''") + "'\n" for s in sections))
    joined = final.with_name(".day1-joined.mp4")
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", manifest, "-c", "copy", joined])
    background, outro = asset_dir / "Background_music.mp3", asset_dir / "outro.mp3"
    for path in (background, outro):
        if not path.is_file():
            raise FileNotFoundError(path)
    tail = min(6.0, duration(outro))
    music_end = total - tail
    filters = (f"[0:a]loudnorm=I={VOICE_TARGET_LUFS}:TP={VOICE_TRUE_PEAK_DBTP}:LRA=11,aresample=48000,asplit=2[voice][side];"
               f"[1:a]loudnorm=I={MUSIC_BASE_LUFS}:TP={MUSIC_TRUE_PEAK_DBTP}:LRA=11,aresample=48000,atrim=duration={music_end:.6f},afade=t=in:d=1,afade=t=out:st={max(0,music_end-1):.6f}:d=1,apad=whole_dur={total:.6f}[bed];"
               "[bed][side]sidechaincompress=threshold=0.04:ratio=2.5:attack=30:release=350:makeup=1[duck];"
               f"[2:a]loudnorm=I={MUSIC_BASE_LUFS}:TP={MUSIC_TRUE_PEAK_DBTP}:LRA=11,aresample=48000,atrim=duration={tail:.6f},afade=t=in:d=0.4,afade=t=out:st={max(0,tail-.7):.6f}:d=0.7,adelay={round(music_end*1000)}:all=1[tail];"
               f"[voice][duck][tail]amix=inputs=3:normalize=0:duration=first,alimiter=limit=.95,atrim=duration={total:.6f}[out]")
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", joined, "-stream_loop", "-1", "-i", background, "-i", outro, "-filter_complex", filters, "-map", "0:v", "-map", "[out]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", "-t", f"{total:.6f}", "-movflags", "+faststart", final])
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", final, "-vn", "-c:a", "libmp3lame", "-b:a", "192k", audio])
    info = probe(final)
    actual = float(info["format"]["duration"])
    video = next(s for s in info["streams"] if s["codec_type"] == "video")
    sound = next(s for s in info["streams"] if s["codec_type"] == "audio")
    if abs(actual - total) > .15 or [video["width"], video["height"]] != list(dimensions) or abs(float(video.get("duration", actual))-float(sound.get("duration", actual))) > .15:
        raise RuntimeError("Final two-section video failed canvas/duration/audio alignment QA")
    qa = {"passed": True, "two_section_day1": True, "final_file": str(final), "combined_mp3": str(audio), "duration": actual, "video_output": list(dimensions), "fps": fps, "review_gw": review_gw, "scene_keys": [s["key"] for s in sections], "scene_count": 2, "sections": sections, "output_contract": {"passed": True}, "external_media_integration": {"applied": True, "opening": {"duration": 0}, "background_music": str(background), "outro_seconds": tail, "final_sha256": sha(final)}}
    Path(qa_file).write_text(json.dumps(qa, indent=2))
    manifest.unlink(missing_ok=True)
    joined.unlink(missing_ok=True)
    return qa
