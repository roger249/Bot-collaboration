from __future__ import annotations

import json
from typing import Any

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

# Query dimensions understood by ``search_similar`` (see
# ``src/integrations/product_tool.py``).  Kept here as the canonical list of
# flattened tool arguments so the Pydantic schema and the query builder stay
# in sync without importing the heavier product_tool module at import time.
_QUERY_DIMENSIONS: tuple[str, ...] = (
    "risk_rating",
    "expected_return",
    "product_type",
    "asset_class",
    "region",
    "sector",
    "time_to_maturity",
    "coupon",
    "trade_date",
)


class ProductSearchInput(BaseModel):
    """Input for the product similarity search tool.

    Either provide a ``product_id`` (anchor product → find similar products,
    automatically excluding the anchor) or one or more query attribute fields.
    At least one of these is required.
    """

    model_config = {"extra": "forbid"}

    product_id: str | None = Field(
        default=None,
        description=(
            "Anchor product ID. If set, find products similar to this product "
            "and ignore the attribute fields below."
        ),
    )
    risk_rating: int | None = Field(
        default=None,
        description="Target risk rating (1-10). Only products with risk_rating <= this are matched.",
    )
    expected_return: float | None = Field(
        default=None,
        description="Target expected return (percentage).",
    )
    product_type: str | None = Field(
        default=None,
        description="Product type, e.g. bond, bond_fund, equity_fund, stock, money_market_fund, balanced_fund.",
    )
    asset_class: str | None = Field(
        default=None,
        description="Asset class, e.g. fixed_income, equity, cash, balanced.",
    )
    region: str | None = Field(
        default=None,
        description="Region, e.g. US, HK, CN, Global.",
    )
    sector: str | None = Field(
        default=None,
        description="Sector, e.g. Technology, Financials, Government.",
    )
    time_to_maturity: str | None = Field(
        default=None,
        description="Target time to maturity for bonds, e.g. '2y', '6m', '30d'.",
    )
    coupon: float | None = Field(
        default=None,
        description="Target coupon / dividend yield (percentage).",
    )
    trade_date: str | None = Field(
        default=None,
        description="Reference trade date (ISO 8601) for maturity calculations. Defaults to today.",
    )
    top_n: int = Field(default=3, description="Maximum number of products to return.")
    risk_rating_hard_filter: bool = Field(
        default=True,
        description="If true, only products with risk_rating <= query risk_rating are considered.",
    )
    diversification: bool = Field(
        default=True,
        description="If true, group results by product_type and cap each group.",
    )
    max_candidates_per_product_type: int = Field(
        default=2,
        description="Max candidates per product_type group when diversification is true.",
    )
    exclude_product_ids: list[str] | None = Field(
        default=None,
        description="Product IDs to exclude from results.",
    )


def _build_query_dict(inputs: ProductSearchInput) -> dict[str, Any]:
    """Build a ``search_similar`` query dict from the flattened tool inputs.

    Only explicitly provided (non-None) dimensions are included, which lets
    ``search_similar`` score on a partial query and renormalize weights.
    """
    query: dict[str, Any] = {}
    for dim in _QUERY_DIMENSIONS:
        value = getattr(inputs, dim)
        if value is not None:
            query[dim] = value
    return query


class ProductSearchTool(BaseTool):
    name: str = "ProductSearch"
    description: str = (
        "Search the investable product catalog for products similar to given "
        "attributes, ranked by similarity score. "
        "Use this to discover candidate products for a client. "
        "Provide either a product_id (find products similar to that product) "
        "or one or more attribute fields such as risk_rating, product_type, "
        "asset_class, region, sector, expected_return, time_to_maturity, coupon. "
        "Action Input format rule: provide a single key-value dictionary per tool call, "
        "for example {\"product_type\": \"bond_fund\", \"top_n\": 5}."
    )
    args_schema: type[BaseModel] = ProductSearchInput

    def _run(
        self,
        product_id: str | None = None,
        risk_rating: int | None = None,
        expected_return: float | None = None,
        product_type: str | None = None,
        asset_class: str | None = None,
        region: str | None = None,
        sector: str | None = None,
        time_to_maturity: str | None = None,
        coupon: float | None = None,
        trade_date: str | None = None,
        top_n: int = 3,
        risk_rating_hard_filter: bool = True,
        diversification: bool = True,
        max_candidates_per_product_type: int = 2,
        exclude_product_ids: list[str] | None = None,
    ) -> str:
        inputs = ProductSearchInput(
            product_id=product_id,
            risk_rating=risk_rating,
            expected_return=expected_return,
            product_type=product_type,
            asset_class=asset_class,
            region=region,
            sector=sector,
            time_to_maturity=time_to_maturity,
            coupon=coupon,
            trade_date=trade_date,
            top_n=top_n,
            risk_rating_hard_filter=risk_rating_hard_filter,
            diversification=diversification,
            max_candidates_per_product_type=max_candidates_per_product_type,
            exclude_product_ids=exclude_product_ids,
        )

        # Lazy import: keep the tool module lightweight when it's only imported
        # (e.g. by `_build_tool_instance`), not invoked.
        from src.integrations.product_tool import (
            search_by_product_id,
            search_similar,
            search_similar_to_product,
        )

        if product_id:
            product = search_by_product_id(str(product_id).strip())
            if product is None:
                raise ValueError(f"Product not found: {product_id}")
            result = search_similar_to_product(
                product,
                top_n=top_n,
                diversification=diversification,
                max_candidates_per_product_type=max_candidates_per_product_type,
                risk_rating_hard_filter=risk_rating_hard_filter,
                exclude_product_ids=list(exclude_product_ids or []),
            )
        else:
            query = _build_query_dict(inputs)
            if not query:
                raise ValueError(
                    "Provide at least one query attribute (risk_rating, product_type, "
                    "asset_class, region, sector, expected_return, time_to_maturity, "
                    "coupon) or a product_id."
                )
            result = search_similar(
                query=query,
                top_n=top_n,
                risk_rating_hard_filter=risk_rating_hard_filter,
                diversification=diversification,
                max_candidates_per_product_type=max_candidates_per_product_type,
                exclude_product_ids=exclude_product_ids,
            )

        return json.dumps(result, ensure_ascii=False)
