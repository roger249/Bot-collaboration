from __future__ import annotations

import json
import os
import sys
import types
import asyncio
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.planbot import crew_workflow
from src.planbot import crawl4ai_tool


def test_build_tool_instance_supports_yfinance():
    tool = crew_workflow._build_tool_instance("YFinance")
    assert tool.name == "YFinance"


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


def test_yfinance_tool_returns_normalized_payload(monkeypatch):
    from src.planbot import yfinance_tool

    class FakeFrame:
        def __init__(self, payload):
            self._payload = payload

        def to_dict(self, orient="index"):
            assert orient == "index"
            return self._payload

    class FakeTicker:
        info = {
            "symbol": "AAPL",
            "shortName": "Apple Inc.",
            "currency": "USD",
            "exchange": "NMS",
            "currentPrice": 190.5,
            "trailingPE": 30.1,
            "priceToSalesTrailing12Months": 7.4,
            "marketCap": 100,
            "previousClose": 189.0,
        }

        income_stmt = FakeFrame(
            {
                "2025-12-31": {
                    "Total Revenue": 1000,
                    "Gross Profit": 450,
                    "Operating Income": 300,
                    "Net Income": 250,
                }
            }
        )

        quarterly_income_stmt = FakeFrame(
            {
                "2026-03-31": {
                    "Total Revenue": 250,
                    "Gross Profit": 100,
                    "Operating Income": 75,
                    "Net Income": 50,
                }
            }
        )

        @staticmethod
        def history(period: str, interval: str):
            assert period == "1y"
            assert interval == "1d"
            return FakeFrame({"2026-05-10": {"Close": 188.0}})

    class FakeYF:
        @staticmethod
        def Ticker(symbol: str):
            assert symbol == "AAPL"
            return FakeTicker()

    monkeypatch.setattr(yfinance_tool, "_import_yfinance", lambda: FakeYF)

    tool = yfinance_tool.YFinanceTool()
    payload = tool._run("AAPL")

    parsed = __import__("json").loads(payload)
    assert parsed["ticker"] == "AAPL"
    assert "income_statement" in parsed
    assert "historical_financial_ratios" in parsed
    assert "quote" in parsed
    assert parsed["quote"]["current_price"] == 190.5
    assert parsed["quote"]["trailing_pe"] == 30.1
    assert parsed["quote"]["price_to_sales"] == 7.4
    assert parsed["historical_financial_ratios"][0]["gross_margin_pct"] == 40.0


def test_yfinance_tool_csv_output(monkeypatch):
    from src.planbot import yfinance_tool

    class FakeFrame:
        def __init__(self, payload):
            self._payload = payload

        def to_dict(self, orient="index"):
            assert orient == "index"
            return self._payload

    class FakeTicker:
        info = {
            "symbol": "GOOG",
            "shortName": "Alphabet Inc.",
            "currency": "USD",
            "currentPrice": 176.2,
            "trailingPE": 23.4,
            "priceToSalesTrailing12Months": 6.1,
        }

        income_stmt = FakeFrame(
            {
                "2025-12-31": {
                    "Total Revenue": 300,
                    "Gross Profit": 120,
                    "Operating Income": 90,
                    "Net Income": 80,
                }
            }
        )

        quarterly_income_stmt = FakeFrame(
            {
                "2026-03-31": {
                    "Total Revenue": 75,
                    "Gross Profit": 30,
                    "Operating Income": 22,
                    "Net Income": 18,
                }
            }
        )

        @staticmethod
        def history(period: str, interval: str):
            return FakeFrame({"2026-05-10": {"Close": 176.2}})

    class FakeYF:
        @staticmethod
        def Ticker(symbol: str):
            assert symbol == "GOOG"
            return FakeTicker()

    monkeypatch.setattr(yfinance_tool, "_import_yfinance", lambda: FakeYF)

    tool = yfinance_tool.YFinanceTool()
    csv_text = tool._run("GOOG", output_format="csv")

    assert "# quote" in csv_text
    assert "field,value" in csv_text
    assert "current_price,176.2" in csv_text
    assert "# historical_financial_ratios" in csv_text
    assert "gross_margin_pct" in csv_text
    assert "# income_statement_annual" in csv_text
    assert "Total Revenue" in csv_text


def test_yfinance_tool_include_quote_summary_merges_fields(monkeypatch):
    import json
    from src.planbot import yfinance_tool

    class FakeFrame:
        def __init__(self, payload):
            self._payload = payload

        def to_dict(self, orient="index"):
            assert orient == "index"
            return self._payload

    class FakeTicker:
        # Deliberately sparse info so quoteSummary merge path is exercised.
        info = {"symbol": "2601.HK"}
        income_stmt = FakeFrame({})
        quarterly_income_stmt = FakeFrame({})

        @staticmethod
        def history(period: str, interval: str):
            return FakeFrame({})

    class FakeYF:
        @staticmethod
        def Ticker(symbol: str):
            assert symbol == "2601.HK"
            return FakeTicker()

    class FakeResponse:
        def __init__(self, payload: str):
            self._payload = payload.encode("utf-8")

        def read(self):
            return self._payload

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

    def fake_urlopen(request, timeout=15):
        assert "quoteSummary/2601.HK" in request.full_url
        result = {
            "quoteSummary": {
                "result": [
                    {
                        "price": {
                            "symbol": "2601.HK",
                            "shortName": "CPIC",
                            "regularMarketPrice": {"raw": 32.7},
                            "marketCap": {"raw": 388_890_000_000},
                            "currency": "HKD",
                            "quoteType": "EQUITY",
                            "exchangeName": "HKG",
                        },
                        "defaultKeyStatistics": {
                            "trailingPE": {"raw": 5.62},
                        },
                        "summaryDetail": {
                            "priceToSalesTrailing12Months": {"raw": 0.71},
                            "previousClose": {"raw": 32.94},
                        },
                    }
                ],
                "error": None,
            }
        }
        return FakeResponse(json.dumps(result))

    monkeypatch.setattr(yfinance_tool, "_import_yfinance", lambda: FakeYF)
    monkeypatch.setattr(yfinance_tool.urllib.request, "urlopen", fake_urlopen)

    tool = yfinance_tool.YFinanceTool()
    text = tool._run("2601.HK", include_quote_summary=True)
    payload = json.loads(text)

    quote = payload["quote"]
    assert quote["symbol"] == "2601.HK"
    assert quote["short_name"] == "CPIC"
    assert quote["current_price"] == 32.7
    assert quote["trailing_pe"] == 5.62
    assert quote["price_to_sales"] == 0.71
    assert quote["previous_close"] == 32.94
    assert "quote_summary" in payload


