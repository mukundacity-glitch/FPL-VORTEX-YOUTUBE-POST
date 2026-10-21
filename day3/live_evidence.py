"""Public FPL evidence, refreshed per execution and rechecked before upload."""
from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import hashlib
import ipaddress
import json
import math
import re
import time
from typing import Any
from urllib.parse import urlencode, urljoin, urlparse
from xml.etree import ElementTree

from bs4 import BeautifulSoup
import requests


FPL_BASE = "https://fantasy.premierleague.com/api/"
SCORING_URL = "https://www.premierleague.com/en/news/2174909/"
PRESS_DOMAINS = {"bbc.com", "bbc.co.uk", "reuters.com", "skysports.com", "theguardian.com"}
PLAYER_FIELDS = (
    "id", "code", "team", "element_type", "status", "news", "news_added", "can_select", "removed",
    "chance_of_playing_this_round", "chance_of_playing_next_round", "team_join_date", "now_cost",
    "scout_risks", "scout_news_link", "starts", "minutes", "defensive_contribution", "goals_scored", "assists",
)


class EvidenceChangedError(RuntimeError):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def date(value: Any) -> datetime | None:
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        try:
            result = parsedate_to_datetime(str(value))
        except (TypeError, ValueError, OverflowError):
            return None
    return result.astimezone(timezone.utc) if result.tzinfo is not None else None


def fingerprint(value: Any) -> str:
    def clean(item: Any) -> Any:
        if isinstance(item, dict):
            return {str(key): clean(entry) for key, entry in item.items()}
        if isinstance(item, (list, tuple)):
            return [clean(entry) for entry in item]
        if hasattr(item, "item"):
            return clean(item.item())
        if isinstance(item, float):
            return None if not math.isfinite(item) else int(item) if item.is_integer() else item
        return item
    return hashlib.sha256(json.dumps(clean(value), sort_keys=True, allow_nan=False).encode()).hexdigest()


def core_fingerprint(bootstrap: dict, fixtures: list[dict], gameweek: int) -> str:
    players = [{key: player.get(key) for key in PLAYER_FIELDS}
               for player in sorted(bootstrap["elements"], key=lambda row: int(row["id"]))]
    market = {key: [int(player["id"]) for player in sorted(bootstrap["elements"],
               key=lambda row: (-float(row.get(key) or 0), int(row["id"])))[:20]]
              for key in ("transfers_in_event", "transfers_out_event", "selected_by_percent")}
    events = [{key: event.get(key) for key in ("id", "deadline_time", "finished", "data_checked")}
              for event in bootstrap["events"] if int(event["id"]) <= gameweek]
    fixture_fields = ("id", "event", "team_h", "team_a", "kickoff_time", "started", "finished",
                      "finished_provisional", "team_h_score", "team_a_score", "stats")
    return fingerprint({"players": players, "market": market, "events": events,
                        "fixtures": [{key: row.get(key) for key in fixture_fields}
                                     for row in sorted(fixtures, key=lambda row: int(row["id"]))],
                        "positions": bootstrap.get("element_types"), "gameweek": gameweek,
                        "scoring": bootstrap.get("game_config", {}).get("scoring")})


def public_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        return False
    try:
        return ipaddress.ip_address(parsed.hostname).is_global
    except ValueError:
        return "." in parsed.hostname and not parsed.hostname.endswith((".local", ".localhost", ".internal"))


class PublicClient:
    def text(self, url: str) -> str:
        critical = urlparse(url).hostname in {"fantasy.premierleague.com", "www.premierleague.com"}
        attempts = 3 if critical else 1
        for attempt in range(attempts):
            if not public_url(url):
                raise ValueError("Evidence requires a public HTTPS URL")
            try:
                response = requests.get(url, timeout=(20, 30) if critical else (5, 10), allow_redirects=False,
                                        headers={"User-Agent": "Mozilla/5.0 FPL-VORTEX/1.0", "Cache-Control": "no-cache"})
            except (requests.ConnectionError, requests.Timeout):
                if attempt + 1 == attempts:
                    raise
                time.sleep(2 ** attempt)
                continue
            redirects = 0
            while response.is_redirect:
                url = urljoin(url, response.headers["Location"])
                redirects += 1
                if redirects > 4 or not public_url(url):
                    raise ValueError("Unsafe evidence redirect")
                response = requests.get(url, timeout=(20, 30) if critical else (5, 10), allow_redirects=False)
            if response.status_code in {429, 500, 502, 503, 504} and attempt + 1 < attempts:
                retry = response.headers.get("Retry-After", "")
                if retry.isdigit() and int(retry) > 30:
                    response.raise_for_status()
                time.sleep(max(2 ** attempt, int(retry) if retry.isdigit() else 0))
                continue
            response.raise_for_status()
            if len(response.content) > 5_000_000:
                raise ValueError("Evidence response exceeds bounded size")
            return response.text
        raise RuntimeError("Evidence request exhausted retries")

    def json(self, url: str) -> Any:
        return json.loads(self.text(url))


