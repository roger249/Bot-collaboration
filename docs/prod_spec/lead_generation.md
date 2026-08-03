# Lead Generation & Proposal Types

## Overview

The system generates three types of proposals, each triggered by a different
scenario. All three share a common downstream assembly pipeline that produces the
final investor-facing document (see `proposal_sections.md`).

| # | Proposal Type | Trigger | Direction |
|---|---|---|---|
| 1 | **Reinvestment Brief** | Existing holding reaches maturity; freed-up cash needs redeployment | Product → Client |
| 2 | **Product Opportunity Brief** | RM wants to push specific products to likely buyers | Product → Client |
| 3 | **Portfolio Optimization Proposal** | Periodic review or RM-initiated health check | Client → Product |

---

## 1. Reinvestment Brief

### Trigger
- A product in the client's portfolio approaches maturity or coupon payment,
  releasing capital.
- New cash injection that needs deployment.

### Process
1. Scan client portfolios for positions that will mature within a configurable
   window (e.g., 30 days).
2. Calculate freed-up cash amount per client.
3. Match each client against products with a **similar risk/return profile**
   to the maturing instrument (same asset class, comparable duration, adjacent
   credit rating).
4. Rank candidates and select the top recommendation.

### Input
- Client holdings database
- Product catalog with maturity dates and risk attributes

### Output
- A proposal that recommends what to buy with the freed-up capital, including
  funding source, expected return/risk shift, and alternatives (see
  `proposal_sections.md` §2–§6).

---

## 2. Product Opportunity Brief

### Trigger
- Relationship Manager selects a list of products — popular picks, bank
  promotions, or custom selection.
- System is asked: *"Which of my clients would be interested in these?"*

### Process
1. RM supplies a product shortlist.
2. System scores each client against the product list using:
   - Client risk profile and investment objectives
   - Existing portfolio composition (avoid duplication/concentration)
   - Historical transaction patterns and expressed preferences
3. Filter and rank clients by match quality.
4. Generate a per-client recommendation with rationale.

### Input
- RM-selected product list
- Client profiles and holdings database
- Product catalog

### Output
- Per-client proposal recommending the product, with allocation suggestion,
  pros/cons from portfolio perspective, and product specification (see
  `proposal_sections.md` §2–§7).

---

## 3. Portfolio Optimization Proposal

### Trigger
- Scheduled periodic portfolio review.
- RM-initiated holistic health check.

### Process
1. Load the client's full portfolio.
2. Evaluate across multiple dimensions:
   - **Better product selection** — are existing holdings still the best-in-class
     for their role?
   - **Concentration risk** — overexposure to single issuer, sector, or asset class.
   - **Cash drag** — idle cash that could be deployed.
   - **Goal-based alignment** — does the portfolio serve the client's stated goals?
3. Identify optimization opportunities.
4. Optionally apply efficient-frontier analysis to propose an improved
   risk/return allocation.
5. Generate actionable recommendations.

### Input
- Client profile, goals, and holdings
- Product catalog
- Market data (for scenario analysis)

### Output
- A comprehensive proposal covering all recommendation types: product swaps,
  reallocation, new positions, and risk mitigation (see `proposal_sections.md`
  §1–§11, the full TOC).

---

## Shared Pipeline: Proposal Assembly

All three proposal types feed into a common downstream Python pipeline that
composes the final investor-facing document:

1. **Portfolio return calculation** — computed from recommended trades, market
   data, and scenario assumptions.
2. **Scenario analysis** — adverse, base, and favourable market-condition
   projections.
3. **Risk disclaimer** — standard disclosures injected into every proposal.

The pipeline consumes a structured JSON payload (see
`proposal_JSON_output_s1.md`) and produces the final Markdown proposal
structured per `proposal_sections.md`.

---

## Relationship to Other Specs

| Document | Role |
|---|---|
| `proposal_sections.md` | Defines the TOC and section contents of the final proposal |
| `proposal_JSON_output_s1.md` | Structured JSON payload contract between matching engine and assembly pipeline |
| `product_client_matching.d2` | Visual diagram of the matching flow |
| `product_investor_matcher.md` | Detailed matching/scoring algorithm |

