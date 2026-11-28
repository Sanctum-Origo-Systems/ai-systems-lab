"""Static checks on deploy/compose: pinned images, healthchecks, limits, loopback publishes.

Reads the files as text (no YAML dependency, no Docker). Each service is the block of lines
indented under its two-space key inside the top-level `services:` mapping.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "deploy" / "compose"

PGVECTOR = (
    "pgvector/pgvector:0.8.7-pg17"
    "@sha256:b513c48566e4777cd3370451400000c78eda6a08131d68f4c31d4a76f27bd8fd"
)
ELASTICMQ = (
    "softwaremill/elasticmq-native:1.7.1"
    "@sha256:e4580ab9ad1bd5cd37b4ba04911bc5ccc8cd2d9ab4de56ece65acee71c24e05c"
)
PROMETHEUS = (
    "prom/prometheus:v3.16.0"
    "@sha256:e04987641b57704f408e31f6373ba4138ecf27cb4a165d24aabb6c38fddd0f06"
)
GRAFANA = (
    "grafana/grafana:13.2.7@sha256:9fd7619deb8923fc422f2183c3f82fc8dc2f668fd2b54b087336f597cfd92b0d"
)
ALLOWED_IMAGES = {PGVECTOR, ELASTICMQ, PROMETHEUS, GRAFANA}

FILES = ["base.yaml", "obs.yaml", "test.yaml"]


def _text(name: str) -> str:
    return (COMPOSE / name).read_text()


def _top_level(text: str) -> dict[str, list[str]]:
    blocks: dict[str, list[str]] = {}
    current = None
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = re.match(r"^([A-Za-z_][\w.-]*):(.*)$", line)
        if m:
            current = m.group(1)
            blocks[current] = [m.group(2).strip()] if m.group(2).strip() else []
        elif current is not None:
            blocks[current].append(line)
    return blocks


def services(name: str) -> dict[str, str]:
    out: dict[str, list[str]] = {}
    current = None
    for line in _top_level(_text(name)).get("services", []):
        m = re.match(r"^  ([A-Za-z_][\w.-]*):\s*$", line)
        if m:
            current = m.group(1)
            out[current] = []
        elif current is not None:
            out[current].append(line)
    return {k: "\n".join(v) for k, v in out.items()}


def _key(block: str, key: str) -> str | None:
    m = re.search(rf"^    {re.escape(key)}:(.*)$", block, re.M)
    return None if m is None else m.group(1).strip()


def all_services() -> list[tuple[str, str, str]]:
    return [(f, s, b) for f in FILES for s, b in services(f).items()]


def test_expected_services_per_file():
    assert sorted(services("base.yaml")) == ["elasticmq", "postgres"]
    assert sorted(services("obs.yaml")) == ["grafana", "prometheus"]
    assert sorted(services("test.yaml")) == ["test-postgres"]


def test_every_image_is_one_of_the_pinned_digests():
    for path in sorted(COMPOSE.glob("*.yaml")):
        images = re.findall(r"^\s*image:\s*(\S+)\s*$", path.read_text(), re.M)
        assert images, path
        for image in images:
            assert "@sha256:" in image, (path.name, image)
            assert image in ALLOWED_IMAGES, (path.name, image)


def test_service_images():
    assert _key(services("base.yaml")["postgres"], "image") == PGVECTOR
    assert _key(services("base.yaml")["elasticmq"], "image") == ELASTICMQ
    assert _key(services("obs.yaml")["prometheus"], "image") == PROMETHEUS
    assert _key(services("obs.yaml")["grafana"], "image") == GRAFANA
    assert _key(services("test.yaml")["test-postgres"], "image") == PGVECTOR


@pytest.mark.parametrize("key", ["healthcheck", "cpus", "mem_limit"])
def test_every_service_has_healthcheck_and_limits(key):
    for f, svc, block in all_services():
        assert _key(block, key) is not None, (f, svc, key)


def test_only_grafana_and_test_postgres_publish_and_only_on_loopback():
    publishers = {svc for _, svc, block in all_services() if _key(block, "ports") is not None}
    assert publishers == {"grafana", "test-postgres"}
    assert _key(services("obs.yaml")["grafana"], "ports") == '["127.0.0.1:3000:3000"]'
    assert _key(services("test.yaml")["test-postgres"], "ports") == '["127.0.0.1:55432:5432"]'


def test_publishers_carry_loopback_label():
    for f, svc in [("obs.yaml", "grafana"), ("test.yaml", "test-postgres")]:
        assert re.search(r'^      lab\.publish: "loopback"$', services(f)[svc], re.M), svc


def test_base_has_no_profile_and_attaches_to_lab_network():
    base = _top_level(_text("base.yaml"))
    assert "  lab:" in base["networks"]
    assert "    name: lab" in base["networks"]
    for svc, block in services("base.yaml").items():
        assert _key(block, "profiles") is None, svc
        assert re.search(r"^    networks:\n      - lab$", block, re.M), svc


def test_base_postgres_requires_password_and_uses_named_volume():
    block = services("base.yaml")["postgres"]
    assert "POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?set in .env}" in block
    assert "- pgdata:/var/lib/postgresql/data" in block
    assert "  pgdata:" in _top_level(_text("base.yaml"))["volumes"]
    assert '"pg_isready -U postgres"' in block


def test_base_elasticmq_healthcheck():
    block = services("base.yaml")["elasticmq"]
    assert "wget -q -O /dev/null http://localhost:9324/?Action=ListQueues" in block


def test_obs_declares_lab_network_and_obs_profile():
    obs = _top_level(_text("obs.yaml"))
    assert "  lab:" in obs["networks"]
    for svc, block in services("obs.yaml").items():
        assert _key(block, "profiles") == '["obs"]', svc


def test_prometheus_config_mount_retention_and_readiness():
    block = services("obs.yaml")["prometheus"]
    assert "- ./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro" in block
    assert "--storage.tsdb.retention.time=15d" in block
    assert "/-/ready" in block


def test_grafana_password_and_health():
    block = services("obs.yaml")["grafana"]
    assert "GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_ADMIN_PASSWORD:?set in .env}" in block
    assert "/api/health" in block


def test_test_postgres_is_ephemeral_and_isolated():
    top = _top_level(_text("test.yaml"))
    assert top["name"] == ["ai-systems-lab-test"]
    block = services("test.yaml")["test-postgres"]
    assert "POSTGRES_PASSWORD: example-test-only" in block
    assert re.search(r"^    tmpfs:\n      - /var/lib/postgresql/data$", block, re.M)
    assert '"pg_isready -U postgres"' in block


def test_prometheus_scrapes_only_itself_every_15s():
    text = (COMPOSE / "prometheus" / "prometheus.yml").read_text()
    assert re.search(r"^  scrape_interval: 15s$", text, re.M)
    assert re.findall(r"job_name:\s*(\S+)", text) == ["prometheus"]
    assert re.findall(r"targets:\s*(.+)$", text, re.M) == ['["localhost:9090"]']


def test_env_example_has_grafana_password_and_only_fake_values():
    lines = [
        line
        for line in (ROOT / ".env.example").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]
    assert "GRAFANA_ADMIN_PASSWORD=example-not-a-secret" in lines
    for line in lines:
        _, value = line.split("=", 1)
        assert value.startswith("example-"), line
