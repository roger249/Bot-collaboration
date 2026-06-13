from __future__ import annotations

import csv
from pathlib import Path

import pytest


def test_get_market_data_generates_single_valid_csv(monkeypatch, tmp_path: Path):
    from src.planbot import market_data_module

    class FakeFrame:
        def __init__(self, payload):
            self._payload = payload

        def to_dict(self, orient="index"):
            assert orient == "index"
            return self._payload

    class FakeTicker:
        info = {
            "quoteType": "ETF",
            "shortName": "Fake ETF",
            "longName": "Fake ETF Long Name",
            "currency": "USD",
            "averageVolume": 2_000_000,
        }

        @staticmethod
        def history(period: str, interval: str):
            assert interval == "1wk"
            payload_by_period = {
                "1y": {
                    "2026-05-31": {"Close": 130},
                    "2026-02-28": {"Close": 110},
                    "2025-12-31": {"Close": 100},
                },
                "3y": {
                    "2026-05-31": {"Close": 130},
                    "2024-05-31": {"Close": 90},
                    "2023-05-31": {"Close": 80},
                },
            }
            return FakeFrame(payload_by_period.get(period, {}))

    class FakeYF:
        @staticmethod
        def Ticker(symbol: str):
            assert symbol in {"XLK", "XLF", "SGOV"}
            return FakeTicker()

    monkeypatch.setattr(market_data_module, "_import_yfinance", lambda: FakeYF)

    output_path = market_data_module.get_market_data(
        tickers=["XLK", "XLF"],
        output_filename="generated.csv",
        frequency="1w",
        periods=["1y", "3y"],
        output_dir=tmp_path,
    )

    assert output_path.exists()
    text = output_path.read_text(encoding="utf-8")
    assert "# quote" not in text
    assert "|" not in text

    for line in text.splitlines():
        if line.strip():
            assert not line.rstrip().endswith(",")

    with output_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames or []
        rows = list(reader)

    expected_columns = {
        "ticker",
        "asset_class",
        "name",
        "currency",
        "last_update_date",
        "last_closing_price",
        "1y_return",
        "3y_return",
        "1y_cagr",
        "3y_cagr",
        "1y_max_drawdown",
        "3y_max_drawdown",
        "price_1y_IHR_20",
        "price_3y_IHR_20",
        "price_1y_IHR_80",
        "price_3y_IHR_80",
        "risk_rating",
        "expected_return",
        "certainty_1y_rating",
        "certainty_3y_rating",
        "certainty_5y_rating",
        "liquidity_rating",
    }
    assert expected_columns.issubset(set(headers))
    assert headers[-1] == "last_update_date"
    assert len(rows) == 2
    assert rows[0]["ticker"] == "XLK"
    assert rows[1]["ticker"] == "XLF"
    assert rows[0]["name"] == "Fake ETF Long Name"
    assert rows[0]["last_closing_price"].count(".") == 1
    assert len(rows[0]["last_closing_price"].split(".")[1]) == 2
    assert rows[0]["risk_rating"].isdigit()
    assert rows[0]["expected_return"] != ""
    assert rows[0]["certainty_1y_rating"].isdigit()
    assert rows[0]["certainty_3y_rating"].isdigit()
    assert rows[0]["certainty_5y_rating"].isdigit()
    assert rows[0]["liquidity_rating"].isdigit()


def test_get_market_data_rejects_invalid_frequency(tmp_path: Path):
    from src.planbot.market_data_module import get_market_data

    with pytest.raises(ValueError, match="Unsupported frequency"):
        get_market_data(
            tickers=["XLK"],
            frequency="2w",
            output_filename="bad.csv",
            output_dir=tmp_path,
        )


def test_load_market_data_config_validates_periods(tmp_path: Path):
    from src.planbot.market_data_module import load_market_data_config

    cfg_file = tmp_path / "config_marketdata.yaml"
    cfg_file.write_text(
        """
output_filename: selected_etf.csv
frequency: 1w
periods: []
tickers:
    - XLK
""".strip()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="periods cannot be empty"):
        load_market_data_config(cfg_file)


