"""Keep official multiword FPL web names valid in Ryan narration QA.

The pinned speech module matches an initialled token (``E.Le``) even when it
is only the first part of an official full web name (``E.Le Fée``). Retain the
upstream fail-closed checks for every non-official or standalone abbreviation.
"""
from __future__ import annotations

import re
from functools import wraps
from typing import Any, Callable


_INITIALLED_NAME = re.compile(r"\b(?:[A-Z]\.\s*)+[A-Z][\w’'-]+")


def install_official_web_name_compat(prepare_tts: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    if getattr(prepare_tts, "_wc_fh_official_web_names", False):
        return prepare_tts

    @wraps(prepare_tts)
    def validate(original: str, bootstrap: dict[str, Any] | None = None,
                 player_ids: tuple[int, ...] | list[int] = ()) -> dict[str, Any]:
        audit = prepare_tts(original, bootstrap, player_ids)
        unresolved = audit.get("unresolved_tokens", [])
        if not unresolved or not bootstrap:
            return audit

        cleaned = audit["tts_cleaned_narration"]
        official_names = {
            name for player in bootstrap.get("elements", [])
            if (name := str(player.get("web_name") or "").strip())
        }
        # Only consider complete, verified names with an initialled prefix.
        covered_spans = [
            match.span()
            for name in official_names
            if " " in name and _INITIALLED_NAME.match(name)
            for match in re.finditer(r"(?<!\w)" + re.escape(name) + r"(?!\w)", cleaned)
        ]
        if not covered_spans:
            return audit

        invalid = []
        for token in unresolved:
            if not _INITIALLED_NAME.fullmatch(token):
                invalid.append(token)
                continue
            matches = list(re.finditer(r"(?<!\w)" + re.escape(token) + r"(?!\w)", cleaned))
            if not matches or any(
                not any(start <= match.start() and match.end() <= stop
                        for start, stop in covered_spans)
                for match in matches
            ):
                invalid.append(token)

        if len(invalid) == len(unresolved):
            return audit
        return dict(audit, unresolved_tokens=invalid, validation_passed=not invalid)

    validate._wc_fh_official_web_names = True
    return validate


def patch_narration_loader(source: str) -> str:
    """Patch only the existing, exact speech-import contract of Cell 14."""
    import ast

    matches = [
        node for node in ast.parse(source).body
        if isinstance(node, ast.ImportFrom) and node.module == "tts_narration"
        and {alias.name for alias in node.names} >= {"prepare_tts", "PROFILE", "VERSION"}
    ]
    if len(matches) != 1:
        raise ValueError("Pinned narration loader contract changed; expected one speech import")
    lines = source.splitlines(keepends=True)
    position = matches[0].end_lineno
    lines[position:position] = [
        "\nfrom wc_fh.tts_compat import install_official_web_name_compat as _wc_fh_install_official_web_name_compat\n"
        "prepare_tts = _wc_fh_install_official_web_name_compat(prepare_tts)\n"
        "_vx_tts_module.prepare_tts = prepare_tts\n"
    ]
    return "".join(lines)
