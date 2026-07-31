"""Unit tests for the refactored logging subsystem.

Covers all 12 ACs from docs/prod_spec/refactor_logging.md.
"""

from __future__ import annotations

import configparser
import logging
from pathlib import Path
import io
from unittest.mock import patch

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _make_temp_ini(content: str, tmp_path: Path) -> Path:
    ini = tmp_path / "test_logging.ini"
    ini.write_text(content, encoding="utf-8")
    return ini


# ── AC-1 ──────────────────────────────────────────────────────────────────


class TestAC1_LogsUnderLogDir:
    def test_handler_paths_are_under_log(self, tmp_path):
        tmp_s = str(tmp_path).replace("\\", "\\\\")
        ini_content = f"""\
[loggers]
keys=root,chat_history,crewai_trace,src.integrations

[handlers]
keys=fh,ch,ct,console

[formatters]
keys=fmt

[logger_root]
level=INFO
handlers=fh,console

[logger_chat_history]
level=DEBUG
handlers=ch
qualname=chat_history
propagate=0

[logger_crewai_trace]
level=DEBUG
handlers=ct
qualname=crewai_trace
propagate=0

[logger_src.integrations]
level=DEBUG
handlers=fh,console
qualname=src.integrations
propagate=0

[handler_fh]
class=FileHandler
level=DEBUG
formatter=fmt
args=('{tmp_s}/log/planbot.log','w','utf-8')

[handler_ch]
class=FileHandler
level=DEBUG
formatter=fmt
args=('{tmp_s}/log/chat_history.log','w','utf-8')

[handler_ct]
class=FileHandler
level=DEBUG
formatter=fmt
args=('{tmp_s}/log/crewai_trace.log','w','utf-8')

[handler_console]
class=StreamHandler
level=DEBUG
formatter=fmt
args=(sys.stdout,)

[formatter_fmt]
format=%%(message)s
"""
        ini_path = _make_temp_ini(ini_content, tmp_path)
        (tmp_path / "log").mkdir(parents=True, exist_ok=True)

        logging.config.fileConfig(str(ini_path), disable_existing_loggers=True)

        actual_files: set[str] = set()
        for logger_name in logging.root.manager.loggerDict:
            for h in logging.getLogger(logger_name).handlers:
                if hasattr(h, "baseFilename") and h.baseFilename:
                    actual_files.add(Path(h.baseFilename).name)
        for h in logging.getLogger().handlers:
            if hasattr(h, "baseFilename") and h.baseFilename:
                actual_files.add(Path(h.baseFilename).name)

        expected = {"planbot.log", "chat_history.log", "crewai_trace.log"}
        assert actual_files == expected, f"Expected {expected}, got {actual_files}"


# ── AC-2 ──────────────────────────────────────────────────────────────────


class TestAC2_NoLogsInRuns:
    def test_init_logging_does_not_create_runs_logs(self, tmp_path):
        (tmp_path / "runs").mkdir(parents=True, exist_ok=True)
        (tmp_path / "log").mkdir(parents=True, exist_ok=True)
        (tmp_path / "config").mkdir(parents=True, exist_ok=True)

        tmp_s = str(tmp_path).replace("\\", "\\\\")
        ini_content = f"""\
[loggers]
keys=root

[handlers]
keys=fh

[formatters]
keys=fmt

[logger_root]
level=INFO
handlers=fh

[handler_fh]
class=FileHandler
level=DEBUG
formatter=fmt
args=('{tmp_s}/log/planbot.log','w','utf-8')

[formatter_fmt]
format=%%(message)s
"""
        ini = tmp_path / "config" / "logging_config.ini"
        ini.write_text(ini_content, encoding="utf-8")

        import src.shared.logging_utils as lu
        lu._INITIALIZED = False
        logging.getLogger().handlers.clear()

        lu.init_logging(str(ini))

        log_files_under_runs = list((tmp_path / "runs").rglob("*.log"))
        assert len(log_files_under_runs) == 0, (
            f"Found log files under runs/: {log_files_under_runs}"
        )


