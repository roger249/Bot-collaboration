from __future__ import annotations

import logging
import logging.config
from pathlib import Path

_INITIALIZED: bool = False

_LOGGER = logging.getLogger(__name__)


def init_logging(ini_path: str | Path = "config/logging_config.ini") -> None:
    """Initialise logging from ``config/logging_config.ini``.

    - Creates the ``log/`` directory if it does not exist.
    - Idempotent: calling a second time is a no-op (handlers are not
      double-registered).
    - The ini must be self-contained — literal level values, no
      ``%(…)s`` placeholders.

    This is the *only* function in the codebase that calls
    ``logging.config.fileConfig``, ``logging.basicConfig``, or
    ``logging.FileHandler``.
    """
    global _INITIALIZED
    if _INITIALIZED and logging.getLogger().handlers:
        return

    ini = Path(ini_path)
    if not ini.is_absolute():
        # Resolve relative to project root (two dirs up from src/shared/).
        root = Path(__file__).resolve().parents[2]
        ini = root / ini

    if not ini.exists():
        _LOGGER.warning(
            "Logging config not found at %s — using basicConfig fallback", ini,
        )
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
        _INITIALIZED = True
        return

    # Ensure log/ directory exists (ini paths are relative to project root).
    log_dir = ini.parent.parent / "log"
    log_dir.mkdir(parents=True, exist_ok=True)

    logging.config.fileConfig(str(ini), disable_existing_loggers=False)
    _INITIALIZED = True
    _LOGGER.info("Logging initialized from %s", ini)