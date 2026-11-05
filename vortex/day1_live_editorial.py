"""Day 1: current-GW expert opinions, extracted from current source articles.

Source articles are *editorial context*, not official FPL facts or the VORTEX
model. This module extracts only explicit first-person positions, paraphrases
them into small decision labels, resolves mentioned players against the live
official player list, and stores URL/provenance. No season/GW/player advice is
hard-coded. Fail closed on stale, unavailable or ambiguous inputs.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
from html import unescape
from html.parser import HTMLParser
from xml.etree import ElementTree
import json
import os
from pathlib import Path
import re
import unicodedata
from urllib.parse import urlparse

from vortex.expert_editorial import FEED, OFFICIAL, _fetch, _gameweek, _url, parse_feed

MAX_ARTICLES = 8
ARTICLE_AGE_DAYS = 7
SOURCE_VERSION = "DAY1-EXPERT-CURRENT-GW-V2"
ACTION_TERMS = re.compile(
    r"\b(?:i|we)\b.{0,145}\b(?:plan(?:ning)?|lean(?:ing)?|prefer|would|"
    r"consider(?:ing)?|decid(?:ed|ing)|looking|intend|expect|likely)\b",
    re.I,
)
GW_PATTERN = r"\b(?:fpl\s*)?(?:gw|gameweek)\s*0?%d\b"


def _normal(value):
    value = unicodedata.normalize("NFKD", str(value))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def _players_in(text, elements):
    hay = " " + _normal(text) + " "
    matches = []
    names = {}
    for p in elements:
        label = str(p.get("web_name") or "").strip()
        name = _normal(label)
        if len(name) >= 4:
            names.setdefault(name, []).append(p)
    for normalized, rows in names.items():
        if len(rows) != 1 or (" " + normalized + " ") not in hay:
            continue
        p = rows[0]
        if not isinstance(p.get("id"), int) or not isinstance(p.get("team"), int):
            continue
        matches.append({"id": int(p["id"]), "name": str(p["web_name"]),
                        "team_id": int(p["team"]), "status": str(p.get("status") or ""),
                        "position": p.get("element_type")})
    # Longest first prevents "Pedro" from superseding "Joao Pedro".
    matches.sort(key=lambda row: (-len(_normal(row["name"])), row["id"]))
    seen = set()
    result = []
    for row in matches:
        if row["id"] not in seen:
            result.append(row)
            seen.add(row["id"])
    return result[:4]


class ArticleBlocks(HTMLParser):
    """Extract article headings and paragraph text; ignore scripts/sidebars."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.bad = 0
        self.capture = ""
        self.parts = []
        self.heading = ""
        self.author = "AllAboutFPL"
        self.blocks = []
        self.article_seen = False
        self.in_article = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {"script", "style", "nav", "footer", "aside", "form"}:
            self.bad += 1
        if tag == "article":
            self.article_seen = True
            self.in_article += 1
        if self.bad or self.capture or tag not in {"p", "li", "h2", "h3", "h4"}:
            return
        self.capture, self.parts = tag, []

    def handle_data(self, data):
        if self.capture and not self.bad:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if self.capture == tag:
            text = " ".join(unescape(" ".join(self.parts)).split()).strip()
            if tag in {"h2", "h3", "h4"}:
                self.heading = text
                # A named author's section establishes identity until next one.
                m = re.match(r"^([A-Za-zÀ-ž]+)[’']s\s+.+(?:Team|Transfer|Captain)",
                             text, re.I)
                if m:
                    self.author = m.group(1)
            elif 24 <= len(text) <= 1100:
                self.blocks.append((self.heading, self.author, text))
            self.capture = ""
            self.parts = []
        if tag in {"script", "style", "nav", "footer", "aside", "form"} and self.bad:
            self.bad -= 1
        if tag == "article" and self.in_article:
            self.in_article -= 1


