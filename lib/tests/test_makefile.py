"""The root Makefile: targets, WS/OBS handling and stubs, checked with `make -n` in a temp copy."""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

MAKEFILE = Path(__file__).resolve().parents[2] / "Makefile"
TARGETS = [
    "help",
    "verify",
    "up",
    "down",
    "clean",
    "test-deps",
    "test-deps-down",
    "bench",
    "push",
    "tf-plan",
    "tf-apply",
    "tf-destroy",
]
STUB_MSG = "not yet: arrives with workstream 01 / 00 Task 11"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    shutil.copy(MAKEFILE, tmp_path / "Makefile")
    (tmp_path / ".env").write_text("FAKE=1\n")
    return tmp_path


def make(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["make", "--no-print-directory", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def compose_lines(stdout: str) -> list[str]:
    return [line for line in stdout.splitlines() if line.startswith("docker compose")]


@pytest.mark.parametrize("args", [(), ("help",)])
def test_help_is_default_and_lists_every_target(repo: Path, args: tuple[str, ...]):
    result = make(repo, *args)
    assert result.returncode == 0, result.stderr
    listed = {line.split()[0] for line in result.stdout.splitlines() if line.strip()}
    assert set(TARGETS) <= listed


def test_every_target_is_phony():
    phony = re.search(r"^\.PHONY:(.*)$", MAKEFILE.read_text(), re.MULTILINE)
    assert phony
    assert set(TARGETS) <= set(phony.group(1).split())


def test_verify_runs_the_gate(repo: Path):
    assert "./scripts/verify.sh" in make(repo, "-n", "verify").stdout


@pytest.mark.parametrize("target", ["up", "down", "clean"])
def test_ws_is_required(repo: Path, target: str):
    result = make(repo, target)
    assert result.returncode != 0
    assert "WS is required, e.g. make up WS=00" in result.stderr


def test_up_ws00_with_obs(repo: Path):
    result = make(repo, "-n", "up", "WS=00", "OBS=1")
    assert result.returncode == 0, result.stderr
    [cmd] = compose_lines(result.stdout)
    for part in [
        "--env-file .env",
        "-f deploy/compose/base.yaml",
        "-f deploy/compose/obs.yaml",
        "--profile obs",
    ]:
        assert part in cmd
    assert cmd.endswith("up -d --wait")


def test_up_ws00_without_obs(repo: Path):
    result = make(repo, "-n", "up", "WS=00")
    assert result.returncode == 0, result.stderr
    [cmd] = compose_lines(result.stdout)
    assert "--env-file .env" in cmd
    assert "-f deploy/compose/base.yaml" in cmd
    assert "obs.yaml" not in cmd
    assert "--profile obs" not in cmd


@pytest.mark.parametrize(("target", "suffix"), [("down", " down"), ("clean", " down -v")])
def test_down_and_clean_ws00(repo: Path, target: str, suffix: str):
    result = make(repo, "-n", target, "WS=00")
    assert result.returncode == 0, result.stderr
    [cmd] = compose_lines(result.stdout)
    assert "-f deploy/compose/base.yaml" in cmd
    assert cmd.endswith(suffix)


def test_other_ws_uses_its_compose_file(repo: Path):
    (repo / "07-example").mkdir()
    (repo / "07-example" / "compose.yaml").write_text("services: {}\n")
    result = make(repo, "-n", "up", "WS=07")
    assert result.returncode == 0, result.stderr
    [cmd] = compose_lines(result.stdout)
    assert "--env-file .env -f 07-example/compose.yaml" in cmd
    assert "base.yaml" not in cmd


def test_other_ws_without_compose_file_fails(repo: Path):
    result = make(repo, "up", "WS=07")
    assert result.returncode != 0
    assert "no compose.yaml for workstream 07 yet" in result.stderr


def test_missing_env_file_fails(repo: Path):
    (repo / ".env").unlink()
    result = make(repo, "up", "WS=00")
    assert result.returncode != 0
    assert "cp .env.example .env" in result.stderr
    assert "docker compose" not in result.stdout


def test_test_deps(repo: Path):
    up = make(repo, "-n", "test-deps").stdout
    assert "docker compose -f deploy/compose/test.yaml up -d --wait" in up
    down = make(repo, "-n", "test-deps-down").stdout
    assert "docker compose -f deploy/compose/test.yaml down" in down


@pytest.mark.parametrize("target", ["bench", "push", "tf-plan", "tf-apply", "tf-destroy"])
def test_stubs_exit_1(repo: Path, target: str):
    result = make(repo, target, "WS=00")
    assert result.returncode == 2  # make reports a failed recipe (exit 1) as 2
    assert STUB_MSG in result.stderr
    assert "Error 1" in result.stderr


def test_no_terraform_or_aws_invocations():
    recipes = [line for line in MAKEFILE.read_text().splitlines() if line.startswith("\t")]
    assert not [line for line in recipes if re.search(r"terraform|aws ", line)]
