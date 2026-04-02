# Standard
- Parameters (output filename, ai provider, prompts) shall be externalized to a yaml configuration

# Unit test
- Python unittest shall be used to build unit test
- Basic have two unit test - one normal flow and one on exception condition

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