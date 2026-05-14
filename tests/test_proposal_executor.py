from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from src.planbot.orchestrator import ExecutionContext
from src.planbot.proposal_executor import ProposalExecutor


def _make_context(client_id: str = "C0001") -> ExecutionContext:
    return ExecutionContext(
        run_id="run-123",
        index=0,
        client_id=client_id,
        client_profile=f"## Client ID: {client_id}\nProfile text",
        client_holding={"client_id": client_id, "cash": "100000", "equity": "250000"},
        bindings={"client_id": client_id, "index": 0},
    )


def test_execute_with_context_writes_generated_inputs_and_overrides(monkeypatch, tmp_path: Path):
    config_path = tmp_path / "config_planbot.yaml"
    config_path.write_text(
        """
client_product_fit_analysis:
  references_root: data/planbot/client_product_fit
""".strip()
        + "\n",
        encoding="utf-8",
    )

    app_config = SimpleNamespace(root_dir=tmp_path)
    executor = ProposalExecutor(
        app_config,
        config_path,
        run_id="20260514-101010",
        keep_generated_client_inputs=True,
        generated_inputs_root="runs/client_product_fit_analysis/generated_inputs",
    )

    captured: dict = {}

    def fake_run_crew_planbot(app_cfg, cfg_path, proposal_name, runtime_reference_overrides=None, output_file_override=None):
        captured["proposal_name"] = proposal_name
        captured["runtime_reference_overrides"] = runtime_reference_overrides
        captured["output_file_override"] = output_file_override
        return SimpleNamespace(output_path=output_file_override)

    monkeypatch.setattr(
        "src.planbot.proposal_executor.run_crew_planbot",
        fake_run_crew_planbot,
    )

    output_path = executor.execute_with_context(
        proposal_name="client_product_fit_analysis",
        context=_make_context("C0001"),
        output_file_template="runs/sample_outputs/client_product_fit_analysis_C0001.md",
    )

    generated_dir = (
        tmp_path
        / "runs/client_product_fit_analysis/generated_inputs/20260514-101010/C0001"
    )
    profile_file = generated_dir / "C0001_profile.md"
    holdings_file = generated_dir / "C0001_holdings.csv"

    assert profile_file.exists()
    assert holdings_file.exists()
    assert "Profile text" in profile_file.read_text(encoding="utf-8")
    assert "client_id,cash,equity" in holdings_file.read_text(encoding="utf-8")

    overrides = captured["runtime_reference_overrides"]
    assert "client_profiles" in overrides
    assert overrides["client_profiles"] == [
        "runs/client_product_fit_analysis/generated_inputs/20260514-101010/C0001/C0001_profile.md",
        "runs/client_product_fit_analysis/generated_inputs/20260514-101010/C0001/C0001_holdings.csv",
    ]

    expected_output = tmp_path / "runs/sample_outputs/client_product_fit_analysis_C0001.md"
    assert Path(output_path) == expected_output
    assert captured["output_file_override"] == expected_output

    # Keep flag on: cleanup should not remove generated files.
    executor.cleanup_temp_files()
    assert profile_file.exists()
    assert holdings_file.exists()


def test_cleanup_temp_files_removes_generated_inputs_when_disabled(monkeypatch, tmp_path: Path):
    config_path = tmp_path / "config_planbot.yaml"
    config_path.write_text(
        """
client_product_fit_analysis:
  references_root: data/planbot/client_product_fit
""".strip()
        + "\n",
        encoding="utf-8",
    )

    app_config = SimpleNamespace(root_dir=tmp_path)
    executor = ProposalExecutor(
        app_config,
        config_path,
        run_id="20260514-202020",
        keep_generated_client_inputs=False,
        generated_inputs_root="runs/client_product_fit_analysis/generated_inputs",
    )

    def fake_run_crew_planbot(app_cfg, cfg_path, proposal_name, runtime_reference_overrides=None, output_file_override=None):
        return SimpleNamespace(output_path=output_file_override)

    monkeypatch.setattr(
        "src.planbot.proposal_executor.run_crew_planbot",
        fake_run_crew_planbot,
    )

    executor.execute_with_context(
        proposal_name="client_product_fit_analysis",
        context=_make_context("C0002"),
        output_file_template="runs/sample_outputs/client_product_fit_analysis_C0002.md",
    )

    generated_dir = (
        tmp_path
        / "runs/client_product_fit_analysis/generated_inputs/20260514-202020/C0002"
    )
    profile_file = generated_dir / "C0002_profile.md"
    holdings_file = generated_dir / "C0002_holdings.csv"

    assert profile_file.exists()
    assert holdings_file.exists()

    executor.cleanup_temp_files()

    assert not profile_file.exists()
    assert not holdings_file.exists()


def test_execute_with_context_uses_generated_inputs_root_override(monkeypatch, tmp_path: Path):
    config_path = tmp_path / "config_planbot.yaml"
    config_path.write_text(
        """
client_product_fit_analysis:
  references_root: data/planbot/client_product_fit
""".strip()
        + "\n",
        encoding="utf-8",
    )

    app_config = SimpleNamespace(root_dir=tmp_path)
    executor = ProposalExecutor(
        app_config,
        config_path,
        run_id="20260514-303030",
        keep_generated_client_inputs=True,
        generated_inputs_root="runs/client_product_fit_analysis/generated_inputs",
    )

    captured: dict = {}

    def fake_run_crew_planbot(app_cfg, cfg_path, proposal_name, runtime_reference_overrides=None, output_file_override=None):
        captured["runtime_reference_overrides"] = runtime_reference_overrides
        return SimpleNamespace(output_path=output_file_override)

    monkeypatch.setattr(
        "src.planbot.proposal_executor.run_crew_planbot",
        fake_run_crew_planbot,
    )

    executor.execute_with_context(
        proposal_name="client_product_fit_analysis",
        context=_make_context("C0003"),
        output_file_template="runs/sample_outputs/client_product_fit_analysis_C0003.md",
    )

    generated_dir = (
        tmp_path
        / "runs/client_product_fit_analysis/generated_inputs/20260514-303030/C0003"
    )
    profile_file = generated_dir / "C0003_profile.md"
    holdings_file = generated_dir / "C0003_holdings.csv"

    assert profile_file.exists()
    assert holdings_file.exists()

    overrides = captured["runtime_reference_overrides"]
    assert overrides["client_profiles"] == [
        "runs/client_product_fit_analysis/generated_inputs/20260514-303030/C0003/C0003_profile.md",
        "runs/client_product_fit_analysis/generated_inputs/20260514-303030/C0003/C0003_holdings.csv",
    ]
