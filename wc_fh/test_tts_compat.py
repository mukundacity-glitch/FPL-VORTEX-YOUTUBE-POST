from __future__ import annotations

import unittest
from types import ModuleType
from unittest.mock import patch

from wc_fh.tts_compat import install_official_web_name_compat, patch_narration_loader


class OfficialWebNameCompatibilityTests(unittest.TestCase):
    @staticmethod
    def original(narration, bootstrap=None, player_ids=()):
        web_names = {p["web_name"] for p in (bootstrap or {}).get("elements", [])}
        unknown = [token for token in ("E.Le", "J.Ped", "X.Ab")
                   if token in narration and token not in web_names]
        return {"original_narration": narration, "tts_cleaned_narration": narration,
                "unresolved_tokens": unknown, "validation_passed": not unknown,
                "replacements_applied": []}

    def setUp(self):
        self.bootstrap = {"elements": [{"id": 542, "web_name": "E.Le Fée"},
                                        {"id": 165, "web_name": "João Pedro"}]}
        self.prepare = install_official_web_name_compat(self.original)

    def test_official_multiword_web_name_is_not_blocked(self):
        narration = "Our pick is E.Le Fée for this gameweek."
        result = self.prepare(narration, self.bootstrap, [542])
        self.assertEqual(result["unresolved_tokens"], [])
        self.assertTrue(result["validation_passed"])
        self.assertEqual(result["tts_cleaned_narration"], narration)

    def test_standalone_shorthand_is_still_rejected(self):
        result = self.prepare("E.Le replaces E.Le Fée.", self.bootstrap, [542])
        self.assertEqual(result["unresolved_tokens"], ["E.Le"])
        self.assertFalse(result["validation_passed"])

    def test_unknown_initialled_name_is_still_rejected(self):
        result = self.prepare("X.Ab replaces E.Le Fée.", self.bootstrap, [542])
        self.assertEqual(result["unresolved_tokens"], ["X.Ab"])
        self.assertFalse(result["validation_passed"])

    def test_must_be_current_official_name(self):
        result = self.prepare("E.Le Fée is available.", {"elements": []}, [542])
        self.assertFalse(result["validation_passed"])
        self.assertEqual(result["unresolved_tokens"], ["E.Le"])

    def test_other_validation_failures_survive(self):
        def original(text, bootstrap=None, player_ids=()):
            return {"tts_cleaned_narration": text,
                    "unresolved_tokens": ["E.Le", "NOTACODE"], "validation_passed": False}
        result = install_official_web_name_compat(original)("E.Le Fée", self.bootstrap, [542])
        self.assertEqual(result["unresolved_tokens"], ["NOTACODE"])
        self.assertFalse(result["validation_passed"])

    def test_repeated_install_does_not_wrap_again(self):
        self.assertIs(install_official_web_name_compat(self.prepare), self.prepare)

    def test_import_contract_fails_closed(self):
        for source in ("pass\n", "from tts_narration import prepare_tts\n",
                       "from tts_narration import prepare_tts, PROFILE, VERSION\n" * 2):
            with self.subTest(source=source), self.assertRaisesRegex(ValueError, "loader contract changed"):
                patch_narration_loader(source)

    def test_cell14_loader_preserves_original_preflight(self):
        source = ("import tts_narration as _vx_tts_module\n"
                  "from tts_narration import prepare_tts, PROFILE as VX_FIXED_TTS_PROFILE, "
                  "VERSION as VX_TTS_TEXT_VERSION\n"
                  "result = prepare_tts('E.Le Fée', {'elements': [{'id': 542, 'web_name': 'E.Le Fée'}]}, [542])\n")
        speech = ModuleType("tts_narration")
        speech.prepare_tts = self.original
        speech.PROFILE = {}
        speech.VERSION = "test"
        with patch.dict("sys.modules", {"tts_narration": speech}):
            scope = {}
            exec(patch_narration_loader(source), scope)
        self.assertTrue(scope["result"]["validation_passed"])
        self.assertIs(scope["prepare_tts"], speech.prepare_tts)


if __name__ == "__main__":
    unittest.main()