def test_get_market_data_from_config_uses_yaml_tickers(monkeypatch, tmp_path: Path):
    from src.planbot import market_data_module

    class FakeFrame:
        def __init__(self, payload):
            self._payload = payload

        def to_dict(self, orient="index"):
            assert orient == "index"
            return self._payload

    class FakeTicker:
        info = {
            "quoteType": "ETF",
            "shortName": "Fake ETF",
            "currency": "USD",
            "averageVolume": 2_000_000,
        }

        @staticmethod
        def history(period: str, interval: str):
            assert interval == "1wk"
            # Market module should translate 6m -> 6mo for yfinance calls.
            if period == "6mo":
                return FakeFrame(
                    {
                        "2026-05-31": {"Close": 110},
                        "2026-02-28": {"Close": 100},
                    }
                )
            return FakeFrame(
                {
                    "2026-05-31": {"Close": 110},
                    "2025-05-31": {"Close": 100},
                }
            )

    class FakeYF:
        @staticmethod
        def Ticker(symbol: str):
            assert symbol in {"XLK", "XLF", "SGOV"}
            return FakeTicker()

    monkeypatch.setattr(market_data_module, "_import_yfinance", lambda: FakeYF)

    cfg_file = tmp_path / "config_marketdata.yaml"
    cfg_file.write_text(
        """
output_filename: generated.csv
metrics:
    - return
    - CAGR
    - calmar_ratio
    - downside_risk
    - volatility
frequency: 1w
periods:
  - 6m
  - 1y
name_preference: short
tickers:
  - XLK
  - XLF
""".strip()
        + "\n",
        encoding="utf-8",
    )

    output_path = market_data_module.get_market_data_from_config(
        config_path=cfg_file,
        output_dir=tmp_path,
    )

    with output_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        headers = reader.fieldnames or []

    assert len(rows) == 2
    assert [row["ticker"] for row in rows] == ["XLK", "XLF"]
    assert rows[0]["name"] == "Fake ETF"
    assert "6m_return" in headers
    assert "1y_cagr" in headers
    assert "1y_calmar_ratio" in headers
    assert "1y_downside_risk" in headers
    assert "1y_volatility" in headers
    assert "6m_max_drawdown" not in headers


def test_get_market_data_from_config_uses_ticker_groupname_and_output_placeholder(
    monkeypatch, tmp_path: Path
):
    from src.planbot import market_data_module

    class FakeFrame:
        def __init__(self, payload):
            self._payload = payload

        def to_dict(self, orient="index"):
            assert orient == "index"
            return self._payload

    class FakeTicker:
        info = {
            "quoteType": "ETF",
            "longName": "Group ETF",
            "currency": "USD",
            "averageVolume": 2_000_000,
        }

        @staticmethod
        def history(period: str, interval: str, timeout: int = 20):
            assert interval == "1wk"
            assert period == "1y"
            return FakeFrame(
                {
                    "2026-05-31": {"Close": 110},
                    "2025-05-31": {"Close": 100},
                }
            )

    class FakeYF:
        @staticmethod
        def Ticker(symbol: str):
            assert symbol in {"SPY", "QQQ", "SGOV"}
            return FakeTicker()

    monkeypatch.setattr(market_data_module, "_import_yfinance", lambda: FakeYF)

    cfg_file = tmp_path / "config_marketdata.yaml"
    cfg_file.write_text(
        """
output_filename: runs/market_data/<tickers_groupname>.csv
metrics:
  - return
frequency: 1w
periods:
  - 1y
ticker_groups:
  demo-group:
    - SPY
    - QQQ
""".strip()
        + "\n",
        encoding="utf-8",
    )

    output_path = market_data_module.get_market_data_from_config(
        config_path=cfg_file,
        output_dir=tmp_path,
        ticker_groupname="demo-group",
    )

    project_root = Path(market_data_module.__file__).resolve().parents[2]
    assert output_path == project_root / "runs" / "market_data" / "demo-group.csv"
    with output_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)

    assert [row["ticker"] for row in rows] == ["SPY", "QQQ"]


