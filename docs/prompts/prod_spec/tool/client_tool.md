Client tool
===========

API

# filter_by_id

# filter
risk_rating
age
product_types_in_holdings
concentration_score
cash_score


# Schema

Client_id
Client Name
Birthdate
Occupation
Risk Rating
Marital Status
Children Info
Income Stability
Investment experience
Needs:
    retirement:
        basic:
            target_date:
            amount:
            outstanding_amount:
        wants:
            target_date:
            amount:
            outstanding_amount:
    mortgage_down_payment:
        target_date:
        amount:
        outstanding_amount:


## Needs classification

Essential / Non-Negotiable (Needs): Housing, core living expenses, healthcare, basic retirement income. Input target: High certainty, near-zero tolerance for permanent capital loss.

Target Lifestyle (Wants): Early retirement padding, buying a secondary property, funding a specific education milestone. Input target: Moderate flexibility; willing to accept structural volatility for higher expected returns.

Aspirational / Legacy (Wishes): Intergenerational wealth transfer, angel investing, high-impact philanthropy. Input target: Maximum risk tolerance; can tolerate complete illiquidity or deep drawdowns.
