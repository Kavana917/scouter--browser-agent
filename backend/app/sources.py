"""Registered, bounded source adapters for Scouter."""

from __future__ import annotations

import html
import base64
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import parse_qs, quote_plus, urlparse
from uuid import uuid4

import httpx


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


class DuckDuckGoParser(HTMLParser):
    """Extract result links and snippets from DuckDuckGo's lightweight HTML page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.items: list[dict[str, str]] = []
        self._link: dict[str, str] | None = None
        self._capture: str | None = None
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        classes = set((attr.get("class") or "").split())
        if tag == "a" and "result__a" in classes:
            self._link = {"href": attr.get("href") or "", "title": ""}
            self._capture = "title"
            self._parts = []
        elif tag in {"a", "div"} and "result__snippet" in classes and self.items:
            self._capture = "snippet"
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._capture == "title" and tag == "a" and self._link:
            title = _clean_text("".join(self._parts))
            href = self._link["href"]
            parsed = urlparse(href)
            if parsed.hostname and parsed.hostname.endswith("duckduckgo.com"):
                href = parse_qs(parsed.query).get("uddg", [href])[0]
            if href.startswith(("https://", "http://")) and title:
                self.items.append({"title": title, "url": href, "snippet": ""})
            self._link = None
            self._capture = None
            self._parts = []
        elif self._capture == "snippet" and tag in {"a", "div"}:
            if self.items:
                self.items[-1]["snippet"] = _clean_text("".join(self._parts))
            self._capture = None
            self._parts = []


class BingSearchParser(HTMLParser):
    """Extract standard web result cards from Bing's server-rendered HTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.items: list[dict[str, str]] = []
        self._card: dict[str, str] | None = None
        self._li_depth = 0
        self._in_heading = False
        self._capture: str | None = None
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        classes = set((attr.get("class") or "").split())
        if tag == "li" and "b_algo" in classes:
            self._card = {"url": "", "title": "", "snippet": ""}
            self._li_depth = 1
        elif self._card is not None:
            if tag == "li":
                self._li_depth += 1
            if tag == "h2":
                self._in_heading = True
                self._capture = "title"
                self._parts = []
            elif tag == "a" and self._in_heading:
                self._card["url"] = attr.get("href") or ""
            elif tag == "p" and not self._card["snippet"]:
                self._capture = "snippet"
                self._parts = []

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "h2" and self._in_heading:
            if self._card is not None and self._capture == "title":
                self._card["title"] = _clean_text("".join(self._parts))
            self._capture = None
            self._parts = []
            self._in_heading = False
        elif tag == "p" and self._capture == "snippet":
            if self._card is not None:
                self._card["snippet"] = _clean_text("".join(self._parts))
            self._capture = None
            self._parts = []
        elif tag == "li" and self._card is not None:
            self._li_depth -= 1
            if self._li_depth <= 0:
                if self._card["url"] and self._card["title"]:
                    self.items.append(self._card)
                self._card = None


class BraveSearchParser(HTMLParser):
    """Read Brave's server-rendered organic result cards."""

    _void_tags = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.items: list[dict[str, str]] = []
        self._card: dict[str, str] | None = None
        self._depth = 0
        self._capture: str | None = None
        self._capture_tag = ""
        self._capture_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        classes = set((attr.get("class") or "").split())
        if self._card is None:
            if tag == "div" and "snippet" in classes and attr.get("data-type") == "web":
                self._card = {"url": "", "title": attr.get("title") or "", "snippet": ""}
                self._depth = 1
            return
        if tag not in self._void_tags:
            self._depth += 1
        if tag == "a" and not self._card["url"]:
            self._card["url"] = attr.get("href") or ""
        if tag == "div" and "search-snippet-title" in classes:
            self._card["title"] = attr.get("title") or ""
            self._capture, self._capture_tag, self._capture_depth, self._parts = "title", tag, self._depth, []
        elif tag == "div" and "generic-snippet" in classes:
            self._capture, self._capture_tag, self._capture_depth, self._parts = "snippet", tag, self._depth, []

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._card is None:
            return
        if self._capture and tag == self._capture_tag and self._depth == self._capture_depth:
            if self._capture == "snippet" and self._card is not None:
                self._card["snippet"] = _clean_text("".join(self._parts))
            elif self._capture == "title" and self._card is not None and not self._card["title"]:
                self._card["title"] = _clean_text("".join(self._parts))
            self._capture = None
            self._parts = []
        if tag not in self._void_tags:
            self._depth -= 1
        if self._depth <= 0:
            if self._card["url"] and self._card["title"]:
                self.items.append(self._card)
            self._card = None


