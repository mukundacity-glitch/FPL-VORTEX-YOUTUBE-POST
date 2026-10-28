# CELL 16 — GW REVIEW • PLAYER-BY-PLAYER EXACT SYNC
# ============================================================

from pathlib import Path
import json, math, re, subprocess
import pandas as pd

ROOT   = Path(globals().get("PROJECT_ROOT", "/content/drive/MyDrive/FPL_VORTEX"))
HTML   = Path(globals().get("HTML_WORK_DIR", "/content/FPL_VORTEX_FIRST_DAY_WORK/html"))
AUDIO  = Path(globals().get("AUDIO_WORK_DIR", "/content/FPL_VORTEX_FIRST_DAY_WORK/audio")) / "review_segments"
TIMING = Path(globals().get("DATA_DIR", "/content/FPL_VORTEX_FIRST_DAY_WORK/data"))
MP3_OUT = Path(globals().get("MP3_DIR", "/content/FPL_VORTEX_FIRST_DAY_WORK/mp3"))

SRC_HTML  = HTML/"gw_review_scene_4k.html"
ANIM_HTML = HTML/"gw_review_scene_4k_animated.html"
PACKAGE   = TIMING/"gw_review_package.json"
MASTER_MP3 = MP3_OUT/"gw_review.mp3"
MASTER_VTT = TIMING/"gw_review_master.vtt"

if not SRC_HTML.exists():
    raise FileNotFoundError("Run Cell 14 first.")

# Canonical Cell 15 package handoff.
_review_pkg_memory = None

if "GW_REVIEW_PACKAGE" in globals():
    _review_pkg_memory = GW_REVIEW_PACKAGE
elif "review_package" in globals():
    # Compatibility with a Cell 15 execution completed before this fix
    # was loaded into the current Colab runtime.
    _review_pkg_memory = review_package

