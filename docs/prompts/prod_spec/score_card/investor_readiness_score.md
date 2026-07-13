# Investor Readiness Score Card

## Objective

Screen the entire client pool to surface the clients who most urgently need a transaction due to structural portfolio anomalies.  Top-ranked clients feed into downstream workflows: **product matching**, **portfolio review**, and **reinvestment proposals**.

## Data Sources

Two CSVs are loaded into a DuckDB database on first run:

| Source | File | Content |
|--------|------|---------|
| Holdings | `data/planbot/shared/client_profile/client_list.csv` | Wide‑format: one row per client, nested‑column holdings (0…9) |
| Demographics | `data/planbot/shared/client_profile/client_profile.csv` | Birthdate, occupation, risk rating, marital status, … |

**DuckDB location:** `data/planbot/db/planbot.duckdb`

Schema (three tables):

```
clients(client_id PK, name, aum, cash_pct, region)
profiles(client_name PK, birthdate, occupation, risk_rating, …)
holdings(client_id, holding_idx PK, asset_class, region, market_value, …)
```

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

Cash drag penalises portfolios that sit on idle cash instead of earning a risk‑adjusted return.  “Cash” includes deposits **plus** Money Market Funds (holdings with `asset_class = "Cash"`).

```
k_cash = max(client_cash_pct, holdings_cash_market_value / aum)   # in ratio, 0‑1
s_cash = LinearInterpolate(k_cash, pivot)                          # flat extrapolation at edges
```

| k_cash | s_cash |
|-------:|-------:|
|   0.00 |      0 |
|   0.20 |      3 |
|   0.50 |      9 |
|   1.00 |     10 |

> If a client holds 30 % cash the raw score is interpolated between 0.20 → 3 and 0.50 → 9, yielding (3 + 9)/(0.5‑0.2) · 0.1 ≈ **4**.

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

> **Sector exposure** is defined in the original spec but **not yet implemented** — the holdings CSV does not carry a sector field.  When sector data becomes available (e.g., via Yahoo Finance enrichment), a fourth sub‑dimension `s_sector_exposure` can be added under `max(…)`.

---

### 3. Investment Experience (Active Management)

Proxies the client's willingness to accept portfolio rebalancing based on whether they already hold any investable assets.

```
s_active = has_fund ? has_fund_score : 0
```

| Condition | Score |
|-----------|------|
| Client holds ≥ 1 position with `asset_class ≠ "Cash"` | 3 |
| Otherwise | 0 |

> **Trade frequency** (`score_number_of_trading_ttm`) is defined in the original spec but **deferred** — no trade‑history feed is currently available.

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

The score card is accessible via **CLI** and **Python API**, with a **FastAPI HTTP endpoint** planned.

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

### 3. FastAPI (planned)

```
GET  /api/v1/investor-readiness/scores
GET  /api/v1/investor-readiness/scores?top_n=10
GET  /api/v1/investor-readiness/scores/{client_id}
POST /api/v1/investor-readiness/refresh          # rebuild DuckDB from CSVs
```

**Response shape (list endpoint):**

```json
{
  "generated_at": "2026-07-13T09:19:23Z",
  "total_clients": 23,
  "scores": [
    {
      "rank": 1,
      "client_id": "PB-HK-000001-8",
      "name": "David Kim",
      "total_score": 29.50,
      "s_cash": 8.00,
      "s_concentration": 10.00,
      "s_active": 3.00,
      "s_lifestage": 8.50
    }
  ]
}
```

**Single‑client endpoint** adds dimension detail:

```json
{
  "client_id": "PB-HK-000001-8",
  "total_score": 29.50,
  "dimensions": {
    "cash_drag":        { "k_cash": 0.56, "s_cash": 8.00 },
    "concentration":    { "k_single": 0.24, "k_region": 1.00, "k_asset": 0.63, "s_concentration": 10.00 },
    "active_manage":    { "has_fund": true, "s_active": 3.00 },
    "life_stage":       { "age": 42, "s_lifestage": 8.50 }
  }
}
```

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
| ETF/MF tag on holdings | ⚠️ Approximated | `has_fund` uses `asset_class ≠ "Cash"`; a dedicated `vehicle` column would be more precise |
| FastAPI endpoint | 🔜 Planned | See API section above |
| ML weight calibration | 🔮 Future | Requires labelled outcome data from bank |
| Incremental refresh | 🔮 Future | Currently full‑rebuild DuckDB from CSVs each run |