def _explicit_opinion(heading, author, body, elements, article):
    # An author may state a captaincy comparison as "between X and Y
    # for me", without using an explicit first-person verb.
    author_captain = re.search(
        r"\bcaptaincy\b.{0,140}\bbetween\b.{0,130}\b(?:for me|my)\b",
        body, re.I,
    )
    if not ACTION_TERMS.search(body) and not author_captain:
        return None
    sentences = re.split(r"(?<=[.!?])\s+", body)
    headline = (heading or "").casefold()
    for sentence in sentences:
        if not 24 <= len(sentence) <= 320:
            continue
        explicit_comparison = re.search(
            r"\bcaptaincy\b.{0,130}\bbetween\b.{0,130}\b(?:for me|my)\b",
            sentence, re.I,
        )
        if not ACTION_TERMS.search(sentence) and not explicit_comparison:
            continue
        lower = sentence.casefold()
        action, names = None, []
        if re.search(r"\broll\b.{0,35}\btransfer\b|\btransfer\b.{0,45}\broll\b", lower):
            if re.search(r"\b(?:plan|planning|lean|likely|want|intend)\b", lower):
                action = "ROLL"
        elif "bench boost" in lower and re.search(r"\b(?:plan|planning|activate|use)\b", lower):
            action = "BENCH_BOOST"
        elif ("captain" in lower or "captain" in headline) and (
             "between" in lower or re.search(r"\b(?:lean(?:ing)?|captain(?:ing)?|choos(?:e|ing)|prefer)\b", lower)):
            names = _players_in(sentence, elements)
            if names:
                action = "CAPTAIN_COMPARE"
        elif re.search(
            r"\b(?:i|we)\b.{0,95}\b(?:leaning towards|leaning toward|"
            r"planning to|plan to|decided to|going to)\s+start(?:ing)?\b", lower
        ):
            start = re.search(r"\bstart(?:ing)?\b", sentence, flags=re.I)
            names = _players_in(sentence[start.end():] if start else "", elements)
            if 1 <= len(names) <= 2:
                action = "START"
        elif re.search(
            r"\b(?:i|we)\b.{0,95}\b(?:leaning towards|leaning toward|"
            r"planning to|plan to|decided to|going to)\s+bench(?:ing)?\b", lower
        ):
            start = re.search(r"\bbench(?:ing)?\b", sentence, flags=re.I)
            names = _players_in(sentence[start.end():] if start else "", elements)
            if 1 <= len(names) <= 2:
                action = "BENCH"
        elif re.search(r"\b(?:getting in|bring in|buy|transfer in|replacement|move to|move .{1,60}? to)\b", lower):
            # A sentence with both OUT and IN is restricted to the named
            # targets after the positive acquisition phrase.
            incoming = re.split(
                r"\b(?:getting in|bring in|transfer in|replacement|move to|"
                r"move .{1,60}? to)\b",
                sentence, maxsplit=1, flags=re.I,
            )
            probe = incoming[-1] if len(incoming) > 1 else sentence
            names = _players_in(probe, elements)
            if names:
                action = "BUY_CONSIDER"
        elif re.search(r"\b(?:sell|remov(?:e|ing)|get rid of)\b", lower):
            outgoing = re.search(r"\b(?:sell|selling|remove|removing|get rid of)\b",
                                 sentence, flags=re.I)
            if outgoing:
                # Only players syntactically AFTER the sale verb are possible
                # sales. Names elsewhere in the paragraph are not sell picks.
                tail = sentence[outgoing.end():]
                tail = re.split(r"\b(?:because|due to|instead|later on)\b",
                                tail, maxsplit=1, flags=re.I)[0]
                names = _players_in(tail[:90], elements)
            if 1 <= len(names) <= 2:
                action = "SELL_CONSIDER"
        if not action:
            continue
        # A negative formulation must not become a positive BUY verdict.
        if action == "BUY_CONSIDER" and re.search(
            r"\b(?:not|never|don't|wouldn't)\b.{0,22}\b(?:buy|bring in|get in)\b", lower
        ):
            continue
        labels = [x["name"] for x in names]
        join = " or ".join(labels) if len(labels) <= 2 else ", ".join(labels[:3])
        verbs = {
            "ROLL": "considering keeping the free transfer",
            "BENCH_BOOST": "considering using Bench Boost",
            "CAPTAIN_COMPARE": "weighing " + join + " for captaincy",
            "START": "leaning towards starting " + join,
            "BENCH": "leaning towards benching " + join,
            "BUY_CONSIDER": "considering " + join + " as a transfer option",
            "SELL_CONSIDER": ("considering a future sale of " + join
                              if re.search(r"\b(?:coming weeks|later on|after the break)\b", lower)
                              else "considering moving on " + join),
        }
        return {
            "author": author, "topic": "captaincy" if action == "CAPTAIN_COMPARE"
            else "chips" if action == "BENCH_BOOST"
            else "bench" if action in {"START", "BENCH"} else "transfers",
            "decision": verbs[action], "action": action,
            "players": names, "url": article["url"], "gw": article["gameweek"],
            "published_at": article["published_at"],
            "evidence_sha256": hashlib.sha256(sentence.encode("utf-8")).hexdigest(),
            "extraction": "explicit_author_statement_current_article",
        }
    return None


