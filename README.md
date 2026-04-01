# Author-Reviewer Prototype

This project contains a Phase 1 Python prototype for a two-bot author-reviewer workflow.

## Quick start

1. Create a virtual environment if desired.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. (Optional for real providers) create a `.env` file in the project root with keys like:

```bash
POE_API_KEY=your_key_here
OPENAI_API_KEY=your_key_here
DEEPSEEK_API_KEY=your_key_here
```

The app loads `.env` automatically if the file exists.

4. Run in mock mode:

```bash
python -m src.main run --config config/config.yaml
```

5. Run PlanBot in mock mode (no external provider call):

```bash
python -m src.main run-planbot --config config/config.yaml
```

5. To use an OpenAI-compatible API, update `config/config.yaml` and set:

- `provider: openai_compatible`
- `api_key_env`
- `base_url`
- `model`

Author-reviewer outputs are written to `runs/<workflow-name>_<timestamp>/` by default.

If `workflow.overwrite_output_folder: true`, author-reviewer writes to `runs/<workflow-name>/` and replaces that folder on each run.

PlanBot outputs are written to `runs/planbot/<planbot-name>_<timestamp>/` by default.

If `planbot.overwrite_output_folder: true`, PlanBot writes to `runs/planbot/<planbot-name>/` and replaces that folder on each run.