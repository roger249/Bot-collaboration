**Market Spot Reference (September 2026):**

* **USD/HKD Spot:** $7.8420$
* **GBP/USD Spot:** $1.3493$
* **AUD/USD Spot:** $0.7167$

A **Target Redemption Forward (TRF)** allows an investor to buy or sell a base currency at a Strike Rate more favourable than the prevailing spot, with a capped total payout. Once the accumulated gain reaches the designated **Target Profit (Redemption Target)**, the structure terminates automatically (**Knocks Out**).

If the spot moves against the Strike Rate, the investor takes delivery at $2\times$ leverage on fixing days without a target cap protecting downside exposure.

---

### Key Structuring Parameters & Target Cap Mechanics

* **Target Profit Cap (Target Amount):** Stated as either a fixed currency value or pips per fixing (e.g., $100\text{ pips} \times \text{Notional}$ or $2.00\text{--}3.50\%$ of Total Notional).
* **Guaranteed Period:** 1 to 2 months of initial fixings are often protected against early termination regardless of target accumulation.
* **Pricing Dynamic:** A higher target level or longer duration allows for a wider (more favourable) strike rate.

---

## Sample Target Redemption Forward Terms

### 1. USD/HKD (Buying USD / Selling HKD)

| Trade Parameter | 6-Month USD/HKD TRF | 1-Year USD/HKD TRF |
| --- | --- | --- |
| **Spot Reference** | $7.8420$ | $7.8420$ |
| **Strike Rate (Discount)** | **$7.8340$** (~$0.10\%$ discount) | **$7.8290$** (~$0.17\%$ discount) |
| **Target Redemption Cap** | **HKD $150,000$** (~$1.0\%$ total return cap) | **HKD $300,000$** (~$2.0\%$ total return cap) |
| **Guaranteed Period** | First 1 Month (20 Fixings) | First 2 Months (40 Fixings) |
| **Gearing / Leverage** | $2\times$ below Strike | $2\times$ below Strike |
| **Fixing Frequency** | Daily (126 trading days) | Daily (252 trading days) |
| **Daily Base Notional** | USD $100,000$ | USD $100,000$ |

### 2. GBP/USD (Selling GBP / Buying USD)

*Profile: Importer / Base Currency Seller (Selling GBP / Buying USD)*

| Parameter | 4-Month Tenor | 6-Month Tenor |
| --- | --- | --- |
| **Current Spot Reference** | **1.3493** | **1.3493** |
| **Notional per Fixing** | GBP 1,000,000 | GBP 1,000,000 |
| **Fixing Frequency** | 4 Monthly Fixings | 6 Monthly Fixings |
| **Enhanced Strike ($K$)** | **1.3590** *(~97 pips above spot)* | **1.3620** *(~127 pips above spot)* |
| **Knock-Out Target ($T$)** | **250 pips** (USD 25,000 total gain) | **400 pips** (USD 40,000 total gain) |
| **Guaranteed Period** | First 1 Month (1 Fixing) | First 2 Months (2 Fixings) |
| **Favourable Payoff ($S_i < K$)** | Sell GBP at $K$; accrue gain $(K - S_i)$ | Sell GBP at $K$; accrue gain $(K - S_i)$ |
| **Leveraged Obligation ($S_i > K$)** | **Sell 2x Notional** (GBP 2M) at $K$ | **Sell 2x Notional** (GBP 2M) at $K$ |
| **Early Termination** | Knocks out when cumulative gain $\ge T$ | Knocks out when cumulative gain $\ge T$ |

### 3. AUD/USD (Selling AUD / Buying USD)

*Profile: Importer / Base Currency Seller (Selling AUD / Buying USD)*

| Parameter | 4-Month Tenor | 6-Month Tenor |
| --- | --- | --- |
| **Current Spot Reference** | **0.7167** | **0.7167** |
| **Notional per Fixing** | AUD 1,000,000 | AUD 1,000,000 |
| **Fixing Frequency** | 4 Monthly Fixings | 6 Monthly Fixings |
| **Enhanced Strike ($K$)** | **0.7225** *(~58 pips above spot)* | **0.7250** *(~83 pips above spot)* |
| **Knock-Out Target ($T$)** | **150 pips** (USD 15,000 total gain) | **250 pips** (USD 25,000 total gain) |
| **Guaranteed Period** | First 1 Month (1 Fixing) | First 2 Months (2 Fixings) |
| **Favourable Payoff ($S_i < K$)** | Sell AUD at $K$; accrue gain $(K - S_i)$ | Sell AUD at $K$; accrue gain $(K - S_i)$ |
| **Leveraged Obligation ($S_i > K$)** | **Sell 2x Notional** (AUD 2M) at $K$ | **Sell 2x Notional** (AUD 2M) at $K$ |
| **Early Termination** | Knocks out when cumulative gain $\ge T$ | Knocks out when cumulative gain $\ge T$ |

---

### Key Structural Dynamics of Shorter Tenors

* **Tighter Strike Spreads:** Because a 4-month or 6-month structure has fewer fixing dates, there is less time to accumulate option premium. As a result, the enhanced strike ($K$) sits closer to spot compared to a 12-month structure.
* **Lower Cumulative Target Caps:** The Target Cap ($T$) is adjusted downward proportionately to reflect the shorter duration and lower total potential gain before knockout.
* **Leverage Impact:** If spot rises above $K$ on any monthly fixing date, the 2x leverage requires settling double the monthly notional at the strike rate ($K$).