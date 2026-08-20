# General
- Don't start any new implementation for a specification until authorization from user.
- If outstanding issues found in reviewing a specification, add a section at the end of the spec and number those issues for further discuss with users.
- If a design is agreed by user for the outstanding issues, put the design in the corresponding section in the specification, and remove the issue from the list of outstanding issues.

# Standard
- Parameters (output filename, ai provider, prompts) shall be externalized to a yaml configuration

# Unit test
- Python unittest shall be used to build unit test
- Basic have two unit tests - one normal flow and one on exception condition
- These two serve as the minimal regression test after major code changes.

# Logging
- All logging should be done via the python logging module
- Good for different modules to use different logger.
- Logging configuration shall be externalized and defined in the config/config.yaml
- Standard log file shall be put in log/root.log
- Logging to file will have hte file overwritten for every new execution.  This behavior will be changed in production.
- No print statement shall be used throughout the code

# Migration
- Minor compatibility drift is acceptable only if TCO or code size improves.
- Validate phase exit criteria before merge (no runtime error, required outputs present, no empty required sections).
- Document new dependencies/runtime prerequisites in requirements and setup notes.

# API Contract Sources for Coding
- OpenAPI source of truth: `docs/specification/data_api/openapi_data.json` (bank data server) and `docs/specification/data_api/openapi_proposal.json` (proposal server)
- Concise endpoint index: `docs/specification/data_api/endpoint_index.md`
- Client API functional notes: `docs/specification/data_api/client_api.md`
- Product API functional notes: `docs/specification/data_api/product_api.md`
- Runtime integration implementation: `src/integrations`
- Scorecard source docs: `docs/specification/scorecard/investor_readiness_score.md`, `docs/specification/scorecard/product_fitness_score.md`
- When generating or modifying integration code, follow OpenAPI schema and operation IDs first; treat prose docs as supplementary.
- Regenerate the OpenAPI specs after endpoint changes with `./.venv/bin/python scripts/export_openapi.py`.

# Database Schema and Test Data
- Single DuckDB file: `data/planbot/db/planbot.duckdb`
- Schema documentation (source of truth):
  - Product catalog: `docs/specification/schema_product/product_catalog_schema.md`
  - Client & holdings: `docs/specification/schema_client/client_holdings_schema.md`
- Seeder scripts:
  - Product catalog: `src/test_data/product_catalog_seed.py`
  - Client/holdings ETL: `src/test_data/client_seed.py`
- ⚠️ The live DuckDB may contain **manual edits** not reproducible from seeders.  The product-catalog seeder (`product_catalog_seed.py`) is **destructive** — it `DELETE FROM products` and re-fetches Yahoo market data, overwriting manual edits to `expected_return`/`risk_rating`/`performance_history` and adding spurious ticker rows.  For a column-only change (e.g. `investment_note`), prefer a targeted `UPDATE` over a full re-seed; if a re-seed is unavoidable, snapshot the DB first (`git show HEAD:data/planbot/db/planbot.duckdb`) and restore every column except the intended one afterward.
- The `embeddings` table is a **derived cache** (never a source of truth) written by `src/planbot/embeddings_store.py`; it is safe to `DELETE FROM embeddings` (it regenerates lazily).  Semantic-embedding config lives in `config/config_screener.yaml` (not `config_planbot.yaml`).
- Rule: **Any schema change must be applied to all three layers synchronously:**
  1. DuckDB schema (ALTER TABLE / seeder CREATE TABLE)
  2. Test data (seeder scripts must populate new columns with realistic values)
  3. API contract (`docs/specification/data_api/openapi_data.json` via `scripts/export_openapi.py`, and downstream API code in `src/integrations`)
- Documentation (`docs/specification/schema_product/*.md`, `docs/specification/schema_client/*.md` and `docs/specification/data_api/*.md`) must stay aligned with the live DuckDB schema.


# Regression Test

The test in the suite file:///Users/roger/Documents/GitHub/Bot%20collaboration@@vsc@@/Users/roger/Documents/GitHub/Bot collaboration/tests/test_proposal_API.py is a regression test that uses for end-to-end test.  It shall be executed whenever significant changes are made to the integration code but they're also very slow.  The test is designed to validate the following API endpoints:

/api/v1/reinvestment-proposals/propose_reinvestment_for_maturing_holdings
/api/v1/product-opportunity-proposal
/api/v1/product-opportunity-proposal-automatch