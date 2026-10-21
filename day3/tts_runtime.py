from __future__ import annotations

import ast
import asyncio
import math
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable
from time import monotonic


def retry_after_seconds(error: Exception) -> float | None:
    headers = getattr(error, "headers", None)
    value = headers.get("Retry-After") if headers else None
    if value is None:
        return None
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        try:
            deadline = parsedate_to_datetime(str(value))
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=timezone.utc)
            seconds = (deadline - datetime.now(timezone.utc)).total_seconds()
        except (TypeError, ValueError, OverflowError):
            return None
    return max(0.0, seconds) if math.isfinite(seconds) else None


class RyanSpeechClient:
    def __init__(
        self, loader: Callable[[], Any], supports_boundary: Callable[[Any], bool]
    ) -> None:
        self.loader = loader
        self.supports_boundary = supports_boundary
        self.lock = asyncio.Lock()
        self.next_request_at = 0.0

    async def synthesize(
        self, text: str, voice: str, profile: dict[str, str], attempts: int = 3
    ) -> tuple[bytes, list[dict[str, Any]]]:
        if not str(text).strip() or attempts < 1:
            raise ValueError("Narration needs non-empty text and at least one attempt")
        kwargs = {name: str(profile[name]) for name in ("rate", "pitch", "volume")}
        module = self.loader()
        if self.supports_boundary(module):
            kwargs["boundary"] = "WordBoundary"

        # Hold the gate during cooldown so other scenes cannot bypass a 429 response.
        async with self.lock:
            transient_failures = 0
            rate_limit_failures = 0
            while True:
                remaining = self.next_request_at - monotonic()
                if remaining > 0:
                    await asyncio.sleep(remaining)
                audio = bytearray()
                words: list[dict[str, Any]] = []
                try:
                    communicate = module.Communicate(str(text), voice, **kwargs)
                    async for chunk in communicate.stream():
                        if chunk.get("type") == "audio":
                            audio.extend(chunk.get("data", b""))
                        elif chunk.get("type") == "WordBoundary":
                            words.append({
                                "text": str(chunk.get("text", "")),
                                "start": float(chunk.get("offset", 0)) / 10_000_000,
                                "duration": float(chunk.get("duration", 0)) / 10_000_000,
                            })
                    if not audio or not words:
                        raise RuntimeError(
                            f"empty TTS payload (audio_bytes={len(audio)}, word_boundaries={len(words)})"
                        )
                    return bytes(audio), words
                except Exception as error:
                    status = getattr(error, "status", None)
                    if status == 429:
                        rate_limit_failures += 1
                        delay = max(
                            min(180.0, 15.0 * 2 ** (rate_limit_failures - 1)),
                            retry_after_seconds(error) or 0.0,
                        )
                        self.next_request_at = monotonic() + delay
                        if rate_limit_failures >= 6 or delay > 300:
                            raise RuntimeError(
                                "Ryan TTS rate limit persists; narration stopped without substituting audio"
                            ) from error
                        print(f"⚠️ Ryan TTS HTTP 429: cooldown {delay:.1f}s ({rate_limit_failures}/5)")
                    else:
                        transient_failures += 1
                        if transient_failures >= attempts:
                            raise RuntimeError(
                                f"Ryan TTS failed after {attempts} attempts: {type(error).__name__}"
                            ) from error
                        self.next_request_at = monotonic() + 1.5 * transient_failures
                finally:
                    self.next_request_at = max(self.next_request_at, monotonic() + 1.0)


def patch_tts_runtime_source(source: str) -> str:
    functions = [
        node for node in ast.parse(source).body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "vx_edge_tts_stream"
    ]
    if len(functions) != 1:
        raise RuntimeError("Ryan TTS patch expected exactly one vx_edge_tts_stream definition")
    function = functions[0]
    replacement = '''from day3.tts_runtime import RyanSpeechClient as _RyanSpeechClient
_vx_ryan_speech_client = _RyanSpeechClient(
    vx_load_edge_tts, _vx_edge_tts_supports_boundary_option
)

async def vx_edge_tts_stream(text, profile, attempts=3):
    return await _vx_ryan_speech_client.synthesize(text, VOICE, profile, attempts)
'''
    lines = source.splitlines(keepends=True)
    return "".join(lines[:function.lineno - 1]) + replacement + "".join(lines[function.end_lineno:])
