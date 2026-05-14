from __future__ import annotations

import logging
import logging.config
from logging.handlers import RotatingFileHandler
from pathlib import Path


_LAST_LOG_FILE: Path | None = None
_LAST_CHAT_HISTORY_LOG_FILE: Path | None = None


def _configure_chat_history_logger(
    chat_history_log_file: Path,
    enabled: bool,
    max_bytes: int,
    backup_count: int,
) -> None:
    logger = logging.getLogger("chat_history")

    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    if not enabled:
        logger.disabled = True
        logger.propagate = False
        return

    logger.disabled = False
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    handler = RotatingFileHandler(
        chat_history_log_file,
        maxBytes=max(0, max_bytes),
        backupCount=max(0, backup_count),
        encoding="utf-8",
    )
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(handler)


def configure_logging(
    level: str,
    log_file: Path,
    chat_history_log_file: Path,
    config_file: Path | None = None,
    chat_history_enabled: bool = True,
    chat_history_max_bytes: int = 5_000_000,
    chat_history_backup_count: int = 5,
) -> None:
    global _LAST_LOG_FILE, _LAST_CHAT_HISTORY_LOG_FILE

    log_file.parent.mkdir(parents=True, exist_ok=True)
    chat_history_log_file.parent.mkdir(parents=True, exist_ok=True)

    resolved_log_file = log_file.resolve()
    resolved_chat_history_file = chat_history_log_file.resolve()

    # Reuse existing logger setup when targets are unchanged.
    if (
        _LAST_LOG_FILE == resolved_log_file
        and _LAST_CHAT_HISTORY_LOG_FILE == resolved_chat_history_file
        and logging.getLogger().handlers
    ):
        _configure_chat_history_logger(
            chat_history_log_file,
            enabled=chat_history_enabled,
            max_bytes=chat_history_max_bytes,
            backup_count=chat_history_backup_count,
        )
        return

    if config_file is not None and config_file.exists():
        logging.config.fileConfig(
            config_file,
            defaults={
                "log_level": level.upper(),
                "log_file": str(log_file),
                "chat_history_log_file": str(chat_history_log_file),
            },
            disable_existing_loggers=False,
        )
        _configure_chat_history_logger(
            chat_history_log_file,
            enabled=chat_history_enabled,
            max_bytes=chat_history_max_bytes,
            backup_count=chat_history_backup_count,
        )
        _LAST_LOG_FILE = resolved_log_file
        _LAST_CHAT_HISTORY_LOG_FILE = resolved_chat_history_file
        return

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    _configure_chat_history_logger(
        chat_history_log_file,
        enabled=chat_history_enabled,
        max_bytes=chat_history_max_bytes,
        backup_count=chat_history_backup_count,
    )
    _LAST_LOG_FILE = resolved_log_file
    _LAST_CHAT_HISTORY_LOG_FILE = resolved_chat_history_file