# CELL 22 — FULL-WORD NARRATION
# NO SHORT CODES • NO INITIALS • NO ABBREVIATED TTS LABELS
# ============================================================

import html as _vx_html
import re as _vx_re

for _vx_required in ("teams", "players"):
    if _vx_required not in globals():
        raise RuntimeError(
            f"Run the canonical FPL data cells before FULL-WORD NARRATION — missing {_vx_required}"
        )


def _vx_narration_records(obj):
    if hasattr(obj, "to_dict"):
        try:
            return list(obj.to_dict(orient="records"))
        except TypeError:
            pass
    if isinstance(obj, list):
        return [dict(x) for x in obj if isinstance(x, dict)]
    if isinstance(obj, tuple):
        return [dict(x) for x in obj if isinstance(x, dict)]
    return []


def _vx_narration_key(value):
    return _vx_re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def _vx_narration_spoken_player_name(value):
    text = str(value or "").strip()
    match = _vx_re.fullmatch(
        r"[A-Za-z]\.\s*([^\W\d_][\w'’\-]*(?:\s+[^\W\d_][\w'’\-]*)*)",
        text,
    )
    return match.group(1) if match else text


# ------------------------------------------------------------
# CANONICAL TEAM SPEECH REGISTRY
# Built dynamically from the official FPL team table.
# No club names or club-code replacements are hard-coded here.
# ------------------------------------------------------------

VX_NARRATION_TEAM_BY_ID = {}
VX_NARRATION_TEAM_BY_CODE = {}
VX_NARRATION_TEAM_BY_ALIAS = {}
VX_NARRATION_TEAM_SHORT_ALIASES = set()

for _vx_team in _vx_narration_records(teams):
    try:
        _vx_team_id = int(_vx_team.get("id"))
    except Exception:
        continue

    _vx_spoken = str(_vx_team.get("name") or "").strip()
    if not _vx_spoken:
        continue

    VX_NARRATION_TEAM_BY_ID[_vx_team_id] = _vx_spoken

    try:
        _vx_code = int(_vx_team.get("code"))
        VX_NARRATION_TEAM_BY_CODE[_vx_code] = _vx_spoken
    except Exception:
        pass

    for _vx_alias in (
        _vx_team.get("name"),
        _vx_team.get("short_name"),
    ):
        _vx_alias = str(_vx_alias or "").strip()
        if not _vx_alias:
            continue
        VX_NARRATION_TEAM_BY_ALIAS[_vx_narration_key(_vx_alias)] = _vx_spoken

    _vx_short = str(_vx_team.get("short_name") or "").strip()
    if _vx_short:
        VX_NARRATION_TEAM_SHORT_ALIASES.add(_vx_short.casefold())


# ------------------------------------------------------------
# CANONICAL PLAYER SPEECH REGISTRY
# Every player resolves to official FPL web_name.
# Full names and initial+surname forms are generated from FPL data,
# never from a manually-maintained player replacement table.
# ------------------------------------------------------------

VX_NARRATION_PLAYER_BY_ID = {}
VX_NARRATION_PLAYER_BY_CODE = {}
VX_NARRATION_PLAYER_BY_ALIAS = {}
VX_NARRATION_PLAYER_TEXT_ALIASES = []

_vx_second_name_candidates = {}

for _vx_player in _vx_narration_records(players):
    try:
        _vx_player_id = int(_vx_player.get("id"))
    except Exception:
        continue

    _vx_web = str(_vx_player.get("web_name") or "").strip()
    if not _vx_web:
        continue
    _vx_spoken = _vx_narration_spoken_player_name(_vx_web)

    VX_NARRATION_PLAYER_BY_ID[_vx_player_id] = _vx_web

    try:
        _vx_code = int(_vx_player.get("code"))
        VX_NARRATION_PLAYER_BY_CODE[_vx_code] = _vx_web
    except Exception:
        pass

    _vx_first = str(_vx_player.get("first_name") or "").strip()
    _vx_second = str(_vx_player.get("second_name") or "").strip()
    _vx_full = " ".join(x for x in (_vx_first, _vx_second) if x).strip()

    for _vx_alias in (_vx_web, _vx_full):
        if _vx_alias:
            VX_NARRATION_PLAYER_BY_ALIAS[_vx_narration_key(_vx_alias)] = _vx_web

    if _vx_second:
        _vx_second_name_candidates.setdefault(_vx_narration_key(_vx_second), set()).add(_vx_web)

    if _vx_full and _vx_narration_key(_vx_full) != _vx_narration_key(_vx_web):
        VX_NARRATION_PLAYER_TEXT_ALIASES.append((_vx_full, _vx_spoken))

    if _vx_spoken.casefold() != _vx_web.casefold():
        VX_NARRATION_PLAYER_TEXT_ALIASES.append((_vx_web, _vx_spoken))

    if _vx_first and _vx_second:
        _vx_initial = _vx_first[0]
        VX_NARRATION_PLAYER_TEXT_ALIASES.extend([
            (f"{_vx_initial}. {_vx_second}", _vx_spoken),
            (f"{_vx_initial} {_vx_second}", _vx_spoken),
        ])

