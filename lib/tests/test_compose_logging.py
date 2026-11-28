"""Container logs reach Loki over gelf, with no Docker socket or /var/lib/docker mounts.

The compose checks read the normalized JSON from `docker compose config`, so anchors,
interpolation and short-form ports are resolved exactly as Docker will see them. The
Alloy and Loki config checks read the files as text and need no docker CLI.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_DIR = REPO_ROOT / "deploy" / "compose"
ALLOY_CONFIG = COMPOSE_DIR / "alloy" / "config.alloy"
LOKI_CONFIG = COMPOSE_DIR / "loki" / "loki.yaml"

EXPECTED_LOGGING = {
    "driver": "gelf",
    "options": {
        "gelf-address": "udp://127.0.0.1:12201",
        "tag": "{{.Name}}",
        "mode": "non-blocking",
        "max-buffer-size": "4m",
    },
}
LOKI_IMAGE = (
    "grafana/loki:3.7.11@sha256:4c86f2ad5003304c8da84d29da2279b04eb999d716f8089c88e4fa4a44b0781e"
)
ALLOY_IMAGE = (
    "grafana/alloy:v1.22.0@sha256:9acc2529bc1edb7f5b2bd801dd8334ebc80c158e3a9e5526ecd7c9a273d43189"
)
ALLOY_HEALTHCHECK = [
    "CMD",
    "bash",
    "-c",
    "exec 3<>/dev/tcp/127.0.0.1/12345 && printf 'GET /-/ready HTTP/1.0\\r\\n\\r\\n' >&3"
    " && grep -q 200 <&3",
]

requires_docker = pytest.mark.skipif(
    shutil.which("docker") is None,
    reason="docker CLI not installed: compose logging checks need `docker compose config`",
)


def compose_config(name: str, *profiles: str) -> dict:
    args = ["docker", "compose", "--env-file", ".env.example", "-f", f"deploy/compose/{name}"]
    for profile in profiles:
        args += ["--profile", profile]
    result = subprocess.run(
        [*args, "config", "--format", "json"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


@pytest.fixture(scope="module")
def configs() -> dict[str, dict]:
    return {
        "base.yaml": compose_config("base.yaml"),
        "obs.yaml": compose_config("obs.yaml", "obs"),
    }


@pytest.fixture(scope="module")
def obs(configs) -> dict:
    return configs["obs.yaml"]["services"]


def _all_services(configs: dict[str, dict]):
    for source, config in configs.items():
        for name, service in config["services"].items():
            yield f"{source}:{name}", service


@requires_docker
def test_obs_declares_loki_and_alloy(obs):
    assert {"prometheus", "grafana", "loki", "alloy"} <= set(obs)
    for name in ("loki", "alloy"):
        assert obs[name]["profiles"] == ["obs"]
        assert set(obs[name]["networks"]) == {"ai-systems-lab"}


@requires_docker
def test_every_service_ships_logs_over_nonblocking_gelf(configs):
    services = dict(_all_services(configs))
    assert {"base.yaml:postgres", "obs.yaml:loki", "obs.yaml:alloy"} <= set(services)
    for where, service in services.items():
        assert service.get("logging") == EXPECTED_LOGGING, where


@requires_docker
def test_no_service_mounts_docker_socket_or_state(configs):
    for where, service in _all_services(configs):
        for volume in service.get("volumes") or []:
            source = volume.get("source") or ""
            assert source != "/var/run/docker.sock", where
            assert not source.startswith("/var/lib/docker"), where
            assert "docker.sock" not in source, where


@requires_docker
def test_every_image_is_pinned_by_digest(configs):
    for where, service in _all_services(configs):
        assert "@sha256:" in service["image"], where


def _is_non_root_numeric(user: str) -> bool:
    uid, _, gid = user.partition(":")
    return uid.isdigit() and int(uid) != 0 and (not gid or (gid.isdigit() and int(gid) != 0))


@pytest.mark.parametrize(
    ("user", "ok"),
    [
        ("10001:10001", True),
        ("473", True),
        ("0:0", False),
        ("0", False),
        ("root", False),
        ("473:0", False),
        ("", False),
    ],
)
def test_non_root_numeric_user_rule(user, ok):
    assert _is_non_root_numeric(user) is ok


@requires_docker
def test_collectors_run_as_non_root_numeric_users(obs):
    for name in ("loki", "alloy"):
        assert _is_non_root_numeric(obs[name].get("user", "")), name


@requires_docker
def test_loki_is_unprivileged_unpublished_and_mounted_read_only(obs):
    loki = obs["loki"]
    assert loki["image"] == LOKI_IMAGE
    assert loki["command"] == ["-config.file=/etc/loki/loki.yaml"]
    assert loki["user"] == "10001:10001"
    assert loki["read_only"] is True
    assert "/tmp" in loki["tmpfs"]
    assert loki.get("cpus") and loki.get("mem_limit")
    assert not loki.get("ports")
    assert "healthcheck" not in loki or loki["healthcheck"].get("disable")

    mounts = {v["target"]: v for v in loki["volumes"]}
    config_mount = mounts["/etc/loki/loki.yaml"]
    assert config_mount["type"] == "bind"
    assert config_mount["source"] == str(LOKI_CONFIG)
    assert config_mount["read_only"] is True
    assert mounts["/loki"]["type"] == "volume"


@requires_docker
def test_alloy_publishes_only_gelf_udp_on_loopback(obs):
    alloy = obs["alloy"]
    assert alloy["image"] == ALLOY_IMAGE
    assert alloy["command"] == [
        "run",
        "/etc/alloy/config.alloy",
        "--storage.path=/var/lib/alloy/data",
        "--server.http.listen-addr=0.0.0.0:12345",
    ]
    assert alloy["user"] == "473:473"
    assert alloy["read_only"] is True
    assert set(alloy["tmpfs"]) == {"/var/lib/alloy/data", "/tmp"}
    assert alloy.get("cpus") and alloy.get("mem_limit")
    assert alloy["labels"]["lab.publish"] == "loopback"
    ports = [
        (p["host_ip"], str(p["published"]), p["target"], p["protocol"]) for p in alloy["ports"]
    ]
    assert ports == [("127.0.0.1", "12201", 12201, "udp")]

    mounts = {v["target"]: v for v in alloy["volumes"]}
    assert set(mounts) == {"/etc/alloy/config.alloy"}
    assert mounts["/etc/alloy/config.alloy"]["source"] == str(ALLOY_CONFIG)
    assert mounts["/etc/alloy/config.alloy"]["read_only"] is True


@requires_docker
def test_alloy_healthcheck_and_waits_for_loki(obs):
    alloy = obs["alloy"]
    assert alloy["healthcheck"]["test"] == ALLOY_HEALTHCHECK
    assert alloy["depends_on"]["loki"]["condition"] == "service_started"


def test_loki_comment_explains_missing_healthcheck():
    text = (COMPOSE_DIR / "obs.yaml").read_text()
    before_loki = text.split("\n  loki:\n", 1)[0].rsplit("\n\n", 1)[-1]
    assert "distroless" in before_loki
    assert "service_started" in before_loki


def test_compose_files_share_one_logging_anchor():
    for name in ("base.yaml", "obs.yaml"):
        text = (COMPOSE_DIR / name).read_text()
        assert text.count("x-logging: &logging\n") == 1, name
        services_section = text.split("\nservices:\n", 1)[1].split("\nnetworks:\n", 1)[0]
        services = re.findall(r"^  [a-z][\w-]*:$", services_section, re.M)
        assert services, name
        assert services_section.count("    logging: *logging\n") == len(services), name


def test_loki_retains_logs_for_seven_days():
    text = LOKI_CONFIG.read_text()
    assert re.search(r"^limits_config:\n(?:  .*\n)*?  retention_period: 168h$", text, re.M)
    compactor = re.search(r"^compactor:\n((?:  .*\n)+)", text, re.M)
    assert compactor
    assert "  retention_enabled: true\n" in compactor.group(1)
    assert "  delete_request_store: filesystem\n" in compactor.group(1)
    assert "filesystem:" in text


def _block(text: str, header: str) -> str:
    start = text.index(header)
    depth = 0
    for i in range(text.index("{", start), len(text)):
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        if depth == 0:
            return text[start : i + 1]
    raise AssertionError(f"unterminated block {header}")


def _code(text: str) -> str:
    """Drop whole-line `//` comments, so prose never satisfies a config assertion."""
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("//"))


def test_alloy_receives_gelf_and_pushes_to_loki():
    text = _code(ALLOY_CONFIG.read_text())
    source = _block(text, 'loki.source.gelf "')
    assert 'listen_address = "0.0.0.0:12201"' in source
    assert "loki.write." in source

    write = _block(text, 'loki.write "')
    assert 'url = "http://loki:3100/loki/api/v1/push"' in write


def test_alloy_labels_only_service_and_host():
    text = _code(ALLOY_CONFIG.read_text())
    relabel = _block(text, 'loki.relabel "')
    assert set(re.findall(r'target_label\s*=\s*"([^"]+)"', relabel)) == {"service", "host"}
    sources = re.findall(r"source_labels\s*=\s*\[([^\]]*)\]", relabel)
    assert any("__gelf_message_container_name" in s for s in sources)
    assert "external_labels" not in text
    assert "loki.process" not in text
