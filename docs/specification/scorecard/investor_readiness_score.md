# Investor Readiness Score Card

## Objective

Screen the entire client pool to surface the clients who most urgently need a transaction due to structural portfolio anomalies.  Top-ranked clients feed into downstream workflows: **product matching**, **portfolio review**, and **reinvestment proposals**.


## Factors in the scorecard

| Factor | What it measures | Example portfolio decision |
|--------|------------------|----------------------------|
| Cash drag | Whether the client has too much of the portfolio in Money Market funds or idle cash. | A client sitting on 30% idle cash earns little return; the score flags them for redeployment into higher‑yielding fixed income or equity. |
| Concentration risk | Over‑exposure to a single holding, region, or asset class. | A portfolio heavily concentrated in equity (e.g., one dominant tech name) may need diversification into precious metals or bonds to reduce single‑asset risk. |
| Investment experience | Inferred from the holdings (presence of non‑cash assets). | A client holding only cash scores low, so simpler, lower‑risk products are suggested; a client already holding equities can be offered more complex products. |
| Life stage | Proximity to peak‑wealth years where needs (retirement, education, estate) multiply. | A client in their mid‑40s (peak earning years) is prioritised for retirement/education planning; corporate entities and the very young or old score lower. |


## Input

The score card reads **two data entities** — `clients` and `holdings` — through the data‑access layer (DAL).  The DAL is configured by `data_source` in `config_planbot.yaml`: a self‑contained DuckDB backend by default, or the bank REST API when `common.get_client_product_from_restapi: true`.  The schema is documented in [`client_holdings_schema.md`](../schema_client/client_holdings_schema.md).  No other data feeds the score.

The score card itself is **I/O‑free**: it consumes plain `list[dict]` rows returned by the data adapters (`fetch_clients`, `fetch_holdings`).  The CLI path loads them from the DuckDB backend (`run_score_card`); the HTTP/API path loads the same entities through the DAL (`search_by_investor_readiness_score`).  Both call the identical scoring functions.

### Factors consumed

| Dimension | Factor | Source field(s) |
|-----------|--------|-----------------|
| Cash drag | Reported cash % of AUM | `clients.cash_pct` (0‑100) |
| Cash drag | Money‑market‑fund (MMF) value | `holdings.market_value` where `holdings.asset_class = "Cash"`, summed per client |
| Concentration | Single‑holding size | `holdings.market_value` (max per client) |
| Concentration | Regional exposure | `holdings.market_value` grouped by `holdings.region` |
| Concentration | Asset‑class exposure | `holdings.market_value` grouped by `holdings.asset_class` |
| Active management | Presence of non‑cash holdings | `holdings.asset_class ≠ "Cash"` |
| Life stage | Age | `clients.birthdate` (`YYYY-MM-DD`, or `"N/A"` for corporate entities) |

Every ratio is normalised against **`clients.aum`** (total portfolio value, base currency).  Clients whose `aum` is `NULL`, `0`, or negative are scored `0` for the ratio‑based dimensions (cash drag and concentration).

---

## Score Formula

```
total_score = w_cash · s_cash
            + w_concentration · s_concentration
            + w_active      · s_active
            + w_lifestage   · s_lifestage
```

| Term | Scale | Meaning |
|------|-------|---------|
| s_*  | 0‑10  | Dimension sub‑score |
| w_*  | 0.5‑2 | Configurable weight (default 1.0) |

Weights are **candidates for ML calibration** once a sufficient sample of labelled clients is available from the bank.

---

## Dimensions

### 1. Cash Drag

Cash drag penalises portfolios that sit on idle cash instead of earning a risk‑adjusted return.  Two cash measures are considered, and the score uses the **larger** of them so they are never double‑counted:

1. **Reported cash** — `clients.cash_pct` (deposits, 0‑100).
2. **Money Market Funds** — the summed `market_value` of holdings with `asset_class = "Cash"`, expressed as a % of AUM.

```
cash_pct_reported = clients.cash_pct                                  # %
mmf_pct           = Σ(market_value of asset_class == "Cash") / aum × 100   # %
k_cash            = max(cash_pct_reported, mmf_pct) / 100             # ratio, 0‑1
s_cash            = LinearInterpolate(k_cash, pivot)                  # flat extrapolation at edges
```

