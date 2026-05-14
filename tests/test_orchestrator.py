from __future__ import annotations

import pytest
from pathlib import Path

from src.planbot.orchestrator import (
    FilterBuilder,
    FilterOutput,
    PipelineOrchestrator,
    PlaceholderResolver,
)


class TestFilterBuilder:
    """Test filter extraction and transformation logic."""

    def test_product_investor_matching_filter_extraction(self):
        """Test extracting client profiles by header."""
        sample_output = """
## Client ID: C0001
### Profile for C0001
- Age: 35
- Risk: Medium

## Client ID: C0002
### Profile for C0002
- Age: 50
- Risk: Conservative

Some trailing text
"""
        profiles, ids = FilterBuilder.product_investor_matching_filter(
            sample_output,
            header_pattern="## Client ID:",
            client_id_regex=r"(?<=## Client ID:)\s*(\w+)",
        )

        assert len(ids) == 2
        assert "C0001" in ids
        assert "C0002" in ids
        assert "C0001" in profiles
        assert "C0002" in profiles
        assert "### Profile for C0001" in profiles["C0001"]
        assert "### Profile for C0002" in profiles["C0002"]

    def test_client_holdings_filter_csv_parsing(self, tmp_path):
        """Test loading and mapping holdings from CSV."""
        csv_content = """client_id,cash,shares
C0001,100000,50
C0002,200000,100
"""
        csv_file = tmp_path / "holdings.csv"
        csv_file.write_text(csv_content)

        holdings = FilterBuilder.client_holdings_filter(csv_file, ["C0001", "C0002"])

        assert len(holdings) == 2
        assert "C0001" in holdings
        assert holdings["C0001"]["cash"] == "100000"
        assert holdings["C0001"]["shares"] == "50"
        assert "C0002" in holdings
        assert holdings["C0002"]["cash"] == "200000"


class TestPlaceholderResolver:
    """Test placeholder resolution in templates."""

    def test_resolve_single_placeholder(self):
        """Test resolving a single placeholder."""
        result = PlaceholderResolver.resolve(
            "output_{client_id}.md",
            {"client_id": "C0001"},
        )
        assert result == "output_C0001.md"

    def test_resolve_multiple_placeholders(self):
        """Test resolving multiple placeholders."""
        result = PlaceholderResolver.resolve(
            "runs/sample_{proposal}_{client_id}_{index}.md",
            {"proposal": "analysis", "client_id": "C0001", "index": 0},
        )
        assert result == "runs/sample_analysis_C0001_0.md"

    def test_resolve_no_placeholders(self):
        """Test template with no placeholders."""
        result = PlaceholderResolver.resolve(
            "output.md",
            {"client_id": "C0001"},
        )
        assert result == "output.md"


class TestPipelineOrchestrator:
    """Test orchestrator structure and logic."""

    def test_orchestrator_initialization(self, tmp_path):
        """Test initializing orchestrator."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("run_configurations: {}")

        orchestrator = PipelineOrchestrator(tmp_path, config_file)
        assert orchestrator.root_dir == tmp_path
        assert orchestrator.run_id  # Should be auto-generated


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
