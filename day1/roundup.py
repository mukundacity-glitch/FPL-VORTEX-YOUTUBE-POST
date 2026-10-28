"""Evidence-only match stories; fixture numbers come from the shared WC/FH model."""
from __future__ import annotations

import hashlib
import json
import math
import random
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from vortex.fixture_forecast import fixture_values

POSITIONS = {1: "goalkeeper", 2: "defender", 3: "midfielder", 4: "forward"}
DISCIPLINE_SOURCE = "https://www.premierleague.com/en/news/4425344/which-players-are-suspended-or-close-to-a-ban-in-fantasy"


def stamp(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def state(fixture):
    scored = all(fixture.get(key) is not None for key in ("team_h_score", "team_a_score"))
    if (fixture.get("finished") or fixture.get("finished_provisional")) and scored and int(fixture.get("minutes") or 0) >= 90:
        return "FULL TIME"
    return "LIVE" if fixture.get("started") else "TO PLAY"


def kickoff_label(value, spoken=False):
    moment = stamp(value)
    if moment is None:
        return "kickoff time to be confirmed" if spoken else "KICKOFF TBC"
    local = moment.astimezone(ZoneInfo("Europe/London"))
    if spoken:
        return local.strftime("%A %-d %B at %-I:%M %p") + " UK time"
    return local.strftime("%a %-d %b · %H:%M %Z").upper()


def booking_warning(player, fixtures):
    """Club match cutoffs, never GW number; a red alone does not prove a ban length."""
    completed = sum(state(f) == "FULL TIME" and player["team"] in (f["team_h"], f["team_a"]) for f in fixtures)
    yellows = player.get("yellow_cards")
    if yellows is None or player.get("status") == "s":
        return ""
    for threshold, cutoff, ban in ((5, 19, 1), (10, 32, 2), (15, 38, 3)):
        if int(yellows) == threshold - 1 and completed < cutoff:
            return (f"One booking from a {ban}-match league ban: {int(yellows)} yellows; "
                    f"the {threshold}-card cutoff is the club's first {cutoff} league matches.")
    return ""


def upcoming(player, snapshot, forecasts, start_gw, count=5):
    teams = {t["id"]: t for t in snapshot["bootstrap"]["teams"]}
    mapped = {int(row["fixture_id"]): row for row in forecasts}
    slots = []
    for gw in range(start_gw, min(39, start_gw + count)):
        fixtures = sorted((f for f in snapshot["fixtures"] if f.get("event") == gw and player["team"] in (f["team_h"], f["team_a"])), key=lambda f: (f.get("kickoff_time") or "9999", f["id"]))
        items = []
        for f in fixtures:
            home = f["team_h"] == player["team"]
            opponent = teams[f["team_a"] if home else f["team_h"]]
            # Completed fixtures have no future forecast. Never substitute official FPL difficulty.
            values = fixture_values([mapped[f["id"]]], f["id"], player["team"], "DEF" if player["element_type"] <= 2 else "MID") if f["id"] in mapped else None
            items.append({"fixture_id": f["id"], "opponent": opponent["short_name"], "opponent_name": opponent["name"], "venue": "H" if home else "A", "code": opponent.get("code"), "kickoff": kickoff_label(f.get("kickoff_time")), **(values or {"fdr": None, "clean_sheet_probability": None, "projected_goals": None})})
        slots.append({"gw": gw, "fixtures": items})
    return slots


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def card(player, snapshot, forecasts, start_gw):
    team = next(t for t in snapshot["bootstrap"]["teams"] if t["id"] == player["team"])
    minutes = number(player.get("minutes"))
    def per90(key):
        value = number(player.get(key))
        return value * 90 / minutes if value is not None and minutes and minutes > 0 else None
    fixtures = upcoming(player, snapshot, forecasts, start_gw)
    first = next((f for slot in fixtures for f in slot["fixtures"] if f["clean_sheet_probability"] is not None), None)
    return {"id": player["id"], "first_name": player.get("first_name", ""), "last_name": player.get("second_name") or player["web_name"], "name": player["web_name"], "club": team["name"], "club_code": team.get("code"), "position": POSITIONS[player["element_type"]], "photo": player.get("photo"), "price": number(player.get("now_cost")), "ownership": number(player.get("selected_by_percent")), "xg_per90": per90("expected_goals"), "xa_per90": per90("expected_assists"), "goals_per90": per90("goals_scored"), "assists_per90": per90("assists"), "clean_sheet_probability": first["clean_sheet_probability"] if first else None, "points_per_match": number(player.get("points_per_game")), "fixtures": fixtures, "status": player.get("status"), "news": player.get("news") or "", "yellow_cards": player.get("yellow_cards"), "warning": booking_warning(player, snapshot["fixtures"])}


class Wording:
    """Persist used copy outside resettable output; rotate choices within and across runs."""
    def __init__(self, path, run_id=None):
        self.path = Path(path)
        try:
            self.history = json.loads(self.path.read_text())
        except (FileNotFoundError, ValueError):
            self.history = {"phrases": {}, "welcomes": []}
        self.rng = random.Random(run_id or secrets.token_hex(16))
        self.used = {}

    def choose(self, key, options):
        prior = self.history["phrases"].get(key, [])
        used = self.used.setdefault(key, [])
        candidates = [v for v in options if v not in used and v not in prior[-min(3, len(options) - 1):]]
        if not candidates:
            candidates = [v for v in options if v not in used] or list(options)
        value = self.rng.choice(candidates)
        used.append(value)
        return value

    def welcome(self, gw, headline):
        for _ in range(200):
            hello = self.choose("hello", ["Welcome back, managers.", "Good to have you with us.", "Hello, and welcome to FPL Vortex.", "Managers, let's get into it.", "Come on in. There's plenty to unpack.", "Welcome to your Gameweek catch-up.", "Great to have your company.", "Pull up a chair, managers."])
            bridge = self.choose("bridge", ["Let's make sense of the weekend.", "Here's what matters for your squad.", "Time to catch up before the next deadline.", "Let's see what the results mean for our teams.", "There are a few names worth a closer look.", "Let's walk through the football together."])
            text = f"{hello} Gameweek {gw}. {headline} {bridge}"
            digest = hashlib.sha256(text.encode()).hexdigest()
            if digest not in self.history["welcomes"]:
                self.history["welcomes"].append(digest)
                return text
        raise RuntimeError("Unable to generate a fresh introduction")

    def save(self):
        for key, values in self.used.items():
            self.history["phrases"][key] = (self.history["phrases"].get(key, []) + values)[-40:]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(self.history, indent=2))
        temp.replace(self.path)