> The `max` avoids double‑counting: a client's reported `cash_pct` may already include MMF balances, so the score takes whichever measure is larger rather than summing them.

| k_cash | s_cash |
|-------:|-------:|
|   0.00 |      0 |
|   0.20 |      3 |
|   0.50 |      9 |
|   1.00 |     10 |

> Example: a client holds 30 % cash (k_cash = 0.30).  This falls between the 0.20 → 3 and 0.50 → 9 pivots, so s_cash = 3 + (9 - 3)/(0.5 - 0.2) · (0.30 - 0.20) = 3 + 20 · 0.10 = **5**.

---

### 2. Concentration Risk

Captures vulnerability from over‑exposure to a single asset, region, or asset class.  The score is the **maximum** of the three interpolated sub‑scores.

```
k_single = max(holding.market_value) / aum
k_region = max(region_total_mv / aum)           per (client, region)
k_asset  = max(asset_class_total_mv / aum)      per (client, asset_class)

s_concentration = max(
    LinearInterpolate(k_single, single_pivot),
    LinearInterpolate(k_region, region_pivot),
    LinearInterpolate(k_asset,  asset_pivot),
)
```

| Sub‑dimension | Pivot (exposure → score) |
|---------------|---------------------------|
| Single holding | 0.20 → 0, 1.00 → 10 |
| Region exposure | 0.40 → 0, 1.00 → 10 |
| Asset class exposure | 0.60 → 0, 1.00 → 10 |

#### Future implementation: sector exposure

> ⚠️ **Future implementation** — not yet enabled.  The `holdings` entity does not carry a `sector` field today.

When sector data becomes available (e.g., via Yahoo Finance enrichment of holdings), a fourth sub‑dimension `s_sector_exposure` joins the `max(…)`:

```
k_sector = max(sector_total_mv / aum)      per (client, sector)

s_concentration = max(
    LinearInterpolate(k_single, single_pivot),
    LinearInterpolate(k_region, region_pivot),
    LinearInterpolate(k_asset,  asset_pivot),
    LinearInterpolate(k_sector, sector_pivot),   # future
)
```

Proposed pivot (placeholder — to be finalised with the bank):

| Sub‑dimension | Pivot (exposure → score) |
|---------------|---------------------------|
| Sector exposure | 0.60 → 0, 1.00 → 10 |

Activation requires: a `sector` field on `holdings`, and a `score_concentration_risk.s_sector_exposure` entry in `config_planbot.yaml`.

---

### 3. Investment Experience (Active Management)

Proxies the client's willingness to accept portfolio rebalancing based on whether they already hold any investable assets.

```
s_active = has_any_non_cash_holding ? has_fund_score : 0
```

`has_any_non_cash_holding` is true when the client holds ≥ 1 position with `asset_class ≠ "Cash"`; `has_fund_score` is the configured value (`score_active_manage.has_fund`, default **3**).

| Condition | Score |
|-----------|------|
| Client holds ≥ 1 position with `asset_class ≠ "Cash"` | `has_fund` (3) |
| Otherwise | 0 |

#### Future implementation: trade frequency

> ⚠️ **Future implementation** — deferred.  No trade‑history feed is currently available from the bank.

The original spec adds a trade‑frequency term, `number_of_trading_ttm` (trades in the trailing twelve months), as a second input to the experience score.  A client who trades actively is presumed more willing to accept rebalancing.

Proposed design (placeholder — to be finalised with the bank):

```
s_active = has_any_non_cash_holding ? has_fund_score : 0
         + LinearInterpolate(number_of_trading_ttm, trading_pivot)   # future
```

Proposed pivot (placeholder):

| number_of_trading_ttm | score |
|----------------------:|------:|
|   0 | 0 |
|   2 | 2 |
|  10 | 5 |
|  20 | 7 |

> Adding the trade term changes the active‑management scale, so the combined score, its cap, and the dimension weight must be reconciled against the 0‑10 dimension target before activation.

Activation requires: a `number_of_trading_ttm` field on `clients` (or a trade‑history feed) and a `score_active_manage.trading_pivot` entry in `config_planbot.yaml`.

---

### 4. Life Stage

Scores the client's proximity to peak‑wealth years where needs (retirement, education, estate) multiply.

