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
- Preserve major functionality (artifacts, stop/decision behavior, required output sections).
- Minor compatibility drift is acceptable only if TCO or code size improves.
- Validate phase exit criteria before merge (no runtime error, required outputs present, no empty required sections).
- Keep changes reversible at code level even if rollback is not required.
- Document new dependencies/runtime prerequisites in requirements and setup notes.

# API Contract Sources for Coding
- OpenAPI source of truth: `docs/prod_spec/tool/openapi.json`
- Concise endpoint index: `docs/prod_spec/tool/endpoint_index.md`
- Client API functional notes: `docs/prod_spec/tool/client_tool.md`
- Product API functional notes: `docs/prod_spec/tool/product_tool.md`
- Runtime integration implementation: `src/integrations`
- Scorecard source docs: `docs/prod_spec/score_card/investor_readiness_score.md`, `docs/prod_spec/score_card/product_fitness_score.md`
- When generating or modifying integration code, follow OpenAPI schema and operation IDs first; treat prose docs as supplementary.