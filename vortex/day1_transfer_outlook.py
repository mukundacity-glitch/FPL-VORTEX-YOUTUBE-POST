"""Scene 4 transfer tables and evidence-led narration from a single FPL snapshot."""
from datetime import datetime, timezone
from html import escape
import json
from pathlib import Path

from .day1_player_hero import number
from .football_identity import full_club_name

ROWS = 6
SPOKEN_ROWS = 3
NARRATION_LIMIT = 119
ORDINALS = ("first", "second", "third")
AVAILABILITY = {"i": "injured", "s": "suspended", "u": "unavailable", "n": "unavailable"}


def _count(value):
    parsed = number(value)
    return int(parsed) if parsed is not None and parsed >= 0 and parsed.is_integer() else None


def build_outlook(bootstrap, fixtures, gameweek, captured_at):
    next_event = [event["id"] for event in bootstrap["events"] if event.get("is_next")]
    if next_event != [gameweek]:
        raise ValueError("Transfer snapshot does not match the official upcoming gameweek")
    teams = {team["id"]: team for team in bootstrap["teams"]}
    positions = {p["id"]: (p["singular_name"], p["singular_name_short"])
                 for p in bootstrap["element_types"]}
    upcoming = sorted((fixture for fixture in fixtures if fixture.get("event") == gameweek),
                      key=lambda match: (match.get("kickoff_time") or "", match["id"]))
    players = []
    for element in bootstrap["elements"]:
        incoming = _count(element.get("transfers_in_event"))
        outgoing = _count(element.get("transfers_out_event"))
        cost = _count(element.get("now_cost"))
        if incoming is None or outgoing is None or not element.get("web_name"):
            continue
        team_id = element["team"]
        position, short_position = positions[element["element_type"]]
        opponents = [full_club_name(teams[f["team_a"] if f["team_h"] == team_id else f["team_h"]], speech=True)
                     for f in upcoming if team_id in (f["team_h"], f["team_a"])]
        players.append({
            "id": element["id"], "name": element["web_name"], "team": team_id,
            "position": position, "short_position": short_position,
            "price": cost / 10 if cost is not None else None,
            "in": incoming, "out": outgoing, "net": incoming - outgoing,
            "form": number(element.get("form")), "status": element.get("status"),
            "chance": number(element.get("chance_of_playing_next_round")),
            "opponents": opponents, "element": element,
        })
    if not players:
        raise ValueError("Official FPL snapshot has no usable player transfer counts")
    return {
        "gameweek": gameweek, "captured": captured_at.astimezone(timezone.utc).isoformat(),
        "in": sorted((p for p in players if p["in"] > 0),
                     key=lambda p: (-p["in"], -p["net"], p["id"]))[:ROWS],
        "out": sorted((p for p in players if p["net"] < 0),
                      key=lambda p: (p["net"], -p["out"], p["id"]))[:ROWS],
    }


def _say_count(count):
    return f"{count:,}" if count < 10000 else f"about {round(count / 1000):,} thousand"


def _evidence(player, *, compact=False):
    chance = player["chance"]
    if status := AVAILABILITY.get(player["status"]):
        return f"FPL lists this player as {status}"
    if chance is not None and 0 <= chance < 100:
        return f"FPL gives this player a {chance:g} percent chance of playing"
    form = player["form"]
    if form is not None:
        return f"recent form is {form:g} points per match"
    if player["opponents"] and not compact:
        return f"the next opponent is {player['opponents'][0]}"
    if player["price"] is not None and not compact:
        return f"the current price is {player['price']:.1f} million pounds"
    return ""


