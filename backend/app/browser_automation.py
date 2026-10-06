"""Isolated Playwright worker for registered, bounded public web sources."""

from __future__ import annotations

import asyncio
import ipaddress
import json
import os
import socket
from urllib.parse import quote_plus, urljoin, urlparse
from uuid import uuid4

from playwright.async_api import Browser, BrowserContext, Error as PlaywrightError, async_playwright

from .sources import now_iso


class BrowserAutomationError(RuntimeError):
    def __init__(self, code: str, message: str, status: str = "unavailable") -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message
        self.status = status


def configured_site_domains() -> list[str]:
    raw = os.getenv("ALLOWED_SITE_DOMAINS", "")
    return [entry.strip().lower().lstrip(".") for entry in raw.split(",") if entry.strip()]


def _host_allowed(host: str, allowed: set[str]) -> bool:
    host = host.lower().rstrip(".")
    return any(host == domain or host.endswith(f".{domain}") for domain in allowed)


async def _public_host(host: str, cache: dict[str, bool]) -> bool:
    host = host.strip("[]").rstrip(".").lower()
    if host in cache:
        return cache[host]
    try:
        literal = ipaddress.ip_address(host)
        result = literal.is_global
    except ValueError:
        if host in {"localhost", "localhost.localdomain"} or host.endswith(".localhost") or host.endswith(".local"):
            result = False
        else:
            try:
                records = await asyncio.to_thread(socket.getaddrinfo, host, None, type=socket.SOCK_STREAM)
                addresses = {ipaddress.ip_address(record[4][0].split("%", 1)[0]) for record in records}
                result = bool(addresses) and all(address.is_global for address in addresses)
            except (OSError, ValueError):
                result = False
    cache[host] = result
    return result


def _http_url(url: str, allow_hosts: set[str] | None = None) -> str:
    if not url or len(url) > 2048:
        raise BrowserAutomationError("INVALID_TARGET", "Enter a valid public page URL.", "failed")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise BrowserAutomationError("INVALID_TARGET", "Only public HTTP or HTTPS pages can be opened.", "failed")
    if parsed.port not in {None, 80, 443}:
        raise BrowserAutomationError("INVALID_TARGET", "This page uses a port that Scouter does not open.", "failed")
    host = parsed.hostname.lower().rstrip(".")
    if allow_hosts and not _host_allowed(host, allow_hosts):
        raise BrowserAutomationError("INVALID_TARGET", "That page is outside the allowed host for this visit.", "failed")
    return url


def validate_open_page_url(url: str) -> str:
    return _http_url(url)


