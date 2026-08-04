Product Opportunity Proposal — Q&A 1: Matcher Context & Data Flow
====================================================================

## Gap: Matcher per-client context not passed to LLM

### Problem

The matcher outputs a full markdown document.  The summary table is parsed
into structured pairs (`client_id`, `product_id`, `rationale`, …), but the
**per-client detail section** — the ``### PB-HK-000001-8 (David Kim)``
block with contextual bullet points — is **not passed** to the LLM.

This is lost context.  The LLM generates a proposal from only:
- Client profile (fields from DB)
- Product specification (fields from DB)
- A one-line ``rationale`` string
- Alternative product IDs

### Actual matcher per-client section (sample)

```
### PB-HK-000001-8 (David Kim)

- **Recommendation:** Buy PROD016 Healthcare Innovation Fund – USD 77,048 (8.1% of AUM), funded by selling STOCK-TSLA Tesla Inc. – USD 77,048.
- **Fitness score:** 4.20 (Risk Match 10.0, Concentration 0.0, Experience 6.0, Better Product 0.0).
- **Expected return comparison:** PROD016 13.8% vs STOCK-TSLA 15.98%. …
- **Client needs:** Long-term capital growth with controlled drawdown; …
- **Market outlook / rationale:** Healthcare innovation offers defensive growth …
- **Concentration impact:** No increase in single-name concentration; …
- **Alternative suggestion:** PROD001 Tech Leaders Equity Fund …
```

This section already contains the funding source, expected return
comparison, fitness score breakdown, client needs analysis, market
rationale, concentration impact, and alternative products.

---

## New approach: dedicated `api://suggested_products_and_rationale` path

A dedicated path lets the ``tasks.yaml`` author write:

```yaml
description: |
  ...
  Client profiles:
  {client_profiles}

  Recommended product and rationale:
  {suggested_products_and_rationale}

  Available products:
  {product_catalogs}
```

### Config reference

The ``product_opportunity_proposal`` section in
``config/config_planbot.yaml`` already has a placeholder slot at
line 146:

```yaml
    suggested_products_and_rationale:
      # Matcher per-client analysis markdown — resolved from product_investor_matcher
      # output at runtime, but may also be supplied as a file glob by the RM.
      - name: suggested_products/*.md
        purpose: Suggested products, fitness scores, funding sources, client needs analysis, and rationale
```

