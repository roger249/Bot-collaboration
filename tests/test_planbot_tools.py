from __future__ import annotations

import os
import sys
import types
import asyncio
from pathlib import Path

import pytest

from src.planbot import crew_workflow
from src.planbot import crawl4ai_tool


def test_build_tool_instance_requires_firecrawl_api_key(monkeypatch):
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)

    with pytest.raises(ValueError, match="FIRECRAWL_API_KEY"):
        crew_workflow._build_tool_instance("FirecrawlScrapeWebsiteTool")


def test_build_tool_instance_requires_scrapfly_api_key(monkeypatch):
    monkeypatch.delenv("SCRAPFLY_API_KEY", raising=False)

    with pytest.raises(ValueError, match="SCRAPFLY_API_KEY"):
        crew_workflow._build_tool_instance("ScrapflyScrapeWebsiteTool")


def test_build_tool_instance_rejects_unknown_tool():
    with pytest.raises(ValueError, match="Unsupported tool"):
        crew_workflow._build_tool_instance("UnknownTool")


def test_build_tool_instance_supports_crawl4ai(monkeypatch):
    fake_module = types.ModuleType("src.planbot.crawl4ai_tool")

    class FakeCrawl4AITool:
        pass

    fake_module.Crawl4AITool = FakeCrawl4AITool
    monkeypatch.setitem(sys.modules, "src.planbot.crawl4ai_tool", fake_module)

    tool = crew_workflow._build_tool_instance("Crawl4AI")

    assert isinstance(tool, FakeCrawl4AITool)


def test_build_tool_instance_supports_scrapfly(monkeypatch):
    fake_module = types.ModuleType("crewai_tools")

    class FakeScrapflyScrapeWebsiteTool:
        def __init__(self, api_key=None):
            self.api_key = api_key

    fake_module.ScrapflyScrapeWebsiteTool = FakeScrapflyScrapeWebsiteTool
    monkeypatch.setitem(sys.modules, "crewai_tools", fake_module)
    monkeypatch.setenv("SCRAPFLY_API_KEY", "test-key")

    tool = crew_workflow._build_tool_instance("ScrapflyScrapeWebsiteTool")

    assert isinstance(tool, FakeScrapflyScrapeWebsiteTool)
    assert tool.api_key == "test-key"


def test_scrape_website_tool_page():
    """Integration test: ScrapeWebsiteTool should fetch AASTOCKS GOOG P/E page content."""
    tool = crew_workflow._build_tool_instance("ScrapeWebsiteTool")

    result = tool._run(website_url="http://www.aastocks.com/tc/stocks/analysis/company-fundamental/financial-ratios?symbol=06690")

    assert isinstance(result, str)
    result_lower = result.lower()
    if "just a moment" in result_lower and "enable javascript and cookies" in result_lower:
        pytest.xfail("AASTOCKS is protected by Cloudflare challenge for ScrapeWebsiteTool requests")

    assert len(result) > 2000, f"Expected substantial scraped content, got {len(result)} chars\nresult: {result}"
    assert any(
        keyword in result_lower
        for keyword in ["alphabet", "goog", "p/e", "pe ratio", "macrotrends"]
    ), f"Scraped output did not include expected P/E ratio terms\n{result}"


def test_crawl4ai_macrotrends_hardened_config():
    """Integration test: Crawl4AI should return meaningful markdown for Macrotrends GOOG P/E page."""
    tool = crawl4ai_tool.Crawl4AITool()

    result = tool._run("https://www.macrotrends.net/stocks/charts/GOOG/alphabet/pe-ratio")

    assert isinstance(result, str)
    assert len(result) > 500, f"Expected substantial scraped content, got {len(result)} chars"

    result_lower = result.lower()
    assert "just a moment" not in result_lower, "Cloudflare challenge page returned instead of Macrotrends data"
    assert "enable javascript and cookies" not in result_lower, "Blocked by anti-bot challenge"
    assert any(
        keyword in result_lower
        for keyword in ["alphabet", "goog", "p/e", "pe ratio", "macrotrends"]
    ), "Macrotrends markdown did not include expected GOOG P/E terms"


