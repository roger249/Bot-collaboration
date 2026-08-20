# Semantic Embedding Enhancement for PFS

## Objective

The current PFS (Product Fitness Score) computation consumes **structured data only** — `risk_rating`, `expected_return`, `product_type`, `asset_class`, `region`, `sector`, and holding-derived concentration/experience metrics (see [`product_fitness_score.md`](product_fitness_score.md)).  It ignores the descriptive, free-text features that a Relationship Manager actually weighs when recommending a product.

This enhancement introduces **semantic (sentence) embeddings** so the PFS can also measure how well a candidate product's description aligns with the client's stated preferences and history.  The embeddings are used to compute **cosine-similarity features**, which are added as additional inputs to the PFS.

## Fields to embed

A sentence embedding model encodes the following fields.  **List fields (`like_products` / `dislike_products`) are embedded one vector per element** (not one concatenated vector), so `max` aggregation preserves the dominant-keyword signal.

**Client profile**

| Field | Type | Notes |
|-------|------|-------|
| `like_products` | `list[str]` | Keywords/products the client has expressed interest in — one vector per keyword. |
| `dislike_products` | `list[str]` | Keywords/products the client has rejected or shown aversion to — one vector per keyword. |
| `RM_note` | `str` | Free-text RM notes. Maps to the existing `clients.qualitative_profile` field (already present today). |

**Product catalog**

| Field | Type | Notes |
|-------|------|-------|
| `investment_note` | `str` | Narrative summary from the product prospectus / house view — embedded for the like / dislike / holding-similarity features. |
| `name` | `str` | Legal product name — embedded **only** for the `similarity_to_RM_note` feature (see below). |

> The like / dislike / holding features use **only** `product.investment_note`, not `product.name`: legal names are dominated by boilerplate wrapper words ("State Street … Select Sector … SPDR ETF") that mean-pool to near-noise, so they carry almost no semantic signal for those features.  The `investment_note` (which holds the actual thematic concepts) is the primary product-side embed source.  The `name` is additionally embedded **solely** for `similarity_to_RM_note`, where the RM's free text often names a specific theme or sector that the name captures better than a broad note.

## New PFS features

Four new cosine-similarity features are added as inputs to the PFS:

> Note: the original draft header said "three", but the confirmed set is **four** features.

| Feature | Computed as cosine similarity between | Purpose |
|---------|---------------------------------------|---------|
| `similarity_product_note_in_like_products` | candidate `product.investment_note` vs. each keyword in `client.like_products` | Lift products matching stated interests. |
| `similarity_product_note_in_dislike_products` | candidate `product.investment_note` vs. each keyword in `client.dislike_products` | Penalise products matching stated aversions. |
| `similarity_to_current_holding` | candidate product description vs. each holding's product description (cached catalog embedding) | Lift products similar to what the client already holds; max aggregation. |
| `similarity_to_RM_note` | candidate product (`name` **and** `investment_note`) vs. `client.RM_note` (max) | Align with qualitative RM guidance. |

These are **direct alignment features** (cosine distance scalars), **not** raw embedding vectors — raw vectors are high-dimensional and are not passed into a tree model.

### Feature computation

**Scale mapping** — cosine similarity is bounded in `[-1, +1]`, but dense sentence embeddings are *anisotropic*: every text sits in a narrow positive cosine band (unrelated text scores a positive floor, a strong match only modestly higher).  PFS dimensions are on a 0-10 scale, so each similarity feature is **min-max normalised** onto 0-10 using the model's empirically-observed bounds:

```
score = (sim − floor) / (ceiling − floor) × 10
```

This maps `sim ≤ floor` → 0 (irrelevant), `sim ≥ ceiling` → 10 (strong match), and the band midpoint → 5.  Applied before weights are applied in the weighted sum.

> **Per-feature floor/ceiling calibration** — the four features have *different* cosine bands (keyword↔note vs note↔note), so each carries its own `(floor, ceiling)` pair, externalised as `embedding.similarity_bounds` in `config_screener.yaml`.  For `intfloat/e5-base-v2` the bands are measured over the full DuckDB (23 clients × 133 products, ~37k pairs), using the 5th percentile as `floor` (irrelevant) and the 95th percentile as `ceiling` (strong match):