At runtime, the section is populated by the API resolver (``_build_proposal_resolver``),
which injects the matcher's per-client block via ``API_SUGGESTED_PRODUCTS_AND_RATIONALE``.
If an RM wants to pre-supply content on disk, they drop a markdown file matching
the glob ``data/planbot/product_opportunity_proposal/suggested_products/*.md``.
The config parser treats this section exactly like every other reference section:
standard file glob resolution, no special-casing.

---

## Data flow (revised)

### New constant

```
src/planbot/input_loader.py

API_SUGGESTED_PRODUCTS_AND_RATIONALE = "api://suggested_products_and_rationale"
```

### Extraction (`_extract_top_pairs`)

Add a ``matching_context`` field to each pair dict — the raw per-client
markdown block **in its entirety** (including the alternative suggestion
sub-section, which may carry rationale that the structured
``alternative_product_ids`` list alone doesn't capture):

```python
# After existing alternative-product extraction — capture the entire client block
pair["matching_context"] = section_block
```

This keeps the extraction logic simple — no stripping or filtering needed.
The structured ``alternative_product_ids`` are still parsed for use in
``API_PRODUCT_CATALOG`` spec-sheet resolution; the full markdown block
preserves the original narrative context for the LLM.

The same principle applies to the optional ``#### Portfolio`` table that
may appear in some per-client sections: it is left verbatim.  No parsing,
no summarization.  Whatever the matcher outputs goes in as-is.

### Resolver (`_build_proposal_resolver`)

Accept ``matching_context`` and build the new document.  Rationale is
moved *out* of ``API_CLIENT_PROFILE`` and into the new path:

```python
def _build_proposal_resolver(
    client_data, product_data, *,
    rationale="",
    matching_context="",
    market_outlook=None,
    …
):
    client_content = format_client_profile_markdown(client_data)
    if holdings:
        client_content += "\n\n" + format_holdings_bullets(holdings)
    # rationale is NO LONGER appended to client_content

    # Build suggested-products-and-rationale document
    rationale_content = ""
    if matching_context:
        rationale_content += f"## Matcher Analysis\n\n{matching_context}\n\n"
    if rationale:
        rationale_content += f"## Rationale\n\n{rationale}\n"

    return build_api_resolver({
        API_CLIENT_PROFILE: ReferenceDocument(
            path=Path("api://client_profile"),
            content=client_content,       # client fields + holdings only
            source_type="markdown",
        ),
        API_PRODUCT_CATALOG: ReferenceDocument(…),
        API_MARKET_OUTLOOK: ReferenceDocument(…),
        API_SUGGESTED_PRODUCTS_AND_RATIONALE: ReferenceDocument(  # ← NEW
            path=Path("api://suggested_products_and_rationale"),
            content=rationale_content,
            source_type="markdown",
        ),
    })
```

### Runtime reference override (`_process_one_pair`)

The call to ``run_crew_planbot`` must include the new section:

```python
runtime_reference_overrides={
    "client_profiles":                  [API_CLIENT_PROFILE, API_HOLDINGS],
    "product_catalogs":                 [API_PRODUCT_CATALOG],
    "market_outlook":                   [API_MARKET_OUTLOOK],
    "suggested_products_and_rationale": [API_SUGGESTED_PRODUCTS_AND_RATIONALE],  # ← NEW
},
```

---

## Per-pair data flow (summary)

```
_extract_top_pairs() → pair["matching_context"]  (raw markdown block, entire per-client section)
        │
        │  pair["rationale"]  (one-liner from summary table, "Key Rationale" column)
        ↓
_process_one_pair(client_id, product_id, matching_context=…, rationale=…, …)
        ↓
_build_proposal_resolver(matching_context=…, rationale=…, …)
        ↓
build_api_resolver({
    API_CLIENT_PROFILE:                        client fields + holdings  (no rationale)
    API_PRODUCT_CATALOG:                       product specs by ID — primary + alternatives  (no narrative)
    API_MARKET_OUTLOOK:                        market narrative
    API_SUGGESTED_PRODUCTS_AND_RATIONALE:      matcher analysis + rationale  ← NEW  (the narrative)
})
```

---

## The resolved documents (example)

**``API_CLIENT_PROFILE`` content:**

```
# Client Profile

- Client ID: PB-HK-000001-8
- Name: David Kim
…

# Holdings

- STOCK-TSLA Tesla Inc.: $77,048 (equity, 0.0%)
…
```

**``API_SUGGESTED_PRODUCTS_AND_RATIONALE`` content (new):**

```
## Matcher Analysis

- **Recommendation:** Buy PROD016 Healthcare Innovation Fund – USD 77,048 …
- **Fitness score:** 4.20 (Risk Match 10.0, Concentration 0.0, …)
- **Expected return comparison:** PROD016 13.8% vs STOCK-TSLA 15.98%. …
- **Client needs:** Long-term capital growth with controlled drawdown; …
- **Market outlook / rationale:** Healthcare innovation offers defensive growth …
- **Concentration impact:** No increase in single-name concentration; …

## Rationale

Replace single-stock Tesla risk with diversified healthcare innovation exposure; …
```

**``API_PRODUCT_CATALOG`` content (spec sheet only — no recommendation narrative):**

```
# Suggested Product

## PROD016 — Healthcare Innovation Fund
- Type: mutual_fund
- Risk Rating: 6
- Expected Return: 13.8%
- Region: Global
- Sector: Healthcare
- Expense Ratio: 0.75%
…

## Alternative Products

1. PROD001 — Tech Leaders Equity Fund (risk=7, expected_return=12.5%)
2. PROD013 — Global Dividend Equity Fund (risk=5, expected_return=9.8%)
```

---

## Separation of concerns: narrative vs. product specs

The matching context (flowing through ``API_SUGGESTED_PRODUCTS_AND_RATIONALE``)
already describes the alternative products in narrative form — what they
are, why they fit the client, how they compare to the primary suggestion.
The ``API_PRODUCT_CATALOG`` document should **not** repeat this narrative.

Instead, ``API_PRODUCT_CATALOG`` serves a purely supplementary role:
given the product IDs from the matching context, it resolves each to
structured factual details — risk rating, expected return, asset class,
region, sector, time-to-maturity, fee structure, and any type-specific
attributes.  Think of it as the **spec sheet**, not the **recommendation
rationale**.

| Path | Role | Content |
|------|------|---------|
| ``API_SUGGESTED_PRODUCTS_AND_RATIONALE`` | **Narrative: why** | Matcher per-client analysis + rationale.  Already names and describes alternatives in free text. |
| ``API_PRODUCT_CATALOG`` | **Specs: what** | Structured product details resolved by product ID — primary + alternatives.  No recommendation narrative. |
| ``API_CLIENT_PROFILE`` | **Client: who** | Demographics + holdings. |
| ``API_MARKET_OUTLOOK`` | **Market: where** | Macro-level market context. |

**Implementation impact:** ``format_product_single()`` already produces a
compact one-liner per alternative (``product_id — name, risk=…, return=…``).
No change needed — it's already in the right shape.  The function can be
extended later with richer per-product fields (sector, region, fees) if the
LLM needs them for deeper analysis.

---

## Phase B (HTTP resolver) compatibility

The ``HttpApiResolver.as_callable()`` only handles ``API_CLIENT_PROFILE``,
``API_HOLDINGS``, and ``API_PRODUCT_CATALOG``.  Since matching context and
rationale come from the matcher output (not the data service), the HTTP
resolver needs **no changes** — the new path is only served by the
Phase‑A ``_build_proposal_resolver()`` path.

---

## Implementation tasks

| # | Task | File |
|---|------|------|
| 1 | Add ``API_SUGGESTED_PRODUCTS_AND_RATIONALE`` constant | ``src/planbot/input_loader.py`` |
| 2 | Config parser: skip ``None`` reference entries gracefully | ``src/planbot/config.py`` |
| 3 | ``_extract_top_pairs()``: capture entire per-client section block as ``matching_context`` (no stripping) | ``src/integrations/product_investor_matcher.py`` |
| 4 | ``_build_proposal_resolver()``: accept ``suggested_products_and_rationale``, build new ``API_SUGGESTED_PRODUCTS_AND_RATIONALE`` doc, remove rationale from ``API_CLIENT_PROFILE`` | ``src/integrations/product_opportunity_proposal.py`` |
| 5 | ``_process_one_pair()``: pass ``suggested_products_and_rationale`` through; add new section to ``runtime_reference_overrides`` | ``src/integrations/product_opportunity_proposal.py`` |
| 6 | ``propose_product_opportunity_automatch()``: pass ``pair.get("matching_context", "")`` | ``src/integrations/product_opportunity_proposal.py`` |
| 7 | Update ``tasks.yaml`` to include ``{suggested_products_and_rationale}`` placeholder | ``data/planbot/product_opportunity_proposal/crewai/tasks.yaml`` |
| 8 | JSON sidecar: include ``matching_context`` in ``_pairs.json`` (already handled if field is present in dict) | (automatic) |
| 9 | ``config_planbot.yaml``: give ``suggested_products_and_rationale`` a proper file glob (``suggested_products/*.md``) | ``config/config_planbot.yaml`` |
| 10 | ``OpportunityProposalRequest``: add ``suggested_products_and_rationale`` field (default ``""``) | ``src/integrations/proposal_server.py`` |

---

## Resolved questions (moved into spec)

| Q | Resolution |
|---|-----------|
| Strip alternative suggestions from matching_context? | **No.** Keep the entire per-client block verbatim. The LLM gets full context; extraction stays simple. |
| Strip ``#### Portfolio`` table? | **No.** Same logic — no parsing, no filtering. Whatever the matcher outputs goes in as-is. |
| Config parser: skip ``None`` or require ``[]``? | **Skip ``None`` silently.** The parser checks ``if entries is None: continue`` before iterating. |
| File glob or runtime-only? | **Support both.** The YAML has a proper glob (``suggested_products/*.md``). When files exist on disk, they're loaded like any other section. When populated at runtime, the API resolver injects content via ``API_SUGGESTED_PRODUCTS_AND_RATIONALE``. |
