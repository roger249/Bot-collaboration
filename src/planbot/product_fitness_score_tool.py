from __future__ import annotations

import json
from typing import Any

from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class ProductFitnessScoreInput(BaseModel):
    """Input for the product-fitness-score tool."""

    model_config = {"extra": "forbid"}

    client_id: str = Field(
        ...,
        description="Client ID whose fitness against the given products is scored.",
    )
    product_ids: list[str] = Field(
        ...,
        description="Candidate product IDs to score against the client.",
    )
    top_n: int = Field(default=10, description="Maximum number of scored pairs to return.")
    risk_rating_hard_filter: bool = Field(
        default=True,
        description="If true, products with risk_rating > client.risk_rating are excluded.",
    )
    exclude_dimensions: list[str] | None = Field(
        default=None,
        description="Score dimensions to exclude from the fitness computation (optional).",
    )


class ProductFitnessScoreTool(BaseTool):
    name: str = "product_fitness_score_tool"
    description: str = (
        "Compute a product fitness score for a client against one or more "
        "candidate products. Returns a ranked list of "
        "client×product pairs with fitness_score and component_scores "
        "(risk_rating_match, diversification, investment_experience, "
        "better_product, semantic similarity). "
        "Use this to quantify how well each candidate product fits a client "
        "before recommending it. "
        "Action Input format rule: provide a single key-value dictionary per tool call, "
        "for example {\"client_id\": \"PB-HK-000020-8\", \"product_ids\": [\"PROD020\", \"ETF-BKLN\"]}."
    )
    args_schema: type[BaseModel] = ProductFitnessScoreInput

    def _run(
        self,
        client_id: str,
        product_ids: list[str],
        top_n: int = 10,
        risk_rating_hard_filter: bool = True,
        exclude_dimensions: list[str] | None = None,
    ) -> str:
        if not client_id or not str(client_id).strip():
            raise ValueError("product_fitness_score_tool requires a non-empty client_id.")
        if not product_ids:
            raise ValueError("product_fitness_score_tool requires at least one product_id.")

        # Lazy import: keep the tool module lightweight when it is only imported
        # (e.g. by `_build_tool_instance`), not invoked.
        from src.integrations.product_tool import search_product_by_fitness_score

        result: dict[str, Any] = search_product_by_fitness_score(
            client_ids=[str(client_id).strip()],
            product_ids=list(product_ids),
            top_n=top_n,
            risk_rating_hard_filter=risk_rating_hard_filter,
            exclude_dimensions=exclude_dimensions,
        )

        return json.dumps(result, ensure_ascii=False)