> | feature | floor | ceiling |
> |---|---|---|
> | `like` (note↔keyword) | 0.72 | 0.81 |
> | `dislike` (note↔keyword) | 0.73 | 0.82 |
> | `holding` (note↔note) | 0.79 | 0.87* |
> | `rm` (RM↔name+note) | 0.77 | 0.83 |
>
> \* `holding`'s 95th percentile is 0.998 — boilerplate-inflated because many products share identical note templates — so its ceiling is capped at ~the 75th percentile (0.87) to avoid a binary 0-or-10.  This is a stopgap; the real fix is `investment_note` enrichment (Outstanding Issue #5).  An unset feature defaults to the identity mapping `(0.0, 1.0)`.

**List aggregation (`like_products` / `dislike_products`)** — these fields are lists of keywords, but cosine similarity is scalar-vs-scalar.  The feature uses the **max** similarity between the candidate `product.investment_note` embedding and each keyword embedding (dominant keyword wins).  An empty list → neutral score (5).

> Keywords are embedded **individually** (one vector per keyword), not concatenated into a single paragraph vector.  Concatenation dilutes heterogeneous keywords into a semantic centroid that matches nothing and is order-sensitive; per-keyword + `max` preserves a strong single-keyword match.

#### `similarity_product_note_in_like_products`

- `sim = max_k cosine(emb(product.investment_note), emb(keyword_k))` across the client's `like_products`.
- `score = (sim − floor) / (ceiling − floor) × 10`.  Higher = product matches a stated interest.

#### `similarity_product_note_in_dislike_products`

- Same `max` aggregation across the client's `dislike_products`, but **inverted** so it acts as a penalty:

  `score = 10 − (sim − floor) / (ceiling − floor) × 10`

- Disliked (`sim → ceiling`) → 0 (penalized); unrelated (`sim → floor`) → 10 (comfortable); the band midpoint → 5 (neutral).  This keeps a positive weight in `config_screener.yaml`.

#### `similarity_to_current_holding`

- **Assumption:** every holding's product is present in the product catalog, so its description embedding is the cached product-catalog embedding (`embeddings` table, `entity_type = 'product'`).  No separate holding embedding is required.
- For a candidate product `P` and the client's holdings `H_1 … H_k`:
  - `s_i = cosine(emb(P), emb(H_i))` for each holding `i`.
  - `sim = max_i(s_i)` (dominant holding wins — no softmax, so no temperature parameter).
- `score = (sim − floor) / (ceiling − floor) × 10` (standard mapping).  Higher = candidate resembles the client's most-similar existing holding.
- Single holding (`k = 1`) → `sim = s_1` (the raw cosine, not a constant).
- With no holdings (`k = 0`) → neutral score (5).

#### `similarity_to_RM_note`

- The RM note is free text that may name a specific theme/sector (best caught by the product `name`) **or** express a broader suitability concern (best caught by `investment_note`).  So the feature matches against **both** surfaces and takes the **max**:

  `sim = max( cosine(emb(product.name), emb(RM_note)), cosine(emb(product.investment_note), emb(RM_note)) )`

- `score = (sim − floor) / (ceiling − floor) × 10` (standard mapping).  Higher = product description aligns with the RM's qualitative notes.
- Missing `RM_note` (empty `qualitative_profile`) → neutral score (5).
- If only one product surface is available (e.g. a product with no `investment_note`), the feature falls back to the single available surface.

### Phasing: weighted-sum → LightGBM

The new features are introduced in two phases:

1. **Phase 1 (weighted-sum, immediate)** — the four similarity features are appended to the existing PFS as additional weighted dimensions.  They are scored alongside the current four dimensions (`risk_rating_match_score`, `diversification_score`, `has_similar_investment_experience_score`, `better_product_score`) using the existing weighted-sum + renormalisation machinery.
2. **Phase 2 (LightGBM, later)** — once labelled client→product outcome data is available, replace the hand-weighted sum with a LightGBM ranker/regressor that consumes all structured features **plus** the similarity scalars.  This mirrors the roadmap already noted in `investor_readiness_score.md` ("ML weight calibration").

## Tasks

### 1. Add client-profile fields

Add the following fields to the client profile:

| Field | Type | Update cadence |
|-------|------|----------------|
| `like_products` | `list[str]` (DuckDB `VARCHAR[]`) | RM-maintained |
| `dislike_products` | `list[str]` (DuckDB `VARCHAR[]`) | RM-maintained |
| `date_last_traded` | `date` | Static date of the last trade; updated whenever a new trade is recorded |
| `product_name_last_traded` | `str` | Updated whenever a new trade is recorded |
| `position_bought` | `float` | Signed monetary amount of the last trade (buy = positive, sell = negative); updated whenever a new trade is recorded |

