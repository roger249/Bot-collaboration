"""
One-shot seeder:  reads selected_etf.csv + Yahoo Finance + otc_products.md
and populates data/planbot/db/planbot.duckdb (products table; coexists with clients/holdings/profiles).

Usage:
    python -m src.test_data.product_catalog_seed
"""

from __future__ import annotations

import csv
import json
import re
import time
from pathlib import Path
from typing import Any


from src.test_data.product_catalog import (
    DB_PATH,
    get_conn,
    init_db,
    get_summary,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
CSV_PATH = Path("data/planbot/shared/product_catalog/selected_etf.csv")
OTC_PATH = Path("data/planbot/shared/product_catalog/otc_products.md")
YAHOO_CACHE_PATH = Path("runs/test_data/.yahoo_cache.json")

# ---------------------------------------------------------------------------
# Classification helpers
# ---------------------------------------------------------------------------

# Tickers we explicitly know are money-market funds
MONEY_MARKET_TICKERS = frozenset({"VMRXX", "FZDXX", "SPAXX"})

# Asset-class values that indicate a single stock (not a fund/ETF)
STOCK_ASSET_CLASSES = frozenset({"EQUITY"})

# Asset-class values that are out of scope for fund/stock seeding
EXCLUDE_ASSET_CLASSES = frozenset({
    "CURRENCY", "CRYPTOCURRENCY", "INDEX",
})

# Keywords in asset_class or name that indicate a bond fund
BOND_KEYWORDS = [
    "bond", "treasury", "t-bill", "government", "floating rate",
    "money market", "ultrashort", "short-term", "short duration",
    "corporate", "high yield", "bank loan", "convertible",
    "emerging market", "emerging-markets",
]


def is_money_market(row: dict) -> bool:
    return row["ticker"] in MONEY_MARKET_TICKERS


def is_bond_fund(row: dict) -> bool:
    """Heuristic: asset_class or name contains bond-like keywords."""
    if is_money_market(row):
        return False
    text = f"{row.get('asset_class', '')} {row.get('name', '')}".lower()
    return any(kw in text for kw in BOND_KEYWORDS)


def is_equity_etf(row: dict) -> bool:
    """Everything in CSV that is not MM, not bond, not a single stock/currency/crypto."""
    ac = row.get("asset_class", "").strip()
    if ac in EXCLUDE_ASSET_CLASSES or ac in STOCK_ASSET_CLASSES:
        return False
    if is_money_market(row) or is_bond_fund(row):
        return False
    return True


def is_stock(row: dict) -> bool:
    """Single stock ticker from CSV."""
    ac = row.get("asset_class", "").strip()
    return ac in STOCK_ASSET_CLASSES


def classify_row(row: dict) -> str | None:
    """Return product_type or None if this row should be skipped."""
    if is_money_market(row):
        return "money_market_fund"
    if is_bond_fund(row):
        return "bond_fund"
    if is_equity_etf(row):
        return "equity_fund"
    if is_stock(row):
        return "stock"
    return None  # FX, crypto, etc.


# ---------------------------------------------------------------------------
# Performance history extraction from CSV
# ---------------------------------------------------------------------------

PERF_PERIODS = ["6m", "1y", "3y", "5y", "10y"]
PERF_METRICS = ["return", "cagr", "max_drawdown", "calmar_ratio",
                "downside_risk", "volatility"]


def extract_performance_history(row: dict) -> dict:
    """Parse CSV columns into {period: {metric: value, ...}, ...}."""
    perf: dict[str, dict[str, float | None]] = {}
    for period in PERF_PERIODS:
        entry: dict[str, float | None] = {}
        for metric in PERF_METRICS:
            col_name = f"{period}_{metric}"
            if col_name in row and row[col_name]:
                try:
                    entry[metric] = float(row[col_name])
                except (ValueError, TypeError):
                    entry[metric] = None
            else:
                entry[metric] = None
        perf[period] = entry
    return perf


# ---------------------------------------------------------------------------
# Yahoo Finance enrichment (with disk cache)
# ---------------------------------------------------------------------------


def _load_yahoo_cache() -> dict:
    if YAHOO_CACHE_PATH.exists():
        return json.loads(YAHOO_CACHE_PATH.read_text(encoding="utf-8"))
    return {}


def _save_yahoo_cache(cache: dict) -> None:
    YAHOO_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    YAHOO_CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _fetch_yahoo_info(ticker: str, cache: dict) -> dict[str, Any]:
    """Fetch yfinance.Ticker(symbol).info, with disk cache."""
    ticker_key = ticker.upper()
    if ticker_key in cache:
        return cache[ticker_key]

    try:
        import yfinance as yf
    except ImportError:
        print(f"  [WARN] yfinance not installed — skipping Yahoo enrichment for {ticker}")
        return {}

    try:
        t = yf.Ticker(ticker_key)
        info = t.info
        if info and isinstance(info, dict):
            # Keep only the fields we actually use
            slim = {
                k: info.get(k)
                for k in (
                    "longBusinessSummary", "shortName", "longName",
                    "fundFamily", "category", "navPrice", "totalAssets",
                    "annualReportExpenseRatio", "yield", "morningStarRiskRating",
                    "isin", "exchange", "country", "quoteType",
                    "marketCap", "dividendYield", "industry", "sector",
                )
            }
            cache[ticker_key] = slim
            print(f"  [YAHOO] fetched {ticker}")
            time.sleep(0.3)  # be polite to Yahoo
            return slim
    except Exception as exc:
        print(f"  [YAHOO] error for {ticker}: {exc}")
        cache[ticker_key] = {}

    return {}


# ---------------------------------------------------------------------------
# Synthesise type-specific fields when Yahoo data is missing
# ---------------------------------------------------------------------------


def _synthesize_money_market(row: dict, yahoo: dict) -> dict:
    nav = yahoo.get("navPrice", 1.0)
    # Guess yield type and credit quality from name
    name = row.get("name", "").lower()
    if "government" in name or "treasury" in name:
        credit = "government"
    elif "prime" in name or "federal" in name:
        credit = "prime"
    else:
        credit = "government"

    if "cash reserves" in name:
        maturity = "ultra_short"
    else:
        maturity = "ultra_short"

    return {
        "nav": nav if nav else 1.0,
        "yield_type": "current",
        "credit_quality": credit,
        "maturity_profile": maturity,
        "dividend_treatment": "distributing",
    }


def _synthesize_bond_fund(row: dict, yahoo: dict) -> dict:
    name = row.get("name", "")
    provider = yahoo.get("fundFamily") or _infer_provider(name)
    nav = yahoo.get("navPrice")
    expense = yahoo.get("annualReportExpenseRatio")
    summary = yahoo.get("longBusinessSummary") or f"{name}. Category: {row.get('asset_class', '')}."
    aum = yahoo.get("totalAssets")

    # Domicile heuristic
    ticker = row.get("ticker", "")
    if ticker.endswith(".HK"):
        domicile = "HK"
    elif provider and "iShares" in provider:
        domicile = "IE" if "iShares" in provider else "US"
    elif provider and "Vanguard" in provider:
        domicile = "US"
    elif provider and "State Street" in provider:
        domicile = "US"
    else:
        domicile = "US"

    # Use expected_return (3y CAGR) as proxy for YTM
    ytm = row.get("expected_return")
    if ytm is not None:
        try:
            ytm = float(ytm) / 100.0 if float(ytm) > 1 else float(ytm)
        except (ValueError, TypeError):
            ytm = None

    return {
        "provider": provider,
        "nav": round(nav, 4) if nav else None,
        "expense_ratio": round(expense, 4) if expense else None,
        "share_class": "institutional",
        "strategy_summary": summary,
        "dividend_frequency": "monthly",
        "aum": round(aum, 0) if aum else None,
        "strategy": "income",
        "theme": None,
        "domicile": domicile,
        "rebalancing_frequency": "monthly",
        "dividend_treatment": "distributing",
        "ytm": ytm,
        "yield_to_worst": None,
        "effective_duration": None,
        "option_adjusted_spread": None,
        "weighted_average_duration": None,
        "weighted_average_coupon": None,
    }


def _synthesize_equity_fund(row: dict, yahoo: dict) -> dict:
    name = row.get("name", "")
    provider = yahoo.get("fundFamily") or _infer_provider(name)
    nav = yahoo.get("navPrice")
    summary = yahoo.get("longBusinessSummary") or f"{name}. Category: {row.get('asset_class', '')}."
    ter = yahoo.get("annualReportExpenseRatio")
    aum = yahoo.get("totalAssets")

    ticker = row.get("ticker", "")
    if ticker.endswith(".HK"):
        domicile = "HK"
    elif provider and "iShares" in provider:
        domicile = "IE"
    else:
        domicile = "US"

    return {
        "provider": provider,
        "nav": round(nav, 4) if nav else None,
        "strategy_summary": summary,
        "replication_method": "physical",
        "ter": round(ter, 4) if ter else None,
        "domicile": domicile,
        "aum": round(aum, 0) if aum else None,
        "dividend_treatment": "distributing",
        "dividend_frequency": "quarterly",
    }


def _infer_provider(name: str) -> str | None:
    """Guess provider from fund name."""
    name_lower = name.lower()
    if "ishares" in name_lower:
        return "iShares"
    if "vanguard" in name_lower:
        return "Vanguard"
    if "state street" in name_lower or name.startswith("State Street"):
        return "State Street SPDR"
    if "spdr" in name_lower:
        return "State Street SPDR"
    if "invesco" in name_lower:
        return "Invesco"
    if "fidelity" in name_lower:
        return "Fidelity"
    if "jpmorgan" in name_lower or "jp morgan" in name_lower:
        return "JPMorgan"
    if "vaneck" in name_lower:
        return "VanEck"
    if "csi" in name_lower or "csop" in name_lower:
        return "CSOP"
    if "chinaamc" in name_lower:
        return "ChinaAMC"
    if "hang seng" in name_lower:
        return "Hang Seng"
    if "tracker fund" in name_lower:
        return "State Street SPDR"
    return None


def _infer_region(ticker: str, asset_class: str) -> str | None:
    if ticker.endswith(".HK"):
        return "APAC"
    # US tickers (no suffix) are North America / Global
    if not re.search(r"\.[A-Z]{2}$", ticker):
        if "emerging" in asset_class.lower():
            return "EM"
        return "US"
    return None


def _infer_vehicle(product_type: str) -> str:
    if product_type in ("money_market_fund", "bond_fund", "equity_fund"):
        return "ETF"
    if product_type == "balanced_fund":
        return "Mutual Fund"
    if product_type == "stock":
        return "Direct"
    if product_type == "bond":
        return "Direct"
    return "ETF"


# ---------------------------------------------------------------------------
# Synthesise: stock (individual equity)
# ---------------------------------------------------------------------------


def _synthesize_stock(row: dict, yahoo: dict) -> dict:
    ticker = row.get("ticker", "")
    exchange = yahoo.get("exchange") or _infer_exchange(ticker)
    market_cap = yahoo.get("marketCap")
    dividend_yield = yahoo.get("dividendYield")
    industry = yahoo.get("industry") or row.get("asset_class", "")

    return {
        "company_name": row.get("name", ""),
        "industry": industry if industry and industry != "EQUITY" else None,
        "exchange": exchange,
        "lot_size": 100 if ticker.endswith(".HK") else 1,
        "market_cap": round(market_cap, 0) if market_cap else None,
        "dividend_paying": (dividend_yield is not None and dividend_yield > 0),
        "dividend_yield": round(dividend_yield, 4) if dividend_yield else None,
    }


def _infer_exchange(ticker: str) -> str | None:
    if ticker.endswith(".HK"):
        return "HKEX"
    # US stocks (no suffix)
    if not re.search(r"\.[A-Z]{2}$", ticker):
        return "NYSE/NASDAQ"
    if ticker.endswith(".SZ"):
        return "SZSE"
    return None


def _synthesize_bond(otc: dict) -> dict:
    """Return type_specific dict for an individual bond."""
    coupon_str = otc.get("couponRate", "").replace("%", "").strip()
    coupon_rate = None
    try:
        coupon_rate = float(coupon_str) / 100.0
    except (ValueError, TypeError):
        pass

    coupon_str_lower = otc.get("couponRate", "").lower()
    coupon_type = "floating" if ("libor" in coupon_str_lower or "sofr" in coupon_str_lower) else "fixed"

    return {
        "issuer_name": otc.get("issuer"),
        "issuer_sector": _map_bond_sector(otc.get("sector", "")),
        "issuer_country": None,
        "coupon_type": coupon_type,
        "coupon_rate": coupon_rate,
        "coupon_frequency": "semi-annual",
        "day_count_convention": "thirty_360",
        "credit_rating": otc.get("bondRating"),
        "maturity": otc.get("maturity", otc.get("term")),
        "seniority": "senior",
        "callable": False,
        "puttable": False,
        "convertible": "convertible" in otc.get("name", "").lower(),
        "green_bond": "green" in otc.get("name", "").lower(),
        "sukuk": False,
    }


def _map_bond_sector(sector: str) -> str | None:
    sector_lower = sector.lower()
    if "government" in sector_lower:
        return "government"
    if "corporate" in sector_lower:
        return "corporate"
    if "municipal" in sector_lower:
        return "municipal"
    if "financial" in sector_lower:
        return "corporate"
    return "corporate"


# ---------------------------------------------------------------------------
# OTC parsers (shared)
# ---------------------------------------------------------------------------


def _parse_otc_table(section_header: str) -> list[dict]:
    """Generic parser for any Markdown table section in otc_products.md."""
    text = OTC_PATH.read_text(encoding="utf-8")
    m = re.search(rf"## {section_header}[^\n]*\n(.*?)(?=\n## |\n---|\Z)", text, re.DOTALL)
    if not m:
        return []
    lines = m.group(1).strip().split("\n")
    headers, data_start = [], None
    for i, line in enumerate(lines):
        line = line.strip()
        if line.startswith("|") and "id" in line.lower():
            headers = [h.strip() for h in line.split("|")[1:-1]]
            data_start = i + 2
            break
    if data_start is None:
        return []
    rows = []
    for line in lines[data_start:]:
        line = line.strip()
        if not line.startswith("|"):
            break
        cells = [c.strip() for c in line.split("|")[1:-1]]
        if len(cells) == len(headers):
            rows.append(dict(zip(headers, cells)))
    return rows


def _parse_all_otc_funds() -> list[dict]:
    """Return all fund rows from otc_products.md."""
    return _parse_otc_table("Fund")


def _classify_otc_fund(row: dict) -> str:
    """Classify an OTC fund row as 'balanced_fund' or 'equity_fund'."""
    name = row.get("name", "").lower()
    sector = row.get("sector", "").lower()
    is_balanced = (
        "balanced" in sector or "balanced" in name
        or "multi-asset" in sector or "multi-asset" in name
    )
    is_conservative_income = (
        "conservative" in sector or "conservative" in name
    ) and "income" in name
    if is_balanced or is_conservative_income:
        return "balanced_fund"
    return "equity_fund"


def _parse_otc_bonds() -> list[dict]:
    return _parse_otc_table("Bond")


def _otc_to_general(row: dict, product_type: str, vehicle: str) -> dict:
    """Build the general columns dict from an OTC row."""
    ret = row.get("expectedReturn", "")
    try:
        ret = float(str(ret).replace("%", "").strip())
    except (ValueError, TypeError):
        ret = None
    return {
        "product_id": row.get("id", ""),
        "isin": None,
        "name": row.get("name", ""),
        "ticker": None,
        "trading_currency": "USD",
        "risk_rating": int(row.get("riskLevel", "2")),
        "expected_return": ret,
        "region": None,
        "country": None,
        "sector": row.get("sector", ""),
        "remarks": f"OTC {product_type}. Rating: {row.get('rating', 'N/A')}/5.",
        "product_type": product_type,
        "vehicle": vehicle,
        "type_specific": None,
        "performance_history": json.dumps({}),
    }


def _synthesize_balanced_fund(otc: dict) -> dict:
    """Return type_specific dict for a balanced fund."""
    name = otc.get("name", "")
    name_lower = name.lower()
    has_growth = "growth" in name_lower
    has_income = "income" in name_lower
    has_conservative = "conservative" in name_lower

    if has_conservative or (has_income and not has_growth):
        eq, fi, ca, al = 0.25, 0.65, 0.05, 0.05
        risk, style = "conservative", "income"
    elif has_growth and not has_income:
        eq, fi, ca, al = 0.60, 0.30, 0.05, 0.05
        risk, style = "moderate", "growth"
    elif has_growth and has_income:
        eq, fi, ca, al = 0.50, 0.38, 0.07, 0.05
        risk, style = "moderate", "balanced"
    else:
        eq, fi, ca, al = 0.50, 0.38, 0.07, 0.05
        risk, style = "moderate", "balanced"

    ret = otc.get("expectedReturn", "")
    try:
        ret = float(str(ret).replace("%", "").strip())
    except (ValueError, TypeError):
        ret = ""

    return {
        "provider": "Bank Internal",
        "nav": None,
        "strategy_summary": (
            f"{name}. A {risk} multi-asset portfolio targeting "
            f"{ret}% annual return with {eq:.0%} equity / "
            f"{fi:.0%} fixed income allocation. "
            f"Risk rating {otc.get('riskLevel','N/A')}/5."
        ),
        "equity_exposure": round(eq, 2),
        "fixed_income_exposure": round(fi, 2),
        "cash_exposure": round(ca, 2),
        "alternative_exposure": round(al, 2),
        "investment_style": style,
        "risk_profile": risk,
        "dividend_treatment": "distributing",
    }


def _synth_otc_equity_fund(otc: dict) -> dict:
    """Return type_specific dict for an OTC equity mutual fund."""
    name = otc.get("name", "")
    sector = otc.get("sector", "")
    aum_str = otc.get("fundAum", "").replace("$", "").replace(",", "")
    aum = None
    try:
        aum = float(aum_str.replace("M", "")) * 1_000_000 if "M" in aum_str else None
    except (ValueError, TypeError):
        pass
    mgmt_fee = otc.get("managementFee", "").replace("%", "")
    ter = None
    try:
        ter = float(mgmt_fee) / 100.0
    except (ValueError, TypeError):
        pass

    return {
        "provider": "Bank Internal",
        "nav": None,
        "strategy_summary": (
            f"{name}. OTC mutual fund focused on {sector}. "
            f"AUM: {otc.get('fundAum', 'N/A')}. "
            f"Mgmt fee: {otc.get('managementFee', 'N/A')}. "
            f"Risk rating {otc.get('riskLevel', 'N/A')}/5."
        ),
        "replication_method": None,
        "ter": round(ter, 4) if ter else None,
        "domicile": None,
        "aum": round(aum, 0) if aum else None,
        "dividend_treatment": "distributing",
        "dividend_frequency": "annual",
    }


# ---------------------------------------------------------------------------
# Main seeder
# ---------------------------------------------------------------------------

DDL_COLUMNS = [
    "product_id", "isin", "name", "ticker", "trading_currency",
    "risk_rating", "expected_return", "region", "country", "sector",
    "remarks", "product_type", "vehicle", "type_specific", "performance_history",
]


def seed(use_yahoo: bool = True) -> None:
    """Main entry point: read CSV + OTC, enrich, insert single-table into DuckDB."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = get_conn(read_only=False)
    init_db(conn)

    # Clear products table only (not clients/holdings/profiles)
    conn.execute("DELETE FROM products")
    yahoo_cache = _load_yahoo_cache() if use_yahoo else {}
    counts: dict[str, int] = {}

    # ================================================================
    # 1. CSV products
    # ================================================================
    with open(CSV_PATH, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            pt = classify_row(row)
            if pt is None:
                continue
            ticker = row.get("ticker", "").strip()
            asset_class = row.get("asset_class", "")
            product_id = f"STOCK-{ticker}" if pt == "stock" else f"ETF-{ticker}"

            yahoo = _fetch_yahoo_info(ticker, yahoo_cache) if (use_yahoo and ticker) else {}

            # Synthesise type-specific dict
            if pt == "money_market_fund":
                ts = _synthesize_money_market(row, yahoo)
            elif pt == "bond_fund":
                ts = _synthesize_bond_fund(row, yahoo)
            elif pt == "equity_fund":
                ts = _synthesize_equity_fund(row, yahoo)
            elif pt == "stock":
                ts = _synthesize_stock(row, yahoo)
            else:
                continue

            perf = extract_performance_history(row)

            row_data = {
                "product_id": product_id,
                "isin": yahoo.get("isin"),
                "name": yahoo.get("longName") or yahoo.get("shortName") or row.get("name", ""),
                "ticker": ticker,
                "trading_currency": row.get("currency", "USD"),
                "risk_rating": int(row.get("risk_rating", "3")),
                "expected_return": float(row["expected_return"]) if row.get("expected_return") else None,
                "region": _infer_region(ticker, asset_class),
                "country": yahoo.get("country"),
                "sector": asset_class,
                "remarks": yahoo.get("longBusinessSummary"),
                "product_type": pt,
                "vehicle": _infer_vehicle(pt),
                "type_specific": json.dumps(ts, ensure_ascii=False),
                "performance_history": json.dumps(perf, ensure_ascii=False),
            }
            conn.execute(
                "INSERT OR REPLACE INTO products VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [row_data[k] for k in DDL_COLUMNS],
            )
            counts[pt] = counts.get(pt, 0) + 1

    if use_yahoo:
        _save_yahoo_cache(yahoo_cache)

    # ================================================================
    # 2. OTC: all fund types (balanced_fund + equity_fund)
    # ================================================================
    for otc in _parse_all_otc_funds():
        pt = _classify_otc_fund(otc)
        g = _otc_to_general(otc, pt, "Mutual Fund")
        if pt == "balanced_fund":
            g["type_specific"] = json.dumps(_synthesize_balanced_fund(otc), ensure_ascii=False)
        else:
            g["type_specific"] = json.dumps(_synth_otc_equity_fund(otc), ensure_ascii=False)
        g["performance_history"] = json.dumps({})
        conn.execute(
            "INSERT OR REPLACE INTO products VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [g[k] for k in DDL_COLUMNS],
        )
        counts[pt] = counts.get(pt, 0) + 1

    # ================================================================
    # 3. OTC: individual bonds
    # ================================================================
    for otc in _parse_otc_bonds():
        g = _otc_to_general(otc, "bond", "Direct")
        g["type_specific"] = json.dumps(_synthesize_bond(otc), ensure_ascii=False)
        g["performance_history"] = json.dumps({})
        conn.execute(
            "INSERT OR REPLACE INTO products VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [g[k] for k in DDL_COLUMNS],
        )
        counts["bond"] = counts.get("bond", 0) + 1

    conn.close()

    print()
    print("=" * 50)
    print("SEED COMPLETE")
    for pt in sorted(counts, key=counts.get, reverse=True):
        print(f"  {pt:25s}: {counts[pt]}")
    print(f"  {'TOTAL':25s}: {sum(counts.values())}")
    print(f"  Database: {DB_PATH.resolve()}")
    if use_yahoo:
        print(f"  Yahoo cache: {YAHOO_CACHE_PATH.resolve()}  ({len(yahoo_cache)} entries)")
    print("=" * 50)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    seed(use_yahoo=True)
