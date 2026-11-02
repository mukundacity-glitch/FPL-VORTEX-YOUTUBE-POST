"""Evidence-backed Day 1 introduction: selected scenes determine the visual and spoken agenda."""
from __future__ import annotations
from html import escape


def _card(key, title, subtitle, anchor, speech):
    if anchor.casefold() not in speech.casefold():
        raise ValueError("Missing spoken anchor for " + key)
    return dict(key=key, title=title, subtitle=subtitle, anchor=anchor, speech=speech)


def build_intro_agenda(selected_scenes, *, next_gw, review_gw=None, review_status=None, review_segments=None):
    if not 1 <= int(next_gw) <= 38:
        raise ValueError("Invalid upcoming gameweek")
    selected = list(dict.fromkeys(selected_scenes))
    if "00_intro" not in selected:
        return []
    others = [key for key in selected if key not in {"00_intro", "05_outro", "gw_review"}]
    allowed = {"02_fdr", "03_projected_goals", "04_clean_sheets"}
    if not set(others) <= allowed:
        raise ValueError("Unknown sections in intro agenda")
    cards = []
    if "gw_review" in selected:
        if review_gw is None or not 1 <= int(review_gw) < int(next_gw):
            raise ValueError("Review and next gameweek are inconsistent")
        available = {str(item.get("id") or "") for item in (review_segments or [])}
        necessary = {"headline", "editorial_squad_context", "editorial_routes", "editorial_verdict"}
        if not necessary <= available:
            raise ValueError("Review agenda references missing editorial sections")
        status = "RESULTS MAY CHANGE" if str(review_status or "").upper() not in {"COMPLETE", "FINAL"} else "OFFICIALLY RECORDED RETURNS"
        cards.extend([
            _card("review", f"GW{int(review_gw)} • GAMEWEEK REVIEW", status,
                  "Gameweek review", "Gameweek review: the points that count, and what the score might be hiding."),
            _card("squad", "SQUAD PRESSURE", "MINUTES / TEAM NEWS / BENCH COVER",
                  "Squad pressure", "Squad pressure: the minutes and cover issues worth checking before a transfer."),
        ])
        if not others:
            if "editorial_comparison" in available:
                cards.append(_card("alternatives", "REALISTIC ALTERNATIVES", "MODEL EVIDENCE / MINUTES / RISK",
                    "Realistic alternatives", "Realistic alternatives: one supported comparison, with the risks still in view."))
            elif "editorial_tradeoff" in available:
                cards.append(_card("tradeoffs", "THE TRADE-OFFS", "FIXTURES / MINUTES / FLEXIBILITY",
                    "The trade-offs", "The trade-offs: a friendly fixture isn't enough if the player might not start."))
            cards.extend([
                _card("routes", "HOLD OR MAKE A MOVE?", "ROLL / ONE TRANSFER / HIT",
                      "Transfer routes", "Transfer routes: when holding makes sense, and when spending a transfer solves something."),
                _card("verdict", "FINAL VERDICT", "CHECK THE TEAM NEWS FIRST",
                      "Final verdict", "Final verdict: what needs confirming before making a decision."),
            ])
    known = {
        "02_fdr": ("fixtures", "FIXTURE SWINGS", "THE NEXT RUN OF OPPONENTS", "Fixture swings",
                   "Fixture swings: which schedules genuinely improve, and which ones look tougher."),
        "03_projected_goals": ("goals", "ATTACKING FORECASTS", "ESTIMATES ARE NOT GUARANTEES", "Attacking forecasts",
                                "Attacking forecasts: where the chances might come from, without promising points."),
        "04_clean_sheets": ("defence", "CLEAN-SHEET CHANCES", "STARTING MINUTES STILL MATTER", "Clean-sheet chances",
                            "Clean-sheet chances: numbers only help when the player is likely to start."),
    }
    cards.extend(_card(*known[scene]) for scene in others)
    if not cards:
        cards = [_card("overview", "THE NEXT DECISION", "VERIFY THE FACTS FIRST",
                       "Next decision", "Next decision: only verified facts belong in this week's plan.")]
    if len(cards) > 5:
        raise ValueError("Intro agenda exceeds five readable cards")
    anchors = [card["anchor"].lower() for card in cards]
    if len(set(anchors)) != len(anchors):
        raise ValueError("Agenda has ambiguous narration anchors")
    return cards


def spoken_intro_agenda(cards):
    return " ".join(card["speech"] for card in cards)


def render_intro_agenda(cards):
    rows = []
    for i, card in enumerate(cards, 1):
        title = escape(card["title"], quote=True)
        subtitle = escape(card["subtitle"], quote=True)
        rows.append(
            f'<div class="agenda-card agenda-{i}" data-agenda="{escape(card["key"], quote=True)}">'
            f'<div class="agendaNum">{i:02d}</div><div class="agendaCopy">'
            f'<div class="agenda-title" data-vx-type="{title}">{title}</div>'
            f'<div class="agenda-sub">{subtitle}</div></div>'
            '<div class="agendaAccent" aria-hidden="true"></div></div>'
        )
    return "\n".join(rows)
