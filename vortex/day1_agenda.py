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
        # Preserve exactly the same FIVE original Day 1 agenda card slots.
        # These are topic labels (not invented player or transfer claims), and
        # their narration anchors are verified against the spoken intro.
        has_market = "market_intro" in available
        has_comparison = "editorial_comparison" in available
        target_key = "market" if has_market else "alternatives" if has_comparison else "tradeoffs"
        if has_market:
            targets_sub = "OFFICIAL MARKET MOVEMENT / VERIFY FIXTURES & MINUTES"
            targets_speech = (
                "Transfer targets: buy, hold and sell player cards show current market watchlists. "
                "They are not personalized transfers without verified bank and team news."
            )
        elif has_comparison:
            targets_sub = "VORTEX MODEL / CURRENT PRICE / EXPECTED MINUTES"
            targets_speech = (
                "Transfer targets: compare a model-backed alternative "
                "against the existing squad before deciding to buy, hold or sell."
            )
        else:
            targets_sub = "NO VERIFIED BUY / HOLD IS A REAL OPTION"
            targets_speech = (
                "Transfer targets: no supported replacement is confirmed, "
                "so buy, hold and sell remain conditional on new evidence."
            )
        return [
            _card("review", "GAMEWEEK REVIEW — THE REAL STORY",
                  f"GW{int(review_gw)} / {status}",
                  "Gameweek review",
                  "Gameweek review: the real story is what the verified returns say about our next decision."),
            _card("squad", "SQUAD PRESSURE — WHAT NEEDS FIXING?",
                  "OFFICIAL FLAGS / MINUTES / BENCH COVER",
                  "Squad pressure",
                  "Squad pressure: which genuine availability or minutes issues need fixing first?"),
            _card(target_key, "TRANSFER TARGETS — BUY / HOLD / SELL",
                  targets_sub, "Transfer targets", targets_speech),
            _card("routes", "TRANSFER PLANS — ROLL, MOVE OR TAKE A HIT?",
                  "BANK IF SAFE / FIX A WEAKNESS / HITS NEED EVIDENCE",
                  "Transfer plans",
                  "Transfer plans: roll, move or take a hit? Compare the routes against actual minutes, budget and risk."),
            _card("verdict", "THE FINAL VORTEX VERDICT",
                  "CONDITIONAL / FACT-CHECKED / ONE DECISION",
                  "Final Vortex verdict",
                  "Final Vortex verdict: one conditional decision, with the team-news trigger that could change it."),
        ]
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



# Premium light treatment is scoped ONLY to the existing intro agenda.
# Player-card CSS and entrance/exit animation remain exactly unchanged.
PREMIUM_AGENDA_CSS = """
<style id="vx-day1-agenda-premium">
.agendaWrap .agenda-card {
  background:linear-gradient(135deg,#ffffff 0%,#f4f8fb 100%)!important;
  border:2px solid rgba(103,170,188,.32)!important;
  border-radius:24px!important;
  box-shadow:0 12px 38px rgba(0,8,24,.22),inset 0 1px 0 #fff!important;
}
.agendaWrap .agenda-card:nth-child(even) {
  background:linear-gradient(135deg,#fbfdff 0%,#eaf5fa 100%)!important;
  border-color:rgba(196,156,70,.32)!important;
}
.agendaWrap .agendaNum {
  color:#aa8029!important;font-weight:900!important;
  font-variant-numeric:tabular-nums;
}
.agendaWrap .agenda-card:nth-child(even) .agendaNum{color:#168ea7!important}
.agendaWrap .agenda-title {
  color:#152337!important;text-shadow:none!important;
  font-size:52px!important;letter-spacing:.45px!important;
  font-weight:950!important;
}
.agendaWrap .agenda-sub {
  color:#557083!important;font-weight:850!important;
  font-size:27px!important;letter-spacing:1.15px!important;
}
.agendaWrap .agendaAccent {
  background:linear-gradient(180deg,#17a6bf,#cfad59)!important;
  width:7px!important;box-shadow:none!important;
}
</style>
"""

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
    return PREMIUM_AGENDA_CSS + "\n" + "\n".join(rows)
