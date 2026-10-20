from __future__ import annotations

from array import array
import math
import sys


def compact_transfer_pcm(frames: bytes, words: list[dict], sample_rate: int = 48000):
    """Remove verified silence only; keep speech and remap the TTS word clock.

    PCM is mono signed 16-bit. Word spans and audible 10 ms blocks are protected.
    Long internal gaps retain 350 ms; each section edge retains up to 120 ms.
    """
    if sample_rate <= 0 or len(frames) % 2 or not words:
        raise ValueError("Transfer Desk requires mono PCM and word boundaries")
    samples = array("h")
    samples.frombytes(frames)
    if sys.byteorder != "little":
        samples.byteswap()
    total = len(samples)
    spans = []
    for word in words:
        start = float(word["start"])
        duration = float(word.get("duration", 0.0))
        if not math.isfinite(start + duration) or start < 0 or duration < 0:
            raise ValueError("Invalid Transfer Desk word boundary")
        spans.append((round(start * sample_rate), round((start + duration) * sample_rate)))
    if any(left[0] > right[0] for left, right in zip(spans, spans[1:])):
        raise ValueError("Transfer Desk words must be chronological")
    if max(end for _, end in spans) > total + 1:
        raise ValueError("Transfer Desk word clock exceeds decoded PCM")

    # Only the gaps outside word spans may be cut, even if quiet syllables fall
    # below the waveform threshold. Overlapping word spans remain protected.
    gaps = []
    cursor = 0
    for start, end in spans:
        if start > cursor:
            gaps.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < total:
        gaps.append((cursor, total))

    block = max(1, round(sample_rate * .01))
    quiet = []
    run_start = None
    for start in range(0, total, block):
        values = samples[start:start + block]
        silent = max(values, default=0) <= 32 and min(values, default=0) >= -32
        if silent and run_start is None:
            run_start = start
        if not silent and run_start is not None:
            quiet.append((run_start, start))
            run_start = None
    if run_start is not None:
        quiet.append((run_start, total))

    cuts = []
    guard = round(.12 * sample_rate)
    for quiet_start, quiet_end in quiet:
        for gap_start, gap_end in gaps:
            start, end = max(quiet_start, gap_start), min(quiet_end, gap_end)
            if end <= start:
                continue
            if start == 0:
                cut = (start, end - guard)
            elif end == total:
                cut = (start + guard, end)
            elif end - start > sample_rate:
                keep = round(.35 * sample_rate)
                cut = (start + keep // 2, end - (keep - keep // 2))
            else:
                continue
            if cut[1] > cut[0]:
                cuts.append(cut)

    def remap(position):
        return position - sum(max(0, min(position, end) - start) for start, end in cuts)

    chunks = []
    cursor = 0
    for start, end in cuts:
        chunks.append(frames[cursor * 2:start * 2])
        cursor = end
    chunks.append(frames[cursor * 2:])
    shifted = []
    for word, (start, end) in zip(words, spans):
        updated = dict(word)
        updated["start"] = remap(start) / sample_rate
        updated["duration"] = (remap(end) - remap(start)) / sample_rate
        shifted.append(updated)
    return b"".join(chunks), shifted