def normalize(value: str) -> str:
    return re.sub(r"[^\w]+", " ", value.casefold()).strip()


def mentions(text: str, names: list[str]) -> bool:
    return any(" " + normalize(name) + " " in " " + normalize(text) + " " for name in names if name)


def concern(text: str) -> bool:
    negative = re.search(r"injur|suspend|ruled out|doubt|not fit|not ready|benched|dropped|rotation|transfer|loan|depart|changed role|new role|position switch|deeper role", text, re.I)
    recovery = re.search(r"returns? (?:from|after)|back in (?:training|contention)|passed fit|cleared to play", text, re.I)
    unresolved = re.search(r"not ready|not fit|doubt|ruled out|still|but|however", text, re.I)
    return bool(negative and (not recovery or unresolved))


def research_news(bootstrap: dict, client: PublicClient) -> dict:
    players = {int(row["id"]): row for row in bootstrap["elements"]}
    teams = {int(row["id"]): row for row in bootstrap["teams"]}
    unique = Counter(normalize(str(row.get("web_name", ""))) for row in players.values())
    aliases = {pid: [" ".join(str(row.get(key) or "") for key in ("first_name", "second_name")).strip()]
               + ([str(row["web_name"])] if len(str(row.get("web_name", ""))) >= 5
                  and unique[normalize(str(row.get("web_name", "")))] == 1 else [])
               for pid, row in players.items()}
    coverage = {str(tid): {"primary": False, "press_search": False} for tid in teams}
    reports: dict[str, list[dict]] = {str(pid): [] for pid in players}
    errors: list[dict] = []
    articles: list[dict] = []
    linked: dict[str, set[int]] = {}
    for row in players.values():
        url = str(row.get("scout_news_link") or "")
        if url.startswith("https://"):
            linked.setdefault(url, set()).add(int(row["team"]))

    def primary(url: str, tids: set[int]) -> tuple[dict, list[str]]:
        html = client.text(url)
        soup = BeautifulSoup(html, "html.parser")
        published = soup.find("meta", property="article:published_time")
        structured_date = re.search(r'"datePublished"\s*:\s*"([^\"]+)"', html)
        published_at = published.get("content") if published else structured_date.group(1) if structured_date else None
        article = {"url": url, "title": soup.title.get_text(" ", strip=True) if soup.title else "",
                   "published_at": published_at, "team_ids": sorted(tids), "source": "FPL_LINKED_PRIMARY",
                   "text": "\n".join(node.get_text(" ", strip=True) for node in soup.select("h1,p"))[:30000]}
        links = [urljoin(url, node["href"]).split("#")[0] for node in soup.select("a[href]")
                 if re.search(r"injur|team.news|press.conference|fitness|squad.update", node.get_text(" ") + node["href"], re.I)]
        return article, [link for link in links if urlparse(link).hostname == urlparse(url).hostname and link not in linked][:3]

    with ThreadPoolExecutor(max_workers=6) as executor:
        tasks = {executor.submit(primary, url, tids): (url, tids) for url, tids in sorted(linked.items())}
        discovered: dict[str, set[int]] = {}
        for future in as_completed(tasks):
            url, tids = tasks[future]
            try:
                article, links = future.result()
                articles.append(article)
                for tid in tids:
                    published = date(article["published_at"])
                    coverage[str(tid)]["primary"] |= bool(published is not None and article["text"]
                        and datetime.now(timezone.utc) - timedelta(days=7) <= published <= datetime.now(timezone.utc))
                    for link in links:
                        if sum(tid in values for values in discovered.values()) < 3:
                            discovered.setdefault(link, set()).add(tid)
            except (requests.RequestException, OSError, ValueError, RuntimeError) as error:
                errors.append({"url": url, "error": type(error).__name__})
        followups = {executor.submit(primary, url, tids): url for url, tids in sorted(discovered.items())}
        for future in as_completed(followups):
            try:
                article, _ = future.result()
                articles.append(article)
            except (requests.RequestException, OSError, ValueError, RuntimeError) as error:
                errors.append({"url": followups[future], "error": type(error).__name__})
        searches = {}
        for tid, team in teams.items():
            query = f'"{team["name"]}" football injury suspension team news when:7d'
            url = "https://news.google.com/rss/search?" + urlencode({"q": query, "hl": "en-GB", "gl": "GB", "ceid": "GB:en"})
            searches[executor.submit(client.text, url)] = (tid, url)
        for future in as_completed(searches):
            tid, url = searches[future]
            try:
                root = ElementTree.fromstring(future.result())
                if root.tag != "rss" or root.find("channel") is None:
                    raise ValueError("News discovery did not return an RSS channel")
                coverage[str(tid)]["press_search"] = True
                for item in root.findall(".//item"):
                    source = item.find("source")
                    host = urlparse(source.get("url", "") if source is not None else "").hostname or ""
                    if not any(host == domain or host.endswith("." + domain) for domain in PRESS_DOMAINS):
                        continue
                    title = item.findtext("title", "")
                    articles.append({"url": item.findtext("link"), "title": title, "text": title,
                                     "published_at": item.findtext("pubDate"), "team_ids": [tid],
                                     "source": "CREDIBLE_PRESS_DISCOVERY"})
            except (requests.RequestException, OSError, ValueError, ElementTree.ParseError) as error:
                errors.append({"url": url, "error": type(error).__name__})
    now = datetime.now(timezone.utc)
    for article in articles:
        published = date(article["published_at"])
        if published is None or not now - timedelta(days=7) <= published <= now:
            continue
        for pid, player in players.items():
            if int(player["team"]) not in article["team_ids"]:
                continue
            passages = [part for part in re.split(r"(?<=[.!?])\s+|\n", article["text"]) if mentions(part, aliases[pid])]
            if passages:
                reports[str(pid)].append({key: article[key] for key in ("url", "title", "source", "published_at")})
                reports[str(pid)][-1].update(unresolved_concern=any(concern(part) for part in passages),
                                           certainty="REPORTED_NOT_MEDICAL_CLEARANCE", excerpt=" ".join(passages)[:500])
    ordered = {pid: sorted(items, key=lambda item: str(item["url"])) for pid, items in sorted(reports.items())}
    return {"checked_at": now_iso(), "players": ordered, "coverage": coverage, "errors": errors,
            "fingerprint": fingerprint({"players": ordered, "coverage": coverage})}


