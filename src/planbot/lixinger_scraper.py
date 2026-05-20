"""Utility to scrape Lixinger valuation metrics for stocks using Playwright."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import threading
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Coroutine

from dotenv import load_dotenv
from playwright.async_api import async_playwright


logger = logging.getLogger(__name__)


class LixingerScraperError(RuntimeError):
    """Base error for Lixinger scraping failures."""


class BotBlockedError(LixingerScraperError):
    """Raised when Lixinger anti-bot page is detected."""


class LoginFailedError(LixingerScraperError):
    """Raised when login does not complete successfully."""


class DataPageNotReadyError(LixingerScraperError):
    """Raised when valuation data page is not ready for extraction."""


class PageState(str, Enum):
    BOT_BLOCKED = "bot_blocked"
    LOGIN_REQUIRED = "login_required"
    DETAIL_PAGE = "detail_page"
    SEARCH_PAGE = "search_page"
    UNKNOWN = "unknown"


class ScrapeStage(str, Enum):
    OPEN_INITIAL_PAGE = "open_initial_page"
    LOGIN = "login"
    NAVIGATE_TO_STOCK = "navigate_to_stock"
    PREPARE_DATA_PAGE = "prepare_data_page"


def _metric_aliases(metric_name: str) -> list[str]:
    metric_key = metric_name.upper()
    if metric_key == "PE-TTM":
        return ["PE-TTM", "市盈率(TTM)", "市盈率TTM", "市盈率"]
    if metric_key == "PB":
        return ["PB", "市净率"]
    if metric_key == "PS-TTM":
        return ["PS-TTM", "市销率(TTM)", "市销率TTM", "市销率"]
    return [metric_name]


def _load_local_dotenv() -> None:
    project_root = Path(__file__).resolve().parents[2]
    dotenv_path = project_root / ".env"
    if dotenv_path.exists():
        load_dotenv(dotenv_path=dotenv_path, override=False)


def scrape_lixinger_metrics(stock_symbol: str) -> dict[str, dict[str, float | str]]:
    """
    Scrape Lixinger 10-year valuation metrics for a given stock symbol.

    Args:
        stock_symbol: Stock ticker (e.g., "BABA", "836").

    Returns:
        Dictionary keyed by "PE-TTM", "PB", "PS-TTM", each containing:
            current_value
            current_position
            point_80
            point_50
            point_20
            max_value
            average_value
            min_value
    """
    _load_local_dotenv()
    return _run_async(_scrape_lixinger_async(stock_symbol))


async def _scrape_lixinger_async(stock_symbol: str) -> dict[str, dict[str, float | str]]:
    password = os.getenv("LIXINGER_PASSWORD")
    if not password:
        raise ValueError("LIXINGER_PASSWORD environment variable not set")

    symbol = stock_symbol.strip().upper()
    if not symbol:
        raise ValueError("stock_symbol must be non-empty")

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        try:
            async def _open_stage() -> None:
                # Start from analytics pages instead of homepage to bypass landing CTA.
                await _open_initial_page(page, symbol)
                await _assert_allowed_page(page, stage=ScrapeStage.OPEN_INITIAL_PAGE.value)

            async def _login_stage() -> None:
                await _login_lixinger(page, "roger249", password)
                await _assert_login_completed(page)

            async def _navigate_stage() -> None:
                await _navigate_to_stock(page, symbol)
                await _assert_allowed_page(page, stage=ScrapeStage.NAVIGATE_TO_STOCK.value)

            async def _prepare_stage() -> None:
                await _recover_if_login_required(page, "roger249", password, symbol)
                await _set_duration_10y(page)
                await _assert_allowed_page(page, stage=ScrapeStage.PREPARE_DATA_PAGE.value)

            await _run_stage_with_retries(page, ScrapeStage.OPEN_INITIAL_PAGE, _open_stage, max_attempts=2)
            await _run_stage_with_retries(page, ScrapeStage.LOGIN, _login_stage, max_attempts=2)
            await _run_stage_with_retries(page, ScrapeStage.NAVIGATE_TO_STOCK, _navigate_stage, max_attempts=2)
            await _run_stage_with_retries(page, ScrapeStage.PREPARE_DATA_PAGE, _prepare_stage, max_attempts=2)

            metrics = await _extract_all_metrics_with_retries(page, symbol)
        finally:
            await context.close()
            await browser.close()

    return metrics


async def _open_initial_page(page: Any, stock_symbol: str) -> None:
    """Open detail/search page directly; avoid homepage CTA flow."""
    candidates = _initial_urls_for_symbol(stock_symbol)
    for url in candidates:
        try:
            await page.goto(url, wait_until="domcontentloaded")
            await page.wait_for_timeout(1200)
            await _assert_allowed_page(page, stage="open_initial_page")
            return
        except BotBlockedError:
            raise
        except Exception:
            continue
    raise RuntimeError(f"Unable to open initial Lixinger page for symbol: {stock_symbol}")


def _is_retryable_stage_error(exc: Exception) -> bool:
    # Anti-bot and missing credentials are terminal for this run.
    if isinstance(exc, (BotBlockedError, ValueError)):
        return False
    return isinstance(exc, (LoginFailedError, DataPageNotReadyError, RuntimeError))


async def _run_stage_with_retries(
    page: Any,
    stage: ScrapeStage,
    operation: Callable[[], Coroutine[Any, Any, None]],
    *,
    max_attempts: int,
    retry_delay_ms: int = 1200,
) -> None:
    for attempt in range(1, max_attempts + 1):
        logger.info("lixinger stage start: stage=%s attempt=%s", stage.value, attempt)
        try:
            await operation()
            logger.info("lixinger stage success: stage=%s attempt=%s", stage.value, attempt)
            return
        except Exception as exc:
            if not _is_retryable_stage_error(exc) or attempt >= max_attempts:
                logger.error(
                    "lixinger stage failed: stage=%s attempt=%s reason=%s",
                    stage.value,
                    attempt,
                    type(exc).__name__,
                )
                raise

            logger.warning(
                "lixinger stage retry: stage=%s attempt=%s reason=%s",
                stage.value,
                attempt,
                type(exc).__name__,
            )
            await page.wait_for_timeout(retry_delay_ms)
            try:
                await page.reload(wait_until="domcontentloaded")
            except Exception:
                # Reload is best-effort; next attempt still runs and may recover.
                pass


def _classify_page_state(url: str, body_text: str) -> PageState:
    normalized_url = (url or "").lower()
    normalized_body = (body_text or "").lower()

    if "you are robot" in normalized_body or "are you robot" in normalized_body:
        return PageState.BOT_BLOCKED
    # Login indicators should win even if the URL still looks like a detail/search path.
    if (
        "账号或手机号" in normalized_body
        or "密码" in normalized_body
        or "sign in" in normalized_body
        or "登录" in normalized_body
        or "登录/注册" in normalized_body
    ):
        return PageState.LOGIN_REQUIRED
    if "/analytics/company/detail/" in normalized_url:
        return PageState.DETAIL_PAGE
    if "/analytics/company/search" in normalized_url:
        return PageState.SEARCH_PAGE
    return PageState.UNKNOWN


async def _read_body_text(page: Any, timeout_ms: int = 4000) -> str:
    try:
        return await page.locator("body").inner_text(timeout=timeout_ms)
    except Exception:
        return ""


async def _detect_page_state(page: Any) -> PageState:
    body_text = await _read_body_text(page)
    return _classify_page_state(page.url, body_text)


async def _assert_allowed_page(page: Any, stage: str) -> None:
    state = await _detect_page_state(page)
    if state == PageState.BOT_BLOCKED:
        raise BotBlockedError(
            f"Lixinger anti-bot page detected at stage '{stage}' (url: {page.url})"
        )


async def _assert_login_completed(page: Any) -> None:
    await _assert_allowed_page(page, stage="post_login")
    state = await _detect_page_state(page)
    if state == PageState.LOGIN_REQUIRED:
        raise LoginFailedError("Login form still visible after login attempt")


async def _ensure_data_page_ready(page: Any) -> None:
    await _assert_allowed_page(page, stage="before_extract")
    checks = 15
    for _ in range(checks):
        body_text = await _read_body_text(page)
        html_text = await page.content()
        if _has_metric_marker(body_text) or _has_metric_marker(html_text):
            return
        await page.wait_for_timeout(2000)

    state = _classify_page_state(page.url, await _read_body_text(page))
    if state == PageState.LOGIN_REQUIRED:
        raise LoginFailedError(
            f"Session appears logged out on valuation page (url={page.url})"
        )
    raise DataPageNotReadyError(
        f"Valuation data is not ready for extraction (state={state.value}, url={page.url})"
    )


async def _recover_if_login_required(
    page: Any,
    username: str,
    password: str,
    stock_symbol: str,
) -> None:
    state = await _detect_page_state(page)
    if state != PageState.LOGIN_REQUIRED:
        return

    logger.warning("lixinger session recovery: re-authenticating due to login_required state")
    await _login_lixinger(page, username, password)
    await _assert_login_completed(page)
    await _navigate_to_stock(page, stock_symbol)


def _has_metric_marker(text: str) -> bool:
    normalized = (text or "")
    if not normalized:
        return False

    # Strong markers that are typically present only on valuation metric surfaces.
    marker_patterns = [
        r"PE-TTM\s*[:：]?\s*[-0-9,.]+",
        r"PS-TTM\s*[:：]?\s*[-0-9,.]+",
        r"市盈率(?:\(TTM\)|TTM)?\s*[:：]?\s*[-0-9,.]+",
        r"市销率(?:\(TTM\)|TTM)?\s*[:：]?\s*[-0-9,.]+",
        r"(?:当前值|Current\s*Value)",
        r"(?:当前分位点|Current\s*Value\s*Position)",
        r"(?:PE-TTM\s*&\s*PB\s*&\s*PS-TTM\s*Band)",
    ]
    return any(re.search(pattern, normalized, re.IGNORECASE) for pattern in marker_patterns)


def _initial_urls_for_symbol(stock_symbol: str) -> list[str]:
    """Best-effort initial URLs ordered by reliability for login + navigation."""
    symbol = stock_symbol.upper()

    # Known sample from spec.
    if symbol == "BABA":
        return [
            "https://www.lixinger.com/analytics/company/detail/nyse/BABA/157755200/fundamental/valuation/primary?granularity=y10",
            "https://www.lixinger.com/analytics/company/search?q=BABA",
        ]

    if symbol.isdigit():
        hk_code = symbol.zfill(5)
        return [
            f"https://www.lixinger.com/analytics/company/detail/hk/{hk_code}/{int(symbol)}/fundamental/valuation/primary?granularity=y10",
            f"https://www.lixinger.com/analytics/company/search?q={symbol}",
        ]

    return [f"https://www.lixinger.com/analytics/company/search?q={symbol}"]


async def _click_start_button(page: Any) -> bool:
    selectors = [
        "button:has-text('開始使用')",
        "button:has-text('开始使用')",
        "a:has-text('開始使用')",
        "a:has-text('开始使用')",
        "text=開始使用",
        "text=开始使用",
        "a[href*='login']",
        "a[href*='start']",
    ]

    for selector in selectors:
        try:
            locator = page.locator(selector).first
            await locator.wait_for(timeout=2500)
            await locator.scroll_into_view_if_needed(timeout=1000)
            try:
                await locator.click(timeout=2000)
            except Exception:
                await locator.click(timeout=2000, force=True)
            await page.wait_for_timeout(800)
            return True
        except Exception:
            continue

    # Role/text fallback when CTA is wrapped in nested components.
    role_candidates = [
        page.get_by_role("button", name=re.compile(r"開始使用|开始使用", re.IGNORECASE)).first,
        page.get_by_role("link", name=re.compile(r"開始使用|开始使用", re.IGNORECASE)).first,
    ]
    for candidate in role_candidates:
        try:
            await candidate.scroll_into_view_if_needed(timeout=1000)
            try:
                await candidate.click(timeout=2000)
            except Exception:
                await candidate.click(timeout=2000, force=True)
            await page.wait_for_timeout(800)
            return True
        except Exception:
            continue

    return False


async def _login_lixinger(page: Any, username: str, password: str) -> None:
    """Open sign-in modal and login if form is visible."""
    open_login_selectors = [
        "text=Sign In",
        "text=sign in",
        "text=登入",
        "text=登录",
        "button:has-text('Sign In')",
        "button:has-text('登入')",
        "button:has-text('登录')",
    ]
    for selector in open_login_selectors:
        try:
            await page.click(selector, timeout=2000)
            break
        except Exception:
            continue

    # Prefer exact selectors from recorded Playwright script.
    try:
        user_box = page.get_by_role("textbox", name="账号或手机号")
        await user_box.first.click(timeout=3500)
        await user_box.first.fill(username, timeout=3500)
    except Exception:
        username_fields = [
            "input[placeholder*='账号或手机号']",
            "input[placeholder*='account name']",
            "input[placeholder*='phone number']",
            "input[placeholder*='邮箱']",
            "input[placeholder*='用户名']",
            "input[name*='username']",
            "input[type='text']",
        ]

        username_locator = None
        for selector in username_fields:
            try:
                candidate = page.locator(selector).first
                await candidate.wait_for(timeout=3500)
                username_locator = candidate
                break
            except Exception:
                continue

        if username_locator is None:
            # Already signed in, nothing to do.
            return

        await username_locator.click(timeout=2000)
        await username_locator.fill(username)

    try:
        pwd_box = page.get_by_role("textbox", name="密码")
        await pwd_box.first.fill(password, timeout=3500)
    except Exception:
        password_fields = [
            "input[placeholder*='密码']",
            "input[type='password']",
            "input[name*='password']",
        ]
        for selector in password_fields:
            try:
                await page.fill(selector, password, timeout=3000)
                break
            except Exception:
                continue

    submit_selectors = [
        "button:has-text('登录')",
        "button:has-text('登入')",
        "button:has-text('Sign In')",
        "button:has-text('sign in')",
        "button[type='submit']",
        "text=登录",
    ]
    for selector in submit_selectors:
        try:
            await page.click(selector, timeout=3000)
            break
        except Exception:
            continue

    await page.wait_for_timeout(4000)


async def _navigate_to_stock(page: Any, stock_symbol: str) -> None:
    # First try direct detail URLs (most reliable for known symbols like BABA).
    for url in _initial_urls_for_symbol(stock_symbol):
        if "/analytics/company/detail/" not in url:
            continue
        try:
            await page.goto(url, wait_until="domcontentloaded")
            await page.wait_for_timeout(1800)
            if "/analytics/company/detail/" in page.url:
                return
        except Exception:
            continue

    search_selectors = [
        "input[placeholder*='Search']",
        "input[placeholder*='search']",
        "input[placeholder*='AI|US stock']",
    ]

    search_box = None
    for selector in search_selectors:
        try:
            candidate = page.locator(selector).first
            await candidate.wait_for(timeout=10000)
            search_box = candidate
            break
        except Exception:
            continue

    if search_box is None:
        await _navigate_to_stock_via_search_page(page, stock_symbol)
        return

    await search_box.click()
    await search_box.fill(stock_symbol)
    await page.wait_for_timeout(900)
    await search_box.press("Enter")
    await page.wait_for_timeout(3000)

    if "/analytics/company/detail/" in page.url:
        return

    if await _click_first_company_detail_link(page, stock_symbol):
        return

    await _navigate_to_stock_via_search_page(page, stock_symbol)


async def _navigate_to_stock_via_search_page(page: Any, stock_symbol: str) -> None:
    """Fallback navigation when global search input is not visible."""
    await page.goto(
        f"https://www.lixinger.com/analytics/company/search?q={stock_symbol}",
        wait_until="domcontentloaded",
    )
    await page.wait_for_timeout(1200)

    if await _click_first_company_detail_link(page, stock_symbol):
        return

    raise RuntimeError(f"Could not locate search result for symbol: {stock_symbol}")


async def _click_first_company_detail_link(page: Any, stock_symbol: str) -> bool:
    """Find and click a company detail link from current page content."""
    try:
        await page.wait_for_selector("a[href*='/analytics/company/detail/']", timeout=8000)
    except Exception:
        return False

    # Prefer links containing the symbol, otherwise click first available detail link.
    candidates = page.locator("a[href*='/analytics/company/detail/']")
    try:
        count = await candidates.count()
    except Exception:
        return False

    if count == 0:
        return False

    stock_symbol_lower = stock_symbol.lower()
    for idx in range(count):
        try:
            item = candidates.nth(idx)
            href = (await item.get_attribute("href")) or ""
            if stock_symbol_lower in href.lower():
                await item.click(timeout=3000)
                await page.wait_for_timeout(2500)
                return True
        except Exception:
            continue

    try:
        await candidates.first.click(timeout=3000)
        await page.wait_for_timeout(2500)
        return True
    except Exception:
        return False


async def _open_valuation_band(page: Any) -> None:
    selectors = [
        "text=Valuation",
        "text=估值带",
        "text=Primary Metrics",
        "text=PE-TTM & PB & PS-TTM Band",
    ]
    for selector in selectors:
        try:
            await page.click(selector, timeout=2500)
            await page.wait_for_timeout(700)
        except Exception:
            continue


async def _set_duration_10y(page: Any) -> None:
    selectors = [
        "text=10 Years",
        "text=10 years",
        "text=10y",
        "text=10年",
        "[data-duration='10y']",
    ]
    for selector in selectors:
        try:
            await page.click(selector, timeout=2500)
            await page.wait_for_timeout(1200)
            return
        except Exception:
            continue


async def _extract_all_metrics(page: Any) -> dict[str, dict[str, float | str]]:
    metrics: dict[str, dict[str, float | str]] = {}
    for metric in ["PE-TTM", "PB", "PS-TTM"]:
        await _select_metric(page, metric)
        await page.wait_for_timeout(1000)
        panel_text = await _get_metric_panel_text(page, metric)
        body_text = await page.locator("body").inner_text()
        html_text = await page.content()
        parsed = _parse_metric_from_content(panel_text + "\n" + body_text + "\n" + html_text, metric)
        if parsed is None:
            clues = _collect_metric_clues(body_text)
            raise RuntimeError(
                f"Failed to parse metric panel for {metric} (url={page.url}). "
                f"Snippet clues: {clues}"
            )
        metrics[metric] = parsed
    return metrics


async def _extract_all_metrics_with_retries(
    page: Any,
    stock_symbol: str,
    max_attempts: int = 2,
) -> dict[str, dict[str, float | str]]:
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await _extract_all_metrics(page)
        except RuntimeError as exc:
            last_error = exc
            if attempt >= max_attempts:
                break

            logger.warning(
                "lixinger extract retry: attempt=%s reason=%s",
                attempt,
                type(exc).__name__,
            )
            await _reset_detail_page_for_retry(page, stock_symbol, use_band_fallback=True)

    assert last_error is not None
    raise last_error


async def _reset_detail_page_for_retry(
    page: Any,
    stock_symbol: str,
    use_band_fallback: bool = False,
) -> None:
    detail_urls = [url for url in _initial_urls_for_symbol(stock_symbol) if "/analytics/company/detail/" in url]
    target_url = detail_urls[0] if detail_urls else None

    if target_url:
        await page.goto(target_url, wait_until="domcontentloaded")
    else:
        await page.reload(wait_until="domcontentloaded")

    await page.wait_for_timeout(1500)
    if use_band_fallback:
        await _open_valuation_band(page)
    await _set_duration_10y(page)
    try:
        await _ensure_data_page_ready(page)
    except (DataPageNotReadyError, LoginFailedError):
        # Best-effort reset only; extraction retry will still attempt parsing.
        pass


def _collect_metric_clues(body_text: str, max_lines: int = 8) -> str:
    keywords = [
        "PE-TTM",
        "PB",
        "PS-TTM",
        "市盈率",
        "市净率",
        "市销率",
        "当前值",
        "分位",
        "最高值",
        "最低值",
        "Max",
        "Min",
    ]
    lines = []
    for raw_line in body_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if any(keyword.lower() in line.lower() for keyword in keywords):
            lines.append(line)
        if len(lines) >= max_lines:
            break
    return " | ".join(lines) if lines else "<no metric-like text found>"


async def _get_metric_panel_text(page: Any, metric_name: str) -> str:
    """Try to capture the metric card/panel text for the active metric."""
    selectors: list[str] = []
    for alias in _metric_aliases(metric_name):
        selectors.extend(
            [
                f"text=/{re.escape(alias)}\\s*当前值/i",
                f"text=/{re.escape(alias)}\\s*Current\\s*Value/i",
                f"text=/{re.escape(alias)}/i",
            ]
        )
    for selector in selectors:
        try:
            loc = page.locator(selector).first
            await loc.wait_for(timeout=2000)
            text = await loc.inner_text()
            if text and metric_name.lower() in text.lower():
                return text
        except Exception:
            continue
    return ""


async def _select_metric(page: Any, metric_name: str) -> None:
    # Click the left metric cards where text is often concatenated as
    # e.g. "PE-TTM当前值...当前分位点...".
    selectors: list[str] = []
    for alias in _metric_aliases(metric_name):
        selectors.extend(
            [
                f"text=/{re.escape(alias)}\\s*当前值/i",
                f"text=/{re.escape(alias)}\\s*Current\\s*Value/i",
                f"a:has-text('{alias}')",
                f"span:has-text('{alias}')",
                f"text={alias}",
            ]
        )
    for selector in selectors:
        try:
            await page.locator(selector).first.click(timeout=2500)
            return
        except Exception:
            continue

    # Last resort: search all metric-like cards and click the one containing the metric name.
    try:
        cards = page.locator("text=/当前值|Current\\s*Value/i")
        count = await cards.count()
        metric_lower = metric_name.lower()
        for idx in range(count):
            item = cards.nth(idx)
            text = (await item.inner_text()) or ""
            if metric_lower in text.lower():
                await item.click(timeout=2500)
                return
    except Exception:
        pass


def _parse_metric_from_content(content: str, metric_name: str) -> dict[str, float | str] | None:
    metric_data = {
        "current_value": 0.0,
        "current_position": 0.0,
        "point_80": 0.0,
        "point_50": 0.0,
        "point_20": 0.0,
        "max_value": 0.0,
        "average_value": 0.0,
        "min_value": 0.0,
    }

    metric_alias_pattern = "|".join(re.escape(alias) for alias in _metric_aliases(metric_name))
    metric_section_pattern = (
        rf"(?:{metric_alias_pattern})"
        rf"[\s\S]*?(?:Current\s*Value|当前值)"
        rf"[\s\S]*?(?:Min\s*Value|最低值)\s*:?\s*[-0-9,.]+"
    )
    section = re.search(metric_section_pattern, content, re.IGNORECASE)
    section_text = section.group(0) if section else content

    try:
        patterns_current = [
            r"Current\s*Value\s*:?\s*([-0-9,.]+)",
            r"当前值\s*:?\s*([-0-9,.]+)",
        ]
        for alias in _metric_aliases(metric_name):
            patterns_current.append(rf"{re.escape(alias)}\s*[:：]?\s*([-0-9,.]+)")
        patterns_position = [
            r"Current\s*Value\s*Position\s*:?\s*([-0-9,.]+)%?",
            r"当前分位点\s*:?\s*([-0-9,.]+)%?",
            r"当前百分位\s*:?\s*([-0-9,.]+)%?",
        ]
        patterns_80 = [
            r"80%\s*Point\s*Value\s*:?\s*([-0-9,.]+)",
            r"80%\s*分位(?:点|数)值?\s*:?\s*([-0-9,.]+)",
            r"80%\s*分位(?:点|数)\s*:?\s*([-0-9,.]+)",
        ]
        patterns_50 = [
            r"50%\s*Point\s*Value\s*:?\s*([-0-9,.]+)",
            r"50%\s*分位(?:点|数)值?\s*:?\s*([-0-9,.]+)",
            r"50%\s*分位(?:点|数)\s*:?\s*([-0-9,.]+)",
        ]
        patterns_20 = [
            r"20%\s*Point\s*Value\s*:?\s*([-0-9,.]+)",
            r"20%\s*分位(?:点|数)值?\s*:?\s*([-0-9,.]+)",
            r"20%\s*分位(?:点|数)\s*:?\s*([-0-9,.]+)",
        ]
        patterns_max = [r"Max\s*Value\s*:?\s*([-0-9,.]+)", r"最高值\s*:?\s*([-0-9,.]+)"]
        patterns_avg = [
            r"Average\s*Value\s*:?\s*([-0-9,.]+)",
            r"平均值\s*:?\s*([-0-9,.]+)",
            r"均值\s*:?\s*([-0-9,.]+)",
        ]
        patterns_min = [r"Min\s*Value\s*:?\s*([-0-9,.]+)", r"最低值\s*:?\s*([-0-9,.]+)"]

        for pattern in patterns_current:
            match = re.search(pattern, section_text, re.IGNORECASE)
            if match:
                metric_data["current_value"] = _to_float(match.group(1))
                break

        for pattern in patterns_position:
            match = re.search(pattern, section_text, re.IGNORECASE)
            if match:
                metric_data["current_position"] = _to_float(match.group(1))
                break

        for pattern in patterns_80:
            match = re.search(pattern, section_text, re.IGNORECASE)
            if match:
                metric_data["point_80"] = _to_float(match.group(1))
                break

        for pattern in patterns_50:
            match = re.search(pattern, section_text, re.IGNORECASE)
            if match:
                metric_data["point_50"] = _to_float(match.group(1))
                break

        for pattern in patterns_20:
            match = re.search(pattern, section_text, re.IGNORECASE)
            if match:
                metric_data["point_20"] = _to_float(match.group(1))
                break

        for pattern in patterns_max:
            match = re.search(pattern, section_text, re.IGNORECASE)
            if match:
                metric_data["max_value"] = _to_float(match.group(1))
                break

        for pattern in patterns_avg:
            match = re.search(pattern, section_text, re.IGNORECASE)
            if match:
                metric_data["average_value"] = _to_float(match.group(1))
                break

        for pattern in patterns_min:
            match = re.search(pattern, section_text, re.IGNORECASE)
            if match:
                metric_data["min_value"] = _to_float(match.group(1))
                break

    except ValueError as exc:
        print(f"Error parsing metric {metric_name}: {exc}")

    return metric_data if any(v != 0.0 for v in metric_data.values()) else None


def _to_float(value: str) -> float:
    normalized = value.strip().replace(",", "")
    if normalized.startswith("(") and normalized.endswith(")"):
        normalized = "-" + normalized[1:-1]
    return float(normalized)


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
        except Exception as exc:
            error["value"] = exc

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    thread.join()

    if "value" in error:
        raise error["value"]
    return result.get("value")