if _review_pkg_memory is not None:
    pkg = _review_pkg_memory

    if not isinstance(pkg, dict) or "segments" not in pkg or "gw" not in pkg:
        raise RuntimeError(
            "The in-memory GW review package is invalid. "
            "Rerun CELL 15 — AUTO GW REVIEW DATA + RYAN NARRATION TIMING."
        )

    if "GW_REVIEW" in globals():
        _expected_review_gw = int(GW_REVIEW["gw"])
        if int(pkg["gw"]) != _expected_review_gw:
            raise RuntimeError(
                f"Stale GW review package in memory: package GW {pkg['gw']} "
                f"but current review GW is {_expected_review_gw}. "
                "Rerun CELL 15 before Cell 16."
            )

    GW_REVIEW_PACKAGE = pkg

    if not PACKAGE.exists():
        PACKAGE.parent.mkdir(parents=True, exist_ok=True)
        PACKAGE.write_text(
            json.dumps(pkg, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print("✅ Restored missing GW review package from Cell 15 memory:", PACKAGE)

elif PACKAGE.exists():
    pkg = json.loads(PACKAGE.read_text(encoding="utf-8"))
    GW_REVIEW_PACKAGE = pkg

else:
    raise FileNotFoundError(
        "Missing GW review package and no completed Cell 15 package is "
        "available in memory. Run CELL 15 — AUTO GW REVIEW DATA + "
        "RYAN NARRATION TIMING once, then continue with Cell 16."
    )


for _name in ["PLAYER_CARD_CSS", "PLAYER_CARD_JS"]:
    if _name not in globals():
        raise NameError(
            "Run CELL 15A — PLAYER CARD DESIGN before Cell 16. "
            f"Missing {_name}."
        )

# Cell 16 owns no FDR math and defines no duplicate FDR helpers.
# Cell 14 is the presentation handoff from the authoritative model cells.
for _name in ("fdr_table", "format_fdr_value", "fdr_class"):
    if _name not in globals():
        raise NameError(
            f"Run Cell 14 first: missing shared presentation object {_name!r}. "
            "Do not recreate FDR math or helper functions in Cell 16."
        )
if "team_meta_by_short" not in globals():
    raise NameError("Run LIVE FOOTBALL ENRICHMENT first: missing canonical team metadata.")

# ------------------------------------------------------------
# 1. ENRICH PLAYERS + PITCH POSITIONS
#    HERO CARD DATA ONLY — NO HERO CARD DESIGN LIVES HERE.
# ------------------------------------------------------------

_POSITION_LABEL = {
    "GK":"GOALKEEPER",
    "DEF":"DEFENDER",
    "MID":"MIDFIELDER",
    "FWD":"FORWARD",
}

# Reuse the season already established by the enrichment cell when present.
try:
    _pc_season_start = int(globals().get("EPL_SEASON"))
except Exception:
    from datetime import datetime
    _now = datetime.now()
    _pc_season_start = _now.year if _now.month >= 7 else _now.year - 1

_PC_SEASON_LABEL = f"{_pc_season_start}/{str(_pc_season_start + 1)[-2:]} SEASON"

# Existing verified FDR table is the single source of truth for the card.
_pc_fdr_rows = {
    str(r["team_short"]).upper(): r
    for _, r in fdr_table.iterrows()
}

_pc_model_fdr_by_team_gw = {}
if isinstance(globals().get("model_fixture_fdr_df"), pd.DataFrame) and not model_fixture_fdr_df.empty:
    for _, _r in model_fixture_fdr_df.iterrows():
        _pc_model_fdr_by_team_gw[(str(_r.get("team", "")).upper(), int(_r["gw"]))] = _r

_pc_gk_fdr_by_team_gw = {}
if isinstance(globals().get("goalkeeper_fixture_fdr_df"), pd.DataFrame) and not goalkeeper_fixture_fdr_df.empty:
    for _, _r in goalkeeper_fixture_fdr_df.iterrows():
        _pc_gk_fdr_by_team_gw[(str(_r.get("team", "")).upper(), int(_r["gw"]))] = _r


def _pc_as_list(value):
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    try:
        if hasattr(value, "tolist"):
            out = value.tolist()
            return out if isinstance(out, list) else [out]
    except Exception:
        pass
    return [] if value is None else [value]


def _pc_text_number(value, decimals=1):
    try:
        number = float(value)
        return f"{number:.{decimals}f}"
    except Exception:
        return "—"


def _pc_int(value):
    try:
        return int(float(value))
    except Exception:
        return 0


def _pc_fixture_pack(team_short, position, player_id):
    """Six-GW presentation payload from the authoritative model FDR table."""
    row = _pc_fdr_rows.get(str(team_short).upper())
    if row is None:
        return []

    fixture_values = _pc_as_list(row.get("fixtures"))
    fdr_key = "defence_fdr" if str(position).upper() in {"GK", "DEF"} else "attack_fdr"
    fdr_values = _pc_as_list(row.get(fdr_key))
    if not fdr_values:
        fdr_values = _pc_as_list(row.get("fdr"))

    out = []
    for i, fixture_raw in enumerate(fixture_values[:6]):
        fdr_raw = fdr_values[i] if i < len(fdr_values) else None
        fixture_text = format_fdr_value(fixture_raw)
        fdr_text = format_fdr_value(fdr_raw)

        matches = re.findall(r"\b([A-Z]{3})\s*\(([HA])\)", fixture_text.upper())
        opponent = "+".join(x[0] for x in matches) if matches else (
            "BLANK" if "BLANK" in fixture_text.upper() else "—"
        )
        venue = "+".join(x[1] for x in matches) if matches else ""

        badges = []
        for short, _venue in matches[:2]:
            badge = (team_meta_by_short.get(short, {}) or {}).get("badge", "")
            if badge:
                badges.append(badge)

        gw = int(NEXT_GW) + i
        model_row = _pc_model_fdr_by_team_gw.get((str(team_short).upper(), gw))
        gk_row = _pc_gk_fdr_by_team_gw.get((str(team_short).upper(), gw))
        cls = fdr_class(fdr_raw)
        bucket = cls.rsplit("-", 1)[-1] if cls in {"fdr-1","fdr-2","fdr-3","fdr-4","fdr-5"} else "—"

        out.append({
            "gw": gw,
            "opponent": opponent,
            "venue": venue,
            "fixdiff": fdr_text,
            "fdr_class": cls,
            "fdr_value": fdr_text,
            "badges": badges,
            "attack_fdr_model": (
                float(model_row["attack_fdr_model"])
                if model_row is not None and pd.notna(model_row.get("attack_fdr_model"))
                else None
            ),
            "defence_fdr_model": (
                float(model_row["defence_fdr_model"])
                if model_row is not None and pd.notna(model_row.get("defence_fdr_model"))
                else None
            ),
            "goalkeeper_fdr_model": (
                float(gk_row["goalkeeper_fdr_model"])
                if gk_row is not None and pd.notna(gk_row.get("goalkeeper_fdr_model"))
                else None
            ),
        })
    return out


def _pc_per90(value, season_minutes, decimals=2):
    """Current-season rate only; no preseason or projection fallback."""
    try:
        minutes = float(season_minutes)
        if minutes <= 0:
            return "—"
        return f"{(float(value) * 90.0 / minutes):.{int(decimals)}f}"
    except Exception:
        return "—"


def _pc_avg_minutes_per_start(season_minutes, season_starts):
    try:
        starts = int(float(season_starts))
        if starts <= 0:
            return "—"
        return str(int(round(float(season_minutes) / starts)))
    except Exception:
        return "—"


for p in pkg["players"]:

    # All review-season/player fields were frozen in the single GW_REVIEW
    # package upstream. Do not read shadow globals or refetch player data here.
    p["team_code"] = p.get("team_code")

    team_badge = ""
    try:
        team_badge = (team_meta_by_short.get(str(p["team"]).upper(), {}) or {}).get("badge", "")
    except Exception:
        pass

    # If the local badge cache is unavailable, use the same official PL team code
    # already present in notebook data. This is a display fallback, not new math.
    if not team_badge and p.get("team_code"):
        team_badge = (
            "https://resources.premierleague.com/premierleague/"
            f"badges/100/t{p['team_code']}.png"
        )

    season_minutes = _pc_int(p.get("season_minutes", 0))
    season_starts = _pc_int(p.get("season_starts", 0))
    season_goals = _pc_int(p.get("season_goals", 0))
    season_assists = _pc_int(p.get("season_assists", 0))
    season_clean_sheets = _pc_int(p.get("season_clean_sheets", 0))
    season_goals_conceded = _pc_int(p.get("season_goals_conceded", 0))
    season_saves = _pc_int(p.get("season_saves", 0))
    season_bonus = _pc_int(p.get("season_bonus", 0))
    season_points = _pc_int(p.get("season_total_points", 0))

    stats = {
        "xg_per90": _pc_per90(p.get("season_xg", 0), season_minutes),
        "xa_per90": _pc_per90(p.get("season_xa", 0), season_minutes),
        "goals_per90": _pc_per90(season_goals, season_minutes),
        "assists_per90": _pc_per90(season_assists, season_minutes),
        "points_per90": _pc_per90(season_points, season_minutes),
        "saves_per90": _pc_per90(season_saves, season_minutes),
        "goals_conceded_per90": _pc_per90(season_goals_conceded, season_minutes),
        "bonus_per90": _pc_per90(season_bonus, season_minutes),
        "clean_sheets": season_clean_sheets,
        "season_minutes": season_minutes,
        "season_starts": season_starts,
        "avg_minutes_per_start": _pc_avg_minutes_per_start(season_minutes, season_starts),
        "goals": season_goals,
        "assists": season_assists,
        "saves": season_saves,
        "goals_conceded": season_goals_conceded,
        "bonus": season_bonus,
        "total_points": season_points,
    }

    pos = str(p.get("pos", "")).upper()
    # Player-card display data only: restore meaningful official current-season
    # totals used by the earlier working hero card. No projection/preseason
    # fallback and no card-design/layout change.
    if pos == "GK":
        display_stats = [
            {"icon":"spark", "label":"TOTAL FPL POINTS", "value":str(season_points)},
            {"icon":"shield", "label":"CLEAN SHEETS", "value":str(season_clean_sheets)},
            {"icon":"glove", "label":"SAVES", "value":str(season_saves)},
            {"icon":"target", "label":"MINUTES", "value":str(season_minutes)},
            {"icon":"ball", "label":"xGC", "value":_pc_text_number(p.get("season_xgc"), 2)},
        ]
    else:
        display_stats = [
            {"icon":"spark", "label":"TOTAL FPL POINTS", "value":str(season_points)},
            {"icon":"target", "label":"MINUTES", "value":str(season_minutes)},
            {"icon":"ball", "label":"xG", "value":_pc_text_number(p.get("season_xg"), 2)},
            {"icon":"boot", "label":"xA", "value":_pc_text_number(p.get("season_xa"), 2)},
            {"icon":"target", "label":"xGI", "value":_pc_text_number(p.get("season_xgi"), 2)},
        ]

    fixture = p.get("fixture") or {}
    result_state = vx_review_player_result_state(p)
    if result_state == "AWAITING":
        points_label = "AWAITING RESULT"
    elif result_state == "UNKNOWN":
        points_label = "RESULT UNAVAILABLE"
    elif result_state == "DID_NOT_PLAY":
        points_label = "DID NOT PLAY"
    elif result_state == "PROVISIONAL":
        points_label = f"{p.get('points', 0)} PTS SO FAR"
    else:
        points_label = f"{p.get('points', 0)} PTS"
    review_bits = [
        f"GW {pkg['gw']}",
        points_label,
        f"{p.get('minutes', 0)} MIN" if result_state in {"COMPLETE", "PROVISIONAL"} else "",
    ]
    if fixture.get("opp"):
        review_bits.append(f"{fixture.get('opp')} {fixture.get('ha','')} {fixture.get('score','')}".strip())

    _pid = int(p.get("id", 0) or 0)

    duty = "BENCH" if p.get("bench") else "STARTER"
    if p.get("captain"):
        leadership = "CAPTAIN"
    elif p.get("vice"):
        leadership = "VICE CAPTAIN"
    else:
        leadership = f"GW {pkg['gw']}"

    p["card"] = {
        "id": p.get("id"),
        "name": p.get("name", ""),
        "full_name": p.get("full_name", ""),
        "first_name": p.get("first_name") or str(p.get("full_name", p.get("name", ""))).split(" ")[0],
        "surname": p.get("second_name") or " ".join(str(p.get("full_name", "")).split(" ")[1:]) or p.get("name", ""),
        "position": p.get("pos", ""),
        "position_label": _POSITION_LABEL.get(p.get("pos"), p.get("pos", "PLAYER")),
        "club": p.get("team_name", ""),
        "club_short": p.get("team", ""),
        "club_badge": team_badge,
        "player_image": p.get("photo", ""),
        "asset_label": f"GW {pkg['gw']} PLAYER REVIEW",
        "price": f"£{float(p.get('price', 0)):.1f}m",
        "total_points": _pc_int(p.get("season_total_points", 0)),
        "form": _pc_text_number(p.get("season_form"), 1),
        "ownership": f"{float(p.get('ownership', 0) or 0):.1f}%",
        "avg_minutes_per_start": stats["avg_minutes_per_start"],
        "captain": bool(p.get("captain")),
        "vice": bool(p.get("vice")),
        "gw_raw_points": _pc_int(p.get("points", 0)),
        "gw_applied_points": _pc_int(p.get("points", 0)) * max(0, _pc_int(p.get("multiplier", 0))),
        "stats": stats,
        "display_stats": display_stats,
        "stats_heading": f"{_PC_SEASON_LABEL} • {_POSITION_LABEL.get(p.get('pos'), p.get('pos','PLAYER'))} STATS",
        "fixtures": _pc_fixture_pack(p.get("team", ""), p.get("pos", ""), _pid),
        "verdict_main": f"{_POSITION_LABEL.get(p.get('pos'), p.get('pos','PLAYER'))} REVIEW",
        "verdict_sub": "  |  ".join(review_bits),
        "tags": [
            _POSITION_LABEL.get(p.get("pos"), p.get("pos", "PLAYER")),
            duty,
            leadership,
            f"BONUS {p.get('bonus', 0)}",
            f"BPS {p.get('bps', 0)}",
        ],
        "season_label": _PC_SEASON_LABEL,
    }

# IMPORTANT: pkg["players"], pkg["starters"] and pkg["bench"] may
# contain separate dictionary objects after JSON serialization.
# Rebind starters/bench to the enriched player objects so card data,
# team_code and every later animation field are always present.
_player_by_id = {int(p["id"]): p for p in pkg["players"]}

pkg["starters"] = [
    _player_by_id.get(int(p["id"]), p)
    for p in pkg["starters"]
]

pkg["bench"] = [
    _player_by_id.get(int(p["id"]), p)
    for p in pkg["bench"]
]

# same approved formation geometry
groups = {
    pos:[p for p in pkg["starters"] if p["pos"] == pos]
    for pos in ("GK","DEF","MID","FWD")
}

ys = {"GK":13.5, "DEF":35.5, "MID":58.2, "FWD":82.0}

for pos, arr in groups.items():

    span = 0 if pos == "GK" else 47 if pos == "FWD" else 56

    for i,p in enumerate(arr):

        p["pitch_x"] = (
            50 if len(arr) == 1
            else 50-span/2 + span*(i/(len(arr)-1))
        )

        p["pitch_y"] = ys[pos]

# ------------------------------------------------------------
# 2. CONFIGURABLE GLOBAL AUDIO + VISUAL TIMELINE
# ------------------------------------------------------------

# Fixed editorial beats live here, while every later player/substitute reveal
# is still sourced from Ryan's real WordBoundary timestamp. Override only the
# values that need tuning after a final narration pass, for example:
# GW_REVIEW_ANIMATION_TIMING_OVERRIDES = {"goalkeeper_card_out": 23.4}
GW_REVIEW_ANIMATION_DEFAULTS = {
    "premier_league_logo_at": 0.0,
    "review_title_at": 0.0,
    "pitch_at": 0.0,
    "first_player_at": 0.0,
    "goalkeeper_card_out": 23.0,
    "entrance_duration": 0.42,
    "hero_fade_in": 0.32,
    "hero_fade_out": 0.34,
    "table_reveal_duration": 0.58,
    "metric_highlight_duration": 1.15,
    "final_hold": 3.0,
}

GW_REVIEW_ANIMATION_TIMING = dict(GW_REVIEW_ANIMATION_DEFAULTS)
_review_timing_overrides = globals().get(
    "GW_REVIEW_ANIMATION_TIMING_OVERRIDES", {}
) or {}
_unknown_review_timing = sorted(
    set(_review_timing_overrides) - set(GW_REVIEW_ANIMATION_TIMING)
)
if _unknown_review_timing:
    raise KeyError(
        "Unknown GW Review animation timing overrides: "
        f"{_unknown_review_timing}"
    )
GW_REVIEW_ANIMATION_TIMING.update(
    {key: float(value) for key, value in _review_timing_overrides.items()}
)

for _timing_key, _timing_value in GW_REVIEW_ANIMATION_TIMING.items():
    if not math.isfinite(float(_timing_value)) or float(_timing_value) < 0:
        raise ValueError(
            f"Invalid GW Review animation timing {_timing_key}={_timing_value!r}"
        )


def _vx_build_review_timeline(review_pkg, timing):
    """Attach deterministic audio/visual times to one completed review package."""
    review_segments = list(review_pkg.get("segments") or [])
    starters = list(review_pkg.get("starters") or [])
    if not review_segments or not starters:
        raise RuntimeError("GW Review animation requires narration and a starting eleven.")

    first_starter = starters[0]
    if str(first_starter.get("pos", "")).upper() != "GK":
        raise RuntimeError("GW Review animation must begin with the goalkeeper.")
    first_starter_id = int(first_starter["id"])

    cursor = 0.0
    goalkeeper_gate_applied = False
    first_player_seen = False

    for index, segment in enumerate(review_segments):
        duration = float(segment.get("duration") or 0.0)
        if not math.isfinite(duration) or duration <= 0:
            raise RuntimeError(
                f"GW Review narration duration is invalid for {segment.get('id')}"
            )

        player_id = segment.get("player_id")
        is_first_player = (
            player_id is not None and int(player_id) == first_starter_id
        )

        if index == 0:
            start = 0.0
        elif is_first_player:
            # Start the goalkeeper as soon as the headline finishes speaking.
            name_time = float(segment.get("name_time") or 0.0)
            start = cursor
            timing["first_player_at"] = float(start + name_time)
            first_player_seen = True
        else:
            start = cursor
            if first_player_seen and not goalkeeper_gate_applied:
                # Start the next narration naturally after the previous spoken
                # words. Only delay if its spoken name would arrive before the
                # goalkeeper hero has fully faded.
                goalkeeper_hero_off = (
                    float(timing["goalkeeper_card_out"])
                    + float(timing["hero_fade_out"])
                )
                next_name_time = float(segment.get("name_time") or 0.0)
                start = max(
                    start,
                    goalkeeper_hero_off - next_name_time + 0.08,
                )
                goalkeeper_gate_applied = True

        segment["t0"] = float(start)
        segment["t1"] = float(start + duration)

        word_bounds = list(segment.get("words") or [])
        spoken_end_offset = duration
        if word_bounds:
            spoken_end_offset = max(
                float(word.get("start") or 0.0)
                + float(word.get("duration") or 0.0)
                for word in word_bounds
            )
            spoken_end_offset = min(duration, max(0.0, spoken_end_offset))
        segment["speech_end_at"] = float(start + spoken_end_offset)

        if player_id is not None:
            reveal_at = float(start) + float(segment.get("name_time") or 0.0)
            segment["reveal_at"] = reveal_at

            if str(segment.get("kind", "")) == "starter":
                segment["hero_on"] = reveal_at
                if is_first_player:
                    if abs(reveal_at - float(timing["first_player_at"])) > 1e-6:
                        raise RuntimeError("Goalkeeper reveal drifted from the measured Ryan spoken-name beat.")
                    goalkeeper_card_exit = max(
                        float(reveal_at) + 0.50,
                        float(segment["speech_end_at"]) + 0.25,
                    )
                    timing["goalkeeper_card_out"] = float(goalkeeper_card_exit)
                    segment["hero_exit_at"] = float(goalkeeper_card_exit)
                else:
                    # The explanation completes first; the card then eases away.
                    segment["hero_exit_at"] = float(segment["t1"])
                segment["hero_off"] = (
                    float(segment["hero_exit_at"])
                    + float(timing["hero_fade_out"])
                )
            else:
                # Substitute cards persist in their own dock; no temporary hero.
                segment.pop("hero_on", None)
                segment.pop("hero_exit_at", None)
                segment.pop("hero_off", None)

        # Edge TTS commonly leaves ~0.8s of silence after its last word.
        # Schedule from the spoken end plus a small natural gap; the MP3 tail may
        # overlap because it contains silence, not narration.
        cursor = min(
            float(segment["t1"]),
            float(segment.get("speech_end_at", segment["t1"])) + 0.35,
        )

    if not first_player_seen:
        raise RuntimeError("Goalkeeper narration segment is missing from GW Review.")

    narration_end = cursor
    total = narration_end + float(timing["final_hold"])
    return {
        "narration_end": narration_end,
        "final_hold_at": narration_end,
        "total": total,
        "first_starter_id": first_starter_id,
    }


GW_REVIEW_TIMELINE = _vx_build_review_timeline(
    pkg, GW_REVIEW_ANIMATION_TIMING
)
NARRATION_END = float(GW_REVIEW_TIMELINE["narration_end"])
TOTAL = float(GW_REVIEW_TIMELINE["total"])

# ------------------------------------------------------------
# 2B. SQUAD-REVEAL SYNC QA
# ------------------------------------------------------------

_player_sync_segments=[s for s in pkg["segments"] if s.get("player_id")]
_expected_sync_ids=[
    int(p["id"])
    for p in (pkg["starters"]+pkg["bench"])
]
_actual_sync_ids=[int(s["player_id"]) for s in _player_sync_segments]

if _actual_sync_ids != _expected_sync_ids:
    raise RuntimeError(
        "GW Review sync order mismatch: "
        f"expected {_expected_sync_ids}, got {_actual_sync_ids}"
    )

for s in _player_sync_segments:
    if not (float(s["t0"]) <= float(s["reveal_at"]) < float(s["t1"])):
        raise RuntimeError(f"Reveal outside narration window: {s['id']}")
    if s.get("kind") == "starter":
        if abs(float(s["hero_on"])-float(s["reveal_at"])) > 1e-6:
            raise RuntimeError(f"Hero/pitch reveal not aligned to Ryan name: {s['id']}")
        if not (
            float(s["hero_on"])
            < float(s["hero_exit_at"])
            < float(s["hero_off"])
        ):
            raise RuntimeError(f"Hero window invalid: {s['id']}")
    elif any(key in s for key in ("hero_on", "hero_exit_at", "hero_off")):
        raise RuntimeError(f"Bench segment incorrectly owns a temporary hero: {s['id']}")

# Segment ``t1`` includes Edge TTS's trailing MP3 silence.  The timeline
# intentionally overlaps that silent tail with the next segment, so the data
# board must be gated by the last spoken word rather than the audio container's
# duration.  ``speech_end_at`` is measured from WordBoundary events above and
# falls back to ``t1`` for providers that do not return word timing.
_last_player_speech_end=max(
    float(s.get("speech_end_at", s["t1"]))
    for s in _player_sync_segments
)
_metrics_seg=next(
    (s for s in pkg["segments"] if s["id"]=="metrics_intro"),
    None
)
if (
    _metrics_seg is None
    or float(_metrics_seg["t0"]) < _last_player_speech_end-1e-6
):
    raise RuntimeError("Full data board is scheduled before the final bench review ends.")

print("✅ GW Review sync QA: Ryan name = hero reveal = player reveal")
print("✅ Player images persist; only hero windows end")
print("✅ Full data board begins after the final reserve")
print("✅ Opening: logo/title/pitch animate from frame zero; goalkeeper follows the spoken headline without an eight-second gate")

# ------------------------------------------------------------
# 3. PLACE RYAN SEGMENTS ON THE CONFIGURABLE MASTER TIMELINE
# ------------------------------------------------------------

MASTER_MP3.parent.mkdir(parents=True, exist_ok=True)
_review_audio_inputs = []
_review_audio_filters = []
_review_audio_labels = []

for _audio_index, _segment in enumerate(pkg["segments"]):
    _review_audio_inputs += ["-i", str(Path(_segment["audio"]))]
    _delay_ms = max(0, int(round(float(_segment["t0"]) * 1000.0)))
    _label = f"review{_audio_index}"
    _review_audio_filters.append(
        f"[{_audio_index}:a]aresample=48000,"
        f"adelay=delays={_delay_ms}:all=1[{_label}]"
    )
    _review_audio_labels.append(f"[{_label}]")

_review_audio_filters.append(
    "".join(_review_audio_labels)
    + f"amix=inputs={len(_review_audio_labels)}:duration=longest:normalize=0,"
      f"apad=pad_dur={float(GW_REVIEW_ANIMATION_TIMING['final_hold']):.6f},"
      f"atrim=start=0:end={TOTAL:.6f}[reviewmaster]"
)

subprocess.run(
    [
        "ffmpeg", "-y", "-v", "error",
        *_review_audio_inputs,
        "-filter_complex", ";".join(_review_audio_filters),
        "-map", "[reviewmaster]",
        "-c:a", "libmp3lame",
        "-b:a", "192k",
        "-ar", "48000",
        str(MASTER_MP3),
    ],
    check=True,
)

MASTER_AUDIO_DURATION = float(vx_media_duration(MASTER_MP3))
if abs(MASTER_AUDIO_DURATION - TOTAL) > 0.12:
    raise RuntimeError(
        "GW Review master audio drifted from its visual timeline: "
        f"audio={MASTER_AUDIO_DURATION:.3f}s, timeline={TOTAL:.3f}s"
    )

# ------------------------------------------------------------
# 4. VTT
# ------------------------------------------------------------

def ts(t):
    ms = round(t*1000)
    h,ms = divmod(ms,3600000)
    m,ms = divmod(ms,60000)
    sec,ms = divmod(ms,1000)
    return f"{h:02}:{m:02}:{sec:02}.{ms:03}"

vtt = ["WEBVTT",""]

for i,s in enumerate(pkg["segments"],1):
    vtt += [
        str(i),
        f"{ts(s['t0'])} --> {ts(s['t1'])}",
        s["text"],
        ""
    ]

MASTER_VTT.write_text(
    "\n".join(vtt),
    encoding="utf-8"
)

# ------------------------------------------------------------
# 5. TIMING LOOKUPS
# ------------------------------------------------------------

def seg(name):
    return next(
        (x for x in pkg["segments"] if x["id"] == name),
        None
    )

bench_intro  = seg("bench_intro")
metrics_intro = seg("metrics_intro")

metric_map = {}

for sid,key in [
    ("metric_points","points"),
    ("metric_orank","orank"),
    ("metric_gwrank","gwrank"),
    ("metric_captain","captain"),
    ("metric_bench","bench"),
    ("metric_hit","hit"),
]:
    s = seg(sid)
    if s:
        metric_map[key] = [s["t0"],s["t1"]]

# ------------------------------------------------------------
# 6. REVIEW DATA FOR JAVASCRIPT
# ------------------------------------------------------------

JS_DATA = {
    "gw":pkg["gw"],
    "starters":pkg["starters"],
    "bench":pkg["bench"],
    "segments":pkg["segments"],
    "total":TOTAL,
    "narration_end":NARRATION_END,
    "timeline":GW_REVIEW_ANIMATION_TIMING,

    "bench_t":bench_intro["t0"] if bench_intro else TOTAL,
    "metrics_t":metrics_intro["t0"] if metrics_intro else TOTAL,

    "metric_times":metric_map,
}

# ------------------------------------------------------------
# 7. PREMIUM REVIEW CSS
# ------------------------------------------------------------

CSS = r"""
<!-- VX_REVIEW_START -->
<style id="vx-review-css">

/* The original approved HTML panels remain the sole left-column design. */
.left > .panel{
    opacity:0 !important;
    pointer-events:none !important;
    transform:translateY(34px) scale(.985);
    transform-origin:center center;
    will-change:opacity,transform,filter,box-shadow;
}

.benchPanel .mini{
    opacity:0;
    transform:translateY(28px) scale(.88);
    transform-origin:center bottom;
    will-change:opacity,transform;
}

.reviewPanel .metric{
    transform-origin:center center;
    will-change:transform,filter,box-shadow;
}

.analysisRibbon{
    display:none !important;
}

/* Persistent broadcast furniture is present at frame zero. */
.brand,
.footer{
    opacity:1 !important;
}

/* Every staged element begins hidden; window.__seek owns all motion. */
.plBug{
    opacity:0;
    transform:translateY(-18px) scale(.94);
    transform-origin:top right;
    will-change:opacity,transform;
}

.pitch,
.pitchGlow,
.pitchSvg{
    opacity:0;
    transform:translateY(34px) scale(.975);
    transform-origin:center center;
    will-change:opacity,transform;
}

.pitchHeader{
    opacity:0;
    will-change:opacity,transform;
}

/* player pitch cards initially invisible */
.playerCard{
    opacity:0;
    will-change:transform,opacity,filter;
}

/* -------------------------------------------------------
   HERO CARD SLOT ONLY
   Internal card design is owned by CELL 15A — PLAYER CARD DESIGN.
   This slide controls only placement / available space.
   ------------------------------------------------------- */

#vxHeroWrap{
    position:absolute;
    /* 4K safe hero region: stage-left -> pitch boundary,
       18px below the logo -> 18px above the footer.
       Parent .left is x=54,y=428,w=1202,h=1642; pitch starts x=1286. */
    left:-54px;
    right:-30px;
    top:-4px;
    bottom:-3px;
    z-index:95;
    display:flex;
    align-items:stretch;
    justify-content:stretch;
    overflow:hidden;
    opacity:0;
    pointer-events:none;
    transform:translateY(45px);
    will-change:opacity,transform;
}

#vxHeroWrap > .vx-player-card{
    flex:1 1 auto;
    width:100%;
    height:100%;
}

</style>
"""

# ------------------------------------------------------------
# 8. DETERMINISTIC REVIEW ENGINE
# ------------------------------------------------------------

JS = r"""
<script id="vx-review-engine">

const VX = __VX_DATA__;
window.VX = VX;

function $v(q){ return document.querySelector(q); }

function escv(x){
    return String(x ?? "")
      .replaceAll("&","&amp;")
      .replaceAll("<","&lt;")
      .replaceAll(">","&gt;");
}

function clamp(x,a=0,b=1){
    return Math.max(a,Math.min(b,x));
}

function ease(x){
    x=clamp(x);
    return 1-Math.pow(1-x,3);
}

/* -------------------------------------------------------
   BUILD PITCH XI
   ------------------------------------------------------- */

function vxPitchPhotoFallback(img,code){
    img.style.display="none";
    const avatar=img.nextElementSibling;
    if(avatar) avatar.style.display="flex";
}

function pitchCard(p){

    const crest = p.team_code
      ? `<img class="teamCrest"
           src="https://resources.premierleague.com/premierleague/badges/70/t${p.team_code}.png"
           onerror="this.style.display='none'">`
      : "";

    const badge = p.captain
      ? `<div class="badge">C</div>`
      : p.vice
      ? `<div class="badge vc">VC</div>`
      : "";

    const photo = p.photo
      ? `<img class="vxPitchPlayerImg"
           src="${escv(p.photo)}"
           onerror="vxPitchPhotoFallback(this,${Number(p.code||0)})">`
      : "";

    const avatar = `<div class="avatarFallback"
         style="${p.photo?"display:none":"display:flex"}">${escv(initials(p.name))}</div>`;

    return `
    <div
      id="vxp_${p.id}"
      class="playerCard ${p.captain?"captain":""} ${p.vice?"vice":""}"
      style="left:${p.pitch_x}%;top:${p.pitch_y}%;opacity:0">

      ${badge}

      <div class="photoZone">
        ${photo}
        ${avatar}
        ${crest}
      </div>

      <div class="playerName">${escv(p.name)}</div>

      <div class="playerMeta">
        ${escv(p.fixture.opp)} (${escv(p.fixture.ha)})
        <span class="tinyScore">${escv(p.pos)}</span>
      </div>

      <div class="points ${pointsClass(p.points)}">
        ${p.points}
      </div>

    </div>`;
}

/* -------------------------------------------------------
   INITIAL BUILD
   ------------------------------------------------------- */

function buildReview(){

    const players=$v("#players");
    players.innerHTML=VX.starters.map(p=>pitchCard(p)).join("");

    const left=$v(".left");

    left.insertAdjacentHTML(
      "beforeend",
      `<div id="vxHeroWrap"></div>`
    );

    const benchCards=[...document.querySelectorAll(".benchPanel .mini")];
    if(benchCards.length!==VX.bench.length){
        throw new Error(
          `Approved HTML bench-card count ${benchCards.length} does not match review data ${VX.bench.length}`
        );
    }
    benchCards.forEach((el,index)=>{
        el.id=`vxb_${VX.bench[index].id}`;
    });

    const metricSelectors={
      points:"#gwPoints",
      orank:"#overallRank",
      gwrank:"#gwRank",
      captain:"#captainReturn",
      bench:"#benchPoints",
      hit:"#hitPoints"
    };
    Object.entries(metricSelectors).forEach(([key,selector])=>{
        const metric=$v(selector)?.closest(".metric");
        if(!metric) throw new Error(`Approved HTML metric block missing: ${key}`);
        metric.dataset.vxMetricKey=key;
    });

    $v("#pitchGW").textContent=`GAMEWEEK ${VX.gw} REVIEW`;
    $v("#entryName").textContent="— FPL VORTEX";
    const footerGW=$v("#footerGW");
    if(footerGW) footerGW.textContent=`GAMEWEEK ${VX.gw} REVIEW`;
    $v("#loading").classList.add("hide");

    window.__ready=true;
    window.__seek(0);
}

/* -------------------------------------------------------
   EXACT SEEK ENGINE
   ------------------------------------------------------- */

window.__seek=function(t){

    t=clamp(Number(t)||0,0,VX.total);

    const timing=VX.timeline || {};

    /* ---------- FIXED OPENING BEATS ---------- */

    const pl=$v(".plBug");
    if(pl){
        const p=ease((t-Number(timing.premier_league_logo_at ?? 0))/.46);
        pl.style.opacity=p;
        pl.style.transform=`translateY(${(1-p)*-18}px) scale(${.94+.06*p})`;
    }

    const title=$v(".pitchHeader");
    if(title){
        const p=ease((t-Number(timing.review_title_at ?? 0))/.52);
        title.style.opacity=p;
        title.style.setProperty(
          "transform",
          `translateY(${(1-p)*24}px) scale(${.95+.05*p})`,
          "important"
        );
    }

    const pitchP=ease((t-Number(timing.pitch_at ?? 0))/.62);
    document.querySelectorAll(".pitch,.pitchGlow,.pitchSvg").forEach(el=>{
        el.style.opacity=pitchP;
        el.style.transform=
          `translateY(${(1-pitchP)*34}px) scale(${.975+.025*pitchP})`;
    });

    /* ---------- STARTING XI ---------- */

    VX.segments
      .filter(s=>s.player_id && s.kind==="starter")
      .forEach(s=>{

        const el=$v(`#vxp_${s.player_id}`);

        if(!el) return;

        const p=ease(
          (t-s.reveal_at)/Number(timing.entrance_duration||.42)
        );

        el.style.opacity=p;

        el.style.transform=
          `translate(-50%,-50%) scale(${.70+.30*p})`;

        el.style.filter=
          p>0 && p<1
          ? `brightness(${1+.45*(1-p)})`
          : "";
    });

    /* ---------- BENCH ---------- */

    const benchPanel=$v(".benchPanel");
    const benchPanelP=ease((t-VX.bench_t)/.46);
    benchPanel.style.setProperty("opacity",benchPanelP,"important");
    benchPanel.style.transform=
      `translateY(${(1-benchPanelP)*28}px) scale(${.985+.015*benchPanelP})`;

    VX.segments
      .filter(s=>s.player_id && s.kind==="bench")
      .forEach(s=>{

        const el=$v(`#vxb_${s.player_id}`);
        if(!el) return;

        const p=ease(
          (t-s.reveal_at)/Number(timing.entrance_duration||.42)
        );

        el.style.opacity=p;
        el.style.transform=
          `translateY(${(1-p)*30}px) scale(${.85+.15*p})`;
    });

    /* ---------- TEMP HERO ---------- */

    const heroSeg = VX.segments
      .filter(
        s =>
          s.player_id &&
          s.kind==="starter" &&
          t >= s.hero_on &&
          t < s.hero_off
      )
      .sort((a,b)=>Number(b.hero_on)-Number(a.hero_on))[0];

    const hw=$v("#vxHeroWrap");

    if(heroSeg && t < VX.metrics_t){

        const all=[...VX.starters,...VX.bench];

        const p=all.find(
          x=>x.id===heroSeg.player_id
        );

        if(p){

            if(hw.dataset.pid != String(p.id)){
                if(!window.VXPlayerCard || typeof window.VXPlayerCard.mount !== "function"){
                    throw new Error("PLAYER CARD DESIGN runtime missing. Run Cell 15A before Cell 16.");
                }
                window.VXPlayerCard.mount(hw, p.card || p);
                hw.dataset.pid=String(p.id);
            }

            const ein=ease(
              (t-heroSeg.hero_on)/Number(timing.hero_fade_in||.32)
            );

            const eout=t < heroSeg.hero_exit_at
              ? 1
              : 1-ease(
                  (t-heroSeg.hero_exit_at) /
                  Math.max(.01,heroSeg.hero_off-heroSeg.hero_exit_at)
                );

            const vis=Math.min(ein,eout);

            hw.style.opacity=vis;

            hw.style.transform=
              `translateY(${(1-vis)*34}px)`;
        }
    }
    else{
        hw.style.opacity=0;
    }

    /* ---------- APPROVED LEFT PANELS + NARRATED TABLE EMPHASIS ---------- */

    const panelsP=ease(
      (t-VX.metrics_t)/Number(timing.table_reveal_duration||.58)
    );
    document.querySelectorAll(".reviewPanel,.chipsPanel,.fixturesPanel").forEach(el=>{
        el.style.setProperty("opacity",panelsP,"important");
        el.style.transform=
          `translateY(${(1-panelsP)*38}px) scale(${.985+.015*panelsP})`;
    });

    document.querySelectorAll(".reviewPanel .metric").forEach(el=>{
        el.style.transform="none";
        el.style.filter="";
        el.style.boxShadow="";
    });

    const metricEntries=Object.entries(VX.metric_times||{})
      .map(([key,span])=>({
        key,
        start:Number(span?.[0]||0),
        end:Number(span?.[1]||0)
      }))
      .filter(item=>Number.isFinite(item.start))
      .sort((a,b)=>a.start-b.start);

    const emphasisDuration=Math.max(
      .01,
      Number(timing.metric_highlight_duration||1.15)
    );

    let activeMetric=null;
    for(let index=0;index<metricEntries.length;index++){
        const item=metricEntries[index];
        const nextStart=index+1<metricEntries.length
          ? metricEntries[index+1].start
          : Infinity;
        const narratedEnd=(
          Number.isFinite(item.end) && item.end>item.start
        )
          ? item.end
          : item.start+emphasisDuration;
        const pulseEnd=Math.min(
          item.start+emphasisDuration,
          narratedEnd,
          nextStart
        );
        if(t>=item.start && t<pulseEnd){
            activeMetric={...item,pulseEnd};
            break;
        }
    }

    if(activeMetric){
        const span=Math.max(
          .01,
          activeMetric.pulseEnd-activeMetric.start
        );
        const p=Math.sin(
          clamp((t-activeMetric.start)/span)*Math.PI
        );
        if(p>0){
            const el=document.querySelector(
              `.reviewPanel .metric[data-vx-metric-key="${activeMetric.key}"]`
            );
            if(el){
                el.style.transform=`translateY(${-8*p}px) scale(${1+.025*p})`;
                el.style.filter=`brightness(${1+.14*p}) saturate(${1+.12*p})`;
                el.style.boxShadow=`0 0 ${18+30*p}px rgba(255,190,25,${.18+.32*p})`;
            }
        }
    }

    document.documentElement.dataset.vortexTime=t.toFixed(3);

    return t;
};

window.__auditLayout=function(t){

    window.__seek(t);

    return {
      time:t,
      viewport:[innerWidth,innerHeight],
      scroll:[
        document.documentElement.scrollWidth,
        document.documentElement.scrollHeight
      ],
      brand:Number(getComputedStyle($v(".brand")).opacity||0),
      footer:Number(getComputedStyle($v(".footer")).opacity||0),
      pitchPlayers:
        [...document.querySelectorAll(".playerCard")]
        .filter(x=>Number(x.style.opacity)>.5).length,
      plLogo:Number($v(".plBug")?.style.opacity||0),
      title:Number($v(".pitchHeader")?.style.opacity||0),
      pitch:Number($v(".pitch")?.style.opacity||0),
      hero:Number($v("#vxHeroWrap")?.style.opacity||0),
      benchCards:[...document.querySelectorAll(".benchPanel .mini")]
        .filter(x=>Number(x.style.opacity)>.5).length,
      table:Number(getComputedStyle($v(".reviewPanel")).opacity||0),
      chipsPanel:Number(getComputedStyle($v(".chipsPanel")).opacity||0),
      fixturePanel:Number(getComputedStyle($v(".fixturesPanel")).opacity||0),
      benchPanel:Number(getComputedStyle($v(".benchPanel")).opacity||0),
      activeMetrics:[...document.querySelectorAll(".reviewPanel .metric")]
        .filter(x=>Boolean(x.style.boxShadow))
        .map(x=>String(x.dataset.vxMetricKey||""))
    };
};

if(document.readyState==="loading")
    document.addEventListener("DOMContentLoaded",buildReview);
else
    buildReview();

</script>
<!-- VX_REVIEW_END -->
"""

# ------------------------------------------------------------
# 9. INJECT INTO CELL 14 PITCH HTML
# ------------------------------------------------------------

html = SRC_HTML.read_text(
    encoding="utf-8",
    errors="ignore"
)

# remove previous Cell16 injection if rerun
html = re.sub(
    r"<!-- VX_REVIEW_START -->.*?"
    r"<!-- VX_REVIEW_END -->",
    "",
    html,
    flags=re.S
)

# Disable original page's automatic live render.
# Cell 15 is now the authoritative review-data source.
html = re.sub(
    r"\(async\(\)=>\{\s*"
    r"if\(CONFIG\.forceDemo\).*?"
    r"\}\)\(\);",
    "",
    html,
    flags=re.S
)

html = html.replace(
    "</head>",
    PLAYER_CARD_CSS + "\n" + CSS + "\n</head>"
)

html = html.replace(
    "</body>",
    PLAYER_CARD_JS + "\n" +
    JS.replace(
        "__VX_DATA__",
        json.dumps(JS_DATA,ensure_ascii=False)
    )
    + "\n</body>"
)

html = vx_polish_branding(html)

ANIM_HTML.write_text(
    html,
    encoding="utf-8"
)

# ------------------------------------------------------------
# 10. SAVE ANIMATION MANIFEST
# ------------------------------------------------------------

_review_motion_windows = [
    {
        "id":"premier_league_logo",
        "start":GW_REVIEW_ANIMATION_TIMING["premier_league_logo_at"],
        "end":GW_REVIEW_ANIMATION_TIMING["premier_league_logo_at"] + 0.46,
    },
    {
        "id":"review_title",
        "start":GW_REVIEW_ANIMATION_TIMING["review_title_at"],
        "end":GW_REVIEW_ANIMATION_TIMING["review_title_at"] + 0.52,
    },
    {
        "id":"soccer_pitch",
        "start":GW_REVIEW_ANIMATION_TIMING["pitch_at"],
        "end":GW_REVIEW_ANIMATION_TIMING["pitch_at"] + 0.62,
    },
]

for _segment in pkg["segments"]:
    if _segment.get("player_id") is not None:
        _review_motion_windows.append({
            "id":f"player_{_segment['player_id']}_reveal",
            "start":float(_segment["reveal_at"]),
            "end":float(_segment["reveal_at"])
                  + GW_REVIEW_ANIMATION_TIMING["entrance_duration"],
        })
    if _segment.get("kind") == "starter":
        _review_motion_windows.append({
            "id":f"hero_{_segment['player_id']}_in",
            "start":float(_segment["hero_on"]),
            "end":float(_segment["hero_on"])
                  + GW_REVIEW_ANIMATION_TIMING["hero_fade_in"],
        })
        _review_motion_windows.append({
            "id":f"hero_{_segment['player_id']}_out",
            "start":float(_segment["hero_exit_at"]),
            "end":float(_segment["hero_off"]),
        })

_review_motion_windows.append({
    "id":"approved_substitutes_panel",
    "start":float(JS_DATA["bench_t"]),
    "end":float(JS_DATA["bench_t"]) + 0.46,
})
_review_motion_windows.append({
    "id":"approved_left_information_panels",
    "start":float(JS_DATA["metrics_t"]),
    "end":float(JS_DATA["metrics_t"])
          + GW_REVIEW_ANIMATION_TIMING["table_reveal_duration"],
})

_metric_items = list(metric_map.items())
for _metric_index, (_metric_key, _metric_span) in enumerate(_metric_items):
    _metric_start = float(_metric_span[0])
    _metric_end = float(_metric_span[1])
    _next_metric_start = (
        float(_metric_items[_metric_index + 1][1][0])
        if _metric_index + 1 < len(_metric_items)
        else float("inf")
    )
    _review_motion_windows.append({
        "id":f"metric_{_metric_key}_highlight",
        "start":_metric_start,
        "end":min(
            _metric_end,
            _metric_start
            + GW_REVIEW_ANIMATION_TIMING["metric_highlight_duration"],
            _next_metric_start,
        ),
    })

manifest = {
    "html":str(ANIM_HTML),
    "audio":str(MASTER_MP3),
    "vtt":str(MASTER_VTT),
    "duration":TOTAL,
    "audio_duration":MASTER_AUDIO_DURATION,
    "narration_end":NARRATION_END,
    "final_hold_start":NARRATION_END,
    "final_hold_seconds":GW_REVIEW_ANIMATION_TIMING["final_hold"],
    "canvas":[3840,2160],
    "gw":pkg["gw"],
    "starting_xi":len(pkg["starters"]),
    "bench":len(pkg["bench"]),
    "first_starter_id":GW_REVIEW_TIMELINE["first_starter_id"],
    "timeline":GW_REVIEW_ANIMATION_TIMING,
    "metric_times":metric_map,
    "motion_windows":_review_motion_windows,
    "segments":pkg["segments"]
}

(TIMING/"gw_review_animation_manifest.json").write_text(
    json.dumps(manifest,indent=2),
    encoding="utf-8"
)

print("✅ GW REVIEW ANIMATION READY")
print(f"✅ GW: {pkg['gw']}")
print("✅ Frame zero: header + channel logo + footer only")
print("✅ Gameweek Review logo, title and pitch animate immediately from frame zero")
print("✅ Ryan-name → player pitch reveal")
print("✅ Player remains on pitch")
print("✅ Responsive CELL 15A hero card appears on the spoken name")
print("✅ Hero disappears after explanation")
print("✅ Approved HTML substitutes panel builds one card at a time and persists")
print("✅ Original review, chips and fixture panels reveal without redesign")
print("✅ Original six-cell review table highlights by narration")
print(f"✅ Final completed composition hold: {GW_REVIEW_ANIMATION_TIMING['final_hold']:.2f}s")
print(f"✅ Total review duration: {TOTAL:.2f}s")
print("✅ HTML:",ANIM_HTML)
print("✅ AUDIO:",MASTER_MP3)
