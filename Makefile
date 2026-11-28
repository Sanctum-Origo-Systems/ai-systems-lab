# One way to start, stop and test every workstream.
#   make up WS=00 [OBS=1]   start a workstream's stack
#   make test-deps          start the test Postgres used by the pg_url fixture
# Requires GNU make.

SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

WS ?=
OBS ?=

STUB_MSG := not yet: arrives with workstream 01 / 00 Task 11
TEST_COMPOSE := docker compose -f deploy/compose/test.yaml

.PHONY: help verify up down clean test-deps test-deps-down bench push tf-plan tf-apply tf-destroy

# Compose files for WS: 00 is the shared base (plus obs with OBS=1); any other
# workstream uses its own <WS>-<name>/compose.yaml.
ifeq ($(WS),00)
  COMPOSE_FILES := -f deploy/compose/base.yaml$(if $(filter 1,$(OBS)), -f deploy/compose/obs.yaml --profile obs)
else ifneq ($(WS),)
  WS_COMPOSE := $(firstword $(wildcard $(WS)-*/compose.yaml))
  COMPOSE_FILES := $(if $(WS_COMPOSE),-f $(WS_COMPOSE))
endif

# Expanded inside a recipe, so the checks fire under `make -n` too.
check_ws = $(if $(WS),,$(error WS is required, e.g. make up WS=00))$(if $(COMPOSE_FILES),,$(error no compose.yaml for workstream $(WS) yet))
check_env = test -f .env || { echo "missing .env: run 'cp .env.example .env' first" >&2; exit 1; }
COMPOSE = docker compose --env-file .env $(COMPOSE_FILES)

help: ## List targets
	@grep -E '^[a-z][a-z-]*:.*## ' $(firstword $(MAKEFILE_LIST)) \
	  | awk -F':.*## ' '{ printf "  %-15s %s\n", $$1, $$2 }'

verify: ## Run the lint, format and test gate
	./scripts/verify.sh

up: ## Start workstream WS (OBS=1 adds observability for WS=00)
	$(check_ws)@$(check_env)
	$(COMPOSE) up -d --wait

down: ## Stop workstream WS
	$(check_ws)@$(check_env)
	$(COMPOSE) down

clean: ## Stop workstream WS and delete its volumes
	$(check_ws)@$(check_env)
	$(COMPOSE) down -v

test-deps: ## Start the test Postgres
	$(TEST_COMPOSE) up -d --wait

test-deps-down: ## Stop the test Postgres
	$(TEST_COMPOSE) down

bench: ## Run the workstream benchmark (stub)
	@echo "$(STUB_MSG)" >&2; exit 1

push: ## Push images to the registry (stub)
	@echo "$(STUB_MSG)" >&2; exit 1

tf-plan: ## Plan cloud infrastructure (stub)
	@echo "$(STUB_MSG)" >&2; exit 1

tf-apply: ## Apply cloud infrastructure (stub)
	@echo "$(STUB_MSG)" >&2; exit 1

tf-destroy: ## Destroy cloud infrastructure (stub)
	@echo "$(STUB_MSG)" >&2; exit 1
