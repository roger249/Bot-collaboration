from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator

try:
    from loguru import logger
except Exception:  # pragma: no cover - fallback when loguru is unavailable
    import logging

    logger = logging.getLogger(__name__)


SUPPORTED_FREQUENCIES = {"1d": "1d", "1w": "1wk", "1m": "1mo", "1q": "3mo"}
DEFAULT_PERIODS = ["6m", "1y", "3y", "5y", "10y"]
DEFAULT_METRICS = ["return", "cagr", "max_drawdown", "price_ihr_20", "price_ihr_80"]
ALLOWED_METRICS = set(DEFAULT_METRICS)
ALLOWED_METRICS.add("calmar_ratio")


class MarketDataConfig(BaseModel):
    output_filename: str = "selected_etf.csv"
    metrics: list[str] = Field(default_factory=lambda: list(DEFAULT_METRICS))
    frequency: str = "1w"
    periods: list[str] = Field(default_factory=lambda: list(DEFAULT_PERIODS))
    tickers: list[str] = Field(default_factory=list)
    ticker_groups: dict[str, list[str]] = Field(default_factory=dict)
    asset_class_proxy: dict[str, str] = Field(default_factory=dict)
    execute_ticker_groupname: str | None = None
    name_preference: str = "long"

    @field_validator("frequency")
    @classmethod
    def _validate_frequency(cls, value: str) -> str:
        normalized = str(value).strip().lower()
        if normalized not in SUPPORTED_FREQUENCIES:
            raise ValueError(f"Unsupported frequency '{value}'. Supported: {sorted(SUPPORTED_FREQUENCIES)}")
        return normalized

    @field_validator("periods")
    @classmethod
    def _validate_periods(cls, values: list[str]) -> list[str]:
        cleaned = [str(item).strip().lower() for item in values if str(item).strip()]
        if not cleaned:
            raise ValueError("periods cannot be empty")
        return cleaned

    @field_validator("tickers")
    @classmethod
    def _validate_tickers(cls, values: list[str]) -> list[str]:
        cleaned = [str(item).strip().upper() for item in values if str(item).strip()]
        return cleaned

    @field_validator("ticker_groups")
    @classmethod
    def _validate_ticker_groups(cls, value: dict[str, list[str]]) -> dict[str, list[str]]:
        normalized: dict[str, list[str]] = {}
        for group_name, tickers in (value or {}).items():
            cleaned_group = str(group_name).strip()
            cleaned_tickers = [str(item).strip().upper() for item in (tickers or []) if str(item).strip()]
            if not cleaned_group:
                raise ValueError("ticker_groups cannot contain an empty group name")
            if not cleaned_tickers:
                raise ValueError(f"ticker_groups['{cleaned_group}'] cannot be empty")
            normalized[cleaned_group] = cleaned_tickers
        return normalized

    @field_validator("asset_class_proxy")
    @classmethod
    def _validate_asset_class_proxy(cls, value: dict[str, str]) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for asset_class, proxy_ticker in (value or {}).items():
            cleaned_asset_class = str(asset_class).strip()
            cleaned_proxy = str(proxy_ticker).strip().upper()
            if not cleaned_asset_class or not cleaned_proxy:
                raise ValueError("asset_class_proxy entries must include both asset class and proxy ticker")
            normalized[cleaned_asset_class] = cleaned_proxy
        return normalized

    @field_validator("execute_ticker_groupname")
    @classmethod
    def _validate_execute_ticker_groupname(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    @field_validator("name_preference")
    @classmethod
    def _validate_name_preference(cls, value: str) -> str:
        normalized = str(value).strip().lower()
        if normalized not in {"long", "short"}:
            raise ValueError("name_preference must be either 'long' or 'short'")
        return normalized

    @field_validator("metrics")
    @classmethod
    def _validate_metrics(cls, values: list[str]) -> list[str]:
        normalized = [_normalize_metric_name(item) for item in values if str(item).strip()]
        if not normalized:
            raise ValueError("metrics cannot be empty")
        if len(set(normalized)) != len(normalized):
            raise ValueError("metrics cannot contain duplicates")
        invalid = [item for item in normalized if item not in ALLOWED_METRICS]
        if invalid:
            raise ValueError(
                f"Unsupported metrics: {invalid}. Supported: {sorted(ALLOWED_METRICS)}"
            )
        return normalized


@dataclass
class PeriodMetrics:
    period_return: float | None
    cagr: float | None
    calmar_ratio: float | None
    max_drawdown: float | None
    ihr20: float | None
    ihr80: float | None


def load_market_data_config(config_path: str | Path) -> MarketDataConfig:
    path = Path(config_path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    try:
        return MarketDataConfig(**raw)
    except ValidationError as exc:
        raise ValueError(f"Invalid market data config at {path}: {exc}") from exc


def get_market_data(
    tickers: list[str],
    output_filename: str = "selected_etf.csv",
    frequency: str = "1w",
    metrics: list[str] | None = None,
    periods: list[str] | None = None,
    output_dir: str | Path = "data/planbot/shared/product_catalog",
    name_preference: str = "long",
    asset_class_proxy: dict[str, str] | None = None,
    ticker_groupname: str | None = None,
) -> Path:
    """Generate a single-table CSV market dataset for the provided Yahoo tickers."""
    normalized_tickers = [str(item).strip().upper() for item in tickers if str(item).strip()]
    if not normalized_tickers:
        raise ValueError("tickers cannot be empty")

    normalized_metrics = [_normalize_metric_name(item) for item in (metrics or DEFAULT_METRICS) if str(item).strip()]
    if not normalized_metrics:
        raise ValueError("metrics cannot be empty")
    invalid_metrics = [item for item in normalized_metrics if item not in ALLOWED_METRICS]
    if invalid_metrics:
        raise ValueError(
            f"Unsupported metrics: {invalid_metrics}. Supported: {sorted(ALLOWED_METRICS)}"
        )

    normalized_frequency = str(frequency).strip().lower()
    if normalized_frequency not in SUPPORTED_FREQUENCIES:
        raise ValueError(
            f"Unsupported frequency '{frequency}'. Supported: {sorted(SUPPORTED_FREQUENCIES)}"
        )
    interval = SUPPORTED_FREQUENCIES[normalized_frequency]

    normalized_periods = [str(item).strip().lower() for item in (periods or DEFAULT_PERIODS) if str(item).strip()]
    if not normalized_periods:
        raise ValueError("periods cannot be empty")

    normalized_name_preference = str(name_preference).strip().lower()
    if normalized_name_preference not in {"long", "short"}:
        raise ValueError("name_preference must be either 'long' or 'short'")

    normalized_asset_class_proxy = {
        str(asset_class).strip(): str(proxy).strip().upper()
        for asset_class, proxy in (asset_class_proxy or {}).items()
        if str(asset_class).strip() and str(proxy).strip()
    }

    output_path = _resolve_output_path(
        output_filename=output_filename,
        output_dir=Path(output_dir),
        ticker_groupname=ticker_groupname,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = _build_fieldnames(normalized_periods, normalized_metrics)
    yf = _import_yfinance()
    proxy_history_cache: dict[tuple[str, str], list[dict[str, Any]]] = {}
    sgov_one_year_return = _fetch_benchmark_one_year_return(
        yf=yf,
        interval=interval,
        benchmark_ticker="SGOV",
    )

    rows: list[dict[str, Any]] = []
    for symbol in normalized_tickers:
        ticker_obj = yf.Ticker(symbol)
        info = _safe_to_dict(getattr(ticker_obj, "info", {}) or {})

        row: dict[str, Any] = {
            "ticker": symbol,
            "asset_class": _normalize_asset_class(info),
            "name": _pick_name(info, normalized_name_preference),
            "currency": _as_text(info.get("currency")),
            "last_update_date": "",
            "last_closing_price": "",
        }

        period_results: dict[str, PeriodMetrics] = {}
        latest_row = None

        for period in normalized_periods:
            history = _history_to_rows(
                _fetch_history(ticker_obj=ticker_obj, period=_to_yfinance_period(period), interval=interval)
            )
            if latest_row is None and history:
                latest_row = history[0]

            period_metrics = _calculate_period_metrics(history)
            if _history_needs_proxy(history) or _period_metrics_need_proxy(period_metrics):
                proxy_history = _history_with_proxy_fallback(
                    history=history,
                    asset_class=row["asset_class"],
                    asset_class_proxy=normalized_asset_class_proxy,
                    interval=interval,
                    period=period,
                    yf=yf,
                    proxy_history_cache=proxy_history_cache,
                )
                if proxy_history is not history:
                    period_metrics = _calculate_period_metrics(proxy_history)
            period_results[period] = period_metrics

            metric_values: dict[str, float | None] = {
                "return": period_metrics.period_return,
                "cagr": period_metrics.cagr,
                "calmar_ratio": period_metrics.calmar_ratio,
                "max_drawdown": period_metrics.max_drawdown,
                "price_ihr_20": period_metrics.ihr20,
                "price_ihr_80": period_metrics.ihr80,
            }
            for metric in normalized_metrics:
                row[_metric_column_name(metric, period)] = _round_or_blank(metric_values.get(metric))

        if latest_row:
            row["last_update_date"] = str(latest_row.get("date") or "")
            row["last_closing_price"] = _round_or_blank(_as_float(latest_row.get("close")))

        risk_rating = _estimate_risk_rating(period_results.get("1y"), period_results)
        risk_rating = _enforce_sgov_return_ratio_rule(
            risk_rating=risk_rating,
            one_year_return=(period_results.get("1y").period_return if period_results.get("1y") else None),
            sgov_one_year_return=sgov_one_year_return,
            is_etf=_is_etf(info),
        )
        expected_return_score = _estimate_expected_return_score(period_results.get("3y"))
        certainty_1y_score = _estimate_certainty_score(risk_rating, horizon="1y")
        certainty_3y_score = _estimate_certainty_score(risk_rating, horizon="3y")
        certainty_1y_score, certainty_3y_score = _apply_certainty_caps(
            certainty_1y_score=certainty_1y_score,
            certainty_3y_score=certainty_3y_score,
            risk_rating=risk_rating,
            asset_class=row["asset_class"],
        )

        row["risk_rating"] = risk_rating
        row["expected_return_score"] = expected_return_score
        row["certainty_1y_score"] = certainty_1y_score
        row["certainty_3y_score"] = certainty_3y_score
        row["certainty_8y_score"] = _estimate_certainty_score(risk_rating, horizon="8y")
        row["liquidity_score"] = _estimate_liquidity_score(info)

        rows.append(row)

    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    logger.info("Generated market data CSV at {} with {} rows", output_path, len(rows))
    return output_path


def get_market_data_from_config(
    tickers: list[str] | None = None,
    ticker_groupname: str | None = None,
    config_path: str | Path = "config/config_marketdata.yaml",
    output_dir: str | Path = "data/planbot/shared/product_catalog",
) -> Path:
    cfg = load_market_data_config(config_path)
    effective_ticker_groupname = ticker_groupname or cfg.execute_ticker_groupname
    configured_or_overridden_tickers = _resolve_configured_tickers(
        cfg=cfg,
        tickers=tickers,
        ticker_groupname=effective_ticker_groupname,
    )
    return get_market_data(
        tickers=configured_or_overridden_tickers,
        output_filename=cfg.output_filename,
        frequency=cfg.frequency,
        metrics=cfg.metrics,
        periods=cfg.periods,
        output_dir=output_dir,
        name_preference=cfg.name_preference,
        asset_class_proxy=cfg.asset_class_proxy,
        ticker_groupname=effective_ticker_groupname,
    )


def _import_yfinance() -> Any:
    try:
        import yfinance as yf
    except ImportError as exc:  # pragma: no cover - import guard
        raise RuntimeError("yfinance dependency is missing. Install it with: uv pip install yfinance") from exc
    return yf


def _fetch_history(ticker_obj: Any, period: str, interval: str) -> Any:
    """Fetch price history with a bounded timeout when supported by yfinance."""
    try:
        return ticker_obj.history(period=period, interval=interval, timeout=20)
    except TypeError:
        return ticker_obj.history(period=period, interval=interval)


def _fetch_benchmark_one_year_return(yf: Any, interval: str, benchmark_ticker: str = "SGOV") -> float | None:
    try:
        ticker_obj = yf.Ticker(benchmark_ticker)
        history = _history_to_rows(
            _fetch_history(
                ticker_obj=ticker_obj,
                period=_to_yfinance_period("1y"),
                interval=interval,
            )
        )
        return _calculate_period_metrics(history).period_return
    except Exception:
        logger.warning(f"Unable to retrieve benchmark return for {benchmark_ticker}")
        return None


def _build_fieldnames(periods: list[str], metrics: list[str]) -> list[str]:
    base = [
        "ticker",
        "asset_class",
        "name",
        "currency",
        "last_update_date",
        "last_closing_price",
    ]
    # Category-first ordering driven by metrics list from config,
    # with each category expanded by period.
    dynamic: list[str] = []
    for metric in metrics:
        dynamic.extend(_metric_column_name(metric, period) for period in periods)

    tail = [
        "risk_rating",
        "expected_return_score",
        "certainty_1y_score",
        "certainty_3y_score",
        "certainty_8y_score",
        "liquidity_score",
    ]
    return base + dynamic + tail


def _resolve_configured_tickers(
    cfg: MarketDataConfig,
    tickers: list[str] | None,
    ticker_groupname: str | None,
) -> list[str]:
    if tickers is not None:
        cleaned = [str(item).strip().upper() for item in tickers if str(item).strip()]
        if not cleaned:
            raise ValueError("tickers cannot be empty")
        return cleaned

    if ticker_groupname is not None:
        group_name = str(ticker_groupname).strip()
        if not group_name:
            raise ValueError("ticker_groupname cannot be empty")
        if group_name not in cfg.ticker_groups:
            raise ValueError(
                f"Unknown ticker_groupname '{group_name}'. Available groups: {sorted(cfg.ticker_groups)}"
            )
        return cfg.ticker_groups[group_name]

    if cfg.tickers:
        return cfg.tickers

    if len(cfg.ticker_groups) == 1:
        return next(iter(cfg.ticker_groups.values()))

    if cfg.ticker_groups:
        raise ValueError(
            "ticker_groupname is required when config defines multiple ticker_groups"
        )

    raise ValueError("No tickers configured. Provide tickers or define ticker_groups in config")


def _resolve_output_path(output_filename: str, output_dir: Path, ticker_groupname: str | None = None) -> Path:
    group_name = ticker_groupname or "selected_etf"
    rendered_output_filename = output_filename.replace("<tickers_groupname>", group_name)
    rendered_output_filename = rendered_output_filename.replace("<tickers_group>", group_name)
    candidate = Path(rendered_output_filename)
    if candidate.is_absolute():
        return candidate

    if len(candidate.parts) > 1:
        # Treat nested output_filename as workspace-relative path.
        project_root = Path(__file__).resolve().parents[2]
        return project_root / candidate

    return output_dir / candidate


def _to_yfinance_period(period: str) -> str:
    text = str(period).strip().lower()
    if text.endswith("m") and not text.endswith("mo"):
        return f"{text[:-1]}mo"
    return text


def _safe_to_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _normalize_asset_class(info: dict[str, Any]) -> str:
    candidates = [
        info.get("assetClass"),
        info.get("fundCategory"),
        info.get("category"),
        info.get("quoteType"),
    ]
    for value in candidates:
        text = _as_text(value).strip()
        if text:
            return text
    return ""


def _is_etf(info: dict[str, Any]) -> bool:
    quote_type = _as_text(info.get("quoteType")).strip().lower()
    return quote_type == "etf"


def _history_to_rows(frame: Any) -> list[dict[str, Any]]:
    to_dict = getattr(frame, "to_dict", None)
    if not callable(to_dict):
        return []

    try:
        raw = to_dict(orient="index")
    except Exception:
        return []

    if not isinstance(raw, dict):
        return []

    rows: list[dict[str, Any]] = []
    for index_value, metrics in raw.items():
        if not isinstance(metrics, dict):
            continue

        close = _as_float(metrics.get("Close") if "Close" in metrics else metrics.get("close"))
        if close is None:
            continue

        rows.append({"date": _normalize_index_value(index_value), "close": close})

    rows.sort(key=lambda item: str(item["date"]), reverse=True)
    return rows


def _history_needs_proxy(history_rows: list[dict[str, Any]]) -> bool:
    if len(history_rows) < 2:
        return True
    closes = [float(item["close"]) for item in history_rows if _as_float(item.get("close")) is not None]
    if not closes:
        return True
    return all(abs(close) <= 1e-9 for close in closes)


def _period_metrics_need_proxy(period_metrics: PeriodMetrics) -> bool:
    return (
        _is_blank_or_zero(period_metrics.period_return)
        and _is_blank_or_zero(period_metrics.cagr)
        and _is_blank_or_zero(period_metrics.max_drawdown)
    )


def _history_with_proxy_fallback(
    history: list[dict[str, Any]],
    asset_class: str,
    asset_class_proxy: dict[str, str],
    interval: str,
    period: str,
    yf: Any,
    proxy_history_cache: dict[tuple[str, str], list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    proxy_ticker = asset_class_proxy.get(_as_text(asset_class).strip())
    if not proxy_ticker:
        return history

    cache_key = (proxy_ticker, period)
    if cache_key not in proxy_history_cache:
        proxy_ticker_obj = yf.Ticker(proxy_ticker)
        proxy_history_cache[cache_key] = _history_to_rows(
            _fetch_history(
                ticker_obj=proxy_ticker_obj,
                period=_to_yfinance_period(period),
                interval=interval,
            )
        )
    proxy_history = proxy_history_cache[cache_key]
    if _history_needs_proxy(proxy_history):
        return history

    logger.info(
        "Using proxy ticker {} for asset class {} period {}",
        proxy_ticker,
        asset_class,
        period,
    )
    return proxy_history


def _normalize_index_value(index_value: Any) -> str:
    to_pydatetime = getattr(index_value, "to_pydatetime", None)
    if callable(to_pydatetime):
        try:
            converted = to_pydatetime()
            return str(getattr(converted, "date", lambda: converted)())
        except Exception:
            pass
    return str(index_value)


def _calculate_period_metrics(history_rows: list[dict[str, Any]]) -> PeriodMetrics:
    if len(history_rows) < 2:
        return PeriodMetrics(
            period_return=None,
            cagr=None,
            calmar_ratio=None,
            max_drawdown=None,
            ihr20=None,
            ihr80=None,
        )

    closes_new_to_old = [float(item["close"]) for item in history_rows]
    closes = list(reversed(closes_new_to_old))

    first_close = closes[0]
    last_close = closes[-1]
    if first_close <= 0:
        period_return = None
    else:
        period_return = ((last_close / first_close) - 1.0) * 100.0

    cagr = None
    period_years = _period_to_years_from_rows(history_rows)
    if first_close > 0 and last_close > 0 and period_years > 0:
        cagr = ((last_close / first_close) ** (1.0 / period_years) - 1.0) * 100.0

    max_drawdown = _max_drawdown_pct(closes)
    calmar_ratio = _calmar_ratio(cagr, max_drawdown)
    ihr20 = _percentile(closes, 0.2)
    ihr80 = _percentile(closes, 0.8)

    return PeriodMetrics(
        period_return=period_return,
        cagr=cagr,
        calmar_ratio=calmar_ratio,
        max_drawdown=max_drawdown,
        ihr20=ihr20,
        ihr80=ihr80,
    )


def _calmar_ratio(cagr: float | None, max_drawdown: float | None) -> float | None:
    if cagr is None or max_drawdown is None:
        return None
    denominator = abs(max_drawdown)
    if denominator <= 0:
        return None
    return cagr / denominator


def _period_to_years_from_rows(history_rows: list[dict[str, Any]]) -> float:
    if len(history_rows) < 2:
        return 0.0
    # rows are new->old
    span_points = max(1, len(history_rows) - 1)
    # Works with configured weekly/monthly/quarterly frequencies as an approximation.
    # 52 points/year is a reasonable baseline for CAGR purposes here.
    years = span_points / 52.0
    return max(years, 1 / 52.0)


def _max_drawdown_pct(closes: list[float]) -> float | None:
    if not closes:
        return None

    peak = closes[0]
    min_drawdown = 0.0
    for price in closes:
        peak = max(peak, price)
        if peak <= 0:
            continue
        drawdown = ((price / peak) - 1.0) * 100.0
        min_drawdown = min(min_drawdown, drawdown)
    return min_drawdown


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    if q <= 0:
        return min(values)
    if q >= 1:
        return max(values)

    sorted_values = sorted(values)
    idx = (len(sorted_values) - 1) * q
    lo = math.floor(idx)
    hi = math.ceil(idx)
    if lo == hi:
        return sorted_values[lo]

    weight = idx - lo
    return sorted_values[lo] * (1 - weight) + sorted_values[hi] * weight


def _estimate_risk_rating(one_year_metrics: PeriodMetrics | None, all_metrics: dict[str, PeriodMetrics]) -> int:
    drawdown = one_year_metrics.max_drawdown if one_year_metrics else None
    if drawdown is None:
        # Fall back to the longest available period with drawdown information.
        for key in sorted(all_metrics.keys(), key=_period_to_months, reverse=True):
            drawdown = all_metrics[key].max_drawdown
            if drawdown is not None:
                break

    if drawdown is None:
        return 3

    magnitude = abs(drawdown)
    if magnitude <= 5:
        return 1
    if magnitude <= 10:
        return 2
    if magnitude <= 20:
        return 3
    if magnitude <= 35:
        return 4
    return 5


def _estimate_expected_return_score(period_metrics: PeriodMetrics | None) -> int:
    period_cagr = period_metrics.cagr if period_metrics else None
    if period_cagr is None:
        return 3
    if period_cagr <= 0:
        return 1
    if period_cagr <= 5:
        return 2
    if period_cagr <= 12:
        return 3
    if period_cagr <= 20:
        return 4
    return 5


def _enforce_sgov_return_ratio_rule(
    risk_rating: int,
    one_year_return: float | None,
    sgov_one_year_return: float | None,
    is_etf: bool,
) -> int:
    if not is_etf:
        return risk_rating
    if one_year_return is None or sgov_one_year_return is None:
        return risk_rating
    if sgov_one_year_return <= 0:
        return risk_rating

    required_risk_rating = math.ceil(abs(one_year_return / sgov_one_year_return))
    required_risk_rating = max(1, min(5, required_risk_rating))
    return max(risk_rating, required_risk_rating)


def _estimate_certainty_score(risk_rating: int, horizon: str) -> int:
    base = 6 - int(risk_rating)
    if horizon == "1y":
        base -= 1
    elif horizon == "8y":
        base += 1
    return max(1, min(5, base))


def _is_non_short_duration_bond(asset_class: str) -> bool:
    text = _as_text(asset_class).strip().lower()
    if not text:
        return False

    is_bond_like = ("bond" in text) or ("government" in text)
    is_short_duration = ("short" in text) or (text in {"moneymarket", "money market"})
    return is_bond_like and not is_short_duration


def _apply_certainty_caps(
    certainty_1y_score: int,
    certainty_3y_score: int,
    risk_rating: int,
    asset_class: str,
) -> tuple[int, int]:
    cap = None
    if _is_non_short_duration_bond(asset_class):
        cap = 3
    if int(risk_rating) > 2:
        cap = 3 if cap is None else min(cap, 3)
    if cap is None:
        return certainty_1y_score, certainty_3y_score

    return min(certainty_1y_score, cap), min(certainty_3y_score, cap)


def _estimate_liquidity_score(info: dict[str, Any]) -> int:
    volume = _as_float(
        info.get("averageVolume")
        or info.get("averageDailyVolume10Day")
        or info.get("averageVolume10days")
    )
    if volume is None:
        return 3
    if volume >= 5_000_000:
        return 5
    if volume >= 1_000_000:
        return 4
    if volume >= 200_000:
        return 3
    if volume >= 50_000:
        return 2
    return 1


def _period_to_months(period: str) -> int:
    text = str(period).strip().lower()
    if text.endswith("mo"):
        return int(text[:-2])
    if text.endswith("m"):
        return int(text[:-1])
    if text.endswith("y"):
        return int(text[:-1]) * 12
    return 0


def _as_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        number = float(value)
        if not math.isfinite(number):
            return None
        return number
    except Exception:
        return None


def _is_blank_or_zero(value: float | None, tolerance: float = 1e-9) -> bool:
    if value is None:
        return True
    return abs(float(value)) <= tolerance


def _round_or_blank(value: float | None, digits: int = 2) -> str:
    if value is None:
        return ""
    rounded = round(float(value), digits)
    return f"{rounded:.{digits}f}"


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _pick_name(info: dict[str, Any], preference: str) -> str:
    long_name = _as_text(info.get("longName")).strip()
    short_name = _as_text(info.get("shortName")).strip()

    if preference == "short":
        return short_name or long_name
    return long_name or short_name


def _normalize_metric_name(value: str) -> str:
    text = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    if text == "price_ihr20":
        return "price_ihr_20"
    if text == "price_ihr80":
        return "price_ihr_80"
    return text


def _metric_column_name(metric: str, period: str) -> str:
    if metric == "return":
        return f"{period}_return"
    if metric == "cagr":
        return f"{period}_cagr"
    if metric == "calmar_ratio":
        return f"{period}_calmar_ratio"
    if metric == "max_drawdown":
        return f"{period}_max_drawdown"
    if metric == "price_ihr_20":
        return f"price_{period}_IHR_20"
    if metric == "price_ihr_80":
        return f"price_{period}_IHR_80"
    raise ValueError(f"Unsupported metric '{metric}'")
