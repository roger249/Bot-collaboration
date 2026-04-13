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

PlanBot mock run:

```bash
python -m src.main run-planbot --config config/config.mocktest.yaml
```

### 6. Run with real providers

Use `config/config.yaml` and set the provider and model fields you want:

- `bots.author.provider`
- `bots.reviewer.provider`
- `planbot.provider`
- `planbot.model`

Then run:

```bash
python -m src.main run --config config/config.yaml
python -m src.main run-planbot --config config/config.yaml
```

Author-reviewer outputs are written to `runs/<workflow-name>_<timestamp>/` by default.

If `workflow.overwrite_output_folder: true`, author-reviewer writes to `runs/<workflow-name>/` and replaces that folder on each run.

PlanBot outputs are written to `runs/planbot/<planbot-name>_<timestamp>/` by default.

If `planbot.overwrite_output_folder: true`, PlanBot writes to `runs/planbot/<planbot-name>/` and replaces that folder on each run.