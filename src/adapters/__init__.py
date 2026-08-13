"""Data Access Layer adapters.

Layer 1 — raw data retrieval.  No business logic, no enrichment.
"""

from src.adapters.data_adapter import DataAdapter, build_data_adapters
from src.adapters.duckdb_adapter import DuckDBDataAdapter

__all__ = ["DataAdapter", "build_data_adapters", "DuckDBDataAdapter"]