def _resolve_bing_url(url: str) -> str:
    url = html.unescape(url)
    parsed = urlparse(url)
    if (parsed.hostname or "").lower().endswith("bing.com"):
        encoded = parse_qs(parsed.query).get("u", [""])[0]
        if encoded.startswith("a1"):
            try:
                payload = encoded[2:]
                payload += "=" * (-len(payload) % 4)
                decoded = base64.urlsafe_b64decode(payload).decode("utf-8", "ignore")
                if decoded.startswith(("https://", "http://")):
                    return decoded
            except (ValueError, UnicodeError):
                pass
    return url


def _evidence(tool_id: str, title: str, url: str, snippet: str, **extra) -> dict:
    return {
        "evidence_id": str(uuid4()), "tool_id": tool_id,
        "title": title[:240], "url": url, "snippet": snippet[:700], "retrieved_at": now_iso(),
        **extra,
    }


async def search_web(client: httpx.AsyncClient, query: str, limit: int) -> list[dict]:
    seen: set[str] = set()
    results = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0 Safari/537.36"}
    providers = (
        ("https://search.brave.com/search", {"q": query}, BraveSearchParser, lambda url: html.unescape(url)),
        ("https://www.bing.com/search", {"q": query}, BingSearchParser, _resolve_bing_url),
    )
    for endpoint, params, parser_type, resolve_url in providers:
        try:
            response = await client.get(endpoint, params=params, headers=headers)
            response.raise_for_status()
        except httpx.HTTPError:
            continue
        parser = parser_type()
        parser.feed(response.text)
        for item in parser.items:
            url = resolve_url(item["url"])
            parsed = urlparse(url)
            if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password or url in seen:
                continue
            if parsed.hostname.endswith(("brave.com", "bing.com")):
                continue
            seen.add(url)
            results.append(_evidence("web", item["title"], url, item["snippet"]))
            if len(results) >= limit:
                break
        if results:
            break
    return results


async def search_wikipedia(client: httpx.AsyncClient, query: str, limit: int) -> list[dict]:
    response = await client.get(
        "https://en.wikipedia.org/w/api.php",
        params={"action": "query", "generator": "search", "gsrsearch": query, "format": "json", "utf8": 1, "gsrlimit": limit,
                "prop": "extracts", "exintro": 1, "explaintext": 1},
    )
    response.raise_for_status()
    results = []
    payload = response.json()
    pages = payload.get("query", {}).get("pages", {})
    for item in pages.values():
        title = item.get("title", "")
        if title:
            slug = quote_plus(title.replace(" ", "_"))
            extract = _clean_text(item.get("extract", ""))
            results.append(_evidence("wikipedia", title, f"https://en.wikipedia.org/wiki/{slug}", extract or _clean_text(item.get("snippet", "")), content=extract[:12000]))
    return results


async def search_papers(client: httpx.AsyncClient, query: str, limit: int) -> list[dict]:
    response = await client.get(
        "https://api.crossref.org/works",
        params={"query": query, "rows": limit, "select": "title,URL,author,published,container-title"},
    )
    response.raise_for_status()
    results = []
    for item in response.json().get("message", {}).get("items", []):
        title = (item.get("title") or [""])[0]
        url = item.get("URL")
        if not title or not url:
            continue
        journal = (item.get("container-title") or ["Crossref"])[0]
        year = ((item.get("published") or {}).get("date-parts") or [[None]])[0][0]
        results.append(_evidence("papers", title, url, f"{journal}{f' · {year}' if year else ''}"))
    return results


TOOLS = [
    {"tool_id": "web", "label": "Web search", "description": "Find useful pages across the web.", "enabled": True},
    {"tool_id": "wikipedia", "label": "Wikipedia", "description": "Get fast topic context from Wikipedia.", "enabled": True},
    {"tool_id": "papers", "label": "Research papers", "description": "Find scholarly references through Crossref.", "enabled": True},
    {"tool_id": "youtube", "label": "YouTube", "description": "Find public videos and demonstrations.", "enabled": True},
    {"tool_id": "images", "label": "Image search", "description": "Find visual references with source-page attribution.", "enabled": True},
    {"tool_id": "open_page", "label": "Open a page", "description": "Read any public web page in an isolated viewer.", "enabled": True},
]

ADAPTERS = {"web": search_web, "wikipedia": search_wikipedia, "papers": search_papers}
BROWSER_TOOLS = {"youtube", "images", "open_page"}
