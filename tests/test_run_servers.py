"""Unit tests for docker/run_servers.py process launcher configuration."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

_DOCKER_DIR = Path(__file__).resolve().parent.parent / "docker"
_LAUNCHER_PATH = _DOCKER_DIR / "run_servers.py"


def _load_launcher():
    spec = importlib.util.spec_from_file_location("run_servers", _LAUNCHER_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


run_servers = _load_launcher()


class RunServersTest(unittest.TestCase):
    def test_default_starts_both_servers(self):
        specs = run_servers.build_server_specs({})
        self.assertEqual([s.name for s in specs], ["data-server", "proposal-server"])

    def test_data_server_disabled_starts_proposal_only(self):
        specs = run_servers.build_server_specs({"START_DATA_SERVER": "0"})
        self.assertEqual([s.name for s in specs], ["proposal-server"])

    def test_invalid_port_raises(self):
        with self.assertRaises(ValueError):
            run_servers.build_server_specs(
                {"START_DATA_SERVER": "true", "DATA_PORT": "not-a-number"}
            )


if __name__ == "__main__":
    unittest.main()
