# Overview of product catalog

Product catalog serves two main purpose

- Provide the information to the investor on screen or as a summary pdf
- Provide LLM to find the required product characteristics during investment suggestion such as
  - Portfolio optimization
  - Reinvestment advice

# Product schema

The following fields are used for product classification

```yaml

# =============================================================================
# CATEGORY 1: GENERAL (Universal Identifiers & Cross-Asset Fallbacks)
# Priority 1 for query engine. Every single instrument populates these.
# =============================================================================
general:
  - product_id                # Unique internal bank key
  - isin                      # Universal global identifier (e.g., US1234567890)
  - name                      # Full legal/marketing name of instrument
  - ticker                    # Vendor ticker (Bloomberg, RIC, HKEX code)
  - trading_currency          # Settlement ISO currency code (e.g., HKD, USD)
  - risk_rating               # Internal numeric risk tier score
  - expected_return           # Projected performance / yield baseline (decimal format)
  - region                    # Macro geographic exposure (e.g., APAC, EMEA, Global)
  - country                   # Specific primary risk country code
  - sector                    # Top-level industry category (e.g., Technology, Financials)
  - remarks                   # Free text or links to supporting documentation
  - product_type              # Links directly to CATEGORY 2 keys
  - vehicle                   # Wrapper tag (e.g., Direct, ETF, Mutual Fund, Structure)

# =============================================================================
# CATEGORY 2: ASSET_CLASSIFICATION (Underlying Risk & Market Exposure Parameters)
# Priority 2 for query engine. Defines WHAT market forces drive performance.
# =============================================================================
product_type:
  # === CASH & CASH EQUIVALENTS ===
  money_market_fund:
    - nav                     # Net Asset Value per share
    - yield_type              # current, effective, 7-day
    - credit_quality          # government, prime, municipal
    - maturity_profile        # ultra_short, short, medium
    - dividend_treatment      # accumulating, distributing

  cash:
    - interest_rate_type      # fixed, variable
    - interest_payout_frequency # monthly, quarterly, at_maturity
    - term_days
    - is_callable             # Boolean
    - insured                 # Boolean

  deposit:
    - interest_rate_type      # fixed, variable
    - interest_payout_frequency # monthly, quarterly, at_maturity
    - term_days
    - early_withdrawal_allowed # Boolean
    - insured                 # Boolean
    - minimum_deposit

  # === FIXED INCOME ===
  bond:
    - issuer_name
    - issuer_sector           # government, corporate, municipal, sovereign, agency
    - issuer_country
    - coupon_type             # fixed, floating, zero_coupon, inflation_linked
    - coupon_rate             # Exact percentage in decimal format (e.g., 0.045)
    - coupon_frequency        # monthly, quarterly, semi-annual, annual
    - day_count_convention    # act_360, act_365, thirty_360
    - credit_rating           # AAA, AA, A, BBB, BB, etc.
    - maturity                # Explicit calendar date
    - seniority               # senior, subordinated, junior
    - callable                # Boolean
    - puttable                # Boolean
    - convertible             # Boolean
    - green_bond              # Boolean
    - sukuk                   # Boolean

  # === EQUITY ===
  stock:
    - company_name
    - industry                # Sub-sector granularity
    - exchange                # HKEX, NYSE, NASDAQ, etc.
    - lot_size                # Critical for HKEX (e.g., 100, 500 shares per board lot)
    - market_cap              # Absolute value for dynamic size queries
    - dividend_paying         # Boolean
    - dividend_yield          # Exact yield in decimal format (e.g., 0.032)

  bond_fund:
    - provider                # Asset management house
    - nav                     # Net Asset Value
    - expense_ratio           # Decimal flat rate
    - share_class             # retail, institutional, accumulating, distributing
    - strategy_summary        # Explicit text for LLM/RAG embedding lookups
    - dividend_frequency      # monthly, quarterly, annual, accumulating
    - aum                     # Total vehicle assets value
    - strategy                # growth, value, income, balanced
    - theme                   # ESG, technology, healthcare, emerging markets
    - domicile                # Legal incorporation jurisdiction (e.g., Luxembourg, Ireland)
    - rebalancing_frequency   # monthly, quarterly, semi-annual, annual
    - dividend_treatment      # accumulating, distributing
    - pricing:                # Corrected nested mapping syntax for parsers
        - ytm                 # Yield to Maturity (decimal)
        - yield_to_worst    
        - effective_duration
        - option_adjusted_spread
        - weighted_average_duration
        - weighted_average_coupon

  equity_fund:
    - provider                # ETF / Fund Issuer
    - nav                     # Net Asset Value
    - strategy_summary        # Explicit text for LLM/RAG embedding lookups
    - replication_method      # physical, synthetic, sampling
    - ter                     # Total Expense Ratio (decimal)
    - domicile
    - aum
    - dividend_treatment      # accumulating, distributing
    - dividend_frequency      # monthly, quarterly, annual, accumulating

  # === MIXED / ALLOCATION ===
  balanced_fund:
    - provider
    - nav
    - strategy_summary        # Explicit text for LLM/RAG embedding lookups
    - equity_exposure         # Target allocation decimal (e.g., 0.60)
    - fixed_income_exposure   # Target allocation decimal (e.g., 0.30)
    - cash_exposure           # Target allocation decimal (e.g., 0.05)
    - alternative_exposure    # Target allocation decimal (e.g., 0.05)
    - investment_style        # growth, value, core
    - risk_profile            # conservative, moderate, aggressive
    - dividend_treatment      # accumulating, distributing

  # === STRUCTURED PRODUCTS ===
  structured_product:
    - sub_type                # FCN, CMT RA, ELI/ELN, FX Accumulator, Autocallable
    - provider                # Issuing Desk/Counterparty
    - principal_protection    # full, partial, none
    - capital_at_risk         # Absolute limit or ratio (0.00 to 1.00)
    - underlying_asset_type   # equity, fx, index, commodity, interest_rate, basket
    - underlying_assets       # Array of specific tickers/underlyings
    - basket_type             # worst_of, best_of, average, rainbow
    - strike_level            # Initial reference/strike price or percentage
    - knock_in_level          # Downside protection barrier (e.g., 0.70)
    - knock_out_level         # Autocall trigger barrier (e.g., 1.05)
    - coupon_type             # fixed, conditional, range_accrual, none
    - coupon_frequency        # monthly, quarterly, semi-annual, annual
    - barrier_type            # european, american, daily
    - autocallable            # Boolean
    - early_redemption        # Boolean
    - coupon_rate             # Stated structural coupon rate
    - participation_rate      # Upside multiplier if applicable
    - payout_structure        # Descriptive text for internal or LLM reference
    - expiry                  # Contractual duration until maturity


  # Below product type is reserved for the future and no implementation/planning on them for now.

  # === INSURANCE ===
  insurance:
    - insurance_type          # life, term, whole, critical_illness, annuity
    - provider                # Insurance underwriting carrier
    - description.            # Explicit text for LLM/RAG embedding lookups
    - premium_mode            # single, annual, quarterly, monthly
    - premium_amount
    - coverage_amount
    - term_years              # Term duration if applicable
    - payout_frequency        # monthly, quarterly, annually
    - surrender_charge_schedule
    - tax_qualifying          # Boolean (e.g., QDAP compliance check)    

    # === ANNUITY ===
    - annuity:
      - annuity_type            # immediate, deferred, fixed, variable, indexed
      - premium_type            # single, installment
      - payout_start_age
      - guaranteed_period_years # Absolute years number
      - inflation_protected     # Boolean
      - death_benefit           # Boolean
      - government_backed       # Boolean

  # === FX ===
  fx:
    - currency_pair           # e.g., EUR/USD, USD/JPY, GBP/USD
    - base_currency
    - quote_currency
    - spot_rate               # Current baseline rate value
    - forward_available       # Boolean
    - deliverable             # Boolean
    - settlement_type         # cash, physical
    - volatility_score        # Numerical index value or volatility percentage
    - central_bank_intervention_risk # low, medium, high

  # === PRECIOUS METAL ===
  precious_metal:
    - metal_type              # gold, silver, platinum, palladium
    - form                    # physical, etf, futures, options, certificate
    - purity                  # Fine purity metric (e.g., 0.9999)
    - storage_available       # Boolean
    - vault_location          # Geographic repository location

  # === OPTION ===
  option:
    - asset_class             # fx, equity
    - exchange
    - type                    # call, put
    - strike_price            # Absolute calculation value
    - moneyness_ratio         # e.g., 0.95 or 1.05 of spot
    - expiry_date             # Explicit expiration timestamp or calendar date

  # === CRYPTO ===
  crypto:
    - category                # coin, token, stablecoin, defi, memecoin, layer1, layer2
    - blockchain              # Native network
    - proof_type              # PoW, PoS, PoA
    - market_cap              # Continuous currency valuation
    - circulating_supply
    - max_supply              # Numeric cap; null if uncapped
    - listed_exchanges_count  # Integer threshold
    - usd_pegged              # Boolean
    - staking_available       # Boolean
    - regulatory_status       # approved, restricted, unregulated
    - volatility_score        # Calculated standard deviation metric
    - correlation_to_btc      # Correlation coefficient value (-1.00 to 1.00)

  # === INVESTMENT FUNDS / COLLECTIVES ===
  unit_trust:
    - provider
    - nav
    - strategy
    - domicile
    - aum
    - trust_deed_date
    - dividend_frequency      # monthly, quarterly, annual, accumulating

  hedge_fund:
    - strategy                # long/short, global macro, event-driven, relative value
    - provider                # Fund management house
    - domicile                # Cayman Islands, Delaware, Ireland
    - lock_up_period_years    # Numeric years duration
    - redemption_frequency    # monthly, quarterly, annually
    - redemption_notice_days
    - high_water_mark         # Boolean
    - hurdle_rate             # Decimal hurdle baseline
    - incentive_fee           # Performance carry (decimal)
    - management_fee          # Flat run rate (decimal)
    - aum
    - prime_broker
    - administrator

  private_equity:
    - strategy                # buyout, growth, venture, distressed, secondaries
    - provider                # General Partner (GP) house
    - domicile
    - vintage_year            # Fund inception year (integer)
    - fund_size               # Total committed capital value
    - commitment_period_years
    - fund_life_years
    - management_fee
    - carried_interest
    - hurdle_rate
    - aum
    - irr                     # Internal Rate of Return performance metric
    - tvpi                    # Total Value to Paid-In capital ratio


    ```