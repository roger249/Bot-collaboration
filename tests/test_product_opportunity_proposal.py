"""Unit tests for product_opportunity_proposal module."""

from __future__ import annotations

import io
import json
import logging
import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.integrations.product_opportunity_proposal import (
    propose_product_opportunity,
    propose_product_opportunity_automatch,
    _load_latest_matcher_output,
)

FIT_MARKDOWN = """# Product Opportunity Proposal

## Investment Recommendation

- **Suggested Product:** PROD016 Healthcare Innovation Fund
- **Position:** 8.1% of portfolio

## Supporting Analysis

### Executive Summary
Test proposal generated successfully.

### Product Specification
- Issuer: Test Fund
- Asset Class: Equity

### Scenario Analysis
- Bull case: +15%
- Base case: +8%
- Bear case: -10%

### Risk Disclaimer
Past performance does not guarantee future returns.
"""


def _make_crew_result(markdown: str, output_path_str: str = "/tmp/test_output.md") -> MagicMock:
    """Build a mock crew result."""
    result = MagicMock()

    # Use a simple object for output_path so str() and read_text() both work
    class MockPath:
        def __str__(self):
            return output_path_str

        def read_text(self):
            return markdown

    result.output_path = MockPath()
    return result


class TestProposeProductOpportunity(unittest.TestCase):
    """Normal and exception flow tests."""

    def setUp(self):
        self._crew_patcher = patch(
            "src.integrations.product_opportunity_proposal.run_crew_planbot"
        )
        self.mock_run_crew = self._crew_patcher.start()

    def tearDown(self):
        self._crew_patcher.stop()

    def test_normal_flow(self):
        """Normal flow: valid client + product → successful proposal."""
        test_path = "runs/product_opportunity_proposal/product_opportunity_proposal_PB-HK-000001-8_PROD016.md"
        self.mock_run_crew.return_value = _make_crew_result(FIT_MARKDOWN, test_path)

        result = propose_product_opportunity(
            client_id="PB-HK-000001-8",
            product_id="PROD016",
            rationale="Test rationale for matching.",
        )

        self.assertEqual(result["client_id"], "PB-HK-000001-8")
        self.assertEqual(result["product_id"], "PROD016")
        self.assertIn("output_filename", result)
        self.assertIn("product_opportunity_proposal", result["output_filename"])
        self.assertIn("PB-HK-000001-8", result["output_filename"])
        self.assertIn("PROD016", result["output_filename"])
        self.assertGreater(len(result["proposal_markdown"]), 0)
        self.assertIn("Investment Recommendation", result["proposal_markdown"])
        self.assertIn("Supporting Analysis", result["proposal_markdown"])
        self.assertIn("metadata", result)
        self.assertIn("product_fitness_scores", result["metadata"])

    def test_client_not_found(self):
        """Exception: client ID not in DB."""
        with self.assertRaises(LookupError) as ctx:
            propose_product_opportunity(
                client_id="PB-HK-999999-9",
                product_id="PROD016",
            )
        self.assertIn("Client not found", str(ctx.exception))

    def test_product_not_found(self):
        """Exception: product ID not in DB."""
        with self.assertRaises(LookupError) as ctx:
            propose_product_opportunity(
                client_id="PB-HK-000001-8",
                product_id="PROD999",
            )
        self.assertIn("Product not found", str(ctx.exception))


class TestLoadLatestMatcherOutput(unittest.TestCase):
    """Disk loader tests."""

    def test_no_files_returns_empty(self):
        """No _pairs.json → empty result."""
        with patch.object(
            Path, "glob", return_value=[]
        ):
            run_id, pairs = _load_latest_matcher_output()
        self.assertEqual(run_id, "")
        self.assertEqual(pairs, [])