> All five fields are added as **new columns on the existing `clients` table** (via `ALTER TABLE` / seeder `CREATE TABLE`); no new table is required.  `RM_note` is **not** a new field — it maps to the existing `clients.qualitative_profile`.

> `date_last_traded` is stored as a **static date** (not a day count).  The model input `days_since_last_traded` is **derived at scoring time**: `days_since_last_traded = today − date_last_traded`.

> Trade-derived fields (`date_last_traded`, `product_name_last_traded`, `position_bought`) are populated from the bank's trade feed when available; until then, they are seeded from static data.

> `position_bought` is denominated in the **system base currency** — the same base currency used for `clients.aum` and `holdings.market_value`.

> **`days_to_next_capital_release`** is a **derived feature computed on-the-fly**, not a persisted column.  Its source of truth is maturing holdings (not a new CRM field): reuse the existing `search_holdings_maturing` / `_parse_maturity` (`src/planbot/client_enrichment.py`), which already computes `days_to_mature = maturity − as_of_date` from the product catalog's `type_specific.maturity`.  The feature is:
> - the **per-client minimum** of `days_to_mature` across the client's maturing holdings, and
> - computed with a widened look-ahead window (drop or raise the `within_days` cap) so "next" captures any outstanding maturity.
> - **Already-matured / overdue holdings** (`days_to_mature < 0`) are **clamped to 0** (treated as "releasing now"), not skipped.
> - **No maturing holdings** → the feature is scored **0**.
> Because maturity dates are already static facts in the product catalog, no column is needed and no day-end batch is required.
> The current function only matches `product_type == "bond"`; widening to other maturity-bearing product types is deferred to Sprint 2.

### 2. Introduce semantic embedding

- Use a sentence embedding model.  The concrete model name, device, and batch size are externalised to a new `config_screener.yaml`.
- **Test-env model: `sentence-transformers/all-MiniLM-L6-v2`** (384-dim, instruction-free).  The original `hkunlp/instructor-base` was abandoned for the test env — the `InstructorEmbedding` PyPI package is incompatible with modern `sentence-transformers`, and the instructor checkpoint is non-discriminative without its instruction mechanism (see outstanding issue).  Revisit an INSTRUCTOR-family model in Sprint 2.
- `config_screener.yaml` initially holds embedding model config; over time it will become the home for **all** PFS and IRS parameters (migrating the current `product_fitness_score` and `investor_readiness_score` sections out of `config_planbot.yaml`).
- Build an **embedding pipeline** that embeds the fields listed above and stores the resulting vectors for reuse.  Embedding is **lazy/on-the-fly**: no scheduled batch job — a field is re-embedded only when its content changes.

### 3. Enhance PFS with similarity features

- Add the four similarity features as additional PFS dimensions (Phase 1).
- Their weights are defined in `config_planbot.yaml` under `product_fitness_score.product_fitness_weights` (alongside the existing four dimensions), following the same externalisation rule as today.  Migration to `config_screener.yaml` is deferred to Sprint 2.

### 4. Update the prompt formatter

- Extend the PFS table rendered for the LLM (`format_pfs_table` in `src/shared/resolver_formatters.py`) to add the four similarity scores as additional columns after `Better Product`: `Like`, `Comfort`, `Holding Similarity`, `RM Note Similarity`.
- Extend `compute_pfs_for_products` (now returning `(scores, semantic_embedding_available)`) and the downstream `component_scores` dict with the four new keys: `similarity_product_note_in_like_products`, `similarity_product_note_in_dislike_products`, `similarity_to_current_holding`, `similarity_to_RM_note`.
- Update `product_fitness_score.md` (API response example + `component_scores` contract) to match the new columns and the `meta`/`warnings` response shape.
- **Thread the degradation flag**: `format_product_catalog` / `format_pfs_table` accept `semantic_embedding_available`; when False, a remark is prepended noting the similarity columns are neutral.
- **Add descriptions for the new scores in the rendered prompt**, so the LLM can interpret them correctly.  `format_pfs_table` already emits a legend line describing the existing columns; extend it to describe the four new columns with their direction semantics:
  - `Like` — semantic match between the product description and the client's stated likes (0–10; higher = matches interest).
  - `Comfort` — **inverted** semantic match against the client's dislikes (0 = resembles a dislike, 5 = unrelated, 10 = opposite of a dislike; i.e. higher = the client is comfortable with this product).
  - `Holding Similarity` — max similarity to the client's existing holdings (higher = more familiar territory).
  - `RM Note Similarity` — semantic match to the RM's qualitative notes (0–10; higher = more aligned).

