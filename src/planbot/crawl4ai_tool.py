from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import Coroutine
from typing import Any

from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, DefaultMarkdownGenerator
from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class Crawl4AIInput(BaseModel):
    url: str = Field(..., description="Absolute URL to crawl and extract content from")



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



async def _crawl(url: str):
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(
            url=url,
            config=CrawlerRunConfig(markdown_generator=DefaultMarkdownGenerator()),
        )

    if not result.success:
        message = result.error_message or "unknown crawl error"
        raise RuntimeError(f"Crawl4AI failed for URL '{url}': {message}")
    return result
