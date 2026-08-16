"""Unit tests for ``build_data_adapters`` (REST env-var override + errors)."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from src.adapters.data_adapter import build_data_adapters


_REST_CONFIG = {
    "common": {"get_client_product_from_restapi": True},
    "data_source": {
        "rest": {
            "client_base_url": "http://localhost:8001",
            "product_base_url": "http://localhost:8001",
        }
    },
}


class BuildDataAdaptersTest(unittest.TestCase):
    def test_env_var_overrides_yaml_base_url(self):
        with patch.dict(
            "os.environ",
            {
                "DATA_CLIENT_BASE_URL": "https://bank-client.example.com",
                "DATA_PRODUCT_BASE_URL": "https://bank-product.example.com",
            },
            clear=False,
        ):
            client, product = build_data_adapters(_REST_CONFIG)
        self.assertEqual(client._base_url, "https://bank-client.example.com")
        self.assertEqual(product._base_url, "https://bank-product.example.com")

    def test_missing_base_url_raises(self):
        config = {
            "common": {"get_client_product_from_restapi": True},
            "data_source": {"rest": {}},
        }
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(ValueError):
                build_data_adapters(config)


if __name__ == "__main__":
    unittest.main()
