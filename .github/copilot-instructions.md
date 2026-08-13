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
- OpenAPI source of truth: `docs/prod_spec/tool/openapi.json`
- Concise endpoint index: `docs/prod_spec/tool/endpoint_index.md`
- Client API functional notes: `docs/prod_spec/tool/client_tool.md`
- Product API functional notes: `docs/prod_spec/tool/product_tool.md`
- Runtime integration implementation: `src/integrations`
- Scorecard source docs: `docs/prod_spec/score_card/investor_readiness_score.md`, `docs/prod_spec/score_card/product_fitness_score.md`
- When generating or modifying integration code, follow OpenAPI schema and operation IDs first; treat prose docs as supplementary.

# Database Schema and Test Data
- Single DuckDB file: `data/planbot/db/planbot.duckdb`
- Schema documentation (source of truth):
  - Product catalog: `docs/prod_spec/product_schema/product_catalog_schema.md`
  - Client & holdings: `docs/prod_spec/product_schema/client_holdings_schema.md`
- Seeder scripts:
  - Product catalog: `src/test_data/product_catalog_seed.py`
  - Client/holdings ETL: `src/planbot/investor_readiness_score.py`
- Rule: **Any schema change must be applied to all three layers synchronously:**
  1. DuckDB schema (ALTER TABLE / seeder CREATE TABLE)
  2. Test data (seeder scripts must populate new columns with realistic values)
  3. API contract (`docs/prod_spec/tool/openapi.json` and downstream API code in `src/integrations`)
- Documentation (`docs/prod_spec/product_schema/*.md` and `docs/prod_spec/tool/*.md`) must stay aligned with the live DuckDB schema.


# Regression Test

The test in the suite file:///Users/roger/Documents/GitHub/Bot%20collaboration@@vsc@@/Users/roger/Documents/GitHub/Bot collaboration/tests/test_proposal_API.py is a regression test that uses for end-to-end test.  It shall be executed whenever significant changes are made to the integration code but they're also very slow.  The test is designed to validate the following API endpoints:

/api/v1/reinvestment-proposals/propose_reinvestment_for_maturing_holdings
/api/v1/product-opportunity-proposal
/api/v1/product-opportunity-proposal-automatch