def extract_article_opinions(html_bytes, article, players):
    parser = ArticleBlocks()
    parser.feed(html_bytes.decode("utf-8", errors="replace"))
    # Article heading and RSS title MUST match the live next GW.
    gw = int(article["gameweek"])
    if not re.search(GW_PATTERN % gw, article["title"], re.I):
        return []
    opinions = []
    seen = set()
    for heading, author, body in parser.blocks:
        opinion = _explicit_opinion(heading, author, body, players, article)
        if not opinion:
            continue
        key = (opinion["author"], opinion["action"],
               tuple(p["id"] for p in opinion["players"]))
        if key in seen:
            continue
        seen.add(key)
        opinions.append(opinion)
    return opinions[:8]


def _discover_fresh_articles(gw, now, feed_xml=None):
    """Prefer official RSS, fall back to public WordPress post metadata.

    The WordPress fallback uses *real publication timestamps* and article
    URLs; it never infers freshness from the URL's month or cached opinions.
    """
    if feed_xml is not None:
        return parse_feed(feed_xml, gw, now)
    try:
        rss = parse_feed(_fetch(FEED), gw, now)
        if rss:
            return rss
    except (OSError, ValueError, ElementTree.ParseError):
        pass
    endpoint = ("https://allaboutfpl.com/wp-json/wp/v2/posts"
                f"?per_page=30&search=GW{int(gw)}")
    posts = json.loads(_fetch(endpoint))
    if not isinstance(posts, list):
        raise ValueError("WordPress article index was not a list")
    found = {}
    for post in posts:
        if not isinstance(post, dict):
            continue
        try:
            title = unescape(str((post.get("title") or {}).get("rendered") or ""))
            if not re.search(GW_PATTERN % gw, title, re.I):
                continue
            url = _url(post.get("link"))
            issued = datetime.fromisoformat(str(post.get("date_gmt") or ""))
            if issued.tzinfo is None:
                issued = issued.replace(tzinfo=timezone.utc)
            issued = issued.astimezone(timezone.utc)
            if not now - timedelta(days=ARTICLE_AGE_DAYS) <= issued <= now + timedelta(minutes=10):
                continue
            found[url] = {"url": url, "title": title, "published_at": issued.isoformat()}
        except (TypeError, ValueError, AttributeError):
            continue
    return list(found.values())[:15]


