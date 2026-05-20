from __future__ import annotations

import csv
import io
import json
import math
from datetime import datetime, timezone
from typing import Any
import urllib.parse
import urllib.request

from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class YFinanceInput(BaseModel):
    """Input for YFinance fundamentals and quote lookup."""

    ticker: str = Field(..., description="Stock ticker symbol, for example AAPL or 0700.HK")
    period: str = Field(
        default="1y",
        description="Price history period used for quote context, for example 6mo, 1y, 2y, 5y",
    )
    interval: str = Field(
        default="1d",
        description="Price history interval, for example 1d, 1wk, 1mo",
    )
    output_format: str = Field(
        default="json",
        description="Output format: json (default) or csv",
    )
    include_quote_summary: bool = Field(
        default=False,
        description=(
            "If true, also fetch Yahoo quoteSummary modules "
            "(defaultKeyStatistics, financialData, summaryDetail, price) and merge key fields"
        ),
    )

    include_price_history: bool = Field(
        default=True,
        description="If true (default), include full price history as 'price_history' in output. Set false to omit."
    )


class YFinanceTool(BaseTool):
    name: str = "YFinance"
    description: str = (
        "Fetch stock fundamentals and quote snapshot using yfinance. "
        "Returns normalized JSON or CSV with income_statement, historical_financial_ratios, and quote fields."
    )
    args_schema: type[BaseModel] = YFinanceInput
    max_output_chars: int = 16_000

    def _run(
        self,
        ticker: str,
        period: str = "1y",
        interval: str = "1d",
        output_format: str = "json",
        include_quote_summary: bool = False,
        include_price_history: bool = True,
    ) -> str:
        symbol = str(ticker).strip().upper()
        if not symbol:
            raise ValueError("YFinance requires a non-empty ticker symbol.")

        normalized_format = str(output_format).strip().lower()
        if normalized_format not in {"json", "csv"}:
            raise ValueError("YFinance output_format must be either 'json' or 'csv'.")

        yf = _import_yfinance()
        ticker_obj = yf.Ticker(symbol)

        info: dict[str, Any] = _safe_to_dict(getattr(ticker_obj, "info", {}) or {})
        income_stmt = _safe_dataframe_to_records(getattr(ticker_obj, "income_stmt", None))
        quarterly_income_stmt = _safe_dataframe_to_records(getattr(ticker_obj, "quarterly_income_stmt", None))

        history = _safe_dataframe_to_records(ticker_obj.history(period=period, interval=interval))

        payload = {
            "ticker": symbol,
            "as_of_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "income_statement": {
                "annual": income_stmt,
                "quarterly": quarterly_income_stmt,
            },
            "historical_financial_ratios": _build_historical_ratios(quarterly_income_stmt),
            "quote": _build_quote_snapshot(info=info, history=history),
        }
        if include_price_history:
            payload["price_history"] = history

        if include_quote_summary:
            quote_summary = _fetch_quote_summary(
                symbol,
                modules=["defaultKeyStatistics", "financialData", "summaryDetail", "price"],
            )
            if quote_summary:
                payload["quote_summary"] = quote_summary
                payload["quote"] = _merge_quote_with_summary(payload["quote"], quote_summary)

        payload = _sanitize_for_llm(payload)

        if normalized_format == "csv":
            text = _payload_to_csv(payload)
        else:
            text = json.dumps(payload, ensure_ascii=False, default=str, allow_nan=False)

        if self.max_output_chars > 0 and len(text) > self.max_output_chars:
            omitted = len(text) - self.max_output_chars
            return f"{text[: self.max_output_chars]}... [truncated {omitted} chars]"
        return text


def _import_yfinance() -> Any:
    try:
        import yfinance as yf
    except ImportError as exc:  # pragma: no cover - import guard
        raise RuntimeError("yfinance dependency is missing. Install it with: uv pip install yfinance") from exc
    return yf


def _safe_to_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_dataframe_to_records(frame: Any) -> list[dict[str, Any]]:
    if frame is None:
        return []

    to_dict = getattr(frame, "to_dict", None)
    if not callable(to_dict):
        return []

    try:
        raw = to_dict(orient="index")
    except TypeError:
        try:
            raw = to_dict()
        except Exception:
            return []
    except Exception:
        return []

    if not isinstance(raw, dict):
        return []

    rows: list[dict[str, Any]] = []
    for period_key, metrics in raw.items():
        row: dict[str, Any] = {"period": str(period_key)}
        if isinstance(metrics, dict):
            for key, value in metrics.items():
                row[str(key)] = _to_number_if_possible(value)
        rows.append(row)

    rows.sort(key=lambda item: item.get("period", ""), reverse=True)
    return rows


def _to_number_if_possible(value: Any) -> Any:
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            return None
        return value
    try:
        # Pandas scalar types can be converted this way while preserving JSON safety.
        converted = float(value)
        if converted.is_integer():
            return int(converted)
        return converted
    except Exception:
        return value


