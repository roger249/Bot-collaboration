"""Shared fixtures for real-HTTP integration tests.

Provides a ``proposal_server`` fixture that starts the proposal FastAPI server
in a background thread on an OS-assigned port.  Tests use ``httpx`` to call it
over real TCP — no ``TestClient``, no monkeypatched transport.

Data lookups remain monkeypatched (Phase A / local imports) by individual
tests.  When the external data service is ready, remove the monkeypatch line
and the YAML ``get_client_product_from_db`` + ``data_service_url`` take over
automatically with zero code changes in the test.
"""

from __future__ import annotations

import threading
import time

import httpx
import pytest
import uvicorn


@pytest.fixture(scope="function")
def proposal_server():
    """Start the proposal server in a background thread on port 0 (OS-assigned).

    Yields the server's base URL (e.g. ``http://127.0.0.1:52341``).
    The server is stopped after the test completes.
    """
    from src.integrations.proposal_server import app

    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=False)
    thread.start()

    # Wait for the server to bind and become ready
    timeout = 10.0
    deadline = time.monotonic() + timeout
    port: int | None = None
    while time.monotonic() < deadline:
        if server.started and server.servers:
            sock = server.servers[0].sockets[0]
            port = sock.getsockname()[1]
            break
        time.sleep(0.05)

    if port is None:
        server.should_exit = True
        thread.join(timeout=5)
        raise RuntimeError(f"Proposal server did not start within {timeout}s")

    base_url = f"http://127.0.0.1:{port}"

    # Poll until the server responds
    for _ in range(50):
        try:
            httpx.get(f"{base_url}/docs", timeout=1.0)
            break
        except Exception:
            time.sleep(0.1)
    else:
        server.should_exit = True
        thread.join(timeout=5)
        raise RuntimeError(f"Proposal server not responding at {base_url}")

    yield base_url

    server.should_exit = True
    thread.join(timeout=5)
