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

        @staticmethod
        def history(period: str, interval: str):
            assert period == "1y"
            assert interval == "1mo"
            return FakeFrame({"2026-05-10": {"Close": 188.0}})

    class FakeYF:
        @staticmethod
        def Ticker(symbol: str):
            assert symbol == "AAPL"
            return FakeTicker()

    monkeypatch.setattr(yfinance_tool, "_import_yfinance", lambda: FakeYF)

    tool = yfinance_tool.YFinanceTool()
    payload = tool._run(
        "AAPL",
        period="1y",
        interval="1mo",
        output_format="json",
        include_financial_statement=True,
    )

    parsed = __import__("json").loads(payload)
    assert parsed["ticker"] == "AAPL"
    assert "income_statement" in parsed
    assert "historical_financial_ratios" in parsed
    assert "quote" in parsed
    assert list(parsed.keys())[:3] == ["quote", "income_statement", "historical_financial_ratios"]
    assert parsed["quote"]["current_price"] == 190.5
    assert parsed["quote"]["trailing_pe"] == 30.1
    assert parsed["quote"]["price_to_sales"] == 7.4
    assert parsed["historical_financial_ratios"][0]["gross_margin_pct"] == 45.0


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
    csv_text = tool._run("GOOG", output_format="csv", include_financial_statement=True, include_price_history=True)

    assert "# quote" in csv_text
    assert "field,value" in csv_text
    assert "current_price,176.2" in csv_text
    assert "# income_statement_annual" in csv_text
    assert "Total Revenue" in csv_text
    assert "# price_history" in csv_text
    assert "date,Close" in csv_text
    assert "2026-05-10,176.2" in csv_text
    assert "Close" in csv_text
    assert csv_text.index("# quote") < csv_text.index("# income_statement_annual") < csv_text.index("# price_history")
    assert "# historical_financial_ratios" in csv_text
    assert "gross_margin_pct" in csv_text


@pytest.mark.integration
@pytest.mark.e2e
def test_yfinance_dump_for_human_review():
    """E2E test: dump live Markdown response to artifact file for manual validation."""
    from src.planbot.yfinance_tool import YFinanceTool

    tool = YFinanceTool()
    tool.max_output_chars = 0
    ticker = "2601.HK"

    try:
        markdown_text = tool._run(
            ticker,
            period="1y",
            interval="1mo",
            output_format="md",
            include_quote_summary=True,
            include_financial_statement=True,
            include_price_history=True,
        )
    except Exception as exc:  # pragma: no cover - depends on external network/service
        pytest.xfail(f"Live Yahoo/yfinance call failed: {exc}")

    assert isinstance(markdown_text, str)
    assert "# YFinance Summary:" in markdown_text
    assert "## Quote" in markdown_text
    assert "current_price" in markdown_text
    assert "## Price History" in markdown_text

    out_dir = Path("runs/test_artifacts/yfinance")
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_file = out_dir / f"{ticker.lower()}_live_{stamp}.md"
    out_file.write_text(
        markdown_text,
        encoding="utf-8",
    )

    assert out_file.exists()
    print(f"HUMAN_REVIEW_MD={out_file}")


def test_yfinance_tool_rejects_interval_not_1mo():
    from src.planbot import yfinance_tool

    tool = yfinance_tool.YFinanceTool()
    with pytest.raises(ValueError, match="must be '1mo' only"):
        tool._run("AAPL", interval="1wk")
    with pytest.raises(ValueError, match="must be '1mo' only"):
        tool._run("AAPL", interval="3mo")


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