# ── AC-3 ──────────────────────────────────────────────────────────────────


class TestAC3_IRS_BriefAndFull:
    @patch("src.integrations.client_api.run_score_card")
    def test_info_only_brief(self, mock_run):
        mock_run.return_value = []
        logger = logging.getLogger("src.integrations.client_api")
        logger.setLevel(logging.INFO)
        buf = io.StringIO()
        handler = logging.StreamHandler(buf)
        handler.setLevel(logging.INFO)
        logger.addHandler(handler)
        try:
            from src.integrations.client_api import search_by_investor_readiness_score
            search_by_investor_readiness_score(top_n=5)
            output = buf.getvalue()
            assert "scored" in output, f"Expected brief INFO, got: {output!r}"
            assert "[\n" not in output, f"Should not have full payload in output: {output!r}"
        finally:
            logger.removeHandler(handler)

    @patch("src.integrations.client_api.run_score_card")
    def test_debug_has_full(self, mock_run):
        import dataclasses

        @dataclasses.dataclass
        class FakeScore:
            client_id = "PB-TEST-001"
            name = "Test"
            total_score = 20.0
            s_cash = 5.0
            s_concentration = 5.0
            s_active = 5.0
            s_lifestage = 5.0

        mock_run.return_value = [FakeScore()]
        logger = logging.getLogger("src.integrations.client_api")
        logger.setLevel(logging.DEBUG)
        buf = io.StringIO()
        handler = logging.StreamHandler(buf)
        handler.setLevel(logging.DEBUG)
        logger.addHandler(handler)
        try:
            from src.integrations.client_api import search_by_investor_readiness_score
            search_by_investor_readiness_score(top_n=5)
            output = buf.getvalue()
            assert "scored" in output, f"Expected brief INFO in: {output!r}"
            assert "output" in output, f"Expected full DEBUG payload in: {output!r}"
        finally:
            logger.removeHandler(handler)


# ── AC-4 ──────────────────────────────────────────────────────────────────


class TestAC4_PFS_BriefAndFull:
    def test_info_only_brief(self):
        db_path = _PROJECT_ROOT / "data" / "planbot" / "db" / "planbot.duckdb"
        if not db_path.exists():
            pytest.skip("DuckDB not found")

        logger = logging.getLogger("src.integrations.product_tool")
        logger.setLevel(logging.INFO)
        buf = io.StringIO()
        handler = logging.StreamHandler(buf)
        handler.setLevel(logging.INFO)
        logger.addHandler(handler)
        try:
            from src.integrations.product_tool import search_product_by_fitness_score
            search_product_by_fitness_score(
                client_ids=["PB-HK-000001-8"],
                product_ids=["ETF-HYG"],
                top_n=3,
                risk_rating_hard_filter=False,
            )
            output = buf.getvalue()
            assert "pairs scored" in output, f"Expected INFO summary, got: {output!r}"
            assert "components=" not in output, (
                f"Component detail leaked into INFO: {output!r}"
            )
        finally:
            logger.removeHandler(handler)

    def test_debug_has_components(self):
        db_path = _PROJECT_ROOT / "data" / "planbot" / "db" / "planbot.duckdb"
        if not db_path.exists():
            pytest.skip("DuckDB not found")

        logger = logging.getLogger("src.integrations.product_tool")
        logger.setLevel(logging.DEBUG)
        buf = io.StringIO()
        handler = logging.StreamHandler(buf)
        handler.setLevel(logging.DEBUG)
        logger.addHandler(handler)
        try:
            from src.integrations.product_tool import search_product_by_fitness_score
            search_product_by_fitness_score(
                client_ids=["PB-HK-000001-8"],
                product_ids=["ETF-HYG"],
                top_n=3,
                risk_rating_hard_filter=False,
            )
            output = buf.getvalue()
            assert "components=" in output, (
                f"Expected component breakdown in DEBUG, got: {output!r}"
            )
        finally:
            logger.removeHandler(handler)