def narration(board, name_for, *, compact=False):
    sells, buys = (board[side][:SPOKEN_ROWS] for side in ("out", "in"))
    remaining = dict(enumerate(buys))
    beats = []

    def beat(side, index, player, comparison=None):
        action = "sale" if side == "out" else "buy"
        anchor = f"The {ORDINALS[index]} {action}"
        name = name_for(player)
        line = f"{anchor} is {name}, with {_say_count(player[side])} moving {side}"
        if evidence := _evidence(player, compact=compact):
            line += f"; {evidence}"
        parts = [line + "."]
        if comparison and player["price"] is not None and comparison["price"] is not None:
            difference = round(player["price"] - comparison["price"], 1)
            if difference:
                parts.append(f"{name} is {abs(difference):.1f} million "
                             f"{'cheaper' if difference < 0 else 'more expensive'} than {name_for(comparison)}.")
        if comparison and not compact and player["form"] is not None and comparison["form"] is not None:
            gap = round(player["form"] - comparison["form"], 1)
            if abs(gap) >= 1:
                parts.append(f"{name} has {abs(gap):g} {'more' if gap > 0 else 'fewer'} form points per match than {name_for(comparison)}.")
        return {"anchor": anchor, "row": f"{side}-{player['id']}", "text": " ".join(filter(None, parts))}

    for index, sell in enumerate(sells):
        beats.append(beat("out", index, sell))
        paired = next((i for i, buy in remaining.items()
                       if buy["id"] != sell["id"] and buy["position"] == sell["position"]), None)
        if paired is not None:
            beats.append(beat("in", paired, remaining.pop(paired), sell))
    beats.extend(beat("in", i, buy) for i, buy in remaining.items())
    intro = f"The Gameweek {board['gameweek']} transfer market. The tables show separate totals by player."
    if not beats:
        intro += (" There is no official transfer activity to rank in this snapshot. "
                  "Check the tables again once the current gameweek window has recorded incoming and outgoing transfers.")
    return " ".join([intro, *(beat["text"] for beat in beats)]), beats


def render(board, cues, assets, captions, logo):
    def table(side, title, subtitle):
        entries = []
        for i, player in enumerate(board[side], 1):
            portrait, crest = assets[player["id"]]
            photo_html = f'<img class="portrait" src="{escape(portrait, quote=True)}" alt="">' if portrait else ""
            crest_html = f'<img class="crest" src="{escape(crest, quote=True)}" alt="">' if crest else ""
            price = f" · £{player['price']:.1f}m" if player["price"] is not None else ""
            net = player["net"]
            tone = "positive" if net > 0 else "negative" if net < 0 else ""
            entries.append(f'''<tr id="{side}-{player['id']}">
              <td><div class="identity"><span class="rank">{i:02}</span><span class="avatar">{photo_html}</span>
              <div class="name"><strong>{escape(player['name'])}</strong>
              <span class="meta">{crest_html}{escape(player['short_position'])}{price}</span></div></div></td>
              <td>{player['in']:,}</td><td>{player['out']:,}</td>
              <td class="{tone}">{net:+,}</td></tr>''')
        if not entries:
            entries.append('<tr><td colspan="4">No qualifying transfers in this snapshot</td></tr>')
        return f'''<section class="panel {side}"><div class="panel-heading">
          <h2>{title}</h2><span>{subtitle}</span></div><table>
          <colgroup><col class="player"><col><col><col></colgroup>
          <thead><tr><th>Player</th><th>In</th><th>Out</th><th>Net</th></tr></thead>
          <tbody>{"".join(entries)}</tbody></table></section>'''

    stamp = datetime.fromisoformat(board["captured"]).strftime("%d %b %Y · %H:%M UTC")
    css = Path(__file__).with_suffix(".css").read_text(encoding="utf-8")
    payload = json.dumps({"cues": cues, "captions": captions}).replace("<", "\\u003c")
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><style>{css}</style>
    <body><header>{logo}<div><span>FPL VORTEX</span><h1>Market Outlook</h1></div>
    <strong>GAMEWEEK {board['gameweek']}</strong></header>
    <main>{table("in", "Transfers In", "Ranked by transfers in")}
    {table("out", "Transfers Out", "Ranked by net losses")}</main>
    <footer><span>OFFICIAL FPL · {stamp}</span><span id="caption"></span></footer>
    <script>
    const {{cues,captions}}={payload};
    const rows=[...document.querySelectorAll("tbody tr")];
    const caption=document.getElementById("caption");
    window.__seek=t=>{{
      const cue=cues.find(c=>t>=c.start&&t<c.end);
      const progress=cue?Math.min(1,Math.max(0,(t-cue.start)/.24)):0;
      for(const row of rows){{
        const active=cue?.row===row.id;
        row.classList.toggle("active",!!active);
        row.style.setProperty("--highlight",active?1-(1-progress)**3:0);
      }}
      caption.textContent=captions.find(c=>t>=c.start&&t<c.end)?.text||"";
    }};
    window.__seek(0);
    window.__ready=true;
    </script></body></html>'''
