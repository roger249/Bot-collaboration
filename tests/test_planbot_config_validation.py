from __future__ import annotations

from pathlib import Path

import pytest

from src.planbot.config import load_planbot_config


def _write_base_config(config_path: Path, data_root: str, crewai_folder: str, references_root: str) -> None:
    config_path.write_text(
        f"""
stock_analysis_proposal:
  task: stock_analysis_proposal_task
  data_root: {data_root}
  crewai_config_folder: {crewai_folder}
  references_root: {references_root}
  output_root: runs/stock_analysis
  output_filename: stock_analysis_proposal.md
  references:
    proposal_instructions_and_format:
      - name: proposal_instructions/*.md
        purpose: Instructions
  llm_model: poe_deepseek

llm_models:
  poe_deepseek:
    provider: poe
    model: deepseek-v3.2-exp
    temperature: 0.2
""".strip()
        + "\n",
        encoding="utf-8",
    )



def test_load_planbot_config_succeeds_when_required_paths_exist(tmp_path: Path):
    data_root = tmp_path / "data/planbot/stock_analysis"
    crewai_folder = data_root / "crewai"
    references_root = data_root

    crewai_folder.mkdir(parents=True, exist_ok=True)
    (crewai_folder / "agents.yaml").write_text("default: {}\n", encoding="utf-8")
    (crewai_folder / "tasks.yaml").write_text("stock_analysis_proposal_task: {}\n", encoding="utf-8")

    config_path = tmp_path / "config_planbot.yaml"
    _write_base_config(
        config_path=config_path,
        data_root="data/planbot/stock_analysis",
        crewai_folder="data/planbot/stock_analysis/crewai",
        references_root="data/planbot/stock_analysis",
    )

    cfg = load_planbot_config(config_path, tmp_path, "stock_analysis_proposal")
    assert cfg.name == "stock_analysis_proposal"