```
age = today.year - birth_year  (adjusted for month/day)
s_lifestage = LinearInterpolate(age, pivot)
```

| Age | s_lifestage |
|----:|------------:|
|  25 |           0 |
|  35 |           5 |
|  45 |          10 |
|  65 |          10 |
|  80 |           5 |

Corporate entities (e.g., trusts, holding companies) with `birthdate = "N/A"` receive **s_lifestage = 0**.

---

## Configuration

All pivot tables and weights live in `config/config_planbot.yaml` under the top‑level key `investor_readiness_score`:

```yaml
investor_readiness_score:
  output:
    file: runs/investor_readiness_score/scores.csv
    duckdb: data/planbot/db/planbot.duckdb
  score_cash_drag:
    weight: 1
    pivot:
      0.0: 0
      0.2: 3
      0.5: 9
      1.0: 10
  score_concentration_risk:
    weight: 1
    s_single_holding:       { 0.2: 0, 1.0: 10 }
    s_region_exposure:      { 0.4: 0, 1.0: 10 }
    s_asset_class_exposure: { 0.6: 0, 1.0: 10 }
  score_active_manage:
    weight: 1
    has_fund: 3
  score_life_stage:
    weight: 1
    pivot:
      25: 0
      35: 5
      45: 10
      65: 10
      80: 5
```

---

## API

The score card is accessible via **CLI**, **Python API**, and a **FastAPI HTTP endpoint**.

### 1. CLI

```bash
.venv/bin/python -m src.planbot.investor_readiness_score [config_path]
```

- Defaults to `config/config_planbot.yaml`
- Prints a ranked table to stdout and writes `scores.csv`

### 2. Python

```python
from src.planbot.investor_readiness_score import run_score_card

scores = run_score_card("config/config_planbot.yaml")
# scores: list[ClientScore] — ranked, descending total_score

for s in scores:
    print(s.client_id, s.name, s.total_score)
```

`ClientScore` dataclass fields:

```python
@dataclass
class ClientScore:
    client_id: str
    name: str
    total_score: float
    s_cash: float
    s_concentration: float
    s_active: float
    s_lifestage: float
```

### 3. FastAPI

The data server exposes the ranked scores through the client‑readiness endpoint:

```
GET  /api/v1/clients/readiness            # top 10 by default
GET  /api/v1/clients/readiness?top_n=0    # all clients
```

Implemented in `src/integrations/proposal_server.py` (`get_investor_readiness`), which delegates to `search_by_investor_readiness_score` (`src/integrations/client_api.py`).

**Response** — an array of `ReadinessItem`, sorted by `rank`:

```json
[
  {
    "rank": 1,
    "client_id": "PB-HK-000001-8",
    "name": "David Kim",
    "investor_readiness_score": 29.5,
    "cash_score": 8.0,
    "concentration_score": 10.0,
    "active_score": 3.0,
    "life_stage_score": 8.5
  }
]
```

> The HTTP field names (`investor_readiness_score`, `cash_score`, …) differ from the internal `ClientScore` fields (`total_score`, `s_cash`, …) but carry the same values.

---

## Output

`runs/investor_readiness_score/scores.csv`

| Column | Description |
|--------|-------------|
| rank | 1‑based order (highest total_score first) |
| client_id | PB‑HK‑… |
| name | Client display name |
| total_score | Weighted sum (max ~40) |
| s_cash, s_concentration, s_active, s_lifestage | Per‑dimension 0‑10 sub‑scores |

---

## Roadmap / Known Gaps

| Item | Status | Notes |
|------|--------|-------|
| Sector concentration | 🔜 Pending data | CSV lacks `sector`; enrichable via Yahoo Finance |
| Trade frequency (number_of_trading_ttm) | 🔜 Pending data | Requires trade‑history feed from bank |
| ETF/MF tag on holdings | ⚠️ Approximated | `score_active_manage` uses `asset_class ≠ "Cash"`; a dedicated `vehicle` column would be more precise |
| FastAPI endpoint | ✅ Implemented | `GET /api/v1/clients/readiness` — see API section |
| ML weight calibration | 🔮 Future | Requires labelled outcome data from bank |
| Incremental refresh | 🔮 Future | Currently full‑rebuild DuckDB from CSVs each run |