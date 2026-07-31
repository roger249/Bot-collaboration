from __future__ import annotations

import csv
from pathlib import Path

import pytest


def _linear_price_data(start: float, end: float, n: int) -> dict:
    """Return n weekly data points from *start* to *end* linearly."""
    step = (end - start) / (n - 1)
    return {f"d{i:04d}": {"Close": start + step * i} for i in range(n)}


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
                "5y": _linear_price_data(100, 130, 261),
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
        periods=["1y", "3y", "5y"],
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


def test_expected_return_uses_5y_cagr(monkeypatch, tmp_path: Path):
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
                # 261 weekly points, 100→120 over 5 years → CAGR ≈ 3.71%
                return FakeFrame(_linear_price_data(100, 120, 261))
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
        periods=["1y", "3y", "5y"],
        metrics=["return", "cagr", "max_drawdown"],
        output_dir=tmp_path,
    )

    with output_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)

    assert len(rows) == 1
    assert rows[0]["1y_return"] == "2.00"
    assert rows[0]["3y_return"] == "50.00"
    # expected_return is 5Y CAGR percentage, formatted to 2 decimal places
    assert "expected_return" in rows[0]
    expected_ret = rows[0]["expected_return"]
    assert expected_ret != ""
    # Should be a float around 3.71%
    assert 3.0 < float(expected_ret) < 4.5


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