def test_get_market_data_from_config_uses_yaml_execute_ticker_groupname(
    monkeypatch, tmp_path: Path
):
    from src.planbot import market_data_module

    class FakeFrame:
        def __init__(self, payload):
            self._payload = payload

        def to_dict(self, orient="index"):
            assert orient == "index"
            return self._payload

    class FakeTicker:
        info = {
            "quoteType": "ETF",
            "longName": "Configured Group ETF",
            "currency": "USD",
            "averageVolume": 2_000_000,
        }

        @staticmethod
        def history(period: str, interval: str, timeout: int = 20):
            assert interval == "1wk"
            assert period == "1y"
            return FakeFrame(
                {
                    "2026-05-31": {"Close": 110},
                    "2025-05-31": {"Close": 100},
                }
            )

    class FakeYF:
        @staticmethod
        def Ticker(symbol: str):
            assert symbol in {"SPY", "QQQ", "SGOV"}
            return FakeTicker()

    monkeypatch.setattr(market_data_module, "_import_yfinance", lambda: FakeYF)

    cfg_file = tmp_path / "config_marketdata.yaml"
    cfg_file.write_text(
        """
output_filename: runs/market_data/<tickers_groupname>.csv
metrics:
  - return
frequency: 1w
periods:
  - 1y
execute_ticker_groupname: demo-group
ticker_groups:
  demo-group:
    - SPY
    - QQQ
""".strip()
        + "\n",
        encoding="utf-8",
    )

    output_path = market_data_module.get_market_data_from_config(
        config_path=cfg_file,
        output_dir=tmp_path,
    )

    project_root = Path(market_data_module.__file__).resolve().parents[2]
    assert output_path == project_root / "runs" / "market_data" / "demo-group.csv"
    with output_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)

    assert [row["ticker"] for row in rows] == ["SPY", "QQQ"]


def test_get_market_data_uses_proxy_when_history_metrics_are_blank_or_zero(monkeypatch, tmp_path: Path):
    from src.planbot import market_data_module

    class FakeFrame:
        def __init__(self, payload):
            self._payload = payload

        def to_dict(self, orient="index"):
            assert orient == "index"
            return self._payload

    class FakeTicker:
        def __init__(self, symbol: str):
            self.symbol = symbol
            if symbol == "CASHX":
                self.info = {
                    "assetClass": "MONEYMARKET",
                    "longName": "Cash Fund",
                    "currency": "USD",
                    "averageVolume": 10_000,
                }
            else:
                self.info = {
                    "assetClass": "ETF",
                    "longName": "Proxy Fund",
                    "currency": "USD",
                    "averageVolume": 2_000_000,
                }

        def history(self, period: str, interval: str, timeout: int = 20):
            assert interval == "1wk"
            assert period == "1y"
            if self.symbol == "CASHX":
                return FakeFrame(
                    {
                        "2026-05-31": {"Close": 1.0},
                        "2025-05-31": {"Close": 1.0},
                    }
                )
            if self.symbol == "SGOV":
                return FakeFrame(
                    {
                        "2026-05-31": {"Close": 101},
                        "2025-05-31": {"Close": 100},
                    }
                )
            raise AssertionError(f"Unexpected symbol {self.symbol}")

    class FakeYF:
        @staticmethod
        def Ticker(symbol: str):
            return FakeTicker(symbol)

    monkeypatch.setattr(market_data_module, "_import_yfinance", lambda: FakeYF)

    output_path = market_data_module.get_market_data(
        tickers=["CASHX"],
        output_filename="generated.csv",
        frequency="1w",
        periods=["1y"],
        metrics=["return", "cagr", "max_drawdown"],
        output_dir=tmp_path,
        asset_class_proxy={"MONEYMARKET": "SGOV"},
    )

    with output_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)

    assert len(rows) == 1
    assert rows[0]["ticker"] == "CASHX"
    assert rows[0]["last_closing_price"] == "1.00"
    assert rows[0]["1y_return"] == "1.00"
    assert rows[0]["1y_cagr"] != ""
    assert rows[0]["1y_max_drawdown"] == "0.00"


