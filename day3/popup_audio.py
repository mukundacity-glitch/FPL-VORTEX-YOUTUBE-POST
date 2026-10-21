from __future__ import annotations

import math
from collections.abc import Mapping, Sequence


def popup_audio_filters(
    input_index: int,
    occurrences: Sequence[Mapping[str, object]],
    duration: float,
    has_audio: bool,
) -> list[str]:
    if not has_audio or not occurrences:
        return ["[a_without_popup]anull[a_master]"]
    duration = float(duration)
    starts = [float(occurrence["start"]) for occurrence in occurrences]
    if input_index < 0 or not math.isfinite(duration) or duration <= 0:
        raise ValueError("Popup input index and duration must be valid")
    if any(not math.isfinite(start) or start < 0 for start in starts):
        raise ValueError("Popup start times must be finite and nonnegative")
    filters = [
        f"[{input_index}:a:0]aresample=48000:async=1:first_pts=0,"
        "aformat=channel_layouts=stereo,"
        f"atrim=duration={duration:.6f},asetpts=PTS-STARTPTS[popup_audio]"
    ]
    labels = [f"popup_audio_raw{index}" for index in range(len(starts))]
    if len(starts) > 1:
        filters.append(
            f"[popup_audio]asplit={len(starts)}" + "".join(f"[{label}]" for label in labels)
        )
    else:
        labels = ["popup_audio"]
    for index, (label, start) in enumerate(zip(labels, starts)):
        delay_samples = round(start * 48000)
        filters.append(
            f"[{label}]adelay={delay_samples}S:all=1[popup_chime{index}]"
        )
    chimes = "".join(f"[popup_chime{index}]" for index in range(len(starts)))
    filters.append(
        f"[a_without_popup]{chimes}amix=inputs={len(starts) + 1}:"
        "duration=first:dropout_transition=0:normalize=0,"
        "alimiter=limit=0.98:latency=1[a_master]"
    )
    return filters


def patch_popup_audio_source(source: str) -> str:
    replacements = (
        (
            '    ASSEMBLER_VERSION = "VX21-PRODUCTION-PACKAGING-V10-NARRATION-PACING-TITLE-FIT-V1"',
            '    ASSEMBLER_VERSION = "VX21-PRODUCTION-PACKAGING-V11-NARRATION-TITLE-FIT-POPUP-AUDIO"',
        ),
        (
            '                    "alimiter=limit=0.98[a_master]"\n                )',
            '                    "alimiter=limit=0.98[a_without_popup]"\n                )\n'
            '                from day3.popup_audio import popup_audio_filters\n'
            '                filters.extend(popup_audio_filters(\n'
            '                    _popup_input_index, POPUP_OCCURRENCES, POPUP_DISPLAY_SECONDS,\n'
            '                    bool(_production_assets["popup"]["has_audio"]),\n'
            '                ))',
        ),
    )
    for old, new in replacements:
        if source.count(old) != 1:
            raise RuntimeError("Popup audio: production assembly source contract changed")
        source = source.replace(old, new, 1)
    return source
