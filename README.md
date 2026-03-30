# Author-Reviewer Prototype

This project contains a Phase 1 Python prototype for a two-bot author-reviewer workflow.

## Quick start

1. Create a virtual environment if desired.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Run in mock mode:

```bash
python -m src.main run --config config/workflow.yaml
```

4. To use an OpenAI-compatible API, update `config/workflow.yaml` and set:

- `provider: openai_compatible`
- `api_key_env`
- `base_url`
- `model`

Outputs are written to `runs/<timestamp>/`.