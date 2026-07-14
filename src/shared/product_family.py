"""Shared product-type-to-product-family mapping.

Used by both client_api and product_tool for consistent family grouping.
Unmapped product_type values default to themselves as their own family.
"""

from __future__ import annotations

_PRODUCT_FAMILY_MAP: dict[str, str] = {
    "bond": "bond",
    "bond_fund": "bond",
    "equity_fund": "equity",
    "stock": "equity",
    "money_market_fund": "cash",
    "balanced_fund": "balanced",
}


def get_product_family(product_type: str) -> str:
    """Map a product_type to its product_family.

    Unmapped types default to themselves (e.g. future types like
    ``structured_product`` → ``"structured_product"``).
    """
    return _PRODUCT_FAMILY_MAP.get(product_type, product_type)
