#!/usr/bin/env python3
"""Fetch odd headlines and rebuild the static site.

This script uses only the Python standard library so GitHub Actions can run it
on a clean machine without package setup.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import escape, unescape
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
SOURCES_PATH = ROOT / "data" / "sources.json"
ARCHIVE_DIR = ROOT / "data" / "archive"
PUBLIC_DATA = ROOT / "assets" / "data" / "headlines.json"
LOCAL_TZ = timezone(timedelta(hours=10), "AEST")
USER_AGENT = (
    "StraddieHeadlineOpenMic/1.0 "
    "(+https://auraofintelligence.github.io/straddie-headline-open-mic/)"
)

NAV = [
    ("home", "Home", "index.html"),
    ("headlines", "Headlines", "headlines.html"),
    ("open-mic", "Open Mic", "open-mic.html"),
    ("sources", "Sources", "sources.html"),
    ("archive", "Archive", "archive.html"),
    ("site-map", "Site Map", "site-map.html"),
]

HERO_IMAGES = {
    "home": ("assets/img/hero-home.png", "A comedy microphone beside a stack of newspapers on a warm coastal stage."),
    "headlines": ("assets/img/hero-headlines.png", "A neat editorial desk with newspapers, a pencil, and warm newsroom light."),
    "open-mic": ("assets/img/hero-open-mic.png", "A small community hall stage set for an open mic night."),
    "sources": ("assets/img/hero-sources.png", "A tidy source-checking desk with maps, paper slips, and a microphone lamp."),
    "archive": ("assets/img/hero-archive.png", "A warm archive room with newspapers, date tabs, and open mic objects."),
    "site-map": ("assets/img/hero-site-map.png", "A community noticeboard style map of page cards and newspaper clippings."),
}

SENSITIVE_TERMS = {
    "abuse",
    "assault",
    "attack",
    "attacks",
    "bomb",
    "cancer",
    "capsize",
    "crash",
    "dead",
    "death",
    "dies",
    "died",
    "disaster",
    "defense",
    "drought",
    "earthquake",
    "explosion",
    "famine",
    "fire",
    "flood",
    "funeral",
    "genocide",
    "hostage",
    "hospital",
    "killed",
    "murder",
    "plague",
    "rape",
    "parasite",
    "parasite-ridden",
    "raid",
    "rescued",
    "shooting",
    "shootings",
    "sentenced",
    "suicide",
    "terror",
    "war",
    "occupied",
    "russian-occupied",
}

SENSITIVE_PHRASES = (
    "body cavity",
    "medical condition",
    "military spending",
    "pulse nightclub",
)

SERIOUS_TERMS = {
    "council",
    "court",
    "economy",
    "election",
    "government",
    "minister",
    "parliament",
    "policy",
    "police",
    "president",
    "probe",
    "regulator",
    "senate",
    "tax",
    "trial",
}

SIGNALS: list[tuple[str, int, str]] = [
    (r"\baccidentally\b", 8, "It has the magic news word: accidentally."),
    (r"\bbizarre\b|\bweird\b|\bodd\b|\bunusual\b", 8, "The headline is already trying not to laugh."),
    (r"\bmystery\b", 7, "A mystery is doing a lot of work in a very small sentence."),
    (r"\bchaos\b", 6, "The word chaos gives it open-mic energy."),
    (r"\brow over\b|\bsparks row\b", 5, "It turns a small thing into a public argument."),
    (r"\bin bid to\b", 5, "It has that classic official-plan-meets-real-life shape."),
    (r"\bafter\b.+\b(?:forgot|mistake|mix-up|wrong|missing|stuck)\b", 6, "The second half quietly trips over the first half."),
    (r"\b(?:giant|tiny|mini|world's smallest|world's largest)\b", 5, "The scale is doing deadpan comedy."),
    (r"\b(?:cheese|sausage|sandwich|potato|banana|cake|biscuit|pie|pizza|chocolate)\b", 7, "A very ordinary object has wandered into serious news."),
    (r"\b(?:toilet|trousers|pants|hat|sock|bin|wheelie bin)\b", 8, "A household object has somehow reached the news desk."),
    (r"\b(?:world record|record-breaking|loose|caught|stolen|surprise|auction)\b", 5, "It has the shape of a tiny adventure reported with a straight face."),
    (r"\b(?:mullet|viagra|aliens?|scrambled letters|psychic|toblerone|fish and chip|waterpark)\b", 8, "A wonderfully specific detail has taken centre stage."),
    (r"\bt\.\s*rex\b|\bdinosaur\b|\bpurse\b", 7, "The object list sounds like someone shuffled three different stories together."),
    (r"\b(?:robot|ai|drone)\b", 1, "Technology is present, which means dignity may be optional."),
    (r"\bwhy\b|\bhow\b", 1, "It reads like the setup to a very dry question."),
    (r"\bnot\b.+\b(?:expected|planned|allowed|invited)\b", 5, "The headline has a neat little reversal."),
]

MEDIA_MARKERS = (
    "/podcast",
    "/podcasts/",
    "/sounds/",
    "/video/",
    " - video",
    " \u2013 video",
    " live:",
)


@dataclass
class FeedItem:
    title: str
    link: str
    published: datetime | None
    source_name: str
    country: str
    source_type: str


def load_sources() -> list[dict[str, str]]:
    return json.loads(SOURCES_PATH.read_text(encoding="utf-8-sig"))


def fetch_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=20) as response:
        raw = response.read(2_500_000)
        charset = response.headers.get_content_charset() or "utf-8"
        return raw.decode(charset, errors="replace")


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    value = unescape(value)
    value = repair_mojibake(value)
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def repair_mojibake(value: str) -> str:
    if not any(marker in value for marker in ("â", "Ã", "Â")):
        return value
    try:
        repaired = value.encode("latin-1").decode("utf-8")
    except UnicodeError:
        return value
    old_noise = sum(value.count(marker) for marker in ("â", "Ã", "Â"))
    new_noise = sum(repaired.count(marker) for marker in ("â", "Ã", "Â"))
    return repaired if new_noise < old_noise else value


def parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(LOCAL_TZ)


def child_text(node: ET.Element, tag: str) -> str:
    found = node.find(tag)
    return clean_text(found.text if found is not None else "")


def parse_feed(source: dict[str, str], xml_text: str) -> list[FeedItem]:
    root = ET.fromstring(xml_text)
    items: list[FeedItem] = []

    for item in root.findall(".//item"):
        title = child_text(item, "title")
        link = child_text(item, "link")
        pub = parse_date(child_text(item, "pubDate") or child_text(item, "dc:date"))
        if title and link:
            items.append(
                FeedItem(
                    title=title,
                    link=link,
                    published=pub,
                    source_name=source["name"],
                    country=source["country"],
                    source_type=source["type"],
                )
            )

    atom_ns = {"atom": "http://www.w3.org/2005/Atom"}
    for entry in root.findall(".//atom:entry", atom_ns):
        title = child_text(entry, "{http://www.w3.org/2005/Atom}title")
        link = ""
        for link_node in entry.findall("{http://www.w3.org/2005/Atom}link"):
            if link_node.get("rel", "alternate") == "alternate":
                link = link_node.get("href", "")
                break
        pub = parse_date(
            child_text(entry, "{http://www.w3.org/2005/Atom}updated")
            or child_text(entry, "{http://www.w3.org/2005/Atom}published")
        )
        if title and link:
            items.append(
                FeedItem(
                    title=title,
                    link=link,
                    published=pub,
                    source_name=source["name"],
                    country=source["country"],
                    source_type=source["type"],
                )
            )

    return items


def looks_english(title: str) -> bool:
    letters = re.findall(r"[A-Za-z]", title)
    if len(letters) < 12:
        return False
    ascii_chars = sum(1 for char in title if ord(char) < 128)
    return ascii_chars / max(len(title), 1) > 0.82


def is_sensitive(title: str) -> bool:
    lower = title.lower()
    if any(phrase in lower for phrase in SENSITIVE_PHRASES):
        return True
    words = set(re.findall(r"[a-z']+", title.lower()))
    return bool(words & SENSITIVE_TERMS)


def score_title(title: str) -> tuple[int, list[str]]:
    lower = title.lower()
    if is_sensitive(title) or not looks_english(title):
        return -100, []

    score = 0
    reasons: list[str] = []

    for pattern, points, reason in SIGNALS:
        if re.search(pattern, lower):
            score += points
            if reason not in reasons:
                reasons.append(reason)

    words = re.findall(r"[a-z']+", lower)
    serious = bool(set(words) & SERIOUS_TERMS)
    silly_signal = score >= 7
    if serious and silly_signal:
        score += 5
        reasons.append("A serious-news word is sharing a sentence with something very ordinary.")

    if "?" in title:
        score += 1
        reasons.append("The question mark makes it feel like the host has paused for the room.")

    if re.search(r"\b\d+\b", title) and re.search(r"\b(?:years?|minutes?|days?|people|times)\b", lower):
        score += 2
        reasons.append("The specific number gives the line a dry little thud.")

    word_count = len(words)
    if 6 <= word_count <= 17:
        score += 2

    if not reasons and score > 0:
        reasons.append("The wording has a straight-faced wobble.")

    return score, reasons


def slugify(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.lower())
    return value.strip("-")[:56] or "headline"


def item_id(item: FeedItem) -> str:
    digest = hashlib.sha1(f"{item.title}|{item.link}".encode("utf-8")).hexdigest()[:10]
    return f"{slugify(item.title)}-{digest}"


def collect_headlines(sources: list[dict[str, str]], limit: int = 24) -> tuple[list[dict[str, object]], list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    candidates: list[tuple[int, FeedItem, list[str]]] = []

    for source in sources:
        try:
            xml_text = fetch_text(source["feed_url"])
            items = parse_feed(source, xml_text)
        except (urllib.error.URLError, TimeoutError, ET.ParseError, UnicodeDecodeError) as exc:
            errors.append({"source": source["name"], "error": str(exc)})
            continue

        for item in items:
            title = clean_text(item.title)
            published = item.published
            if published and published < datetime.now(LOCAL_TZ) - timedelta(days=10):
                continue
            media_text = f"{item.link} {title}".lower()
            if any(marker in media_text for marker in MEDIA_MARKERS):
                continue
            if not title or len(title) > 180:
                continue
            score, reasons = score_title(title)
            if score >= 5:
                candidates.append((score, item, reasons))

    candidates.sort(key=lambda row: row[0], reverse=True)
    selected: list[dict[str, object]] = []
    seen: set[str] = set()
    by_source: dict[str, int] = {}

    for score, item, reasons in candidates:
        key = re.sub(r"\W+", "", item.title.lower())
        if key in seen:
            continue
        if by_source.get(item.source_name, 0) >= 5:
            continue
        seen.add(key)
        by_source[item.source_name] = by_source.get(item.source_name, 0) + 1
        published = item.published or datetime.now(LOCAL_TZ)
        selected.append(
            {
                "id": item_id(item),
                "title": clean_text(item.title),
                "url": item.link,
                "source": item.source_name,
                "country": item.country,
                "source_type": item.source_type,
                "published": published.isoformat(),
                "score": score,
                "why": reasons[0] if reasons else "The wording has a straight-faced wobble.",
                "signals": reasons[:3],
            }
        )
        if len(selected) >= limit:
            break

    return selected, errors


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_archive() -> list[dict[str, object]]:
    if not ARCHIVE_DIR.exists():
        return []
    archives = []
    for path in sorted(ARCHIVE_DIR.glob("*.json"), reverse=True):
        try:
            archives.append(json.loads(path.read_text(encoding="utf-8-sig")))
        except json.JSONDecodeError:
            continue
    return archives


def esc(value: object) -> str:
    return escape(str(value), quote=True)


def human_date(value: str | None) -> str:
    if not value:
        return "date not listed"
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return value[:10]
    return parsed.strftime("%d %b %Y")


def nav_html() -> str:
    links = "\n".join(
        f'<a href="{href}" data-nav="{key}">{label}</a>' for key, label, href in NAV
    )
    return f"""