# A surname-only alias is safe only when it points to one official web_name.
for _vx_alias_key, _vx_web_names in _vx_second_name_candidates.items():
    if len(_vx_web_names) == 1:
        _vx_web = next(iter(_vx_web_names))
        VX_NARRATION_PLAYER_BY_ALIAS.setdefault(_vx_alias_key, _vx_web)

# Longest aliases first prevents a short alias from breaking a longer name.
VX_NARRATION_PLAYER_TEXT_ALIASES.sort(
    key=lambda pair: len(pair[0]),
    reverse=True,
)

VX_NARRATION_TEAM_TEXT_ALIASES = sorted(
    [
        (str(_vx_team.get("short_name") or "").strip(), str(_vx_team.get("name") or "").strip())
        for _vx_team in _vx_narration_records(teams)
        if str(_vx_team.get("short_name") or "").strip()
        and str(_vx_team.get("name") or "").strip()
        and _vx_narration_key(_vx_team.get("short_name")) != _vx_narration_key(_vx_team.get("name"))
    ],
    key=lambda pair: len(pair[0]),
    reverse=True,
)


def vx_narration_team(value):
    """Return the canonical spoken team name from id/code/name/short-name input."""
    if isinstance(value, dict):
        for key in ("id", "team_id", "team"):
            if key in value:
                try:
                    team_id = int(value[key])
                    if team_id in VX_NARRATION_TEAM_BY_ID:
                        return VX_NARRATION_TEAM_BY_ID[team_id]
                except Exception:
                    pass
        value = value.get("name") or value.get("short_name") or value.get("team") or ""

    try:
        number = int(value)
        if number in VX_NARRATION_TEAM_BY_ID:
            return VX_NARRATION_TEAM_BY_ID[number]
        if number in VX_NARRATION_TEAM_BY_CODE:
            return VX_NARRATION_TEAM_BY_CODE[number]
    except Exception:
        pass

    text = str(value or "").strip()
    resolved = VX_NARRATION_TEAM_BY_ALIAS.get(_vx_narration_key(text))
    if resolved:
        return resolved
    return text


def vx_narration_player(value):
    """Return the natural spoken player name from id/code/name-like input."""
    if isinstance(value, dict):
        for key in ("id", "player_id", "element"):
            if key in value:
                try:
                    player_id = int(value[key])
                    if player_id in VX_NARRATION_PLAYER_BY_ID:
                        return _vx_narration_spoken_player_name(VX_NARRATION_PLAYER_BY_ID[player_id])
                except Exception:
                    pass
        value = (
            value.get("web_name")
            or value.get("name")
            or " ".join(
                x for x in (
                    str(value.get("first_name") or "").strip(),
                    str(value.get("second_name") or "").strip(),
                ) if x
            )
        )

    try:
        number = int(value)
        if number in VX_NARRATION_PLAYER_BY_ID:
            return _vx_narration_spoken_player_name(VX_NARRATION_PLAYER_BY_ID[number])
        if number in VX_NARRATION_PLAYER_BY_CODE:
            return _vx_narration_spoken_player_name(VX_NARRATION_PLAYER_BY_CODE[number])
    except Exception:
        pass

    text = str(value or "").strip()
    resolved = VX_NARRATION_PLAYER_BY_ALIAS.get(_vx_narration_key(text), text)
    return _vx_narration_spoken_player_name(resolved)


def vx_narration_fixture(opponent, is_home):
    """Natural fixture phrase; caller supplies a canonical team identifier."""
    club = vx_narration_team(opponent)
    return f"{club} at home" if bool(is_home) else f"{club} away"


def _vx_replace_narration_phrase(text, source, target):
    source = str(source or "").strip()
    target = str(target or "").strip()
    if not source or not target or source.casefold() == target.casefold() or source.casefold() not in text.casefold():
        return text
    pattern = _vx_re.compile(
        r"(?<![A-Za-z0-9])" + _vx_re.escape(source) + r"(?![A-Za-z0-9])",
        flags=_vx_re.IGNORECASE,
    )
    return pattern.sub(lambda _m: target, text)


