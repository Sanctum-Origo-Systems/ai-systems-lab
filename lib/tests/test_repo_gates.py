"""Repo-level gates that must stay wired into the default test run.

scripts/tests is only collected because pyproject.toml lists it in testpaths, so this
file lives in a path that is always collected and fails if that wiring, or the
publish-bind check itself, goes missing.
"""

import importlib.util
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PUBLISH_BINDS = REPO_ROOT / "scripts" / "check_publish_binds.py"


def test_pytest_collects_scripts_tests():
    config = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    assert "scripts/tests" in config["tool"]["pytest"]["ini_options"]["testpaths"]


def test_publish_bind_check_rejects_wildcard_publish():
    spec = importlib.util.spec_from_file_location("check_publish_binds", PUBLISH_BINDS)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    config = {
        "services": {
            "api": {
                "labels": {"lab.publish": "loopback"},
                "ports": [{"target": 8000, "published": "8000", "host_ip": "0.0.0.0"}],
            }
        }
    }
    assert module.check_config(config, "deploy/compose/app.yaml")