## Embedding strategy: lazy, on-the-fly with change detection

No scheduled batch job.  The model is a **lazy-loaded singleton** (loaded on first use, kept resident for the process lifetime); re-embedding is triggered **on the fly** only when a free-text field's content changes.

```
free-text fields ──► compute content_hash (SHA-256) / compare updated_at
                          │
                    changed? ── no ──► reuse cached embedding
                          │
                         yes
                          │
                          ▼
                    embed(model, field) ──► store vector + new hash
```

- **Change detection** — the `content_hash` (SHA-256 over the embedded free-text fields) is **always recomputed from the current text on every scoring run** (the text is already read to embed when stale, so hashing is effectively free).  If it matches the stored hash, the cached embedding is reused; a mismatch triggers re-embedding.  No source-provided `updated_at` is relied on, so the same mechanism works unchanged when the source moves to an external API.
- **Product embeddings** are recomputed only when a product's `name` or `investment_note` changes (products are onboarded once).
- **Client embeddings** are recomputed only when the embedded client fields change (RM edits to `qualitative_profile`/`like_products`/`dislike_products`, new trades, etc.).
- **Model loading** — lazy singleton; a one-time load cost of ~1–2 s and a few hundred MB RAM for `all-MiniLM-L6-v2`, after which on-demand embedding is effectively free.
- **Storage separation** — embeddings are *derived artifacts*, not input fields, so they are stored separately from `clients`/`products` in a dedicated `embeddings` table to avoid bloating the source rows and the API/prompt contract:

  | Column | Type | Purpose |
  |--------|------|---------|
  | `entity_type` | `VARCHAR` | `client` or `product` |
  | `entity_id` | `VARCHAR` | FK to `clients.client_id` or `products.product_id` |
  | `field_name` | `VARCHAR` | which field was embedded (`name`, `investment_note`, `like_products`, `dislike_products`, `RM_note`) |
  | `field_idx` | `INTEGER` | 0-based position within a list field; `NULL` for scalar fields |
  | `model` | `VARCHAR` | embedding model id (e.g. `sentence-transformers/all-MiniLM-L6-v2`) |
  | `content_hash` | `VARCHAR` | SHA-256 of the embedded free text (change detection) |
  | `embedding` | `DOUBLE[]` | native DuckDB array for fast similarity math |
  | `updated_at` | `TIMESTAMP` | last embed time |

> **Cache, not source of truth.**  The `embeddings` table is a **derived cache**, never written back to the source system.  Today the source is the local DuckDB; later client/product data will be retrieved from an external FastAPI server.  The design is source-agnostic: `entity_id` is a **logical reference** (not a real FK), and `content_hash` is the **universal invalidation signal** — the current text is hashed regardless of origin, and a mismatch triggers re-embedding.  Because the hash is always recomputed on read, there is no dependence on the source exposing timestamps, so **no code change is needed** when the source moves to an external API.  When data is external, the cache lives in the proposal server's own store (this DuckDB file, or in-memory for a long-lived process).  Stale/orphaned rows (e.g. a deleted entity) are evicted by comparing against current `entity_id`s during scoring.

## Configuration

New file `config/config_screener.yaml` (alongside `config.yaml`, `config_planbot.yaml`, `config_marketdata.yaml`):

```yaml
embedding:
  semantic_model_config: "minilm"    # named preset — switch models by changing only this
  # Deployment / behavior keys (model-independent):
  device: "auto"                     # cpu | cuda | mps | auto
  batch_size: 32
  normalize: true
  lazy_load: true                    # load singleton on first use, keep resident
  change_detection:
    method: content_hash             # sha256 over embedded free-text fields
    store_hash: true                 # persist hash alongside the embedding
  cache:
    product_ttl_hours: -1            # -1 = keep until investment_note hash changes
    client_ttl_hours: -1             # -1 = keep until profile free-text hash changes
  store:
    path: data/planbot/db/planbot.duckdb   # embeddings table (derived cache)
    table: embeddings

semantic_model_configs:
  minilm:                            # symmetric (no prefixes)
    model: "sentence-transformers/all-MiniLM-L6-v2"
    query_prefix: ""
    passage_prefix: ""
    similarity_bounds:               # not yet calibrated
      like:    { floor: 0.0, ceiling: 1.0 }
      dislike: { floor: 0.0, ceiling: 1.0 }
      holding: { floor: 0.0, ceiling: 1.0 }
      rm:      { floor: 0.0, ceiling: 1.0 }
  e5-base:                           # asymmetric (instruction-conditioned)
    model: "intfloat/e5-base-v2"
    query_prefix: "query: "
    passage_prefix: "passage: "
    similarity_bounds:
      like:    { floor: 0.72, ceiling: 0.81 }
      dislike: { floor: 0.73, ceiling: 0.82 }
      holding: { floor: 0.79, ceiling: 0.87 }
      rm:      { floor: 0.77, ceiling: 0.83 }
```