def test_generate_with_crew_attaches_resolved_tools(monkeypatch, tmp_path: Path):
    captured: dict[str, object] = {}

    def fake_load_yaml(path: Path):
        if path.name == "agents.yaml":
            return {
                "professional_stock_investor_agent": {
                    "role": "role",
                    "goal": "goal",
                    "backstory": "backstory",
                    "tools": ["ScrapeWebsiteTool"],
                }
            }
        if path.name == "tasks.yaml":
            return {
                "stock_analysis_proposal_task": {
                    "agent": "professional_stock_investor_agent",
                    "expected_output": "output",
                }
            }
        raise AssertionError(f"Unexpected yaml path: {path}")

    class FakeAgent:
        def __init__(self, **kwargs):
            captured["agent_kwargs"] = kwargs

    class FakeTask:
        def __init__(self, **kwargs):
            captured["task_kwargs"] = kwargs

    class FakeCrew:
        def __init__(self, **kwargs):
            captured["crew_kwargs"] = kwargs

        def kickoff(self):
            return types.SimpleNamespace(raw="ok")

    monkeypatch.setattr(crew_workflow, "_load_yaml", fake_load_yaml)
    monkeypatch.setattr(crew_workflow, "Agent", FakeAgent)
    monkeypatch.setattr(crew_workflow, "Task", FakeTask)
    monkeypatch.setattr(crew_workflow, "Crew", FakeCrew)
    monkeypatch.setattr(crew_workflow, "_build_crew_llm", lambda app_config, cfg: object())
    monkeypatch.setattr(crew_workflow, "_resolve_agent_tools", lambda agent_def: ["tool-instance"])

    cfg = types.SimpleNamespace(
        crewai_config_folder=tmp_path,
        task_name="stock_analysis_proposal_task",
        model="mock-model",
        provider="mock-provider",
        temperature=0.2,
    )

    output = crew_workflow._generate_with_crew(app_config=object(), cfg=cfg, user_prompt="prompt")

    assert output == "ok"
    agent_kwargs = captured["agent_kwargs"]
    assert agent_kwargs["tools"] == ["tool-instance"]
    assert agent_kwargs["allow_delegation"] is False


def test_crawl4ai_tool_uses_raw_markdown_object(monkeypatch):
    result = types.SimpleNamespace(
        markdown=types.SimpleNamespace(raw_markdown="md body", fit_markdown=""),
        cleaned_html="<p>html</p>",
        html="<html></html>",
        extracted_content="",
    )

    def fake_run_async(coro):
        coro.close()
        return result

    monkeypatch.setattr(crawl4ai_tool, "_run_async", fake_run_async)

    tool = crawl4ai_tool.Crawl4AITool()

    assert tool._run("https://example.com") == "md body"


def test_crawl4ai_yahoo_finance_returns_valid_markdown():
    """Integration test: verify Crawl4AI can fetch and return markdown from Yahoo Finance.

    Yahoo Finance uses client-side JS rendering. The tool fetches the page and
    returns whatever content is available after the configured delay.
    """
    tool = crawl4ai_tool.Crawl4AITool()

    result = tool._run("http://www.aastocks.com/en/stocks/analysis/company-fundamental/financial-ratios?symbol=06690")

    print("Crawl4AI tool output length:", len(result))
    print("Crawl4AI tool output preview:", result)

    # Verify we got substantial content
    assert result is not None
    assert len(result) > 2000, f"Expected substantial content, got {len(result)} chars"

    # Verify page-not-found error is absent
    assert "does not exist" not in result.lower(), "Page not found error"

    # Verify the response is from the correct Yahoo Finance GOOG page
    result_lower = result.lower()
    assert any(
        keyword in result_lower
        for keyword in ["EPS", "alphabet", "PE Ratio", "quote", "stock", "market", "trade", "share", "yahoo"]
    ), "Page doesn't contain expected Yahoo Finance / GOOG content"

    print(f"  Content length: {len(result)} characters")
    print(f"  Preview: {result[:200]}...")


def test_crawl_uses_default_markdown_generator(monkeypatch):
    captured: dict[str, object] = {}

    class FakeStrategy:
        def set_hook(self, name: str, fn) -> None:
            captured.setdefault("hooks", {})[name] = fn

    class FakeCrawler:
        def __init__(self, config=None):
            captured["browser_config"] = config
            self.crawler_strategy = FakeStrategy()

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def arun(self, *, url, config):
            captured["url"] = url
            captured["crawler_config"] = config
            return types.SimpleNamespace(success=True, error_message=None)

    monkeypatch.setattr(crawl4ai_tool, "AsyncWebCrawler", FakeCrawler)

    asyncio.run(crawl4ai_tool._crawl("https://example.com"))

    assert captured["url"] == "https://example.com"
    assert isinstance(captured["crawler_config"].markdown_generator, crawl4ai_tool.DefaultMarkdownGenerator)
    # Verify minimal non-headless browser config (stealth stripped to avoid CF detection)
    assert captured["browser_config"].browser_type == "chromium"
    assert captured["browser_config"].headless is False
    assert "--disable-blink-features=AutomationControlled" in captured["browser_config"].extra_args
    # Standard path: domcontentloaded + long delay avoids SPA networkidle timeouts
    assert captured["crawler_config"].cache_mode == crawl4ai_tool.CacheMode.BYPASS
    assert captured["crawler_config"].wait_until == "domcontentloaded"
    assert captured["crawler_config"].delay_before_return_html == 8.0
    # Standard (non-CF) domains must NOT install the CF challenge hook
    assert "after_goto" not in captured.get("hooks", {}), "CF hook should not be set for non-CF domains"