def build_roundup(snapshot, forecasts, start_gw, wording, spoken_name=None):
    boot, gw = snapshot["bootstrap"], snapshot["gw"]
    players = {p["id"]: p for p in boot["elements"]}
    teams = {t["id"]: t for t in boot["teams"]}
    fixtures = sorted((f for f in snapshot["fixtures"] if f.get("event") == gw), key=lambda f: (f.get("kickoff_time") or "9999", f["id"]))
    if not fixtures:
        raise ValueError("No official fixtures for the reviewed Gameweek")
    name = spoken_name or (lambda p: p["web_name"])
    start = min((stamp(f.get("kickoff_time")) for f in fixtures if stamp(f.get("kickoff_time"))), default=datetime.now(timezone.utc))
    finished = sum(state(f) == "FULL TIME" for f in fixtures)
    headline = f"{finished} of {len(fixtures)} matches complete."
    beats = [{"id": "welcome", "kind": "welcome", "text": wording.welcome(gw, headline)}]
    warning_mentions = {}
    for index, fixture in enumerate(fixtures):
        home, away = teams[fixture["team_h"]], teams[fixture["team_a"]]
        status = state(fixture)
        home_score = int(fixture["team_h_score"]) if number(fixture.get("team_h_score")) is not None else None
        away_score = int(fixture["team_a_score"]) if number(fixture.get("team_a_score")) is not None else None
        match = {"fixture_id": fixture["id"], "home": home, "away": away, "status": status, "home_score": home_score, "away_score": away_score, "kickoff": kickoff_label(fixture.get("kickoff_time")), "minutes": fixture.get("minutes"), "index": index + 1, "count": len(fixtures)}
        if status == "TO PLAY":
            text = f"{home['name']} against {away['name']} is still to come, {kickoff_label(fixture.get('kickoff_time'), True)}."
        elif status == "LIVE":
            score = f"{home_score} to {away_score}" if home_score is not None and away_score is not None else "score not confirmed"
            text = f"{home['name']} against {away['name']}, {score}. Still in progress."
        else:
            text = f"{home['name']} {home_score}, {away['name']} {away_score}."
        beats.append({"id": f"fixture_{fixture['id']}", "kind": "fixture", "text": text, "match": match})
        # Merge a player's match events into one mention, then one synchronized card.
        events = {}
        if status != "TO PLAY":
            for stat in fixture.get("stats", []):
                key = stat["identifier"]
                if key not in {"goals_scored", "assists", "own_goals", "yellow_cards", "red_cards", "penalties_missed", "penalties_saved"}:
                    continue
                for side in ("h", "a"):
                    for row in stat.get(side, []):
                        if int(row.get("value") or 0) > 0:
                            events.setdefault(row["element"], {})[key] = int(row["value"])
        for player in players.values():
            if player["team"] not in (fixture["team_h"], fixture["team_a"]):
                continue
            recent_news = stamp(player.get("news_added"))
            # A current availability flag is not proof of an injury during this match.
            if player.get("status") in {"i", "d"} and player.get("news") and recent_news and recent_news >= start:
                events.setdefault(player["id"], {})["availability"] = True
            if booking_warning(player, snapshot["fixtures"]):
                events.setdefault(player["id"], {})["booking_warning"] = True
        ordered = sorted(events, key=lambda pid: (not events[pid].get("goals_scored"), not events[pid].get("red_cards"), not events[pid].get("booking_warning"), players.get(pid, {}).get("web_name", "")))
        for pid in ordered:
            if pid not in players:
                raise ValueError(f"Official match event has unknown player {pid}")
            p, facts = players[pid], events[pid]
            if facts.pop("booking_warning", False):
                warning_mentions[pid] = {"spoken_name": name(p), "player_id": pid, "card": card(p, snapshot, forecasts, start_gw), "facts": {"booking_warning": True}}
            if not facts:
                continue
            details = []
            for key, singular, plural in (("goals_scored", "goal", "goals"), ("assists", "assist", "assists"), ("own_goals", "own goal", "own goals")):
                if facts.get(key):
                    details.append(f"{facts[key]} {singular if facts[key] == 1 else plural}")
            if facts.get("yellow_cards"):
                details.append("booked")
            if facts.get("red_cards"):
                details.append("sent off; check the confirmed suspension before a transfer")
            if facts.get("penalties_missed"):
                details.append("penalty missed")
            if facts.get("penalties_saved"):
                details.append("penalty saved")
            if facts.get("availability"):
                details.append("injury flag" if p["status"] == "i" else "fitness doubt")
            position = POSITIONS[p["element_type"]] if facts.get("goals_scored") else ""
            if facts.get("goals_scored"):
                goal_words = "scored once" if facts["goals_scored"] == 1 else "scored twice" if facts["goals_scored"] == 2 else f"scored {facts['goals_scored']} goals"
                text = f"{name(p)}, a {position}, {goal_words}"
                rest = [d for d in details if not re.match(r"\d+ goals?$", d)]
                text += (", with " + ", ".join(rest) if rest else "") + "."
            else:
                text = f"{name(p)}: " + ", ".join(details) + "."
            beats.append({"id": f"match_{fixture['id']}_player_{pid}", "kind": "player", "text": text, "spoken_name": name(p), "player_id": pid, "match": match, "facts": facts, "card": card(p, snapshot, forecasts, start_gw)})
    for yellows, cutoff, ban in ((4, 19, 1), (9, 32, 2), (14, 38, 3)):
        mentions = [m for m in warning_mentions.values() if int(m["card"]["yellow_cards"]) == yellows]
        for offset in range(0, len(mentions), 5):
            group = mentions[offset:offset+5]
            names = [m["spoken_name"] for m in group]
            joined = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
            text = f"{joined}: {yellows} yellows. Another booking within the first {cutoff} club matches means a {ban}-match league ban."
            beats.append({"id": f"booking_rule_{yellows}_{offset}", "kind": "rule", "text": text, "mentions": group, "source": DISCIPLINE_SOURCE})
    beats.append({"id": "review_handoff", "kind": "handoff", "text": wording.choose("handoff", ["Now, let's see how my own squad got on.", "Right, time for my Gameweek review.", "That's the league picture. Here's how my team fared.", "Let's bring up my squad and look at the returns."])})
    return {"gw": gw, "status": snapshot["status"], "beats": group_incidents(beats), "generated_at": datetime.now(timezone.utc).isoformat(), "discipline_source": DISCIPLINE_SOURCE}