<header class="site-header">
  <div class="header-inner">
    <a class="brand" href="index.html" aria-label="Straddie Headline Open Mic home">
      <span class="brand-mark" aria-hidden="true">H</span>
      <span>Straddie Headline Open Mic</span>
    </a>
    <nav class="site-nav" aria-label="Main navigation">
      {links}
    </nav>
  </div>
</header>
""".strip()


def footer_html(generated_label: str) -> str:
    links = "\n".join(
        f'<a href="{href}" data-nav="{key}">{label}</a>' for key, label, href in NAV
    )
    return f"""
<footer class="site-footer">
  <div class="footer-inner">
    <div>
      <strong>Straddie Headline Open Mic</strong>
      <p>Daily headline scouting with source links, a light touch, and no claim that the internet has finished being strange.</p>
      <p>Last rebuilt: {esc(generated_label)}.</p>
    </div>
    <nav class="footer-nav" aria-label="Footer navigation">
      {links}
    </nav>
  </div>
</footer>
""".strip()


def hero_html(page_key: str, title: str, intro: str, actions: str = "") -> str:
    image, alt = HERO_IMAGES[page_key]
    action_block = f"\n    {actions}" if actions else ""
    return f"""
<section class="page-hero">
  <div class="hero-copy">
    <h1>{title}</h1>
    <p>{intro}</p>{action_block}
  </div>
  <figure class="hero-art">
    <img src="{image}" alt="{esc(alt)}" loading="eager">
  </figure>