class TestAutomatchPromptAndFields(unittest.TestCase):
    """Verify automatch response fields and dump the LLM prompt snapshot."""

    def setUp(self):
        self._crew_patcher = patch(
            "src.integrations.product_opportunity_proposal.run_crew_planbot"
        )
        self.mock_run_crew = self._crew_patcher.start()
        self.captured_kwargs: dict = {}

    def tearDown(self):
        self._crew_patcher.stop()

    def test_automatch_response_fields_and_prompt(self):
        """Run automatch, verify every response field, dump prompt to temp file."""
        from src.planbot.config import load_planbot_config
        from src.planbot.input_loader import load_references
        from src.planbot.workflow import (
            _build_reference_payload,
            _build_user_prompt,
            _build_prompt_snapshot_markdown,
        )
        from src.shared.config_loader import load_config

        _ROOT_DIR = Path(__file__).resolve().parents[1]

        # ── 1. Mock run_crew_planbot to capture kwargs ──────────────────
        def _capture_and_return(
            app_config, config_path, proposal_name,
            runtime_reference_overrides, output_file_override, api_resolver,
        ):
            self.captured_kwargs = {
                "app_config": app_config,
                "config_path": config_path,
                "proposal_name": proposal_name,
                "runtime_reference_overrides": runtime_reference_overrides,
                "output_file_override": output_file_override,
                "api_resolver": api_resolver,
            }
            test_path = f"runs/product_opportunity_proposal/test_automatch_output.md"
            return _make_crew_result(FIT_MARKDOWN, test_path)

        self.mock_run_crew.side_effect = _capture_and_return

        # ── 2. Run automatch ───────────────────────────────────────────
        result = propose_product_opportunity_automatch(
            product_ids=["bank_recommended"],
            product_source="default_yaml",
            client_selection={"risk_rating": [1, 5]},
            run_matcher=False,
            max_proposals=1,
        )

        # ── 3. Verify response structure ───────────────────────────────
        self.assertIn("matcher_run_id", result)
        self.assertIsInstance(result["matcher_run_id"], str)
        self.assertGreater(len(result["matcher_run_id"]), 0,
                           "matcher_run_id must be non-empty")

        self.assertIn("total_clients_matched", result)
        self.assertGreater(result["total_clients_matched"], 0,
                           "total_clients_matched must be > 0")

        self.assertIn("total_proposals_generated", result)
        self.assertEqual(result["total_proposals_generated"], 1,
                         "should generate exactly 1 proposal (max_proposals=1)")

        self.assertIn("errors", result)
        self.assertEqual(result["errors"], [], "no errors expected")

        self.assertIn("proposals", result)
        self.assertIsInstance(result["proposals"], list)
        self.assertEqual(len(result["proposals"]), 1)

        proposal = result["proposals"][0]
        self.assertIn("client_id", proposal)
        self.assertIsInstance(proposal["client_id"], str)
        self.assertGreater(len(proposal["client_id"]), 0)

        self.assertIn("product_id", proposal)
        self.assertIsInstance(proposal["product_id"], str)
        self.assertGreater(len(proposal["product_id"]), 0)

        self.assertIn("proposal_markdown", proposal)
        self.assertIsInstance(proposal["proposal_markdown"], str)
        self.assertGreater(len(proposal["proposal_markdown"]), 0)

        self.assertIn("output_filename", proposal)
        self.assertIsInstance(proposal["output_filename"], str)
        self.assertIn("product_opportunity", proposal["output_filename"])
        # output_filename from mock is hardcoded — real path would include client_id

        self.assertIn("metadata", proposal)
        self.assertIsInstance(proposal["metadata"], dict)
        self.assertIn("model", proposal["metadata"])
        self.assertIn("alternative_products", proposal["metadata"])
        self.assertIn("product_fitness_scores", proposal["metadata"])

        # ── 4. Reconstruct prompt snapshot ─────────────────────────────
        ck = self.captured_kwargs
        self.assertTrue(ck, "run_crew_planbot must have been called")

        cfg = load_planbot_config(
            str(ck["config_path"]),
            ck["app_config"].root_dir,
            ck["proposal_name"],
        )
        api_resolver = ck["api_resolver"]

        # Load references the same way run_crew_planbot would
        loaded_sections: dict = {}
        for section_name, section_cfg in cfg.reference_sections.items():
            effective_globs = section_cfg.globs
            overrides = ck["runtime_reference_overrides"]
            if overrides and section_name in overrides:
                override_globs = overrides[section_name]
                effective_globs = override_globs or section_cfg.globs
            docs = load_references(
                ck["app_config"].root_dir, effective_globs,
                api_resolver=api_resolver,
            )
            loaded_sections[section_name] = (section_cfg.purpose, docs)

        reference_payload_json = _build_reference_payload(
            root_dir=ck["app_config"].root_dir,
            loaded_sections=loaded_sections,
        )
        user_prompt = _build_user_prompt(
            task_prompt="<task prompt>",
            reference_payload_json=reference_payload_json,
        )
        snapshot = _build_prompt_snapshot_markdown(
            task_prompt="<task prompt>",
            loaded_sections=loaded_sections,
            model=cfg.model,
            temperature=cfg.temperature,
            root_dir=ck["app_config"].root_dir,
        )

        # Verify prompt fields are populated
        self.assertIn(f"**Model:** {cfg.model}", snapshot)
        self.assertIn(f"**Temperature:** {cfg.temperature}", snapshot)
        self.assertIn("## Task Prompt", snapshot)
        self.assertIn("## Reference Sections", snapshot)
        self.assertGreater(len(snapshot), 100,
                           "prompt must be non-trivial")
        # suggested_products_and_rationale is gated — only appears when content
        # is non-empty.  Check whether the override was provided.
        _has_suggested = "suggested_products_and_rationale" in (ck["runtime_reference_overrides"] or {})
        if _has_suggested:
            self.assertIn("suggested_products_and_rationale", snapshot,
                          "prompt must reference the new section when content provided")

        # Verify every reference section is present in the markdown
        for sec in ["proposal_instructions_and_format", "guidelines",
                     "client_profiles", "market_outlook", "product_catalogs"]:
            self.assertIn(
                f"### {sec}", snapshot,
                f"section '{sec}' must be present in prompt snapshot",
            )
        if _has_suggested:
            self.assertIn("### suggested_products_and_rationale", snapshot,
                          "section 'suggested_products_and_rationale' must be present when content provided")

        # ── 5. Dump prompt to persistent test output dir ──────────────
        dump_dir = Path(os.environ.get(
            "TEST_PROMPT_DUMP_DIR",
            str(Path(__file__).resolve().parents[1] / "runs" / "test_output"),
        ))
        dump_dir.mkdir(parents=True, exist_ok=True)
        cid = result["proposals"][0]["client_id"]
        snapshot_file = dump_dir / f"prompt_snapshot_{cid}.md"
        snapshot_file.write_text(snapshot, encoding="utf-8")
        print(f"\nPrompt snapshot → {snapshot_file}")

        # ── 6. Verify suggested_products_and_rationale content (in markdown) ─
        if _has_suggested:
            # Find the suggested_products_and_rationale section in the markdown
            spr_start = snapshot.find("### suggested_products_and_rationale")
            self.assertGreater(spr_start, 0,
                               "suggested_products_and_rationale section must be present")
            spr_section = snapshot[spr_start:]
            # Stop at next ### or ---
            next_section = spr_section.find("\n### ", 4)
            if next_section > 0:
                spr_section = spr_section[:next_section]
            self.assertGreater(len(spr_section.strip()), 0,
                               "suggested_products_and_rationale must have content")


if __name__ == "__main__":
    unittest.main()
