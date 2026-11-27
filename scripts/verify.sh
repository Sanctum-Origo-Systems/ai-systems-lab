#!/usr/bin/env bash
# The one gate: AutoLoop (verify + mutation gate), CI and Hedy all run this.
# Rules: offline, no GPU, no AWS, no running stack, under ~3 minutes. Never skip silently.
set -euo pipefail
cd "$(dirname "$0")/.."

uv run --locked ruff check
uv run --locked ruff format --check
uv run --locked pytest -q

# Compose files parse (dummy env, because ${VAR:?} fails without one)
for f in deploy/compose/*.yaml 0*/compose.yaml; do
  [ -e "$f" ] || continue
  docker compose --env-file .env.example -f "$f" config -q
done

# Terraform formatting is offline. `terraform validate` needs provider downloads, so it runs in CI only.
if [ -d deploy/terraform ]; then terraform fmt -check -recursive deploy/terraform; fi

# Section 7: no bare or 0.0.0.0 port publishes (added with 00 Task 3)
if [ -f scripts/check_publish_binds.py ]; then uv run --locked python scripts/check_publish_binds.py; fi