</section>
""".strip()


def page_shell(page_key: str, title: str, description: str, generated_label: str, main: str) -> str:
    cache = datetime.now(LOCAL_TZ).strftime("%Y%m%d%H%M")
    rendered_main = main.strip()
    return f"""<!doctype html>
<html lang="en-AU">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(title)} | Straddie Headline Open Mic</title>
  <meta name="description" content="{esc(description)}">
  <link rel="icon" href="assets/img/favicon.svg" type="image/svg+xml">
  <link rel="stylesheet" href="assets/css/site.css?v={cache}">
</head>
<body data-page="{page_key}">
  <div class="site-shell">
    {nav_html()}
    <main>
{rendered_main}
    </main>
    {footer_html(generated_label)}
  </div>
  <button class="to-top" type="button" aria-label="Back to top">^</button>
  <script src="assets/js/site.js?v={cache}"></script>
</body>
</html>
"""


def headline_card(item: dict[str, object]) -> str:
    search = " ".join(
        str(item.get(key, "")) for key in ["title", "source", "country", "why"]
    ).lower()
    return f"""
<article class="headline-card" data-headline-card data-source="{esc(item["source"])}" data-search="{esc(search)}">
  <div class="card-topline">
    <span>{esc(item["source"])}</span>
    <span>{esc(item["country"])}</span>
    <time datetime="{esc(item["published"])}">{esc(human_date(str(item["published"])))}</time>
  </div>
  <h3><a href="{esc(item["url"])}" target="_blank" rel="noopener noreferrer">{esc(item["title"])}</a></h3>
  <p class="reason">{esc(item["why"])}</p>
