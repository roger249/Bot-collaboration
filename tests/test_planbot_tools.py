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

    class FakeCrawler:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def arun(self, *, url, config):
            captured["url"] = url
            captured["config"] = config
            return types.SimpleNamespace(success=True, error_message=None)

    monkeypatch.setattr(crawl4ai_tool, "AsyncWebCrawler", lambda: FakeCrawler())

    asyncio.run(crawl4ai_tool._crawl("https://example.com"))

    assert captured["url"] == "https://example.com"
    assert isinstance(captured["config"].markdown_generator, crawl4ai_tool.DefaultMarkdownGenerator)
