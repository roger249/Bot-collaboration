**Market Spot Reference (September 2026):**

* **USD/HKD Spot:** $7.8420$ (Pegged Band: $7.7500 - 7.8500$)
* **EUR/USD Spot:** $1.1598$

An FX Accumulator allows an investor to buy a primary currency against a secondary currency at a strike discount to the prevailing spot rate, provided the pair stays below a designated Knock-Out (KO) barrier. If spot drops below the strike, the investor takes delivery at $1\times$ or $2\times$ leverage (Gearing) per fixing day.

---

### Key Structuring Dynamics

* **USD/HKD Considerations:** Because USD/HKD trades inside HKMA's strict $7.7500 - 7.8500$ Linked Exchange Rate System, downside risk for buying USD is capped near $7.7500$, while upside KO barriers are bounded by $7.8500$. This tight volatility compresses the available strike discount.
* **EUR/USD Considerations:** Free-floating currency with higher implied volatility, yielding wider strike discounts and higher KO barriers.

---

### Sample FX Accumulator Terms

#### 1. USD/HKD Accumulators (Buying USD / Selling HKD)

| Trade Parameter | 3-Month USD/HKD Accumulator | 6-Month USD/HKD Accumulator |
| --- | --- | --- |
| **Spot Reference** | $7.8420$ | $7.8420$ |
| **Strike Rate (Discount)** | **$7.8320$** (~$0.13\%$ discount) | **$7.8280$** (~$0.18\%$ discount) |
| **Knock-Out (KO) Level** | **$7.8490$** (~$108\%$ of discount window) | **$7.8495$** (~$108\%$ of discount window) |
| **Guaranteed Period** | First 1 Month (20 Fixings) | First 1 Month (20 Fixings) |
| **Gearing / Leverage** | $2\times$ below Strike | $2\times$ below Strike |
| **Fixing Frequency** | Daily (Approx. 63 trading days) | Daily (Approx. 126 trading days) |
| **Notional per Day** | USD $50,000$ | USD $50,000$ |

---

#### 2. EUR/USD Accumulators (Buying EUR / Selling USD)

| Trade Parameter | 3-Month EUR/USD Accumulator | 6-Month EUR/USD Accumulator |
| --- | --- | --- |
| **Spot Reference** | $1.1598$ | $1.1598$ |
| **Strike Rate (Discount)** | **$1.1380$** (~$1.88\%$ discount) | **$1.1290$** (~$2.65\%$ discount) |
| **Knock-Out (KO) Level** | **$1.1780$** (+ $1.57\%$ above spot) | **$1.1890$** (+ $2.52\%$ above spot) |
| **Guaranteed Period** | 10 Trading Days | 15 Trading Days |
| **Gearing / Leverage** | $2\times$ below Strike | $2\times$ below Strike |
| **Fixing Frequency** | Daily (Approx. 63 trading days) | Daily (Approx. 126 trading days) |
| **Notional per Day** | EUR $50,000$ | EUR $50,000$ |

---

### Scenario Analysis (3-Month EUR/USD Example)

Using **Spot = $1.1598$**, **Strike = $1.1380$**, **KO = $1.1780$**, **Daily Base = EUR $50,000$**:

* **Scenario A (Spot trades between $1.1380$ and $1.1780$):**
Investor buys EUR $50,000$ per day at the discounted strike of $1.1380$, realizing an immediate paper gain against prevailing spot.
* **Scenario B (Spot reaches or exceeds $1.1780$ - Knock Out):**
The contract terminates immediately for all remaining fixings (subject to any prior guaranteed period). The investor keeps all EUR accumulated up to the KO date.
* **Scenario C (Spot falls below $1.1380$):**
The $2\times$ gearing triggers. The investor is obligated to buy EUR $100,000$ per day at the strike of $1.1380$, accumulating loss as spot drops further.

**USD/JPY Spot Reference:** $\approx 157.67$

### Structuring Dynamics for USD/JPY

Because USD/JPY exhibits higher implied volatility than pegged pairs like USD/HKD, the available strike discount is wider, and Knock-Out (KO) levels are placed further out to balance the barrier risk. Additionally, the significant short-term interest rate differential between USD and JPY introduces negative carry for holding JPY against USD, which directly enhances the pricing for buying USD (or selling USD) in accumulator structures.

Below are structured sample terms for buying USD against JPY (USD Accumulator / JPY Deculator) and buying JPY against USD (JPY Accumulator / USD Deculator).

---

### Sample FX Accumulator Terms

#### 1. USD Accumulators (Buying USD / Selling JPY)

| Trade Parameter | 3-Month USD/JPY Accumulator | 6-Month USD/JPY Accumulator |
| --- | --- | --- |
| **Spot Reference** | $157.67$ | $157.67$ |
| **Strike Rate (Discount)** | **$154.20$** (~$2.20\%$ discount) | **$152.80$** (~$3.09\%$ discount) |
| **Knock-Out (KO) Level** | **$160.80$** (+ $1.98\%$ above spot) | **$162.50$** (+ $3.06\%$ above spot) |
| **Guaranteed Period** | First 10 Trading Days | First 15 Trading Days |
| **Gearing / Leverage** | $2\times$ below Strike | $2\times$ below Strike |
| **Fixing Frequency** | Daily (Approx. 63 trading days) | Daily (Approx. 126 trading days) |
| **Notional per Day** | USD $50,000$ | USD $50,000$ |

---

#### 2. JPY Accumulators (Buying JPY / Selling USD)

| Trade Parameter | 3-Month JPY/USD Accumulator | 6-Month JPY/USD Accumulator |
| --- | --- | --- |
| **Spot Reference** | $157.67$ | $157.67$ |
| **Strike Rate (Discount)** | **$161.10$** (~$2.18\%$ discount on JPY) | **$162.80$** (~$3.25\%$ discount on JPY) |
| **Knock-Out (KO) Level** | **$154.50$** (- $2.01\%$ below spot) | **$152.90$** (- $3.03\%$ below spot) |
| **Guaranteed Period** | First 10 Trading Days | First 15 Trading Days |
| **Gearing / Leverage** | $2\times$ above Strike (when USD/JPY rises) | $2\times$ above Strike (when USD/JPY rises) |
| **Fixing Frequency** | Daily (Approx. 63 trading days) | Daily (Approx. 126 trading days) |
| **Notional per Day** | JPY $7,500,000$ | JPY $7,500,000$ |

---

### Scenario Analysis (3-Month USD/JPY Accumulator - Buying USD)

Using **Spot = $157.67$**, **Strike = $154.20$**, **KO = $160.80$**, **Daily Base = USD $50,000$**:

* **Scenario A (Spot trades between $154.20$ and $160.80$):**
The contract remains active. The investor accumulates USD $50,000$ each fixing day at the discounted rate of $154.20$ JPY per USD, securing a favorable entry relative to market spot.
* **Scenario B (Spot reaches or exceeds $160.80$ - Knock Out):**
The contract terminates immediately for all remaining fixings (outside guaranteed days). Accumulation stops, and the investor retains all USD accumulated up to the event date.
* **Scenario C (Spot falls below $154.20$):**
The $2\times$ gearing mechanism triggers. The investor is obligated to buy USD $100,000$ per day at the strike price of $154.20$, resulting in mark-to-market unrealized losses as USD/JPY moves lower.