</article>
""".strip()


def headline_grid(items: Iterable[dict[str, object]], limit: int | None = None) -> str:
    chosen = list(items)
    if limit is not None:
        chosen = chosen[:limit]
    if not chosen:
        return """
<div class="note-card">
  <h3>The news desk was oddly well behaved.</h3>
  <p>No suitable funny headline candidates were found in this run. The next daily scrape will try again.</p>
</div>
""".strip()
    return '<div class="headline-grid">\n' + "\n".join(headline_card(item) for item in chosen) + "\n</div>"


def build_home(payload: dict[str, object], generated_label: str) -> str:
    headlines = list(payload["headlines"])
    main = f"""
{hero_html(
    "home",
    "Today&apos;s odd headlines, read like an open mic bill",
    "A small daily scrape of English-language print news headlines that made the room laugh, blink, or ask one more question.",
    '<div class="hero-actions"><a class="button" href="headlines.html">Read today&apos;s bill</a><a class="button secondary" href="open-mic.html">Float a comedy night</a></div>',
)}
<section class="section tight">
  <h2>Today&apos;s bill</h2>
  <p class="section-lead">These are linked headlines from the latest run. The script avoids tragedy and heavy harm stories, then looks for deadpan wording, strange scale, accidental comedy, and official sentences that have wandered into the wrong room.</p>
  {headline_grid(headlines, limit=6)}