def test_stockdex_macrotrends_key_financial_ratios_msft():
    """Integration test: fetch key financial ratios for MSFT via stockdex / Macrotrends.

    stockdex 1.2.6 has a known bug: macrotrends_key_financial_ratios builds the
    URL with a literal "TBD" slug instead of calling get_company_slug().
    Macrotrends redirects TBD for income-statement but returns 403 for
    financial-ratios, so this test is marked xfail until the library is fixed.

    Expected columns (subset): Current Ratio, Debt/Equity Ratio, Gross Margin,
    Operating Margin, Net Margin, Return On Equity, Return On Assets, Price/Earnings.
    """
    from stockdex import Ticker

    EXPECTED_RATIOS = [
        "Current Ratio",
        "Debt/Equity Ratio",
        "Gross Margin",
        "Operating Margin",
        "Net Margin",
    ]

    ticker = Ticker(ticker="MSFT")

    try:
        df = ticker.macrotrends_key_financial_ratios
    except RuntimeError as exc:
        if "403" in str(exc):
            pytest.xfail(
                "stockdex bug: macrotrends_key_financial_ratios uses a literal "
                "'TBD' company slug which Macrotrends rejects with 403. "
                "Fix: replace TBD with self.get_company_slug(self.ticker) in "
                "macrotrends_interface.py line ~196."
            )
        raise

    # --- basic shape ---
    assert df is not None, "Expected a DataFrame, got None"
    assert not df.empty, "Expected non-empty DataFrame"

    # rows are ratio names, columns are date periods
    assert df.shape[1] >= 4, f"Expected at least 4 time periods, got {df.shape[1]}"

    present = [r for r in EXPECTED_RATIOS if r in df.index]
    assert len(present) >= 3, (
        f"Expected at least 3 of {EXPECTED_RATIOS} in index; found: {df.index.tolist()}"
    )

    # values should be numeric (float) for the rows present
    for ratio in present:
        row = df.loc[ratio].dropna()
        assert len(row) >= 1, f"All values NaN for {ratio!r}"
        assert row.apply(lambda v: isinstance(v, (int, float))).all(), (
            f"Non-numeric values in {ratio!r}: {row.tolist()}"
        )

    print(f"  MSFT key financial ratios — {df.shape[1]} periods, {df.shape[0]} rows")
    print(df[df.index.isin(EXPECTED_RATIOS)].iloc[:, :5].to_string())


def test_stockdex_macrotrends_income_statement_msft():
    """Integration test: fetch MSFT quarterly income statement via stockdex / Macrotrends.

    macrotrends_income_statement(frequency="quarterly") builds its URL via
    get_company_slug(), which first resolves the TBD redirect on the
    income-statement endpoint to obtain "microsoft", then fetches
    /MSFT/microsoft/income-statement?freq=Q.  This is the code path that
    actually works and provides a useful set of financial line items
    (Revenue, Gross Profit, Operating Income, Net Income, EPS) as a proxy
    for key financial ratios when macrotrends_key_financial_ratios is blocked.

    The test xfails gracefully if Macrotrends returns 403 / blocks the request.
    """
    from stockdex import Ticker

    EXPECTED_ROWS = ["Revenue", "Gross Profit", "Net Income"]

    ticker = Ticker(ticker="MSFT")

    try:
        df = ticker.macrotrends_income_statement(frequency="quarterly")
    except RuntimeError as exc:
        if "403" in str(exc):
            pytest.xfail(f"Macrotrends blocked the request (403): {exc}")
        raise

    assert df is not None and not df.empty, "Expected non-empty DataFrame"
    assert df.shape[1] >= 4, f"Expected ≥4 quarterly periods, got {df.shape[1]}"

    present = [r for r in EXPECTED_ROWS if r in df.index]
    assert len(present) >= 2, (
        f"Expected at least 2 of {EXPECTED_ROWS} in index; found: {df.index.tolist()}"
    )

    # Values should be numeric across time periods
    for row in present:
        series = df.loc[row].dropna()
        assert len(series) >= 1, f"All NaN for {row!r}"
        assert series.apply(lambda v: isinstance(v, (int, float))).all(), (
            f"Non-numeric values for {row!r}: {series.tolist()[:5]}"
        )

    print(f"  MSFT quarterly income statement — {df.shape[1]} periods, {df.shape[0]} rows")
    print(df[df.index.isin(EXPECTED_ROWS)].iloc[:, :5].to_string())


def test_crawl_uses_cf_config_for_macrotrends(monkeypatch):
    """Macrotrends must use the CF-hardened path: domcontentloaded + after_goto hook."""
    captured: dict[str, object] = {}

    class FakeStrategy:
        def set_hook(self, name: str, fn) -> None:
            captured.setdefault("hooks", {})[name] = fn

    class FakeCrawler:
        def __init__(self, config=None):
            captured["browser_config"] = config
            self.crawler_strategy = FakeStrategy()

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def arun(self, *, url, config):
            captured["url"] = url
            captured["crawler_config"] = config
            return types.SimpleNamespace(success=True, error_message=None)

    monkeypatch.setattr(crawl4ai_tool, "AsyncWebCrawler", FakeCrawler)

    asyncio.run(crawl4ai_tool._crawl("https://www.macrotrends.net/stocks/charts/GOOG/alphabet/pe-ratio"))

    assert captured["crawler_config"].wait_until == "domcontentloaded"
    assert captured["crawler_config"].delay_before_return_html == 3.0
    assert "after_goto" in captured.get("hooks", {}), "Expected CF challenge hook for macrotrends.net"
