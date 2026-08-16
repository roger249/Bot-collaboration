"""Unit tests for docker/merge_yaml.py partial override merge."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

import yaml

_DOCKER_DIR = Path(__file__).resolve().parent.parent / "docker"
_MERGE_PATH = _DOCKER_DIR / "merge_yaml.py"


def _load_merge_module():
    spec = importlib.util.spec_from_file_location("merge_yaml", _MERGE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


merge_yaml = _load_merge_module()


class ConfigMergeTest(unittest.TestCase):
    def test_partial_yaml_merge(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "config"
            override = Path(tmp) / "config-override"
            target.mkdir()
            override.mkdir()

            (target / "config_planbot.yaml").write_text(
                "data_source:\n"
                "  rest:\n"
                "    client_base_url: http://localhost:8001\n"
                "    timeout_seconds: 10\n"
                "unrelated:\n"
                "  keep: true\n",
                encoding="utf-8",
            )
            (override / "config_planbot.yaml").write_text(
                "data_source:\n"
                "  rest:\n"
                "    client_base_url: http://bank:9000\n",
                encoding="utf-8",
            )

            merge_yaml.apply_override(override, target)

            merged = yaml.safe_load(
                (target / "config_planbot.yaml").read_text(encoding="utf-8")
            )
            self.assertEqual(
                merged["data_source"]["rest"]["client_base_url"],
                "http://bank:9000",
            )
            self.assertEqual(merged["data_source"]["rest"]["timeout_seconds"], 10)
            self.assertTrue(merged["unrelated"]["keep"])

    def test_malformed_yaml_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "config"
            override = Path(tmp) / "config-override"
            target.mkdir()
            override.mkdir()

            (target / "config.yaml").write_text("a: 1\n", encoding="utf-8")
            (override / "config.yaml").write_text("a: [unclosed\n", encoding="utf-8")

            with self.assertRaises(yaml.YAMLError):
                merge_yaml.apply_override(override, target)

    def test_sample_files_are_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "config"
            override = Path(tmp) / "config-override"
            target.mkdir()
            override.mkdir()

            (target / "config_planbot.yaml").write_text(
                "a: 1\n", encoding="utf-8"
            )
            (override / "config_planbot.yaml.example").write_text(
                "a: 999\n", encoding="utf-8"
            )
            (override / ".config_planbot.yaml").write_text(
                "a: 999\n", encoding="utf-8"
            )

            merge_yaml.apply_override(override, target)

            merged = yaml.safe_load(
                (target / "config_planbot.yaml").read_text(encoding="utf-8")
            )
            self.assertEqual(merged["a"], 1)
            self.assertFalse((target / "config_planbot.yaml.example").exists())


if __name__ == "__main__":
    unittest.main()