def test_etf_risk_rating_respects_floor_abs_return_over_sgov(monkeypatch, tmp_path: Path):
    from src.planbot import market_data_module

    class FakeFrame:
        def __init__(self, payload):
            self._payload = payload

        def to_dict(self, orient="index"):
            assert orient == "index"
            return self._payload

    class FakeTicker:
        def __init__(self, symbol: str):
            self.symbol = symbol
            self.info = {
                "quoteType": "ETF",
                "longName": f"{symbol} ETF",
                "currency": "USD",
                "averageVolume": 2_000_000,
            }

        def history(self, period: str, interval: str, timeout: int = 20):
            assert interval == "1wk"
            assert period == "1y"
            if self.symbol == "SGOV":
                return FakeFrame(
                    {
                        "2026-05-31": {"Close": 101},
                        "2025-05-31": {"Close": 100},
                    }
                )
            if self.symbol == "AAA":
                # AAA return is 3.00 vs SGOV return 1.00,
                # so floor(abs(AAA/SGOV)) = 3.
                return FakeFrame(
                    {
                        "2026-05-31": {"Close": 103},
                        "2025-12-31": {"Close": 102},
                        "2025-05-31": {"Close": 100},
                    }
                )
            raise AssertionError(f"Unexpected symbol {self.symbol}")

    class FakeYF:
        @staticmethod
        def Ticker(symbol: str):
            return FakeTicker(symbol)

    monkeypatch.setattr(market_data_module, "_import_yfinance", lambda: FakeYF)

    output_path = market_data_module.get_market_data(
        tickers=["AAA"],
        output_filename="generated.csv",
        frequency="1w",
        periods=["1y"],
        metrics=["return", "cagr", "max_drawdown"],
        output_dir=tmp_path,
    )

    with output_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)

    assert len(rows) == 1
    assert rows[0]["ticker"] == "AAA"
    assert rows[0]["1y_return"] == "3.00"
    assert rows[0]["risk_rating"] == "3"


def test_etf_risk_rating_uses_ceil_abs_return_over_sgov(monkeypatch, tmp_path: Path):
    from src.planbot import market_data_module

    class FakeFrame:
        def __init__(self, payload):
            self._payload = payload

        def to_dict(self, orient="index"):
            assert orient == "index"
            return self._payload

    class FakeTicker:
        def __init__(self, symbol: str):
            self.symbol = symbol
            self.info = {
                "quoteType": "ETF",
                "longName": f"{symbol} ETF",
                "currency": "USD",
                "averageVolume": 2_000_000,
            }

        def history(self, period: str, interval: str, timeout: int = 20):
            assert interval == "1wk"
            assert period == "1y"
            if self.symbol == "SGOV":
                return FakeFrame(
                    {
                        "2026-05-31": {"Close": 101},
                        "2025-05-31": {"Close": 100},
                    }
                )
            if self.symbol == "AAA":
                # 1y return is 2.00 vs SGOV return 1.00 => ratio 2.0 => ceil 2.
                return FakeFrame(
                    {
                        "2026-05-31": {"Close": 102},
                        "2025-05-31": {"Close": 100},
                    }
                )
            raise AssertionError(f"Unexpected symbol {self.symbol}")

    class FakeYF:
        @staticmethod
        def Ticker(symbol: str):
            return FakeTicker(symbol)

    monkeypatch.setattr(market_data_module, "_import_yfinance", lambda: FakeYF)

    output_path = market_data_module.get_market_data(
        tickers=["AAA"],
        output_filename="generated.csv",
        frequency="1w",
        periods=["1y"],
        metrics=["return", "cagr", "max_drawdown"],
        output_dir=tmp_path,
    )

    with output_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)

    assert len(rows) == 1
    assert rows[0]["ticker"] == "AAA"
    assert rows[0]["1y_return"] == "2.00"
    assert rows[0]["risk_rating"] == "2"


