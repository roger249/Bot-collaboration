from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import Coroutine
from typing import Any

from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig, DefaultMarkdownGenerator
from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class Crawl4AIInput(BaseModel):
    """Input for Crawl4AI web crawler tool."""

    url: str = Field(..., description="Mandatory website url to crawl and extract content from")



class Crawl4AITool(BaseTool):
    name: str = "Crawl4AI"
    description: str = (
        "Crawl a webpage and return extracted Markdown content if available, otherwise cleaned HTML. "
        "Use this for web research when a URL is available."
    )
    args_schema: type[BaseModel] = Crawl4AIInput
    max_output_chars: int = 12_000

    def _run(self, url: str) -> str:
        normalized = str(url).strip()
        if not normalized:
            raise ValueError("Crawl4AI requires a non-empty URL.")
        if not normalized.startswith(("http://", "https://")):
            raise ValueError("Crawl4AI URL must start with http:// or https://")

        result = _run_async(_crawl(normalized))

        # Prefer markdown text, but handle Crawl4AI versions that return a markdown result object.
        text = _extract_text(result)
        if not text.strip():
            raise RuntimeError(f"Crawl4AI returned empty content for URL: {normalized}")

        if self.max_output_chars > 0 and len(text) > self.max_output_chars:
            omitted = len(text) - self.max_output_chars
            return f"{text[: self.max_output_chars]}\n...[truncated {omitted} chars]"
        return text


def _extract_text(result: Any) -> str:
    markdown = getattr(result, "markdown", None)
    if isinstance(markdown, str) and markdown:
        return markdown

    raw_markdown = getattr(markdown, "raw_markdown", None)
    if isinstance(raw_markdown, str) and raw_markdown:
        return raw_markdown

    fit_markdown = getattr(markdown, "fit_markdown", None)
    if isinstance(fit_markdown, str) and fit_markdown:
        return fit_markdown

    if hasattr(result, "cleaned_html") and result.cleaned_html and isinstance(result.cleaned_html, str):
        return result.cleaned_html
    if hasattr(result, "html") and result.html and isinstance(result.html, str):
        return result.html

    return getattr(result, "extracted_content", "") or ""


def _run_async(coro: Coroutine[Any, Any, Any]) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: dict[str, Any] = {}
    error: dict[str, Exception] = {}

    def _runner() -> None:
        try:
            result["value"] = asyncio.run(coro)
        except Exception as exc:  # pragma: no cover - passthrough from worker thread
            error["value"] = exc

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    thread.join()

    if "value" in error:
        raise error["value"]
    return result.get("value")



# Domains known to use Cloudflare managed challenge — require the domcontentloaded +
# challenge-hook flow so the CF interstitial can be resolved before content is read.
_CF_PROTECTED_DOMAINS: frozenset[str] = frozenset({"macrotrends.net"})


def _is_cf_protected(url: str) -> bool:
    """Return True if *url* belongs to a domain with Cloudflare managed challenge."""
    from urllib.parse import urlparse

    host = (urlparse(url).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in _CF_PROTECTED_DOMAINS)


async def _crawl(url: str):
    """Crawl *url*, choosing the appropriate anti-bot strategy for the domain."""
    browser_config = BrowserConfig(
        browser_type="chromium",
        headless=False,  # Non-headless: CF managed challenge passes automatically for real browsers
        extra_args=["--disable-blink-features=AutomationControlled"],
    )

    if _is_cf_protected(url):
        # Cloudflare-hardened path: exit goto() early (domcontentloaded) so the
        # after_goto hook can poll for the real page after the managed challenge
        # auto-resolves.  Using networkidle here would cause CF to finish its JS
        # before the hook runs, resulting in a hard block.
        crawler_config = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            markdown_generator=DefaultMarkdownGenerator(),
            wait_until="domcontentloaded",
            delay_before_return_html=3.0,
        )
        install_cf_hook = True
    else:
        # Standard path: domcontentloaded avoids timeouts on SPAs (e.g. Yahoo Finance)
        # that never reach networkidle due to background analytics/ad polling.
        # A longer post-load delay gives JS time to render async content.
        crawler_config = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            markdown_generator=DefaultMarkdownGenerator(),
            wait_until="domcontentloaded",
            delay_before_return_html=8.0,
        )
        install_cf_hook = False

    async with AsyncWebCrawler(config=browser_config) as crawler:
        if install_cf_hook:
            crawler.crawler_strategy.set_hook("after_goto", _handle_cf_challenge)
        result = await crawler.arun(url=url, config=crawler_config)

    if not result.success:
        # Macrotrends (and some other sites) embed Cloudflare's challenge-platform
        # script on every page — including real content pages — causing crawl4ai's
        # antibot detector to false-positive.  Extract and validate the content
        # ourselves: if it looks real (not an actual challenge page), return it.
        text = _extract_text(result)
        text_lower = text.lower()
        is_genuine_block = (
            not text.strip()
            or (
                "just a moment" in text_lower
                and "enable javascript" in text_lower
            )
        )
        if is_genuine_block:
            message = result.error_message or "unknown crawl error"
            raise RuntimeError(f"Crawl4AI failed for URL '{url}': {message}")
        # Content appears genuine — antibot false positive, return result as-is.
    return result


