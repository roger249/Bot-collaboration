#!/usr/bin/env python3
"""Run the proposal server and (optionally) the data API server in one container.

The proposal server is always started.  By default the bundled data API
simulator is also started (serving DuckDB test data on port 8001).  Set
``START_DATA_SERVER`` to a falsey value ("0"/"false") to run the proposal
server only — for example when pointing at an external bank data service.

Each server runs in its own process via uvicorn.  This launcher stays in the
foreground as PID 1, forwards SIGTERM/SIGINT to every child, and exits when any
child exits so Docker can restart the container on a crash.

Environment variables:
  START_DATA_SERVER   "true" (default) also starts the bundled data simulator;
                      "false"/"0" starts the proposal server only.
  DATA_HOST           data server bind address   (default 0.0.0.0)
  DATA_PORT           data server port           (default 8001)
  PROPOSAL_HOST       proposal server bind addr  (default 0.0.0.0)
  PROPOSAL_PORT       proposal server port       (default 8000)
"""

from __future__ import annotations

import os
import signal
import sys
import time
from dataclasses import dataclass
from typing import Mapping


@dataclass
class ServerSpec:
    name: str
    target: str
    host: str
    port: int
    log_config: str | None


_FALSEY = {"", "0", "false", "no", "off"}


def _truthy(raw: str | None, default: bool) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() not in _FALSEY


def build_server_specs(env: Mapping[str, str] | None = None) -> list[ServerSpec]:
    """Build the list of servers to run from environment configuration."""
    env = os.environ if env is None else env
    specs: list[ServerSpec] = []
    if _truthy(env.get("START_DATA_SERVER"), True):
        specs.append(
            ServerSpec(
                name="data-server",
                target="src.integrations.data_server:app",
                host=env.get("DATA_HOST", "0.0.0.0"),
                port=int(env.get("DATA_PORT", "8001")),
                log_config=None,
            )
        )
    specs.append(
        ServerSpec(
            name="proposal-server",
            target="src.integrations.proposal_server:app",
            host=env.get("PROPOSAL_HOST", "0.0.0.0"),
            port=int(env.get("PROPOSAL_PORT", "8000")),
            log_config="config/logging_config.ini",
        )
    )
    return specs


def _run_uvicorn(spec: ServerSpec) -> None:
    import uvicorn

    uvicorn.run(
        spec.target,
        host=spec.host,
        port=spec.port,
        log_config=spec.log_config,
    )


def _spawn(spec: ServerSpec):
    import multiprocessing

    return multiprocessing.Process(
        target=_run_uvicorn,
        args=(spec,),
        name=spec.name,
        daemon=True,
    )


def main(argv: list[str] | None = None) -> int:
    specs = build_server_specs()
    processes = [_spawn(spec) for spec in specs]
    for proc in processes:
        proc.start()

    def _shutdown(signum, frame) -> None:
        for proc in processes:
            if proc.is_alive():
                proc.terminate()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    exit_code = 0
    try:
        while all(proc.is_alive() for proc in processes):
            time.sleep(0.5)

        # At least one child exited: bring down the rest and report its code.
        dead = next(proc for proc in processes if not proc.is_alive())
        exit_code = dead.exitcode if dead.exitcode is not None else 1
        for proc in processes:
            if proc.is_alive():
                proc.terminate()
    finally:
        for proc in processes:
            proc.join(timeout=5)
            if proc.is_alive():
                proc.kill()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
