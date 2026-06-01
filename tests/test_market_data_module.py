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
            assert symbol in {"XLK", "XLF"}
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
        "1y_max_drawdown",
        "3y_max_drawdown",
        "price_1y_IHR_20",
        "price_3y_IHR_20",
        "price_1y_IHR_80",
        "price_3y_IHR_80",
        "risk_rating",
        "expected_return_score",
        "certainty_1y_score",
        "certainty_3y_score",
        "certainty_8y_score",
        "liquidity_score",
    }
    assert expected_columns.issubset(set(headers))
    assert len(rows) == 2
    assert rows[0]["ticker"] == "XLK"
    assert rows[1]["ticker"] == "XLF"
    assert rows[0]["last_closing_price"].count(".") == 1
    assert len(rows[0]["last_closing_price"].split(".")[1]) == 2
    assert rows[0]["risk_rating"].endswith(".00")


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
            assert symbol in {"XLK", "XLF"}
            return FakeTicker()

    monkeypatch.setattr(market_data_module, "_import_yfinance", lambda: FakeYF)

    cfg_file = tmp_path / "config_marketdata.yaml"
    cfg_file.write_text(
        """
output_filename: generated.csv
frequency: 1w
periods:
  - 6m
  - 1y
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
        rows = list(csv.DictReader(handle))

    assert len(rows) == 2
    assert [row["ticker"] for row in rows] == ["XLK", "XLF"]