def vx_assert_full_word_narration(text, context="narration"):
    """Fail closed: abbreviated/compact tokens never reach Ryan Edge TTS."""
    value = str(text or "")
    problems = []

    # Player web_name is explicitly the canonical speech identity. Protect exact
    # official web_name spans from generic initial/acronym diagnostics.
    diagnostic_value = value
    for _vx_web in sorted(set(VX_NARRATION_PLAYER_BY_ID.values()), key=len, reverse=True):
        if not _vx_web or _vx_web.casefold() not in diagnostic_value.casefold():
            continue
        diagnostic_value = _vx_re.sub(
            r"(?<![A-Za-z0-9])" + _vx_re.escape(_vx_web) + r"(?![A-Za-z0-9])",
            " playerwebnameplaceholder ",
            diagnostic_value,
            flags=_vx_re.IGNORECASE,
        )

    # Official short team aliases surviving the dynamic replacement are blocked.
    words = [w.casefold() for w in _vx_re.findall(r"\b[A-Z]{2,}[A-Z0-9]*\b", value)]
    surviving_team_codes = sorted({w for w in words if w in VX_NARRATION_TEAM_SHORT_ALIASES})
    if surviving_team_codes:
        problems.append("team short names: " + ", ".join(surviving_team_codes))

    # API-style labels are not natural narration.
    api_tokens = sorted(set(_vx_re.findall(r"\b[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+\b", diagnostic_value)))
    if api_tokens:
        problems.append("API-style fields: " + ", ".join(api_tokens[:8]))

    # All-cap abbreviations / compact labels, including letter+digit forms.
    compact_caps = sorted(set(_vx_re.findall(r"\b[A-Z]{2,}[A-Z0-9]*\b", diagnostic_value)))
    if compact_caps:
        problems.append("capital abbreviations: " + ", ".join(compact_caps[:8]))

    # Mixed short forms such as lower-case prefix + capital letter are blocked.
    mixed_compact = sorted(set(_vx_re.findall(r"\b[a-z][A-Z][A-Za-z0-9]*\b", diagnostic_value)))
    if mixed_compact:
        problems.append("mixed abbreviations: " + ", ".join(mixed_compact[:8]))

    # Initial + surname forms must resolve to the official web_name first.
    initials = sorted(set(_vx_re.findall(r"\b[A-Z]\.\s+[A-Z][A-Za-z'’-]+\b", diagnostic_value)))
    if initials:
        problems.append("initial-form player names: " + ", ".join(initials[:8]))

    # Parenthesised one-letter fixture labels are compact display syntax.
    compact_fixture = sorted(set(_vx_re.findall(r"\([A-Za-z]\)", diagnostic_value)))
    if compact_fixture:
        problems.append("compact fixture labels: " + ", ".join(compact_fixture[:8]))

    if problems:
        raise RuntimeError(
            f"FULL-WORD NARRATION blocked {context}: " + " | ".join(problems)
        )
    return value


def vx_full_word_narration(text, context="narration"):
    """Canonical final text transform used immediately before every Ryan TTS call."""
    value = _vx_html.unescape(str(text or ""))

    # Resolve player shorthand from official FPL identities to web_name.
    for source, target in VX_NARRATION_PLAYER_TEXT_ALIASES:
        value = _vx_replace_narration_phrase(value, source, target)

    # Resolve official short team names dynamically to canonical team names.
    for source, target in VX_NARRATION_TEAM_TEXT_ALIASES:
        # Uppercase club codes are case-sensitive: ordinary "new" is not Newcastle.
        if source.isupper() and len(source) <= 4:
            value = _vx_re.sub(r"(?<![A-Za-z0-9])" + _vx_re.escape(source) + r"(?![A-Za-z0-9])", lambda m: target, value)
        else:
            value = _vx_replace_narration_phrase(value, source, target)

    # Natural punctuation/number wording; no football-specific replacement table.
    value = _vx_re.sub(r"(?<=\d)\s*%", " percent", value)
    value = value.replace("&", " and ")

    # API-style field syntax is intentionally NOT guessed or expanded here.
    # The fail-closed validator blocks it so a future caller must supply real
    # natural-language narration rather than a machine field label.

    value = _vx_re.sub(r"[ \t]+", " ", value)
    value = _vx_re.sub(r" *\n *", "\n", value)
    value = value.strip()

    return vx_assert_full_word_narration(value, context=context)


def vx_full_word_display(text, context="narration display"):
    """Narration-facing on-screen text follows the exact same full-word contract."""
    return vx_full_word_narration(text, context=context)


print("✅ FULL-WORD NARRATION READY")
print(f"✅ Dynamic team speech names: {len(VX_NARRATION_TEAM_BY_ID)}")
print(f"✅ Dynamic player web names: {len(VX_NARRATION_PLAYER_BY_ID)}")
print("✅ Unknown abbreviations fail closed before Ryan TTS")

