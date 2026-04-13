# Author-Reviewer Prototype

This project contains a Phase 1 Python prototype for a two-bot author-reviewer workflow.

## Quick start (team setup with uv)

### 1. Install uv (one time)

macOS and Linux:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

or with Homebrew:

```bash
brew install uv
```

### 2. Create and activate a virtual environment

From the repo root:

```bash
uv venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
uv pip install -r requirements.txt
```

### 4. Configure API keys (only for real-provider runs)

Create a `.env` file in the project root:

```bash
POE_API_KEY=your_key_here
OPENAI_API_KEY=your_key_here
DEEPSEEK_API_KEY=your_key_here
```

The app loads `.env` automatically if the file exists.

### 5. Run in mock mode (recommended first run)

Author-reviewer mock run:

```bash
python -m src.main run --config config/config.mocktest.yaml
```

PlanBot portfolio review mock run:

```bash
python -m src.main run-planbot --proposal portfolio_review
```

PlanBot client suitability mock run:

```bash
python -m src.main run-planbot --proposal client_suitability
```

### 6. Run with real providers

Author-reviewer with real providers:

```bash
python -m src.main run --config config/config.yaml
```

Update `config/config.yaml` to set:

- `bots.author.provider`
- `bots.reviewer.provider`

PlanBot with real providers:

```bash
python -m src.main run-planbot --proposal portfolio_review
python -m src.main run-planbot --proposal client_suitability
```

Edit `config/config_planbot.yaml` to set `provider` and `model` for each proposal.

Author-reviewer outputs are written to `runs/<workflow-name>_<timestamp>/` by default.

If `workflow.overwrite_output_folder: true`, author-reviewer writes to `runs/<workflow-name>/` and replaces that folder on each run.

PlanBot outputs are written to `runs/<proposal-name>_<timestamp>/` by default.

If `<proposal-name>.overwrite_output_folder: true` in `config/config_planbot.yaml`, PlanBot writes to `runs/<proposal-name>/` and replaces that folder on each run.