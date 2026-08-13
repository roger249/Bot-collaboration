#!/usr/bin/env bash
set -euo pipefail

# Start the Bank API Simulator (data server) locally.
#
# Serves raw client / holding / product data — a stand-in for bank-internal
# systems.  Run this before exercising the REST adapter path or the proposal
# server against real HTTP.
#
# Host and port are read from config/config_planbot.yaml -> server.data
# (default 127.0.0.1:8001).  Override with HOST / PORT environment variables;
# set RELOAD=0 to disable uvicorn auto-reload (e.g. in a container).

# Resolve repository root (parent of this script's directory).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

# Use the project virtualenv if present, otherwise system python.
if [[ -x ".venv/bin/python" ]]; then
  PYTHON=".venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="python3"
else
  echo "Python 3 not found.  Create a .venv or ensure python3 is in PATH."
  exit 1
fi

echo "Starting Bank API Simulator (data server) from ${REPO_ROOT}"
exec "${PYTHON}" -m src.integrations.data_server