</section>
<section class="section band">
  <div class="band-inner split">
    <div>
      <h2>Why keep a little board?</h2>
      <p>Print-style news has a special kind of accidental theatre. A headline can be perfectly serious and still sound like a setup. This site collects the gentle ones, points back to the original source, and leaves the heavy stories alone.</p>
      <div class="button-row"><a class="button secondary" href="sources.html">See the method</a></div>
    </div>
    <div class="quote-panel">
      <p>The joke is not the news. The joke is often the tiny human wording that slips through the news.</p>
    </div>
  </div>
</section>
<section class="section">
  <h2>Could Straddie use an open mic?</h2>
  <p class="section-lead">Maybe this stays as a headline board. Maybe it becomes a relaxed local comedy night where people can try five minutes, read a strange headline, or simply sit in the room and enjoy the courage.</p>
  <div class="principle-grid">
    <article class="note-card"><h3>Short spots</h3><p>Small sets, easy entry, and enough space for first-timers to test one idea without needing a whole act.</p></article>
    <article class="note-card"><h3>Local tone</h3><p>Warm, dry, plain-speaking humour that suits a community hall, a bowls club corner, or a quiet night at a venue.</p></article>
    <article class="note-card"><h3>No pressure</h3><p>The question is open. If people want it, the format can grow from what the room actually enjoys.</p></article>
  </div>
</section>
"""
    return page_shell(
        "home",
        "Today's odd headline bill",
        "A daily board of funny English-language news headlines with a gentle Straddie open mic theme.",
        generated_label,
        main,
    )


def build_headlines(payload: dict[str, object], generated_label: str) -> str:
    headlines = list(payload["headlines"])
    sources = sorted({str(item["source"]) for item in headlines})
    options = "\n".join(f'<option value="{esc(source)}">{esc(source)}</option>' for source in sources)
    main = f"""
{hero_html(
    "headlines",
    "The headline bill",
    "The latest daily picks, linked back to the original sources. Search the room, pick a source, or follow a headline out to the full story.",
)}
<section class="section tight">
  <h2>Latest picks</h2>
  <p class="section-lead">Showing <span id="headline-count">{len(headlines)}</span> headline candidates from the refresh run completed on {esc(generated_label)}.</p>
  <div class="filters" aria-label="Headline filters">
    <div class="field">
      <label for="headline-search">Search headlines</label>
      <input id="headline-search" type="search" placeholder="Try mystery, council, sandwich...">
    </div>
    <div class="field">
      <label for="source-filter">Source</label>
      <select id="source-filter">
        <option value="all">All sources</option>
        {options}
      </select>
    </div>
  </div>
  {headline_grid(headlines)}
</section>
"""
    return page_shell(
        "headlines",
        "The headline bill",
        "Search and read the latest source-linked funny headline picks.",
        generated_label,
        main,
    )


def build_open_mic(generated_label: str) -> str:
    main = f"""
{hero_html(
    "open-mic",
    "Should Straddie try a comedy open mic?",
    "A soft question, not a campaign. If the island wants it, this could become a regular night for short sets, odd headline readings, and low-stakes laughter.",
    '<div class="hero-actions"><a class="button" href="headlines.html">Read headline prompts</a><a class="button secondary" href="sources.html">Check the source rules</a></div>',
)}
<section class="section tight split">
  <div>
    <h2>A possible shape</h2>
    <p>The simplest version is one friendly night a month. A host opens the room, a few people try short spots, someone reads the oddest headline of the day, and nobody has to pretend this is bigger than it is.</p>
    <ul class="simple-list">
      <li>Five-minute sets for anyone who wants to try.</li>
      <li>A headline-reading slot for people who would rather not perform a full bit.</li>
      <li>A venue-friendly format that can fit a quiet midweek night.</li>
      <li>A tone that keeps the room kind, local, and relaxed.</li>
    </ul>
  </div>
  <aside class="quote-panel">
    <p>Start with a microphone, a few chairs, and permission for the first joke to be a bit wobbly.</p>
  </aside>
