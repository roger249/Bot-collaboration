#!/usr/bin/env python3
"""Export the live OpenAPI specs for the data + proposal servers to docs.

Regenerates the bank-facing contract JSON from the FastAPI apps so the
specification never drifts from the implementation:

- ``docs/specification/data_api/openapi_data.json``
- ``docs/specification/data_api/openapi_proposal.json``

Run from the repository root::

    ./.venv/bin/python scripts/export_openapi.py

The generated files are the single source of truth for the bank to implement
the data server against.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.integrations.data_server import app as data_app
from src.integrations.proposal_server import app as proposal_app

_OUT_DIR = _ROOT / "docs" / "specification" / "data_api"

_TARGETS = {
    "openapi_data.json": data_app,
    "openapi_proposal.json": proposal_app,
}


def main() -> None:
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    for filename, app in _TARGETS.items():
        spec = app.openapi()
        out_path = _OUT_DIR / filename
        out_path.write_text(
            json.dumps(spec, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"Wrote {out_path.relative_to(_ROOT)} "
              f"({len(spec.get('paths', {}))} paths)")


if __name__ == "__main__":
    main()
