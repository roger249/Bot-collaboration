## Needs (planned)

| `investment_objective` | `client_profile.csv` → `Investment Objective` | `string` | e.g. `"Long‑term capital growth"` |
| `liquidity_need` | `client_profile.csv` → `Liquidity Need` | `string` | e.g. `"Medium (12 months buffer)"`, `"Low (5‑year horizon)"` |


Goal‑based needs are a future extension and will nest under each client:

```yaml
needs:
  retirement:
    essential:                        # Non‑negotiable
      target_date: "YYYY-MM-DD"
      amount: float
      outstanding_amount: float
    wants:                            # Target lifestyle
      target_date: "YYYY-MM-DD"
      amount: float
      outstanding_amount: float
  mortgage_down_payment:
    target_date: "YYYY-MM-DD"
    amount: float
    outstanding_amount: float
  university_fund:
    target_date: "YYYY-MM-DD"
    amount: float
    outstanding_amount: float
  emergency_fund:
    target_date: null                 # always immediate
    amount: float
    outstanding_amount: float
```

> **Needs classification** (see below) determines certainty / risk tolerance per goal tier.

# Product API


## Needs classification

Essential / Non-Negotiable (Needs): Housing, core living expenses, healthcare, basic retirement income. Input target: High certainty, near-zero tolerance for permanent capital loss.

Target Lifestyle (Wants): Early retirement padding, buying a secondary property, funding a specific education milestone. Input target: Moderate flexibility; willing to accept structural volatility for higher expected returns.

Aspirational / Legacy (Wishes): Intergenerational wealth transfer, angel investing, high-impact philanthropy. Input target: Maximum risk tolerance; can tolerate complete illiquidity or deep drawdowns.
