"""HTTP-based API resolver (Phase B of Sprint 2).

Replaces local Python imports with HTTP calls to the FastAPI server
at ``{base_url}/api/v1/...``.  The returned callable satisfies the
``api_resolver`` contract expected by ``load_references`` without
any code changes in ``input_loader.py`` or ``crew_workflow.py``.

Usage::

    resolver = HttpApiResolver(client_id, source_product_id, base_url=...)
    # Early-exit checks
    if resolver.client_profile is None: ...
    if resolver.source_product is None: ...
    # Pass to run_crew_planbot
    api_resolver = resolver.as_callable()
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

from src.planbot.input_loader import (
    API_CLIENT_PROFILE,
    API_HOLDINGS,
    API_PRODUCT_CATALOG,
    ReferenceDocument,
)

LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# HTTP API Resolver
# ---------------------------------------------------------------------------


class HttpApiResolver:
    """Fetches client/product data via HTTP and formats as ReferenceDocuments.

    Data is lazily fetched and cached on first access.  The ``as_callable()``
    method returns a resolver compatible with ``load_references``.
    """

    def __init__(
        self,
        client_id: str,
        source_product_id: str,
        base_url: str = "http://localhost:8000",
        timeout: float = 30.0,
        max_retries: int = 3,
        retry_backoff_factor: float = 0.5,
    ):
        self._client_id = client_id
        self._source_product_id = source_product_id
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries
        self._retry_backoff_factor = retry_backoff_factor

        # Cached raw data
        self._client_profile: dict | None = None
        self._client_profile_fetched = False
        self._source_product: dict | None = None
        self._source_product_fetched = False
        self._candidate_products: list[dict] | None = None
        self._candidates_fetched = False

    # ── HTTP helper ────────────────────────────────────────────────────

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        url = f"{self._base_url}{path}"
        transport = httpx.HTTPTransport(retries=self._max_retries)
        with httpx.Client(
            transport=transport,
            timeout=httpx.Timeout(self._timeout),
        ) as client:
            LOGGER.debug("HTTP %s %s", method, url)
            response = client.request(method, url, **kwargs)
            response.raise_for_status()
            return response

    # ── Data accessors (lazy) ──────────────────────────────────────────

    @property
    def client_profile(self) -> dict | None:
        """Full client profile including nested holdings (GET /api/v1/clients/{id})."""
        if not self._client_profile_fetched:
            self._client_profile_fetched = True
            try:
                resp = self._request("GET", f"/api/v1/clients/{self._client_id}")
                self._client_profile = resp.json()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 404:
                    LOGGER.warning("Client not found via HTTP: %s", self._client_id)
                    self._client_profile = None
                else:
                    raise
            except httpx.RequestError as exc:
                LOGGER.error("HTTP request failed for client %s: %s", self._client_id, exc)
                raise
        return self._client_profile

    @property
    def source_product(self) -> dict | None:
        """Single product lookup (GET /api/v1/products/{id})."""
        if not self._source_product_fetched:
            self._source_product_fetched = True
            try:
                resp = self._request("GET", f"/api/v1/products/{self._source_product_id}")
                self._source_product = resp.json()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 404:
                    LOGGER.warning("Source product not found via HTTP: %s", self._source_product_id)
                    self._source_product = None
                else:
                    raise
            except httpx.RequestError as exc:
                LOGGER.error("HTTP request failed for product %s: %s", self._source_product_id, exc)
                raise
        return self._source_product

    @property
    def candidate_products(self) -> list[dict]:
        """Reinvestment candidates enriched with full product details.

        Calls POST /api/v1/products/reinvestment-candidates followed by
        GET /api/v1/products/{id} for each candidate.
        """
        if not self._candidates_fetched:
            self._candidates_fetched = True
            try:
                # Step 1 — get candidate list
                cand_resp = self._request(
                    "POST",
                    "/api/v1/products/reinvestment-candidates",
                    json={
                        "client_ids": [self._client_id],
                        "source_product_id": self._source_product_id,
                    },
                )
                cand_data = cand_resp.json()
                candidates_raw = cand_data.get("results_by_client", {}).get(self._client_id, [])

                # Step 2 — enrich each candidate with full product details
                result: list[dict] = []
                for c in candidates_raw:
                    pid = c.get("product_id", "")
                    try:
                        prod_resp = self._request("GET", f"/api/v1/products/{pid}")
                        prod = prod_resp.json()
                    except httpx.HTTPStatusError:
                        prod = {}
                    full = dict(prod)
                    full["similarity_score"] = c.get("similarity_score")
                    result.append(full)

                self._candidate_products = result
            except httpx.RequestError as exc:
                LOGGER.error("HTTP request failed for candidates: %s", exc)
                raise
        return self._candidate_products or []

    # ── ReferenceDocument formatting ───────────────────────────────────

    def _format_profile_markdown(self) -> str:
        cp = self.client_profile or {}
        lines = [
            "# Client Profile",
            "",
            f"- Client ID: {cp.get('client_id', self._client_id)}",
            f"- Name: {cp.get('name', 'N/A')}",
            f"- Age: {cp.get('age', 'N/A')}",
            f"- Birthdate: {cp.get('birthdate', 'N/A')}",
            f"- Occupation: {cp.get('occupation', 'N/A')}",
            f"- Marital Status: {cp.get('marital_status', 'N/A')}",
            f"- Children Info: {cp.get('children_info', 'N/A')}",
        ]
        aum = cp.get("aum")
        lines.append(f"- AUM: ${aum:,.0f}" if aum else "- AUM: N/A")
        lines += [
            f"- Risk Tolerance (1-5): {cp.get('risk_rating', 'N/A')}",
            f"- Region: {cp.get('region', 'N/A')}",
            f"- Cash %: {cp.get('cash_pct', 'N/A')}",
            f"- Liquidity Need: {cp.get('liquidity_need', 'N/A')}",
            f"- Income Stability: {cp.get('income_stability', 'N/A')}",
            f"- Investment Objective: {cp.get('investment_objective', 'N/A')}",
        ]
        irs = cp.get("investor_readiness_score")
        if irs is not None:
            lines.append(f"- Investor Readiness Score: {irs}")
        lines += [
            f"- Cash Score: {cp.get('cash_score', 'N/A')}",
            f"- Concentration Score: {cp.get('concentration_score', 'N/A')}",
            f"- Active Score: {cp.get('active_score', 'N/A')}",
            f"- Life Stage Score: {cp.get('life_stage_score', 'N/A')}",
        ]
        pt_holdings = cp.get("product_types_in_holdings", [])
        if pt_holdings:
            lines.append(f"- Product Types Held: {', '.join(pt_holdings)}")
        has_fund = cp.get("has_fund")
        if has_fund is not None:
            lines.append(f"- Has Fund Holdings: {'Yes' if has_fund else 'No'}")
        lines += [
            "",
            "# Wallet inflow Event",
            "",
            "The following product is maturing:",
            f"- Product ID: {self._source_product_id}",
            f"- Product Name: {self.source_product.get('name', self._source_product_id) if self.source_product else self._source_product_id}",
        ]
        return "\n".join(lines) + "\n"

    def _format_holdings_csv(self) -> str:
        holdings = (self.client_profile or {}).get("holdings", [])
        fieldnames = [
            "client_id", "holding_id", "product_id", "instrument_name",
            "symbol", "asset_class", "region", "currency", "quantity",
            "book_cost", "market_value", "unrealized_pl", "unrealized_pl_pct",
            "yield_pct", "risk_bucket", "esg_score", "liquidity",
        ]
        lines: list[str] = [",".join(fieldnames)]
        for h in holdings:
            row = ",".join(str(h.get(f, "")) for f in fieldnames)
            lines.append(row)
        return "\n".join(lines) + "\n"

    def _format_catalog_json(self) -> str:
        def _serialize_json_fields(d: dict) -> dict:
            out = dict(d)
            for field in ("type_specific", "performance_history"):
                val = out.get(field)
                if isinstance(val, str):
                    try:
                        out[field] = json.loads(val)
                    except (json.JSONDecodeError, TypeError):
                        pass
            return out

        payload = {
            "catalog_version": "1.0",
            "generated_for": self._client_id,
            "instruction": (
                "The following products are the only investable candidates "
                "for this reinvestment proposal. Do not recommend any product "
                "not listed below."
            ),
            "source_product": _serialize_json_fields(self.source_product or {}),
            "candidate_products": [
                _serialize_json_fields(cp) for cp in self.candidate_products
            ],
        }
        return json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n"

    # ── Public resolver callable ───────────────────────────────────────

    def as_callable(self) -> Callable[[str], ReferenceDocument]:
        """Return a resolver compatible with ``load_references``.

        The returned callable handles ``api://client_profile``,
        ``api://holdings``, and ``api://product_catalog`` by formatting
        HTTP-fetched data into ReferenceDocuments.
        """

        def resolve(api_path: str) -> ReferenceDocument:
            if api_path == API_CLIENT_PROFILE:
                return ReferenceDocument(
                    path=Path(f"api://client/{self._client_id}/profile.md"),
                    content=self._format_profile_markdown(),
                    source_type="markdown",
                )
            if api_path == API_HOLDINGS:
                return ReferenceDocument(
                    path=Path(f"api://client/{self._client_id}/holdings.csv"),
                    content=self._format_holdings_csv(),
                    source_type="csv",
                )
            if api_path == API_PRODUCT_CATALOG:
                return ReferenceDocument(
                    path=Path(f"api://client/{self._client_id}/catalog.json"),
                    content=self._format_catalog_json(),
                    source_type="json",
                )
            raise ValueError(
                f"Unknown API path: {api_path!r}. "
                f"Expected one of: {API_CLIENT_PROFILE}, {API_HOLDINGS}, {API_PRODUCT_CATALOG}."
            )

        return resolve
