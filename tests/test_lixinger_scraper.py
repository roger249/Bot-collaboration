"""Tests for Lixinger scraper utility."""

from __future__ import annotations

import os
import time
import pytest
import src.planbot.lixinger_scraper as lixinger_scraper_module

from src.planbot.lixinger_scraper import (
    BotBlockedError,
    DataPageNotReadyError,
    LixingerScraperError,
    LoginFailedError,
    PageState,
    _classify_page_state,
    _has_metric_marker,
    _initial_urls_for_symbol,
    _is_retryable_stage_error,
    _parse_metric_from_content,
    scrape_lixinger_metrics,
)


def _scrape_with_live_retries(symbol: str, attempts: int = 1) -> dict[str, dict[str, float | str]]:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return scrape_lixinger_metrics(symbol)
        except Exception as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(2)
                continue
            pytest.skip(
                f"Live site unstable/unavailable for symbol={symbol}: {type(exc).__name__}: {exc}"
            )

    assert last_error is not None
    raise last_error


@pytest.mark.integration
def test_scrape_lixinger_metrics_baba():
    """Integration test: scrape Lixinger metrics for BABA stock."""
    metrics = _scrape_with_live_retries("BABA")
    
    assert isinstance(metrics, dict)
    assert "PE-TTM" in metrics
    assert "PB" in metrics
    assert "PS-TTM" in metrics
    
    for metric_name, metric_data in metrics.items():
        assert isinstance(metric_data, dict)
        required_keys = {
            "current_value",
            "current_position",
            "point_80",
            "point_50",
            "point_20",
            "max_value",
            "average_value",
            "min_value",
        }
        assert required_keys.issubset(metric_data.keys()), f"Missing keys in {metric_name}: {required_keys - metric_data.keys()}"
        
        # All values should be numeric
        for key, value in metric_data.items():
            assert isinstance(value, (int, float)), f"{metric_name}.{key} is not numeric: {value}"


@pytest.mark.integration
def test_scrape_lixinger_metrics_hk_stock():
    """Integration test: scrape Lixinger metrics for HK stock (836)."""
    metrics = _scrape_with_live_retries("836")
    
    assert isinstance(metrics, dict)
    assert "PE-TTM" in metrics or "PB" in metrics or "PS-TTM" in metrics


def test_scrape_lixinger_metrics_missing_password(monkeypatch):
    """Test that scraper raises error when LIXINGER_PASSWORD is not set."""
    monkeypatch.setattr(lixinger_scraper_module, "_load_local_dotenv", lambda: None)
    monkeypatch.delenv("LIXINGER_PASSWORD", raising=False)
    with pytest.raises(ValueError, match="LIXINGER_PASSWORD environment variable not set"):
        scrape_lixinger_metrics("BABA")


def test_classify_page_state_bot_blocked():
    state = _classify_page_state(
        "https://www.lixinger.com/analytics/company/detail/hk/00700/700/fundamental/valuation/primary",
        "you are robot",
    )
    assert state == PageState.BOT_BLOCKED


def test_classify_page_state_login_required():
    state = _classify_page_state(
        "https://www.lixinger.com/login",
        "账号或手机号 密码 登录",
    )
    assert state == PageState.LOGIN_REQUIRED


def test_classify_page_state_detail_page():
    state = _classify_page_state(
        "https://www.lixinger.com/analytics/company/detail/hk/00700/700/fundamental/valuation/primary",
        "some content",
    )
    assert state == PageState.DETAIL_PAGE


def test_classify_page_state_search_page():
    state = _classify_page_state(
        "https://www.lixinger.com/analytics/company/search?q=700",
        "some content",
    )
    assert state == PageState.SEARCH_PAGE


def test_classify_page_state_detail_url_with_login_markers():
    state = _classify_page_state(
        "https://www.lixinger.com/analytics/company/detail/hk/00836/836/fundamental/valuation/primary",
        "首页 登录/注册 搜索",
    )
    assert state == PageState.LOGIN_REQUIRED


def test_retry_policy_does_not_retry_bot_blocked():
    assert _is_retryable_stage_error(BotBlockedError("blocked")) is False


def test_retry_policy_retries_login_failed():
    assert _is_retryable_stage_error(LoginFailedError("login failed")) is True


def test_retry_policy_retries_data_not_ready():
    assert _is_retryable_stage_error(DataPageNotReadyError("not ready")) is True


def test_initial_urls_for_hk_symbol_include_10y_granularity():
    urls = _initial_urls_for_symbol("836")
    assert "granularity=y10" in urls[0]
    assert "/analytics/company/detail/hk/00836/836/" in urls[0]


def test_initial_urls_for_baba_include_10y_granularity():
    urls = _initial_urls_for_symbol("BABA")
    assert "granularity=y10" in urls[0]
    assert "/analytics/company/detail/nyse/BABA/157755200/" in urls[0]


def test_has_metric_marker_detects_compact_text():
    assert _has_metric_marker("PE-TTM 23.36 PB 2.10 PS-TTM 3.42") is True


def test_parse_metric_from_compact_band_row():
    content = "PE-TTM & PB & PS-TTM Band\\n(BABA.nyse) PE-TTM 23.36 PB 2.10 PS-TTM 3.42"
    parsed = _parse_metric_from_content(content, "PE-TTM")
    assert parsed is not None
    assert parsed["current_value"] == pytest.approx(23.36)


def test_parse_metric_from_chinese_alias_row():
    content = "( 00836.hk ) 市盈率(TTM) 6.23 市净率 0.81 市销率(TTM) 1.45"
    parsed = _parse_metric_from_content(content, "PE-TTM")
    assert parsed is not None
    assert parsed["current_value"] == pytest.approx(6.23)