</section>
<section class="section band">
  <div class="band-inner">
    <h2>What the site can test</h2>
    <p class="section-lead">The headline board is a low-risk way to see whether people enjoy the flavour: dry headlines, odd turns of phrase, and a room that lets humour be neighbourly rather than mean.</p>
    <div class="principle-grid">
      <article class="note-card"><h3>Headline prompts</h3><p>Each daily pick can become a writing prompt, a host opener, or a gentle icebreaker.</p></article>
      <article class="note-card"><h3>Plain tone</h3><p>The copy should sound like a person inviting a room, not a poster barking instructions.</p></article>
      <article class="note-card"><h3>Room first</h3><p>If locals prefer a tiny reading group, a casual showcase, or no night at all, that answer still counts.</p></article>
    </div>
  </div>
</section>
"""
    return page_shell(
        "open-mic",
        "Comedy open mic question",
        "A gentle Straddie open mic concept connected to the daily funny headline board.",
        generated_label,
        main,
    )


def build_sources(payload: dict[str, object], sources: list[dict[str, str]], generated_label: str) -> str:
    error_rows = payload.get("feed_errors", [])
    source_cards = "\n".join(
        f"""
<article class="source-card">
  <h3>{esc(source["name"])}</h3>
  <p>{esc(source["country"])}. {esc(source["type"])}.</p>
  <p><a href="{esc(source["feed_url"])}">RSS / Atom feed</a></p>
</article>
""".strip()
        for source in sources
    )
    errors_html = ""
    if error_rows:
        items = "".join(
            f"<li>{esc(row['source'])}: {esc(row['error'])}</li>" for row in error_rows
        )
        errors_html = f"""
<section class="section">
  <h2>Feed notes from this run</h2>
  <p class="section-lead">Some feeds can be temporarily quiet or grumpy. The site still rebuilds from the feeds that answered.</p>
  <ul class="simple-list">{items}</ul>
</section>
"""
    main = f"""
{hero_html(
    "sources",
    "Sources and selection rules",
    "The daily scout reads public RSS and Atom feeds, keeps the headline and link, then scores odd wording. It does not copy article bodies.",
)}
<section class="section tight">
  <h2>The current feed list</h2>
  <p class="section-lead">The source mix leans toward English-language newspaper, news-agency, and print-style newsroom feeds from Australia, the UK, the US, Canada, New Zealand, Ireland, and international outlets.</p>
  <div class="source-grid">{source_cards}</div>
</section>
<section class="section band">
  <div class="band-inner">
    <h2>How a headline gets picked</h2>
    <div class="principle-grid">
      <article class="note-card"><h3>Look for odd wording</h3><p>The script scores words like mystery, accidentally, bizarre, tiny, giant, and other straight-faced signals.</p></article>
      <article class="note-card"><h3>Leave harm alone</h3><p>Stories about death, assault, disasters, war, and similar heavy subjects are filtered out before scoring.</p></article>
      <article class="note-card"><h3>Link back</h3><p>Each card links to the source. The site stores the headline, source, date, URL, and a short note about the wording.</p></article>
    </div>
  </div>
</section>
{errors_html}
"""
    return page_shell(
        "sources",
        "Sources and selection rules",
        "Source feeds and plain-language rules for the daily headline scout.",
        generated_label,
        main,
    )


def build_archive(archives: list[dict[str, object]], generated_label: str) -> str:
    if not archives:
        archive_html = """
<div class="note-card">
  <h3>No archive yet</h3>
  <p>The first daily refresh will create the opening archive file.</p>
</div>
""".strip()
    else:
        chunks = []
        for archive in archives[:14]:
            date_label = archive.get("date", "undated")
            headlines = list(archive.get("headlines", []))[:5]
            chunks.append(
                f"""
<section class="section tight">
  <h2>{esc(date_label)}</h2>
  {headline_grid(headlines)}
