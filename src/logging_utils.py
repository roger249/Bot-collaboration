from __future__ import annotations

import logging
import logging.config
from pathlib import Path


def configure_logging(level: str, log_file: Path, config_file: Path | None = None) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    if config_file is not None and config_file.exists():
        logging.config.fileConfig(
            config_file,
            defaults={"log_level": level.upper(), "log_file": str(log_file)},
            disable_existing_loggers=False,
        )
        return

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )