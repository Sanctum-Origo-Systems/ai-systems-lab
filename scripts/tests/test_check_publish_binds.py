import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "check_publish_binds.py"
_spec = importlib.util.spec_from_file_location("check_publish_binds", SCRIPT)
cpb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cpb)

LOOPBACK_LABEL = {"lab.publish": "loopback"}


def _config(service: dict, name: str = "api") -> dict:
    return {"services": {name: service}}


def _port(host_ip: str | None = "127.0.0.1") -> dict:
    port = {"target": 8000, "published": "8000", "protocol": "tcp", "mode": "ingress"}
    if host_ip is not None:
        port["host_ip"] = host_ip
    return port


def test_labelled_loopback_port_passes():
    config = _config({"labels": LOOPBACK_LABEL, "ports": [_port("127.0.0.1")]})
    assert cpb.check_config(config, "deploy/compose/app.yaml") == []


@pytest.mark.parametrize("host_ip", [None, "", "0.0.0.0", "::"])
def test_labelled_service_with_unsafe_host_ip_is_a_violation(host_ip):
    config = _config({"labels": LOOPBACK_LABEL, "ports": [_port(host_ip)]})
    violations = cpb.check_config(config, "deploy/compose/app.yaml")
    assert len(violations) == 1


def test_missing_host_ip_is_a_violation():
    config = _config({"labels": LOOPBACK_LABEL, "ports": [_port(None)]})
    assert len(cpb.check_config(config, "x.yaml")) == 1


def test_wildcard_ipv4_host_ip_is_a_violation():
    config = _config({"labels": LOOPBACK_LABEL, "ports": [_port("0.0.0.0")]})
    assert len(cpb.check_config(config, "x.yaml")) == 1


def test_wildcard_ipv6_host_ip_is_a_violation():
    config = _config({"labels": LOOPBACK_LABEL, "ports": [_port("::")]})
    assert len(cpb.check_config(config, "x.yaml")) == 1


def test_unlabelled_service_publishing_loopback_is_a_violation():
    config = _config({"ports": [_port("127.0.0.1")]}, name="postgres")
    violations = cpb.check_config(config, "deploy/compose/data.yaml")
    assert len(violations) == 1
    assert "lab.publish" in violations[0]


def test_wrong_label_value_is_a_violation():
    config = _config({"labels": {"lab.publish": "public"}, "ports": [_port("127.0.0.1")]})
    assert len(cpb.check_config(config, "x.yaml")) == 1


def test_service_without_ports_passes():
    config = _config({"image": "postgres"}, name="postgres")
    assert cpb.check_config(config, "deploy/compose/data.yaml") == []


def test_violation_messages_name_source_service_and_port():
    config = {
        "services": {
            "api": {"labels": LOOPBACK_LABEL, "ports": [_port("0.0.0.0")]},
            "postgres": {"ports": [{"target": 5432, "published": "5432", "host_ip": "127.0.0.1"}]},
        }
    }
    violations = cpb.check_config(config, "deploy/compose/app.yaml")
    assert len(violations) == 2
    api, pg = violations
    assert "deploy/compose/app.yaml" in api and "api" in api and "8000" in api
    assert "deploy/compose/app.yaml" in pg and "postgres" in pg and "5432" in pg


def _fail_if_called(*args, **kwargs):
    raise AssertionError("subprocess.run must not be called")


def test_main_with_no_compose_files_returns_zero(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cpb, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(cpb.subprocess, "run", _fail_if_called)
    assert cpb.main([]) == 0
    out = capsys.readouterr().out
    assert out.strip() and "\n" not in out.strip()


def _canned_run(payload: dict, calls: list):
    def run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(payload), stderr="")

    return run


def test_main_reports_violation_and_returns_one(tmp_path, monkeypatch, capsys):
    (tmp_path / "deploy" / "compose").mkdir(parents=True)
    (tmp_path / "deploy" / "compose" / "app.yaml").write_text("services: {}\n")
    payload = _config({"labels": LOOPBACK_LABEL, "ports": [_port("0.0.0.0")]})
    calls: list = []
    monkeypatch.setattr(cpb, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(cpb.subprocess, "run", _canned_run(payload, calls))

    assert cpb.main([]) == 1

    err = capsys.readouterr().err
    assert "deploy/compose/app.yaml" in err and "api" in err
    ((cmd, kwargs),) = calls
    assert cmd[:5] == ["docker", "compose", "--env-file", ".env.example", "-f"]
    assert cmd[5] == "deploy/compose/app.yaml"
    assert cmd[6:] == ["config", "--format", "json"]
    assert kwargs["check"] is True


def test_main_globs_workstream_compose_and_passes_clean_config(tmp_path, monkeypatch, capsys):
    (tmp_path / "01-serving").mkdir()
    (tmp_path / "01-serving" / "compose.yaml").write_text("services: {}\n")
    payload = _config({"labels": LOOPBACK_LABEL, "ports": [_port("127.0.0.1")]})
    calls: list = []
    monkeypatch.setattr(cpb, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(cpb.subprocess, "run", _canned_run(payload, calls))

    assert cpb.main([]) == 0
    assert [c[0][5] for c in calls] == ["01-serving/compose.yaml"]
    assert capsys.readouterr().err == ""