</section>
""".strip()
            )
        archive_html = "\n".join(chunks)
    main = f"""
{hero_html(
    "archive",
    "The old bills",
    "A dated record of earlier headline boards, kept so the room can remember which strange sentence got the laugh last time.",
)}
{archive_html}
"""
    return page_shell(
        "archive",
        "Headline archive",
        "Dated archive of past daily funny headline boards.",
        generated_label,
        main,
    )


def build_site_map(generated_label: str) -> str:
    cards = "\n".join(
        f"""
<article class="link-card">
  <h3><a href="{href}">{label}</a></h3>
  <p>{description_for_page(key)}</p>
</article>
""".strip()
        for key, label, href in NAV
    )
    main = f"""
{hero_html(
    "site-map",
    "Site map",
    "A plain map of the public pages, data files, and daily automation path.",
)}
<section class="section tight">
  <h2>Pages</h2>
  <div class="link-grid">{cards}</div>
</section>
<section class="section band">
  <div class="band-inner">
    <h2>Useful files</h2>
    <div class="link-grid">
      <article class="link-card"><h3><a href="assets/data/headlines.json">Latest headline data</a></h3><p>The public JSON file generated by the daily refresh.</p></article>
      <article class="link-card"><h3><a href="data/sources.json">Source feed list</a></h3><p>The editable list of public RSS and Atom feeds.</p></article>
    </div>
  </div>
</section>
"""
    return page_shell(
        "site-map",
        "Site map",
        "Public site map for Straddie Headline Open Mic.",
        generated_label,
        main,
    )


def description_for_page(key: str) -> str:
    return {
        "home": "Opening page with today&apos;s bill and the open mic question.",
        "headlines": "Searchable list of the latest headline picks.",
        "open-mic": "A gentle outline for a possible Straddie comedy night.",
        "sources": "Feed list, scoring rules, and content boundaries.",
        "archive": "Dated headline boards from previous refreshes.",
        "site-map": "This page, with public routes and data links.",
    }[key]


def write_docs_site_map() -> None:
    lines = [
        "# Site map",
        "",
        "Public pages generated by `tools/refresh_site.py`:",
        "",
    ]
    for _, label, href in NAV:
        lines.append(f"- `{href}` - {label}")
    lines.extend(
        [
            "",
            "Public data:",
            "",
            "- `assets/data/headlines.json` - latest headline run",
            "- `data/archive/YYYY-MM-DD.json` - dated archive snapshots",
            "- `data/sources.json` - feed configuration",
            "",
        ]
    )
    (ROOT / "docs" / "site-map.md").write_text("\n".join(lines), encoding="utf-8")


def write_pages(payload: dict[str, object], sources: list[dict[str, str]]) -> None:
    generated_label = str(payload["generated_label"])
    archives = read_archive()
    pages = {
        "index.html": build_home(payload, generated_label),
        "headlines.html": build_headlines(payload, generated_label),
        "open-mic.html": build_open_mic(generated_label),
        "sources.html": build_sources(payload, sources, generated_label),
        "archive.html": build_archive(archives, generated_label),
        "site-map.html": build_site_map(generated_label),
    }
    for filename, html in pages.items():
        (ROOT / filename).write_text(html, encoding="utf-8")
    write_docs_site_map()


def main() -> int:
    sources = load_sources()
    now = datetime.now(LOCAL_TZ)
    headlines, errors = collect_headlines(sources)
    payload: dict[str, object] = {
        "site": "Straddie Headline Open Mic",
        "date": now.date().isoformat(),
        "generated_at": now.isoformat(),
        "generated_label": now.strftime("%d %b %Y, %I:%M %p AEST"),
        "source_count": len(sources),
        "headline_count": len(headlines),
        "headlines": headlines,
        "feed_errors": errors,
    }
    write_json(PUBLIC_DATA, payload)
    write_json(ARCHIVE_DIR / f"{now.date().isoformat()}.json", payload)
    write_pages(payload, sources)
    print(f"Built {len(headlines)} headline cards from {len(sources)} feeds.")
    if errors:
        print(f"{len(errors)} feed(s) reported an error; see assets/data/headlines.json.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