def build_day1_brief(*, bootstrap=None, feed_xml=None, article_pages=None, now=None):
    now = now or datetime.now(timezone.utc)
    report = {"version": SOURCE_VERSION, "source": "AllAboutFPL",
              "retrieved_at": now.isoformat(),
              "gameweek": None, "status": "source_unavailable",
              "articles": [], "opinions": [],
              "disclosure": "Independent article author opinions. Not official player news or VORTEX forecasts."}
    try:
        if bootstrap is None:
            bootstrap = json.loads(_fetch(OFFICIAL))
        gw = _gameweek(bootstrap)
        report["gameweek"] = gw
        deadline_event = next(x for x in bootstrap["events"] if x.get("is_next"))
        deadline = datetime.fromisoformat(deadline_event["deadline_time"].replace("Z", "+00:00"))
        if now >= deadline:
            report["status"] = "deadline_passed"
            return report
        if not isinstance(bootstrap.get("elements"), list) or not bootstrap["elements"]:
            raise ValueError("Official player roster missing")
        articles = _discover_fresh_articles(gw, now, feed_xml=feed_xml)
        if not articles:
            report["status"] = "no_current_articles"
            return report
        for entry in articles[:MAX_ARTICLES]:
            article = {**entry, "gameweek": gw}
            try:
                if article_pages is not None:
                    page = article_pages[entry["url"]]
                else:
                    page = _fetch(entry["url"])
                found = extract_article_opinions(page, article, bootstrap["elements"])
            except (OSError, KeyError, ValueError):
                found = []
            report["articles"].append({**entry, "extracted": len(found)})
            report["opinions"].extend(found)
        # Highest-value named actions first, before generic roll/chip topics.
        priority = {"BUY_CONSIDER": 0, "CAPTAIN_COMPARE": 1,
                    "SELL_CONSIDER": 2, "START": 3, "BENCH": 3,
                    "ROLL": 4, "BENCH_BOOST": 5}
        report["opinions"].sort(
            key=lambda x: (priority.get(x["action"], 99), x["url"], x["author"])
        )
        report["opinions"] = report["opinions"][:12]
        report["status"] = ("verified_author_opinions" if report["opinions"]
                            else "article_discovery_only")
    except (OSError, KeyError, ValueError, TypeError, json.JSONDecodeError, ElementTree.ParseError) as error:
        report["status"] = "source_unavailable"
        report["opinions"] = []
        report["warning"] = type(error).__name__ + ": " + str(error)[:180]
    return report


def _fresh(gameweek, path=None):
    path = path or os.environ.get("VORTEX_EDITORIAL_BRIEF")
    if not path:
        return {}
    try:
        report = json.loads(Path(path).read_text(encoding="utf-8"))
        stamp = datetime.fromisoformat(report["retrieved_at"])
        age = datetime.now(timezone.utc) - stamp
        if (report.get("version") != SOURCE_VERSION
                or report.get("gameweek") != int(gameweek)
                or report.get("status") != "verified_author_opinions"
                or not -timedelta(minutes=10) <= age <= timedelta(hours=8)):
            return {}
    except (OSError, TypeError, ValueError, KeyError):
        return {}
    return report


def presenter_note(gameweek, roster, *, max_items=2):
    report = _fresh(gameweek)
    if not report:
        return ""
    owned = {int(p["id"]) for p in roster}
    ranked = sorted(report["opinions"], key=lambda x: (
        -len(owned & {int(p["id"]) for p in x["players"]}),
        0 if x["topic"] == "transfers" else 1,
    ))
    choices = ranked[:max_items]
    if not choices:
        return ""
    lines = ["There's another angle I'm checking before making a decision."]
    for item in choices:
        lines.append("In a current All About FPL article, "
                     + item["author"] + " is " + item["decision"] + ".")
    lines.append("That's their plan, not a transfer instruction for our squad. "
                 "I'll compare the actual minutes, availability and Vortex expected points before acting.")
    return " ".join(lines)


def source_credits(gameweek):
    report = _fresh(gameweek)
    if not report:
        return ""
    links = list(dict.fromkeys(x["url"] for x in report["opinions"]))[:4]
    return ("\n\nIndependent editorial discussion: AllAboutFPL\n"
            + "\n".join(links)
            + "\nArticle author opinions are separately attributed. "
              "FPL VORTEX calculations and verdicts remain independent.")


def main():
    ap = argparse.ArgumentParser(description="Fetch Day 1 current-GW editorial guidance")
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    report = build_day1_brief()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    print("[DAY1 EXPERT] status:", report["status"], "GW:", report["gameweek"],
          "articles:", len(report["articles"]), "explicit recommendations:",
          len(report["opinions"]))
    if report["status"] != "verified_author_opinions":
        print("[DAY1 EXPERT] No current source-backed author opinion available; "
              "proceed with verified official FPL and VORTEX analysis only.")


if __name__ == "__main__":
    main()