def collect(bootstrap: dict, fixtures: list[dict], gameweek: int, *, client: PublicClient | None = None,
            histories: bool = True) -> dict:
    client = client or PublicClient()
    fresh = client.json(FPL_BASE + "bootstrap-static/")
    matches = client.json(FPL_BASE + "fixtures/")
    current = core_fingerprint(fresh, matches, gameweek)
    if current != core_fingerprint(bootstrap, fixtures, gameweek):
        raise EvidenceChangedError("Official FPL inputs changed; restart with fresh canonical data")
    target = next((event for event in fresh["events"] if int(event["id"]) == gameweek), None)
    deadline = date(target.get("deadline_time")) if target else None
    if deadline is None:
        raise RuntimeError("The official target Gameweek deadline is unverified")
    if deadline <= datetime.now(timezone.utc):
        raise EvidenceChangedError("Target Gameweek deadline passed; rebuild for the current planning Gameweek")
    scoring = fresh.get("game_config", {}).get("scoring", {}).get("defensive_contribution", {})
    text = BeautifulSoup(client.text(SCORING_URL), "html.parser").get_text(" ", strip=True).casefold()
    rule_rows = re.findall(r"for\s+(\d+)\s+defensive contributions by a\s+(defender|midfielder|forward)\s+(\d+)", text)
    position_codes = {"defender": "DEF", "midfielder": "MID", "forward": "FWD"}
    thresholds = {position_codes[position]: int(threshold) for threshold, position, points in rule_rows}
    points_by_position = {position_codes[position]: int(points) for threshold, position, points in rule_rows}
    if (set(thresholds) != set(position_codes.values()) or any(value <= 0 for value in thresholds.values())
            or any(scoring.get(position) != points for position, points in points_by_position.items())):
        raise RuntimeError("Current FPL DC rules could not be validated; model review required")
    result = {"version": 1, "gameweek": gameweek, "checked_at": now_iso(), "core_fingerprint": current,
              "bootstrap": fresh, "fixtures": matches, "news": research_news(fresh, client),
              "scoring": {"thresholds": thresholds, "points_by_position": points_by_position, "url": SCORING_URL},
              "histories": {}, "history_errors": {}}
    if histories:
        with ThreadPoolExecutor(max_workers=6) as executor:
            tasks = {executor.submit(client.json, FPL_BASE + f'element-summary/{int(row["id"])}/'): int(row["id"])
                     for row in fresh["elements"]}
            for future in as_completed(tasks):
                pid = tasks[future]
                try:
                    summary = future.result()
                    if not isinstance(summary, dict) or not isinstance(summary.get("history"), list) or any(int(row.get("element", -1)) != pid for row in summary["history"]):
                        raise ValueError("Missing or mismatched official player history")
                    result["histories"][str(pid)] = summary
                except (requests.RequestException, OSError, ValueError, RuntimeError) as error:
                    result["history_errors"][str(pid)] = type(error).__name__
    return result
