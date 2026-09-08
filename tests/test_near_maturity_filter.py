"""Unit tests for the near-maturity exclusion filter helpers.

These are pure-logic tests (no DuckDB / no I/O) covering:
  - ``add_business_days`` (weekend skipping)
  - ``filter_near_maturity`` (normal, boundary, weekend, no-maturity, invalid)
"""

from __future__ import annotations

from datetime import date

from src.planbot.client_enrichment import add_business_days, filter_near_maturity


def _bond(product_id: str, maturity: str | None) -> dict:
    ts = {"maturity": maturity} if maturity is not None else {}
    return {"product_id": product_id, "product_type": "bond", "type_specific": ts}


# ── add_business_days ─────────────────────────────────────────────────────


def test_add_business_days_weekday_advance():
    # 2026-09-09 is a Wednesday.
    assert add_business_days(date(2026, 9, 9), 1) == date(2026, 9, 10)  # Thu
    assert add_business_days(date(2026, 9, 9), 2) == date(2026, 9, 11)  # Fri
    assert add_business_days(date(2026, 9, 9), 3) == date(2026, 9, 14)  # Mon (skip weekend)


def test_add_business_days_skips_weekend():
    # Friday + 1 business day = Monday.
    assert add_business_days(date(2026, 9, 11), 1) == date(2026, 9, 14)
    # Saturday + 2 business days = Tuesday (skip Sat+Sun).
    assert add_business_days(date(2026, 9, 12), 2) == date(2026, 9, 15)


# ── filter_near_maturity — normal flow ────────────────────────────────────


def test_excludes_near_maturity_bond():
    # ref Wed 2026-09-09, default n=2 → cutoff Fri 2026-09-11.
    products = [
        _bond("BOND_MATURES_TOMORROW", "2026-09-10"),   # 1 bd → exclude
        _bond("BOND_FAR", "2026-10-01"),                # keep
    ]
    kept, excluded = filter_near_maturity(products, as_of_date="2026-09-09")
    assert [p["product_id"] for p in kept] == ["BOND_FAR"]
    assert excluded == ["BOND_MATURES_TOMORROW"]


def test_exclusive_boundary_keeps_exact_n_days():
    # ref Wed 2026-09-09, n=2 → cutoff Fri 2026-09-11; maturing exactly on the
    # cutoff (2 business days out) is KEPT (strict less-than).
    products = [_bond("BOND_EXACT", "2026-09-11")]
    kept, excluded = filter_near_maturity(
        products, as_of_date="2026-09-09", min_business_days_to_maturity=2,
    )
    assert [p["product_id"] for p in kept] == ["BOND_EXACT"]
    assert excluded == []


def test_weekend_boundary_excludes_and_keeps():
    # ref Fri 2026-09-11, n=1 → cutoff Mon 2026-09-14.
    products = [
        _bond("BOND_SAT", "2026-09-12"),   # 0 bd (weekend) → exclude
        _bond("BOND_MON", "2026-09-14"),   # 1 bd → keep
    ]
    kept, excluded = filter_near_maturity(
        products, as_of_date="2026-09-11", min_business_days_to_maturity=1,
    )
    assert [p["product_id"] for p in kept] == ["BOND_MON"]
    assert excluded == ["BOND_SAT"]


# ── filter_near_maturity — no-maturity / invalid / past ───────────────────


def test_keeps_product_without_maturity():
    products = [
        _bond("NO_MATURITY", None),
        {"product_id": "ETF", "product_type": "equity_fund", "type_specific": {}},
    ]
    kept, excluded = filter_near_maturity(products, as_of_date="2026-09-09")
    assert [p["product_id"] for p in kept] == ["NO_MATURITY", "ETF"]
    assert excluded == []


def test_keeps_product_with_invalid_maturity_string():
    # Non-ISO maturity string is unparseable → treated as "no maturity date".
    products = [_bond("BAD_MATURITY", "not-a-date")]
    kept, excluded = filter_near_maturity(products, as_of_date="2026-09-09")
    assert [p["product_id"] for p in kept] == ["BAD_MATURITY"]
    assert excluded == []


def test_excludes_already_past_maturity():
    products = [_bond("ALREADY_MATURED", "2026-09-08")]  # before ref Wed 09-09
    kept, excluded = filter_near_maturity(products, as_of_date="2026-09-09")
    assert kept == []
    assert excluded == ["ALREADY_MATURED"]
