"""Fail when a compose file publishes a port anywhere other than loopback.

Published ports must bind 127.0.0.1, and only services labelled
`lab.publish: "loopback"` may publish at all, so datastores publish nothing by default.
The check reads the normalized JSON from `docker compose config`.
"""

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPOSE_GLOBS = ("deploy/compose/*.yaml", "0*/compose.yaml")
PUBLISH_LABEL = "lab.publish"
PUBLISH_LABEL_VALUE = "loopback"
UNSAFE_HOST_IPS = {"", "0.0.0.0", "::"}


def _describe_port(port: dict) -> str:
    published = port.get("published", "?")
    target = port.get("target", "?")
    return f"{published}:{target}"


def check_config(config: dict, source: str) -> list[str]:
    """Return one violation message per port that is not a labelled loopback publish."""
    violations: list[str] = []
    for name, service in (config.get("services") or {}).items():
        ports = service.get("ports") or []
        labels = service.get("labels") or {}
        labelled = labels.get(PUBLISH_LABEL) == PUBLISH_LABEL_VALUE
        for port in ports:
            where = f"{source}: service {name!r} port {_describe_port(port)}"
            host_ip = port.get("host_ip") or ""
            if host_ip in UNSAFE_HOST_IPS:
                shown = host_ip or "missing"
                violations.append(f"{where} binds host_ip {shown}; publish on 127.0.0.1 only")
            if not labelled:
                violations.append(
                    f"{where} is published but the service lacks label "
                    f'{PUBLISH_LABEL}: "{PUBLISH_LABEL_VALUE}"'
                )
    return violations


def _compose_files(root: Path) -> list[Path]:
    files: set[Path] = set()
    for pattern in COMPOSE_GLOBS:
        files.update(root.glob(pattern))
    return sorted(files)


def main(argv: list[str] | None = None) -> int:
    root = REPO_ROOT
    files = _compose_files(root)
    if not files:
        print("check_publish_binds: no compose files found, nothing to check")
        return 0

    violations: list[str] = []
    for path in files:
        source = str(path.relative_to(root))
        result = subprocess.run(
            [
                "docker",
                "compose",
                "--env-file",
                ".env.example",
                "-f",
                source,
                "config",
                "--format",
                "json",
            ],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        violations.extend(check_config(json.loads(result.stdout), source))

    for violation in violations:
        print(violation, file=sys.stderr)
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