class BrowserAutomation:
    """Owns one Chromium process and creates a clean BrowserContext per task."""

    def __init__(self) -> None:
        self._playwright = None
        self._browser: Browser | None = None
        self._semaphore = asyncio.Semaphore(self._max_concurrency())
        self.startup_error: str | None = None

    @staticmethod
    def _max_concurrency() -> int:
        try:
            return max(1, min(4, int(os.getenv("PLAYWRIGHT_MAX_CONCURRENCY", "2"))))
        except ValueError:
            return 2

    @property
    def available(self) -> bool:
        return self._browser is not None and self._browser.is_connected()

    async def start(self) -> None:
        try:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=os.getenv("BROWSER_HEADLESS", "true").lower() != "false")
            self.startup_error = None
        except Exception as exc:
            self.startup_error = type(exc).__name__
            if self._playwright:
                await self._playwright.stop()
            self._playwright = None
            self._browser = None

    async def stop(self) -> None:
        if self._browser and self._browser.is_connected():
            await self._browser.close()
        self._browser = None
        if self._playwright:
            await self._playwright.stop()
        self._playwright = None

    async def _new_context(self, allowed_hosts: set[str]) -> BrowserContext:
        if not self.available or not self._browser:
            detail = "Browser automation is not ready. Install the Playwright Chromium browser and restart the API."
            raise BrowserAutomationError("BROWSER_UNAVAILABLE", detail)
        context = await self._browser.new_context(
            locale="en-US", service_workers="block", accept_downloads=False,
            ignore_https_errors=False, java_script_enabled=True,
            viewport={"width": 1365, "height": 900},
        )
        dns_cache: dict[str, bool] = {}

        async def guard(route) -> None:
            parsed = urlparse(route.request.url)
            host = parsed.hostname or ""
            if (
                parsed.scheme not in {"http", "https"}
                or parsed.port not in {None, 80, 443}
                or not _host_allowed(host, allowed_hosts)
                or not await _public_host(host, dns_cache)
                or route.request.resource_type in {"image", "media", "font"}
            ):
                await route.abort()
                return
            await route.continue_()

        await context.route("**/*", guard)
        context.set_default_timeout(6500)
        context.set_default_navigation_timeout(12000)
        return context

    async def _page(self, context: BrowserContext):
        page = await context.new_page()
        page.on("dialog", lambda dialog: asyncio.create_task(dialog.dismiss()))
        page.on("popup", lambda popup: asyncio.create_task(popup.close()))
        return page

    async def search(self, tool_id: str, query: str, limit: int) -> list[dict]:
        if tool_id == "web":
            results = await self._bing_web(query, limit)
            return results or await self._duckduckgo(query, limit)
        if tool_id == "youtube":
            results = await self._youtube(query, limit)
            if results:
                return results
            fallback = await self._bing_web(f"{query} site:youtube.com/watch", limit)
            return [{**item, "tool_id": "youtube"} for item in fallback if "youtube.com/watch" in item["url"]]
        if tool_id == "images":
            return await self._bing_images(query, limit)
        if tool_id == "open_page":
            return await self._open_page(query, limit)
        raise BrowserAutomationError("UNKNOWN_TOOL", "That browser source is not registered.", "failed")

    async def _duckduckgo(self, query: str, limit: int) -> list[dict]:
        allowed = {"duckduckgo.com"}
        async with self._semaphore:
            context = await self._new_context(allowed)
            try:
                page = await self._page(context)
                await page.goto(f"https://html.duckduckgo.com/html/?q={quote_plus(query)}", wait_until="domcontentloaded")
                cards = await page.locator(".result").all()
                results = []
                seen = set()
                for card in cards:
                    link = card.locator("a.result__a").first
                    title = (await link.inner_text()).strip()
                    url = await link.get_attribute("href")
                    snippet = await card.locator(".result__snippet").first.inner_text() if await card.locator(".result__snippet").count() else ""
                    parsed = urlparse(url or "")
                    if parsed.hostname.endswith("duckduckgo.com"):
                        from urllib.parse import parse_qs
                        url = parse_qs(parsed.query).get("uddg", [""])[0]
                    if not title or not self._safe_link(url) or url in seen:
                        continue
                    seen.add(url)
                    results.append(self._item("web", title, url, snippet))
                    if len(results) >= limit:
                        break
                return results
            except PlaywrightError as exc:
                raise self._page_error(exc) from exc
            finally:
                await context.close()

    async def _bing_web(self, query: str, limit: int) -> list[dict]:
        allowed = {"bing.com", "bing.net", "microsoft.com", "msecnd.net"}
        async with self._semaphore:
            context = await self._new_context(allowed)
            try:
                page = await self._page(context)
                await page.goto(f"https://www.bing.com/search?q={quote_plus(query)}", wait_until="domcontentloaded")
                cards = await page.locator("li.b_algo").all()
                results = []
                seen = set()
                for card in cards:
                    link = card.locator("h2 a").first
                    if not await link.count():
                        continue
                    title = (await link.inner_text()).strip()
                    url = await link.get_attribute("href") or ""
                    snippet_node = card.locator(".b_caption p").first
                    snippet = (await snippet_node.inner_text()).strip() if await snippet_node.count() else ""
                    if not title or not self._safe_link(url) or url in seen:
                        continue
                    seen.add(url)
                    results.append(self._item("web", title, url, snippet))
                    if len(results) >= limit:
                        break
                return results
            except PlaywrightError as exc:
                raise self._page_error(exc) from exc
            finally:
                await context.close()

    async def _youtube(self, query: str, limit: int) -> list[dict]:
        allowed = {"youtube.com", "ytimg.com", "ggpht.com", "googlevideo.com", "googleapis.com", "googleusercontent.com"}
        async with self._semaphore:
            context = await self._new_context(allowed)
            try:
                page = await self._page(context)
                await page.goto(f"https://www.youtube.com/results?search_query={quote_plus(query)}", wait_until="domcontentloaded")
                try:
                    await page.locator("ytd-video-renderer a#video-title, ytd-rich-item-renderer a#video-title").first.wait_for(timeout=3500)
                except PlaywrightError:
                    pass
                cards = await page.locator("ytd-video-renderer, ytd-rich-item-renderer").all()
                results = []
                seen = set()
                for card in cards:
                    link = card.locator("a#video-title").first
                    if not await link.count():
                        continue
                    title = (await link.get_attribute("title") or await link.inner_text()).strip()
                    href = await link.get_attribute("href") or ""
                    url = urljoin("https://www.youtube.com", href)
                    if "/watch?" not in url or url in seen or not title:
                        continue
                    seen.add(url)
                    channel = card.locator("ytd-channel-name").first
                    metadata = card.locator("#metadata-line").first
                    parts = []
                    if await channel.count():
                        parts.append((await channel.inner_text()).strip())
                    if await metadata.count():
                        parts.append((await metadata.inner_text()).strip())
                    results.append(self._item("youtube", title, url, " · ".join(parts)))
                    if len(results) >= limit:
                        break
                return results
            except PlaywrightError as exc:
                raise self._page_error(exc) from exc
            finally:
                await context.close()

    async def _bing_images(self, query: str, limit: int) -> list[dict]:
        allowed = {"bing.com", "bing.net", "microsoft.com", "msecnd.net"}
        async with self._semaphore:
            context = await self._new_context(allowed)
            try:
                page = await self._page(context)
                await page.goto(f"https://www.bing.com/images/search?q={quote_plus(query)}", wait_until="domcontentloaded")
                tiles = await page.locator("a.iusc").all()
                results = []
                seen = set()
                for tile in tiles:
                    metadata = await tile.get_attribute("m")
                    try:
                        item = json.loads(metadata or "{}")
                    except (TypeError, json.JSONDecodeError):
                        continue
                    title = (item.get("t") or "").strip()
                    page_url = item.get("purl") or ""
                    image_url = item.get("murl") or ""
                    page_parsed = urlparse(page_url)
                    image_parsed = urlparse(image_url)
                    if not title or page_parsed.scheme not in {"https", "http"} or not page_parsed.hostname:
                        continue
                    if not self._safe_link(page_url) or not self._safe_link(image_url) or page_url in seen:
                        continue
                    seen.add(page_url)
                    results.append(self._item("images", title, page_url, item.get("desc") or "Image result; open the source page for attribution.", thumbnail_url=image_url))
                    if len(results) >= limit:
                        break
                return results
            except PlaywrightError as exc:
                raise self._page_error(exc) from exc
            finally:
                await context.close()

    async def _open_page(self, url: str, _limit: int) -> list[dict]:
        url = _http_url(url)
        host = urlparse(url).hostname or ""
        # Bind this visit to the host the user entered. Browser route checks also
        # resolve every requested host and reject private or local IP ranges.
        domains = {host.lower().rstrip(".")}
        if not await _public_host(host, {}):
            raise BrowserAutomationError("INVALID_TARGET", "That domain does not resolve to a public address.", "failed")
        async with self._semaphore:
            context = await self._new_context(domains)
            try:
                page = await self._page(context)
                response = await page.goto(url, wait_until="domcontentloaded")
                if response and response.status in {401, 403, 429}:
                    raise BrowserAutomationError("SOURCE_BLOCKED", "This page requires access that Scouter does not use.")
                final = urlparse(page.url)
                if final.scheme not in {"https", "http"} or not _host_allowed(final.hostname or "", domains):
                    raise BrowserAutomationError("INVALID_TARGET", "The page redirected outside the host you entered.", "failed")
                title = (await page.title()).strip() or final.hostname or "Web page"
                content_locator = page.locator("main, article").first
                if not await content_locator.count():
                    content_locator = page.locator("body")
                excerpt = " ".join((await content_locator.inner_text()).split())[:1500]
                if not excerpt:
                    raise BrowserAutomationError("EXTRACTION_FAILED", "No readable page text was found.", "failed")
                return [self._item("open_page", title, page.url, excerpt, content=excerpt[:12000])]
            except BrowserAutomationError:
                raise
            except PlaywrightError as exc:
                raise self._page_error(exc) from exc
            finally:
                await context.close()

    @staticmethod
    def _item(tool_id: str, title: str, url: str, snippet: str, **extra) -> dict:
        return {
            "evidence_id": str(uuid4()), "tool_id": tool_id, "title": title[:240],
            "url": url, "snippet": " ".join((snippet or "").split())[:1000],
            "retrieved_at": now_iso(), **extra,
        }

    @staticmethod
    def _safe_link(url: str) -> bool:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            return False
        if parsed.port not in {None, 80, 443}:
            return False
        try:
            return ipaddress.ip_address(parsed.hostname.strip("[]")).is_global
        except ValueError:
            return True

    @staticmethod
    def _page_error(error: PlaywrightError) -> BrowserAutomationError:
        message = str(error).lower()
        if "timeout" in message:
            return BrowserAutomationError("NAVIGATION_TIMEOUT", "This source took too long to respond.", "timed_out")
        if "net::err_blocked_by_client" in message or "net::err_aborted" in message:
            return BrowserAutomationError("SOURCE_BLOCKED", "This source blocked the automated request.")
        return BrowserAutomationError("NAVIGATION_FAILED", "Could not open this source right now.", "unavailable")
