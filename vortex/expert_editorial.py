"""Attributable AllAboutFPL research for the existing FPL VORTEX video workflows.

Public RSS identifies *current* source articles. Only separately hand-verified
short statements may become spoken opinions. Never reuse stale forecasts, imply
a source opinion is a VORTEX xPts recommendation, or copy article text/images.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import json
import os
from pathlib import Path
import re
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

FEED = "https://allaboutfpl.com/feed/"
OFFICIAL = "https://fantasy.premierleague.com/api/bootstrap-static/"
CURATED = Path(__file__).with_name("allaboutfpl_verified_opinions.json")


def _fetch(url):
    req = Request(url, headers={"User-Agent": "FPL-VORTEX-EditorialResearch/1.0"})
    with urlopen(req, timeout=15) as resp:
        body = resp.read(2_000_001)
    if len(body) > 2_000_000:
        raise ValueError("Editorial response exceeded 2MB")
    return body


def _url(value):
    parsed = urlparse(str(value).strip())
    if parsed.scheme != "https" or parsed.hostname not in ("allaboutfpl.com", "www.allaboutfpl.com"):
        raise ValueError("Source URL is not AllAboutFPL HTTPS")
    if not re.match(r"^/20\d{2}/\d{2}/[^/]+/?$", parsed.path):
        raise ValueError("Source URL is not a dated article")
    return "https://allaboutfpl.com" + parsed.path.rstrip("/") + "/"


def _gameweek(bootstrap):
    events = bootstrap.get("events") or []
    current = [entry for entry in events if entry.get("is_next") is True]
    if len(current) != 1 or not current[0].get("deadline_time"):
        raise ValueError("Official next Gameweek unavailable or ambiguous")
    gw = int(current[0]["id"])
    if not 1 <= gw <= 38:
        raise ValueError("Official next Gameweek invalid")
    return gw


def parse_feed(feed_xml, gw, now):
    root = ET.fromstring(feed_xml)
    if root.find("channel") is None:
        raise ValueError("RSS channel missing")
    found = {}
    pattern = re.compile(r"\b(?:fpl\s*)?(?:gw|gameweek)\s*0?" + str(gw) + r"\b", re.I)
    for item in root.findall("./channel/item"):
        title = (item.findtext("title") or "").strip()
        if not pattern.search(title):
            continue
        try:
            url = _url(item.findtext("link") or "")
            issued = parsedate_to_datetime(item.findtext("pubDate") or "")
            if issued.tzinfo is None:
                issued = issued.replace(tzinfo=timezone.utc)
            issued = issued.astimezone(timezone.utc)
        except (ValueError, TypeError):
            continue
        if not now - timedelta(days=7) <= issued <= now + timedelta(minutes=10):
            continue
        found[url] = {"url": url, "title": title, "published_at": issued.isoformat()}
    return list(found.values())[:15]


def source_brief(bootstrap=None, feed_xml=None, now=None, curated=None):
    now = now or datetime.now(timezone.utc)
    report = {
        "version": "FPL-VORTEX-EXTERNAL-EDITORIAL-V1",
        "source": "AllAboutFPL",
        "retrieved_at": now.isoformat(),
        "gameweek": None, "status": "source_unavailable",
        "articles": [], "opinions": [],
        "disclosure": "Independent author opinions; not official data or VORTEX model recommendations.",
    }
    try:
        if bootstrap is None:
            bootstrap = json.loads(_fetch(OFFICIAL))
        gw = _gameweek(bootstrap)
        report["gameweek"] = gw
        articles = parse_feed(_fetch(FEED) if feed_xml is None else feed_xml, gw, now)
        report["articles"] = articles
        if not articles:
            report["status"] = "no_current_articles"
            return report
        if curated is None:
            curated = json.loads(CURATED.read_text(encoding="utf-8"))
        allowed = {a["url"] for a in articles}
        for op in curated:
            if op.get("gw") != gw:
                continue
            url = _url(op.get("url", ""))
            if url not in allowed:
                continue
            author, topic, decision = (str(op.get(k) or "").strip()
                                       for k in ("author", "topic", "decision"))
            if not author or not topic or not decision or len(decision) > 210:
                raise ValueError("Unverified editorial opinion")
            if re.search(r"[<>{}]", decision):
                raise ValueError("Unsafe editorial markup")
            report["opinions"].append({"author": author, "topic": topic,
                                       "decision": decision, "url": url, "gw": gw})
        report["status"] = ("verified_author_opinions" if report["opinions"]
                            else "article_discovery_only")
    except (OSError, ValueError, KeyError, TypeError, ET.ParseError) as exc:
        report["status"] = "source_unavailable"
        report["warning"] = type(exc).__name__ + ": " + str(exc)[:150]
        report["opinions"] = []
    return report


def load_live_brief(gameweek, path=None):
    path = str(path or os.environ.get("VORTEX_EDITORIAL_BRIEF") or "")
    if not path:
        return {}
    try:
        report = json.loads(Path(path).read_text(encoding="utf-8"))
        age = datetime.now(timezone.utc) - datetime.fromisoformat(report["retrieved_at"])
        if (report.get("gameweek") != int(gameweek)
            or report.get("status") != "verified_author_opinions"
            or not -timedelta(minutes=10) <= age <= timedelta(hours=8)):
            return {}
    except (OSError, ValueError, TypeError, KeyError):
        return {}
    return report


def narrator_note(gameweek, *, topics=("transfers", "captaincy"), max_items=2):
    """Brief original-language comparison, never a copy of source article prose."""
    data = load_live_brief(gameweek)
    selected = [x for x in data.get("opinions", []) if x["topic"] in topics][:max_items]
    if not selected:
        return ""
    lines = ["For perspective, independent All About FPL writers have different plans."]
    for row in selected:
        lines.append("All About FPL author " + row["author"] + " " + row["decision"].removeprefix("He "))
    lines.append("These describe their teams, not yours; compare the alternatives with verified Vortex forecasts.")
    return " ".join(lines)


def source_credits(gameweek=None):
    """Provide original-context attribution in YouTube descriptions only if fresh."""
    if gameweek is None:
        path = os.environ.get("VORTEX_EDITORIAL_BRIEF")
        if not path:
            return ""
        try:
            gameweek = json.loads(Path(path).read_text(encoding="utf-8"))["gameweek"]
        except (OSError, ValueError, TypeError, KeyError):
            return ""
    report = load_live_brief(gameweek)
    if not report:
        return ""
    links = list(dict.fromkeys(op["url"] for op in report["opinions"]))
    return ("\n\nIndependent editorial perspectives reviewed (AllAboutFPL):\n"
            + "\n".join(links[:4])
            + "\nTheir authors' stated plans are independent opinions, not official FPL facts or VORTEX forecasts.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    result = source_brief()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("[EXPERT EDITORIAL] GW:", result["gameweek"],
          "status:", result["status"], "articles:", len(result["articles"]),
          "attributed opinions:", len(result["opinions"]))
    if result["status"] == "source_unavailable":
        print("[EXPERT EDITORIAL] No advice reused after source failure.")


if __name__ == "__main__":
    main()