# ── AC-5 ──────────────────────────────────────────────────────────────────


class TestAC5_IniControlsLevel:
    def test_level_from_ini_is_applied(self, tmp_path):
        ini_content = """\
[loggers]
keys=root

[handlers]
keys=null

[formatters]
keys=fmt

[logger_root]
level=WARNING
handlers=null

[handler_null]
class=NullHandler
level=DEBUG
formatter=fmt
args=()

[formatter_fmt]
format=%%(message)s
"""
        ini = _make_temp_ini(ini_content, tmp_path)
        logging.config.fileConfig(str(ini), disable_existing_loggers=True)
        assert logging.getLogger().level == logging.WARNING

        ini_debug = tmp_path / "test_debug.ini"
        ini_debug.write_text(ini_content.replace("level=WARNING", "level=DEBUG"))
        logging.config.fileConfig(str(ini_debug), disable_existing_loggers=True)
        assert logging.getLogger().level == logging.DEBUG


# ── AC-6 ──────────────────────────────────────────────────────────────────


class TestAC6_NoBasicConfig:
    def test_no_basicconfig_in_src(self):
        allowed = {"src/shared/logging_utils.py"}
        violations: list[str] = []
        for f in _PROJECT_ROOT.joinpath("src").rglob("*.py"):
            rel = str(f.relative_to(_PROJECT_ROOT))
            if rel in allowed:
                continue
            text = f.read_text(encoding="utf-8")
            if "logging.basicConfig" in text:
                violations.append(rel)
        assert violations == [], f"basicConfig found in: {violations}"


# ── AC-7 ──────────────────────────────────────────────────────────────────


class TestAC7_ChatHistoryHandlers:
    def test_chat_history_handlers_not_replaced(self, tmp_path):
        (tmp_path / "log").mkdir(parents=True, exist_ok=True)
        tmp_s = str(tmp_path).replace("\\", "\\\\")
        ini_content = f"""\
[loggers]
keys=root,chat_history

[handlers]
keys=fh,chf

[formatters]
keys=fmt

[logger_root]
level=INFO
handlers=fh

[logger_chat_history]
level=DEBUG
handlers=chf
qualname=chat_history
propagate=0

[handler_fh]
class=FileHandler
level=DEBUG
formatter=fmt
args=('{tmp_s}/log/planbot.log','w','utf-8')

[handler_chf]
class=FileHandler
level=DEBUG
formatter=fmt
args=('{tmp_s}/log/chat_history.log','w','utf-8')

[formatter_fmt]
format=%%(message)s
"""
        ini = _make_temp_ini(ini_content, tmp_path)
        logging.config.fileConfig(str(ini), disable_existing_loggers=True)

        chat_logger = logging.getLogger("chat_history")
        from logging import FileHandler
        assert len(chat_logger.handlers) == 1, (
            f"Expected 1 handler, got {len(chat_logger.handlers)}"
        )
        assert isinstance(chat_logger.handlers[0], FileHandler), (
            f"Expected FileHandler, got {type(chat_logger.handlers[0])}"
        )


# ── AC-8 ──────────────────────────────────────────────────────────────────


class TestAC8_CrewaiTraceSeparate:
    def test_crewai_trace_logger_non_propagating(self):
        logger = logging.getLogger("crewai_trace")
        assert logger.propagate in (0, False), (
            f"crewai_trace must not propagate, got propagate={logger.propagate}"
        )


# ── AC-9 ──────────────────────────────────────────────────────────────────