def _build_historical_ratios(quarterly_income_stmt: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in quarterly_income_stmt:
        revenue = _as_float(row.get("Total Revenue"))
        gross_profit = _as_float(row.get("Gross Profit"))
        operating_income = _as_float(row.get("Operating Income"))
        net_income = _as_float(row.get("Net Income"))

        rows.append(
            {
                "period": row.get("period"),
                "gross_margin_pct": _ratio_percent(gross_profit, revenue),
                "operating_margin_pct": _ratio_percent(operating_income, revenue),
                "net_margin_pct": _ratio_percent(net_income, revenue),
            }
        )

    return rows


def _build_quote_snapshot(info: dict[str, Any], history: list[dict[str, Any]]) -> dict[str, Any]:
    current_price = _first_non_null(
        info.get("currentPrice"),
        info.get("regularMarketPrice"),
        _latest_price_from_history(history),
    )
    trailing_pe = _first_non_null(info.get("trailingPE"), info.get("forwardPE"))
    price_to_sales = _first_non_null(info.get("priceToSalesTrailing12Months"), info.get("priceToSales"))

    return {
        "symbol": info.get("symbol"),
        "short_name": info.get("shortName"),
        "currency": info.get("currency"),
        "exchange": info.get("exchange"),
        "current_price": current_price,
        "previous_close": info.get("previousClose"),
        "market_cap": info.get("marketCap"),
        "trailing_pe": trailing_pe,
        "price_to_sales": price_to_sales,
        "quote_type": info.get("quoteType"),
    }


def _latest_price_from_history(history: list[dict[str, Any]]) -> Any:
    if not history:
        return None
    latest = history[0]
    return latest.get("Close") or latest.get("close")


def _as_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _ratio_percent(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return round((numerator / denominator) * 100, 4)


def _first_non_null(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _fetch_quote_summary(symbol: str, modules: list[str]) -> dict[str, Any]:
    base_url = f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{urllib.parse.quote(symbol)}"
    params = urllib.parse.urlencode({"modules": ",".join(modules)})
    url = f"{base_url}?{params}"
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})

    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            body = response.read().decode("utf-8")
        parsed = json.loads(body)
    except Exception:
        return {}

    result = parsed.get("quoteSummary", {}).get("result")
    if not isinstance(result, list) or not result:
        return {}

    module_payload = result[0]
    if not isinstance(module_payload, dict):
        return {}
    return _normalize_yahoo_value(module_payload)


def _normalize_yahoo_value(value: Any) -> Any:
    if isinstance(value, list):
        return [_normalize_yahoo_value(item) for item in value]

    if isinstance(value, dict):
        if "raw" in value:
            return _normalize_yahoo_value(value.get("raw"))
        return {str(key): _normalize_yahoo_value(item) for key, item in value.items()}

    return value


def _merge_quote_with_summary(base_quote: dict[str, Any], quote_summary: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base_quote)

    price = quote_summary.get("price", {}) if isinstance(quote_summary.get("price"), dict) else {}
    default_stats = (
        quote_summary.get("defaultKeyStatistics", {})
        if isinstance(quote_summary.get("defaultKeyStatistics"), dict)
        else {}
    )
    summary_detail = (
        quote_summary.get("summaryDetail", {}) if isinstance(quote_summary.get("summaryDetail"), dict) else {}
    )

    merged["symbol"] = _first_non_null(merged.get("symbol"), price.get("symbol"))
    merged["short_name"] = _first_non_null(merged.get("short_name"), price.get("shortName"), price.get("longName"))
    merged["currency"] = _first_non_null(merged.get("currency"), price.get("currency"))
    merged["exchange"] = _first_non_null(merged.get("exchange"), price.get("exchangeName"), price.get("exchange"))
    merged["current_price"] = _first_non_null(
        merged.get("current_price"),
        price.get("regularMarketPrice"),
        summary_detail.get("regularMarketPrice"),
    )
    merged["previous_close"] = _first_non_null(
        merged.get("previous_close"),
        summary_detail.get("previousClose"),
    )
    merged["market_cap"] = _first_non_null(merged.get("market_cap"), price.get("marketCap"))
    merged["trailing_pe"] = _first_non_null(
        merged.get("trailing_pe"),
        default_stats.get("trailingPE"),
        summary_detail.get("trailingPE"),
    )
    merged["price_to_sales"] = _first_non_null(
        merged.get("price_to_sales"),
        summary_detail.get("priceToSalesTrailing12Months"),
        default_stats.get("priceToSalesTrailing12Months"),
    )
    merged["quote_type"] = _first_non_null(merged.get("quote_type"), price.get("quoteType"))

    return merged


def _sanitize_for_llm(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _sanitize_for_llm(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_for_llm(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _payload_to_csv(payload: dict[str, Any]) -> str:
    sections: list[str] = []

    sections.append("# quote")
    sections.append(_dict_to_csv(payload.get("quote", {}), key_name="field", value_name="value"))

    sections.append("# historical_financial_ratios")
    sections.append(_records_to_csv(payload.get("historical_financial_ratios", [])))

    income = payload.get("income_statement", {}) if isinstance(payload.get("income_statement"), dict) else {}

    sections.append("# income_statement_annual")
    sections.append(_records_to_csv(income.get("annual", [])))

    sections.append("# income_statement_quarterly")
    sections.append(_records_to_csv(income.get("quarterly", [])))

    return "\n\n".join(sections)


def _dict_to_csv(data: dict[str, Any], key_name: str, value_name: str) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([key_name, value_name])
    for key, value in data.items():
        writer.writerow([key, value])
    return buffer.getvalue().strip()


def _records_to_csv(records: list[dict[str, Any]]) -> str:
    if not records:
        return ""

    field_order: list[str] = []
    field_set: set[str] = set()
    for record in records:
        for key in record.keys():
            if key not in field_set:
                field_set.add(key)
                field_order.append(key)

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=field_order, extrasaction="ignore")
    writer.writeheader()
    for record in records:
        writer.writerow(record)
    return buffer.getvalue().strip()