async def _handle_cf_challenge(page: Any, **kwargs: Any) -> None:
    """After page load, handle the Cloudflare 'Verify you are human' Turnstile challenge.

    Strategy (in order):
    1. Detect if the current page is a Cloudflare challenge (by title or body markers).
    2. Try to auto-click the Turnstile checkbox inside its cross-origin iframe.
    3. Fall back to a polling loop that waits up to 60 s for the user to manually click
       the challenge button in the open browser window (headless=False).  The polling
       loop is resilient to the page navigation that Cloudflare triggers after the
       challenge is solved (which would otherwise destroy wait_for_function contexts).
    If no challenge is present the function is a no-op.
    """
    import asyncio

    _CF_IFRAME_SELECTORS = [
        'iframe[src*="challenges.cloudflare.com"]',
        'iframe[src*="/cdn-cgi/challenge-platform"]',
        'iframe[title*="cloudflare security challenge" i]',
    ]
    _CF_INNER_SELECTORS = [
        "input[type='checkbox']",
        "label[for]",
        ".ctp-checkbox-label",
        "span.mark",
    ]
    _MANUAL_SOLVE_SECS = 40

    async def _is_challenge_page() -> bool:
        try:
            title = await page.title()
            # Only "Just a moment..." is the CF interstitial title — real pages have specific titles
            if "just a moment" in title.lower():
                return True
            # Look for the IUAM orchestrator script AND absence of real body text
            # (real Macrotrends pages also carry CF scripts, so script presence alone is not enough)
            has_cf_script = await page.evaluate(
                "() => !!document.querySelector('script[src*=\"/cdn-cgi/challenge-platform\"]')"
            )
            if not has_cf_script:
                return False
            # CF script present — only treat as a challenge if body text is minimal
            body_len = await page.evaluate("() => document.body.innerText.trim().length")
            return int(body_len) < 500
        except Exception:
            return False

    async def _is_real_page() -> bool:
        """True once the challenge has been solved and the real page content appears."""
        try:
            title = await page.title()
            if "just a moment" in title.lower() or title.strip() == "":
                return False
            body_len = await page.evaluate("() => document.body.innerText.trim().length")
            return int(body_len) > 3000
        except Exception:
            return False  # navigation in progress — keep waiting

    if not await _is_challenge_page():
        return

    # Attempt 1: auto-click the Turnstile checkbox.
    # Wait up to 10 s for the iframe to materialise (it is JS-injected).
    for iframe_sel in _CF_IFRAME_SELECTORS:
        try:
            await page.locator(iframe_sel).first.wait_for(state="attached", timeout=10_000)
            frame_loc = page.frame_locator(iframe_sel)
            for inner_sel in _CF_INNER_SELECTORS:
                try:
                    elem = frame_loc.locator(inner_sel).first
                    await elem.wait_for(state="visible", timeout=3000)
                    await elem.click()
                    await asyncio.sleep(5)
                    return
                except Exception:
                    continue
        except Exception:
            continue

    # Attempt 2: wait for the user to manually click.
    # Poll every second; resilient to page-navigation context destruction.
    print(
        "\n[crawl4ai] Cloudflare challenge detected — please click "
        "'Verify you are human' in the browser window. "
        f"Waiting up to {_MANUAL_SOLVE_SECS} s..."
    )
    for _ in range(_MANUAL_SOLVE_SECS):
        await asyncio.sleep(1)
        if await _is_real_page():
            await asyncio.sleep(2)  # let the real page finish rendering
            return
    # Timed out — let crawl4ai's antibot detector decide the outcome.