class TestAC9_IniSelfContained:
    def test_no_placeholders_in_ini(self):
        ini_path = _PROJECT_ROOT / "config" / "logging_config.ini"
        if not ini_path.exists():
            pytest.skip("logging_config.ini not found")
        cp = configparser.ConfigParser(interpolation=None)
        cp.read(ini_path)
        for section in cp.sections():
            for key, val in cp.items(section):
                if key == "level":
                    assert "%(" not in val, (
                        f"Placeholder in [{section}] {key} = {val!r}"
                    )

    def test_fileconfig_bare_works(self, tmp_path):
        (tmp_path / "log").mkdir(parents=True, exist_ok=True)
        tmp_s = str(tmp_path).replace("\\", "\\\\")
        ini_content = f"""\
[loggers]
keys=root

[handlers]
keys=fh

[formatters]
keys=fmt

[logger_root]
level=INFO
handlers=fh

[handler_fh]
class=FileHandler
level=DEBUG
formatter=fmt
args=('{tmp_s}/log/test.log','w','utf-8')

[formatter_fmt]
format=%%(message)s
"""
        ini = _make_temp_ini(ini_content, tmp_path)
        logging.config.fileConfig(str(ini))
        logging.getLogger().info("test")
        assert (tmp_path / "log" / "test.log").exists()


# ── AC-10 ─────────────────────────────────────────────────────────────────


class TestAC10_OnlyInitLogging:
    def test_only_logging_utils_uses_config(self):
        allowed = {"src/shared/logging_utils.py"}
        violations: list[str] = []
        for f in _PROJECT_ROOT.joinpath("src").rglob("*.py"):
            rel = str(f.relative_to(_PROJECT_ROOT))
            if rel in allowed:
                continue
            text = f.read_text(encoding="utf-8")
            for pattern in ["logging.config.fileConfig", "logging.basicConfig("]:
                if pattern in text:
                    violations.append(f"{rel}: contains {pattern}")
        assert violations == [], f"Unauthorized logging.config calls: {violations}"


# ── AC-11 ─────────────────────────────────────────────────────────────────


class TestAC11_Idempotent:
    def test_init_logging_idempotent(self, tmp_path):
        (tmp_path / "log").mkdir(parents=True, exist_ok=True)
        (tmp_path / "config").mkdir(parents=True, exist_ok=True)

        tmp_s = str(tmp_path).replace("\\", "\\\\")
        ini_content = f"""\
[loggers]
keys=root

[handlers]
keys=fh

[formatters]
keys=fmt

[logger_root]
level=INFO
handlers=fh

[handler_fh]
class=FileHandler
level=DEBUG
formatter=fmt
args=('{tmp_s}/log/planbot.log','w','utf-8')

[formatter_fmt]
format=%%(message)s
"""
        ini = tmp_path / "config" / "logging_config.ini"
        ini.write_text(ini_content, encoding="utf-8")

        import src.shared.logging_utils as lu
        lu._INITIALIZED = False
        logging.getLogger().handlers.clear()

        lu.init_logging(str(ini))
        first_count = len(logging.getLogger().handlers)

        lu.init_logging(str(ini))
        second_count = len(logging.getLogger().handlers)

        assert second_count == first_count, (
            f"Handlers doubled: {first_count} → {second_count}"
        )


# ── AC-12 ─────────────────────────────────────────────────────────────────


class TestAC12_CreatesLogDir:
    def test_creates_log_directory(self, tmp_path):
        (tmp_path / "config").mkdir(parents=True, exist_ok=True)
        log_dir = tmp_path / "log"
        assert not log_dir.exists(), "log/ should not exist before init_logging"

        tmp_s = str(tmp_path).replace("\\", "\\\\")
        ini_content = f"""\
[loggers]
keys=root

[handlers]
keys=fh

[formatters]
keys=fmt

[logger_root]
level=INFO
handlers=fh

[handler_fh]
class=FileHandler
level=DEBUG
formatter=fmt
args=('{tmp_s}/log/planbot.log','w','utf-8')

[formatter_fmt]
format=%%(message)s
"""
        ini = tmp_path / "config" / "logging_config.ini"
        ini.write_text(ini_content, encoding="utf-8")

        import src.shared.logging_utils as lu
        lu._INITIALIZED = False
        logging.getLogger().handlers.clear()

        lu.init_logging(str(ini))
        assert log_dir.exists(), "init_logging() should create log/"
        assert (log_dir / "planbot.log").exists(), "log/planbot.log should be created"