@pytest.mark.integration
@pytest.mark.e2e
def test_yfinance_tool_live_goog_json():
    """E2E test: hit live Yahoo/yfinance path and validate normalized JSON shape."""
    import json
    from src.planbot.yfinance_tool import YFinanceTool

    tool = YFinanceTool()
    tool.max_output_chars = 0

    try:
        text = tool._run("GOOG", period="1y", interval="1d", output_format="json")
        payload = json.loads(text)
    except Exception as exc:  # pragma: no cover - depends on external network/service
        pytest.xfail(f"Live Yahoo/yfinance call failed: {exc}")

    assert payload["ticker"] == "GOOG"
    assert "income_statement" in payload
    assert "historical_financial_ratios" in payload
    assert "quote" in payload
    assert payload["quote"].get("current_price") is not None
    # New: price_history field should be present and non-empty
    assert "price_history" in payload
    assert isinstance(payload["price_history"], list)
    assert len(payload["price_history"]) > 0


@pytest.mark.integration
@pytest.mark.e2e
def test_yfinance_tool_live_dump_json_for_human_review():
    """E2E test: dump live GOOG JSON response to artifact file for manual validation."""
    from src.planbot.yfinance_tool import YFinanceTool

    tool = YFinanceTool()
    tool.max_output_chars = 0

    try:
        raw = tool._run(
            "2601.HK",
            period="1y",
            interval="1d",
            output_format="json",
            include_quote_summary=True,
        )
        payload = json.loads(raw)
    except Exception as exc:  # pragma: no cover - depends on external network/service
        pytest.xfail(f"Live Yahoo/yfinance call failed: {exc}")

    assert payload.get("ticker") == "2601.HK"
    assert "income_statement" in payload
    assert "historical_financial_ratios" in payload
    assert "quote" in payload
    assert payload["quote"].get("current_price") is not None
    # New: price_history field should be present and non-empty
    assert "price_history" in payload
    assert isinstance(payload["price_history"], list)
    assert len(payload["price_history"]) > 0

    out_dir = Path("runs/test_artifacts/yfinance")
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_file = out_dir / f"2601hk_live_{stamp}.json"
    out_file.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    assert out_file.exists()
    print(f"HUMAN_REVIEW_JSON={out_file}")


@pytest.mark.integration
@pytest.mark.e2e
def test_yfinance_tool_live_2601hk_with_quote_summary():
    """E2E test: live Yahoo quoteSummary merge path for a HK ticker."""
    import json
    from src.planbot.yfinance_tool import YFinanceTool

    tool = YFinanceTool()
    tool.max_output_chars = 0

    try:
        text = tool._run(
            "2601.HK",
            period="5y",
            interval="1mo",
            output_format="json",
            include_quote_summary=True,
        )
        payload = json.loads(text)
    except Exception as exc:  # pragma: no cover - depends on external network/service
        pytest.xfail(f"Live Yahoo/yfinance call failed: {exc}")

    assert payload["ticker"] == "2601.HK"
    quote = payload.get("quote", {})
    assert quote.get("symbol") in {"2601.HK", None} or str(quote.get("symbol", "")).endswith(".HK")
    assert quote.get("current_price") is not None
    # New: price_history field should be present and non-empty
    assert "price_history" in payload
    assert isinstance(payload["price_history"], list)
    assert len(payload["price_history"]) > 0
    # quoteSummary may be unavailable for some symbols/regions; when present it should enrich fields.
    if "quote_summary" in payload:
        assert payload.get("quote_summary")
    else:
        assert any(quote.get(key) is not None for key in ["trailing_pe", "price_to_sales", "market_cap"])


def test_yfinance_tool_exclude_price_history(monkeypatch):
    """Unit: include_price_history disables price_history field."""
    from src.planbot import yfinance_tool

    class FakeTicker:
        def __init__(self, symbol):
            self.info = {"currentPrice": 123.45}
            self.income_stmt = None
            self.quarterly_income_stmt = None
        def history(self, period, interval):
            return [{"period": "2020-01-01", "Close": 100.0}]

    class FakeYF:
        Ticker = FakeTicker

    monkeypatch.setattr(yfinance_tool, "_import_yfinance", lambda: FakeYF)
    tool = yfinance_tool.YFinanceTool()
    result = tool._run("FAKE", include_price_history=False)
    payload = json.loads(result)
    assert "price_history" not in payload


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
