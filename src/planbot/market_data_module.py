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


class MarketDataConfig(BaseModel):
    output_filename: str = "selected_etf.csv"
    frequency: str = "1w"
    periods: list[str] = Field(default_factory=lambda: list(DEFAULT_PERIODS))
    tickers: list[str] = Field(default_factory=list)

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
        if not cleaned:
            raise ValueError("tickers cannot be empty")
        return cleaned


@dataclass
class PeriodMetrics:
    period_return: float | None
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
) -> Path:
    """Generate a single-table CSV market dataset for the provided Yahoo tickers."""
    del metrics  # Reserved for future extension.

    normalized_tickers = [str(item).strip().upper() for item in tickers if str(item).strip()]
    if not normalized_tickers:
        raise ValueError("tickers cannot be empty")

    normalized_frequency = str(frequency).strip().lower()
    if normalized_frequency not in SUPPORTED_FREQUENCIES:
        raise ValueError(
            f"Unsupported frequency '{frequency}'. Supported: {sorted(SUPPORTED_FREQUENCIES)}"
        )
    interval = SUPPORTED_FREQUENCIES[normalized_frequency]

    normalized_periods = [str(item).strip().lower() for item in (periods or DEFAULT_PERIODS) if str(item).strip()]
    if not normalized_periods:
        raise ValueError("periods cannot be empty")

    output_path = _resolve_output_path(output_filename=output_filename, output_dir=Path(output_dir))
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = _build_fieldnames(normalized_periods)
    yf = _import_yfinance()

    rows: list[dict[str, Any]] = []
    for symbol in normalized_tickers:
        ticker_obj = yf.Ticker(symbol)
        info = _safe_to_dict(getattr(ticker_obj, "info", {}) or {})

        row: dict[str, Any] = {
            "ticker": symbol,
            "asset_class": _as_text(info.get("quoteType") or info.get("category")),
            "name": _as_text(info.get("shortName") or info.get("longName")),
            "currency": _as_text(info.get("currency")),
            "last_update_date": "",
            "last_closing_price": "",
        }

        period_results: dict[str, PeriodMetrics] = {}
        latest_row = None

        for period in normalized_periods:
            history = _history_to_rows(ticker_obj.history(period=_to_yfinance_period(period), interval=interval))
            period_metrics = _calculate_period_metrics(history)
            period_results[period] = period_metrics

            row[f"{period}_return"] = _round_or_blank(period_metrics.period_return)
            row[f"{period}_max_drawdown"] = _round_or_blank(period_metrics.max_drawdown)
            row[f"price_{period}_IHR_20"] = _round_or_blank(period_metrics.ihr20)
            row[f"price_{period}_IHR_80"] = _round_or_blank(period_metrics.ihr80)

            if latest_row is None and history:
                latest_row = history[0]

        if latest_row:
            row["last_update_date"] = str(latest_row.get("date") or "")
            row["last_closing_price"] = _round_or_blank(_as_float(latest_row.get("close")))

        risk_rating = _estimate_risk_rating(period_results.get("1y"), period_results)
        expected_return_score = _estimate_expected_return_score(period_results.get("1y"))

        row["risk_rating"] = _round_or_blank(float(risk_rating))
        row["expected_return_score"] = _round_or_blank(float(expected_return_score))
        row["certainty_1y_score"] = _round_or_blank(float(_estimate_certainty_score(risk_rating, horizon="1y")))
        row["certainty_3y_score"] = _round_or_blank(float(_estimate_certainty_score(risk_rating, horizon="3y")))
        row["certainty_8y_score"] = _round_or_blank(float(_estimate_certainty_score(risk_rating, horizon="8y")))
        row["liquidity_score"] = _round_or_blank(float(_estimate_liquidity_score(info)))

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
    config_path: str | Path = "config/config_marketdata.yaml",
    output_dir: str | Path = "data/planbot/shared/product_catalog",
) -> Path:
    cfg = load_market_data_config(config_path)
    configured_or_overridden_tickers = tickers if tickers is not None else cfg.tickers
    return get_market_data(
        tickers=configured_or_overridden_tickers,
        output_filename=cfg.output_filename,
        frequency=cfg.frequency,
        periods=cfg.periods,
        output_dir=output_dir,
    )


def _import_yfinance() -> Any:
    try:
        import yfinance as yf
    except ImportError as exc:  # pragma: no cover - import guard
        raise RuntimeError("yfinance dependency is missing. Install it with: uv pip install yfinance") from exc
    return yf


def _build_fieldnames(periods: list[str]) -> list[str]:
    base = [
        "ticker",
        "asset_class",
        "name",
        "currency",
        "last_update_date",
        "last_closing_price",
    ]
    dynamic: list[str] = []
    for period in periods:
        dynamic.extend(
            [
                f"{period}_return",
                f"{period}_max_drawdown",
                f"price_{period}_IHR_20",
                f"price_{period}_IHR_80",
            ]
        )

    tail = [
        "risk_rating",
        "expected_return_score",
        "certainty_1y_score",
        "certainty_3y_score",
        "certainty_8y_score",
        "liquidity_score",
    ]
    return base + dynamic + tail


def _resolve_output_path(output_filename: str, output_dir: Path) -> Path:
    candidate = Path(output_filename)
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
        return PeriodMetrics(period_return=None, max_drawdown=None, ihr20=None, ihr80=None)

    closes_new_to_old = [float(item["close"]) for item in history_rows]
    closes = list(reversed(closes_new_to_old))

    first_close = closes[0]
    last_close = closes[-1]
    if first_close <= 0:
        period_return = None
    else:
        period_return = ((last_close / first_close) - 1.0) * 100.0

    max_drawdown = _max_drawdown_pct(closes)
    ihr20 = _percentile(closes, 0.2)
    ihr80 = _percentile(closes, 0.8)

    return PeriodMetrics(
        period_return=period_return,
        max_drawdown=max_drawdown,
        ihr20=ihr20,
        ihr80=ihr80,
    )


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


def _estimate_expected_return_score(one_year_metrics: PeriodMetrics | None) -> int:
    period_return = one_year_metrics.period_return if one_year_metrics else None
    if period_return is None:
        return 3
    if period_return <= 0:
        return 1
    if period_return <= 5:
        return 2
    if period_return <= 12:
        return 3
    if period_return <= 20:
        return 4
    return 5


def _estimate_certainty_score(risk_rating: int, horizon: str) -> int:
    base = 6 - int(risk_rating)
    if horizon == "1y":
        base -= 1
    elif horizon == "8y":
        base += 1
    return max(1, min(5, base))


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


def _round_or_blank(value: float | None, digits: int = 2) -> str:
    if value is None:
        return ""
    rounded = round(float(value), digits)
    return f"{rounded:.{digits}f}"


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)