def test_expected_return_uses_3y_cagr(monkeypatch, tmp_path: Path):
    from src.planbot import market_data_module

    class FakeFrame:
        def __init__(self, payload):
            self._payload = payload

        def to_dict(self, orient="index"):
            assert orient == "index"
            return self._payload

    class FakeTicker:
        info = {
            "quoteType": "ETF",
            "longName": "AAA ETF",
            "currency": "USD",
            "averageVolume": 2_000_000,
        }

        @staticmethod
        def history(period: str, interval: str, timeout: int = 20):
            assert interval == "1wk"
            if period == "1y":
                # 1y return = 2%
                return FakeFrame(
                    {
                        "2026-05-31": {"Close": 102},
                        "2025-05-31": {"Close": 100},
                    }
                )
            if period == "3y":
                # 3y return = 50%
                return FakeFrame(
                    {
                        "2026-05-31": {"Close": 150},
                        "2023-05-31": {"Close": 100},
                    }
                )
            if period == "6mo":
                return FakeFrame(
                    {
                        "2026-05-31": {"Close": 101},
                        "2026-02-28": {"Close": 100},
                    }
                )
            if period in {"5y", "10y"}:
                return FakeFrame(
                    {
                        "2026-05-31": {"Close": 120},
                        "2021-05-31": {"Close": 100},
                    }
                )
            return FakeFrame({})

    class FakeYF:
        @staticmethod
        def Ticker(symbol: str):
            return FakeTicker()

    monkeypatch.setattr(market_data_module, "_import_yfinance", lambda: FakeYF)

    output_path = market_data_module.get_market_data(
        tickers=["AAA"],
        output_filename="generated.csv",
        frequency="1w",
        periods=["1y", "3y"],
        metrics=["return", "cagr", "max_drawdown"],
        output_dir=tmp_path,
    )

    with output_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)

    assert len(rows) == 1
    assert rows[0]["1y_return"] == "2.00"
    assert rows[0]["3y_return"] == "50.00"
    # expected_return is raw 3Y CAGR percentage, formatted to 2 decimal places
    assert "expected_return" in rows[0]
    expected_ret = rows[0]["expected_return"]
    assert expected_ret != ""
    # Should be a float string (may have decimal point)
    float(expected_ret)


def test_etf_risk_rating_rises_until_return_is_below_risk_times_sgov(
    monkeypatch, tmp_path: Path
):
    from src.planbot import market_data_module

    class FakeFrame:
        def __init__(self, payload):
            self._payload = payload

        def to_dict(self, orient="index"):
            assert orient == "index"
            return self._payload

    class FakeTicker:
        def __init__(self, symbol: str):
            self.symbol = symbol
            self.info = {
                "quoteType": "ETF",
                "longName": f"{symbol} ETF",
                "currency": "USD",
                "averageVolume": 2_000_000,
            }

        def history(self, period: str, interval: str, timeout: int = 20):
            assert interval == "1wk"
            assert period == "1y"
            if self.symbol == "SGOV":
                return FakeFrame(
                    {
                        "2026-05-31": {"Close": 101},
                        "2025-05-31": {"Close": 100},
                    }
                )
            if self.symbol == "AAA":
                return FakeFrame(
                    {
                        "2026-05-31": {"Close": 111},
                        "2025-05-31": {"Close": 100},
                    }
                )
            raise AssertionError(f"Unexpected symbol {self.symbol}")

    class FakeYF:
        @staticmethod
        def Ticker(symbol: str):
            return FakeTicker(symbol)

    monkeypatch.setattr(market_data_module, "_import_yfinance", lambda: FakeYF)

    output_path = market_data_module.get_market_data(
        tickers=["AAA"],
        output_filename="generated.csv",
        frequency="1w",
        periods=["1y"],
        metrics=["return", "cagr", "max_drawdown"],
        output_dir=tmp_path,
    )

    with output_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)

    assert len(rows) == 1
    assert rows[0]["ticker"] == "AAA"
    assert rows[0]["1y_return"] == "11.00"
    assert rows[0]["risk_rating"] == "5"


def test_certainty_cap_for_non_short_duration_bond():
    from src.planbot import market_data_module

    c1, c3 = market_data_module._apply_certainty_caps(
        certainty_1y_score=3,
        certainty_3y_score=4,
        risk_rating=2,
        asset_class="Corporate Bond",
    )

    assert c1 == 3
    assert c3 == 3


def test_certainty_cap_for_risk_rating_above_two():
    from src.planbot import market_data_module

    c1, c3 = market_data_module._apply_certainty_caps(
        certainty_1y_score=5,
        certainty_3y_score=5,
        risk_rating=4,
        asset_class="EQUITY",
    )

    assert c1 == 3
    assert c3 == 3