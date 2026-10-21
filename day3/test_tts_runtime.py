from __future__ import annotations

import asyncio
import types
import unittest
from unittest.mock import patch

from day3.tts_runtime import RyanSpeechClient, patch_tts_runtime_source, retry_after_seconds


class RateLimitError(Exception):
    status = 429

    def __init__(self, retry_after: str | None = None) -> None:
        super().__init__("rate limited")
        self.headers = {} if retry_after is None else {"Retry-After": retry_after}


class SpeechTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.clock = 100.0
        self.active = 0
        self.max_active = 0
        yield_once = asyncio.sleep
        self.waits: list[float] = []
        self.calls: list[tuple[str, str, dict[str, str]]] = []
        self.outcomes: list[Exception | None] = []
        test = self

        class Communicate:
            def __init__(self, text: str, voice: str, **kwargs: str) -> None:
                test.calls.append((text, voice, kwargs))

            async def stream(self):
                test.active += 1
                test.max_active = max(test.max_active, test.active)
                try:
                    await yield_once(0)
                finally:
                    test.active -= 1
                outcome = test.outcomes.pop(0) if test.outcomes else None
                yield {"type": "audio", "data": b"partial" if outcome else b"mp3"}
                if outcome:
                    raise outcome
                yield {"type": "WordBoundary", "text": "Hello", "offset": 5_000_000, "duration": 2_000_000}

        async def sleep(seconds: float) -> None:
            self.waits.append(seconds)
            self.clock += seconds

        self.enterContext(patch("day3.tts_runtime.monotonic", side_effect=lambda: self.clock))
        self.enterContext(patch("day3.tts_runtime.asyncio.sleep", side_effect=sleep))
        self.client = RyanSpeechClient(lambda: types.SimpleNamespace(Communicate=Communicate), lambda module: True)
        self.profile = {"rate": "+17%", "pitch": "-4Hz", "volume": "+0%"}

    async def speak(self):
        return await self.client.synthesize("Hello", "en-GB-RyanNeural", self.profile)

    async def test_429_recovers_after_more_than_original_three_attempts(self) -> None:
        self.outcomes = [RateLimitError() for _ in range(4)] + [None]
        audio, words = await self.speak()
        self.assertEqual(self.waits, [15, 30, 60, 120])
        self.assertEqual(audio, b"mp3")
        self.assertEqual(words, [{"text": "Hello", "start": 0.5, "duration": 0.2}])
        self.assertEqual(self.calls[-1][1], "en-GB-RyanNeural")
        self.assertEqual(self.calls[-1][2], dict(self.profile, boundary="WordBoundary"))

    async def test_retry_after_takes_precedence(self) -> None:
        self.outcomes = [RateLimitError("45"), None]
        await self.speak()
        self.assertEqual(self.waits, [45])

    async def test_persistent_429_stops_with_bounded_attempts(self) -> None:
        self.outcomes = [RateLimitError() for _ in range(6)]
        with self.assertRaisesRegex(RuntimeError, "rate limit persists"):
            await self.speak()
        self.assertEqual(self.waits, [15, 30, 60, 120, 180])
        self.assertEqual(len(self.calls), 6)

    async def test_excessive_retry_after_stops_instead_of_retrying_early(self) -> None:
        self.outcomes = [RateLimitError("3600")]
        with self.assertRaisesRegex(RuntimeError, "rate limit persists"):
            await self.speak()
        self.assertEqual(self.waits, [])

    async def test_other_errors_keep_original_retry_budget(self) -> None:
        self.outcomes = [ConnectionError() for _ in range(3)]
        with self.assertRaisesRegex(RuntimeError, "after 3 attempts"):
            await self.speak()
        self.assertEqual(self.waits, [1.5, 3])

    async def test_concurrent_scene_calls_are_spaced(self) -> None:
        await asyncio.gather(self.speak(), self.speak(), self.speak())
        self.assertEqual(len(self.calls), 3)
        self.assertEqual(self.waits, [1, 1])
        self.assertEqual(self.max_active, 1)

    async def test_missing_word_boundaries_never_return_audio(self) -> None:
        class AudioOnly:
            def __init__(self, *args, **kwargs):
                pass

            async def stream(self):
                yield {"type": "audio", "data": b"mp3"}

        self.client.loader = lambda: types.SimpleNamespace(Communicate=AudioOnly)
        with self.assertRaisesRegex(RuntimeError, "after 3 attempts"):
            await self.speak()


class PatchTests(unittest.TestCase):
    def test_source_patch_preserves_surrounding_helpers(self) -> None:
        source = 'before = True\nasync def vx_edge_tts_stream(text, profile, attempts=3):\n    return None\nafter = True\n'
        updated = patch_tts_runtime_source(source)
        compile(updated, "<test>", "exec")
        self.assertTrue(updated.startswith("before = True\n"))
        self.assertTrue(updated.endswith("after = True\n"))
        self.assertIn("synthesize(text, VOICE, profile, attempts)", updated)

    def test_missing_helper_fails_preflight(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "exactly one"):
            patch_tts_runtime_source("pass\n")

    def test_invalid_retry_after_is_ignored(self) -> None:
        for value in ("invalid", "nan", "inf"):
            self.assertIsNone(retry_after_seconds(RateLimitError(value)))


if __name__ == "__main__":
    unittest.main()