def group_incidents(beats):
    """Read short incident lists as natural sentences; every name still owns a card."""
    output, pending = [], []
    def flush():
        if not pending:
            return
        # Preserve the original order within each category, not a name-per-sentence roll call.
        groups, order = {}, []
        for b in pending:
            key = tuple(sorted(b["facts"]))
            if key not in groups:
                groups[key] = []
                order.append(key)
            groups[key].append(b)
        for key in order:
            items = groups[key]
            if key not in {("yellow_cards",), ("assists",), ("availability",)}:
                output.extend(items)
                continue
            # Injury flags and doubts have distinct meaning, even in a compact edition.
            categories = {}
            for b in items:
                subtype = b["card"]["status"] if key == ("availability",) else "all"
                categories.setdefault(subtype, []).append(b)
            for subtype, category in categories.items():
                for offset in range(0, len(category), 4):
                    part = category[offset:offset+4]
                    names = [b["spoken_name"] for b in part]
                    joined = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
                    if key == ("yellow_cards",):
                        text = f"Yellow cards for {joined}."
                    elif key == ("assists",):
                        # Retain multiple assists for an individual instead of flattening them.
                        if any(b["facts"]["assists"] > 1 for b in part):
                            output.extend(part)
                            continue
                        text = f"Assists from {joined}."
                    else:
                        text = ("New injury flags for " if subtype == "i" else "Fitness doubts for ") + joined + "."
                    output.append({"id": part[0]["id"]+"_group", "kind": "players", "match": part[0]["match"], "text": text, "mentions": [{k: b[k] for k in ("spoken_name", "player_id", "card", "facts")} for b in part]})
        pending.clear()
    for b in beats:
        if b["kind"] == "player":
            pending.append(b)
        else:
            flush()
            output.append(b)
    flush()
    return output