> **Model switching** — `semantic_model_config` names a preset in `semantic_model_configs`.  The preset carries the **model-specific** keys (`model`, `query_prefix`, `passage_prefix`, `similarity_bounds`); the inline `embedding` section holds only model-independent deployment/behavior keys.  A preset's keys are merged over the inline section (preset wins), so a model change is a single name edit — no duplicated per-model keys to drift.  The `embeddings` table keys rows by `model`, so old-model vectors are never mixed with the new model's — but they are **not auto-deleted**.  After a switch, clear the stale vectors manually: `DELETE FROM embeddings WHERE model != '<new model id>';` (safe — it's a derived cache).

> The PFS weights (`product_fitness_weights`) and parameters (`product_fitness_params`) currently live in `config/config_planbot.yaml` under `product_fitness_score` — they are **not** in `config_screener.yaml` yet.  Their migration into `config_screener.yaml` is a Sprint 2 item.
>
> The weight values are illustrative placeholders to be finalised with the business.
>
> Only `embedding.semantic_model_config` (the selector), the resolved preset's `model` / `query_prefix` / `passage_prefix` / `similarity_bounds`, and `embedding.device` + `embedding.store` are currently consumed by the implementation.  `batch_size`, `normalize`, `lazy_load`, `change_detection`, and `cache` are declared as configuration surface but not yet read by code — they are reserved for Sprint 2 (batching, explicit invalidation, TTL eviction).  `lazy_load` behaviour is in effect regardless via the process-wide embedder singleton.

## Schema-change synchronisation

Adding the Task-1 client fields must be applied to all three layers synchronously (per the repo rule):

1. **DuckDB schema** — add the five new columns to the existing `clients` table (`ALTER TABLE` / seeder `CREATE TABLE`).  No new table is required; `RM_note` is **not** added (it maps to the existing `qualitative_profile`), and `days_to_next_capital_release` is a derived feature with no column.
2. **Test data** — `src/test_data/client_seed.py` populates realistic values for the new columns.
3. **API contract** — `docs/specification/data_api/openapi_data.json` regenerated via `scripts/export_openapi.py`, plus downstream API code in `src/integrations` and the `client_holdings_schema.md` / `bank_data_contract.md` / `client_api.md` docs.

---

## Acceptance Criteria

**Embedding & config**
- [ ] `config/config_screener.yaml` exists and externalises `model` (`sentence-transformers/all-MiniLM-L6-v2`), `device`, and `store` (path/table).  (`batch_size`, `normalize`, `lazy_load`, `change_detection`, `cache` are declared but reserved — not yet consumed.)
- [ ] The model loads lazily as a singleton (first use only); later scoring reuses the resident instance.
- [ ] A dedicated `embeddings` table exists with `entity_type`, `entity_id`, `field_name`, `field_idx`, `model`, `content_hash`, `embedding DOUBLE[]`, `updated_at`; embeddings are **not** stored in `clients`/`products`.

**Change detection**
- [ ] Scoring recomputes the SHA-256 `content_hash` over the embedded free-text fields; unchanged rows reuse the cached vector (no re-embed).
- [ ] A changed field (RM note, `like_products`/`dislike_products`, product `investment_note`) triggers re-embedding of only that row.

**Similarity features**
- [ ] The four similarity features are computed per the spec: max aggregation for like/dislike; inverted for dislike (rendered as `Comfort`); `max_i` cosine for holding; standard for RM-note — all mapped through `(sim − floor) / (ceiling − floor) × 10`.
- [ ] `embedding.similarity_bounds` is externalised in `config_screener.yaml` **per feature** (`like` / `dislike` / `holding` / `rm`) and min-max normalises each feature's cosine band onto 0–10; an unset feature falls back to the identity mapping `(0.0, 1.0)`.
- [ ] All feature scores are on a 0–10 scale before weighting.

**PFS integration**
- [ ] PFS accepts the four similarity dimensions alongside the existing four; weights externalised in `config_screener.yaml` and renormalised when dimensions are excluded.
- [ ] `exclude_dimensions` supports the four new similarity dimension keys.
- [ ] The PFS response carries `meta.semantic_embedding_available` (and a `warnings` list).  When embedding fails, similarity dimensions degrade to neutral (5.0) and the flag is set False — **no silent hash fallback**.

**Prompt formatter**
- [ ] `format_pfs_table` renders `Like`, `Comfort`, `Holding Similarity`, `RM Note Similarity` columns plus a legend describing each.
- [ ] When `semantic_embedding_available` is False, `format_pfs_table` prepends a remark that semantic similarity was unavailable and the similarity columns are neutral.
- [ ] `component_scores` includes the four new keys.

**Schema**
- [ ] The five new `clients` columns (`like_products`, `dislike_products`, `date_last_traded`, `product_name_last_traded`, `position_bought`) exist in DuckDB, are seeded by `src/test_data/client_seed.py`, and appear in the regenerated OpenAPI.
- [ ] `days_to_next_capital_release` is derived on-the-fly from maturing holdings (no column, no day-end batch); overdue holdings clamp to 0; no maturing holdings → score 0.

**Tests**
- [ ] Python `unittest` coverage: one normal-flow and one exception-condition test per new module (embedding pipeline, similarity feature computation, schema migration).
- [ ] **Manual scorecard smoke test** — select one product profile (already defined in `config_planbot.yaml` / test data) and 10 random clients from the existing DuckDB, run PFS end-to-end, and write the resulting scorecard to a file for human examination.

---

## Outstanding Issues

> Review findings — open questions and inconsistencies found during review.  Once a decision is agreed, move it into the corresponding section above and remove the row.

| # | Issue | Suggestion |
|---|-------|------------|
| 1 | **INSTRUCTOR model unusable in test env.** `InstructorEmbedding==1.0.1` is incompatible with modern `sentence-transformers` (its `encode()` references a removed attribute), and `hkunlp/instructor-base` loaded natively is non-discriminative without its instruction mechanism (even `banana` vs `quantum physics` scores ~0.83). | Switched to `sentence-transformers/all-MiniLM-L6-v2` (instruction-free).  Revisit INSTRUCTOR via a maintained wrapper + pinned `sentence-transformers==2.x`, or `instructor-large` with instruction handling, in Sprint 2. |

---

## Sprint 2 (Deferred)

> Deferred out of the current sprint.  No immediate decision required; revisit when Sprint 2 planning starts.

| # | Item | Suggestion |
|---|------|------------|
| 1 | **Embedding model upgrade.** | Keep `all-MiniLM-L6-v2` for now; evaluate a larger/domain model (`instructor-large` via a maintained wrapper, or `bge-base-en-v1.5`) after validation; defer hosted-API/GPU/latency to this sprint. |
| 2 | **`config_screener.yaml` parameter migration.** | Phase migration: embed config first, then move `product_fitness_score`/`investor_readiness_score` out of `config_planbot.yaml` with precedence rules. |
| 3 | **Widen `search_holdings_maturing` product coverage.** Currently only matches `product_type == "bond"`. | Extend `search_holdings_maturing` / `_parse_maturity` to include other maturity-bearing products (e.g. structured products with early redemption, deposits with term ends) so `days_to_next_capital_release` captures non-bond capital releases too. |
| 4 | **LightGBM training data & labels.** Phase 2 needs labelled client→product outcomes. | Phase 1 weighted-sum as bootstrap labels until bank outcome data arrives; target ~1k labelled pairs. |
| 5 | **Boilerplate `investment_note` data quality.** Many products (especially US sector ETFs) share near-identical templated `investment_note` text, which pegs `similarity_to_current_holding` (and partially `similarity_to_RM_note`) at ~10.0 / near-constant regardless of genuine fit. | Enrich `investment_note` with product-specific narrative (distinct sector/theme/risk language) in the catalog seeder so the semantic features are discriminative.  The floor/ceiling calibration does **not** fix this — it is a data-quality issue. |
| 6 | **Rigorous floor/ceiling estimation.** `similarity_bounds` per feature are estimated from the current DuckDB (p5/p95 over ~37k real pairs) but will drift if the catalog or RM notes change materially. | Re-measure the per-feature cosine distribution after any catalog re-seed, and bake the updated `(floor, ceiling)` into `config_screener.yaml`.  Consider a held-out reference corpus so bounds are stable across catalog changes. |


