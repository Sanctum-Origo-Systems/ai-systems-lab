# ai-systems-lab: conventions for every builder

## What this repo is
Small, working versions of common AI system designs, each with measured trade-offs.
Read the workstream's README.md before changing its code.

## Layout
- lib/ is the `labkit` package: settings, logging, Queue, ObjectStore, metrics.
- 0N-name/src/lab_<name>/ holds all Python for a workstream. services/ holds thin Dockerfiles only.
- Tests live only in <folder>/tests/ (lib/tests/, 0N-name/tests/).

## Tests: hard rules
- Every behavior change ships a test under a tests/ folder that fails without the change.
- Tests never need a GPU, a model, AWS, the internet, or a running compose stack.
  Use the fakes: the lab_serving fake backend, labkit's in-memory Queue and ObjectStore,
  the fake ContainerRuntime.
- Postgres is the one exception: use the `pg_url` fixture (root conftest.py) against the
  test Postgres from `make test-deps`. Never fake SKIP LOCKED with SQLite.
- Never add skip, xfail or importorskip to get a check to pass.
- Inject time and randomness (clock and rng parameters). No time.sleep in tests.
- `gpu` and `aws` marked tests are excluded by default. A change's only test must not carry those markers.

## Run before every commit
./scripts/verify.sh

## Code rules
- Code calls labkit interfaces. boto3 and the Docker SDK appear only inside adapters.
- Config comes from env via labkit.settings. No hard-coded endpoints, ports or credentials.
- Published ports bind 127.0.0.1. Datastores publish nothing.
- No credentials in any file. .env.example holds fake values only.
- Fictitious data only: no real people, companies, employers or messages.
- Write READMEs as engineering design docs: what the system does, how, what it trades off, and what was measured. Nothing about where the ideas came from.
- Pin versions: base images by digest, Python dependencies via uv.lock, models by revision.

## Protected: don't edit
autoloop.toml, .github/, .claude/, scripts/verify.sh, deploy/terraform/base/.
If a task needs one changed, stop and say so in the PR description.

## Commits
`<type>: <description> (#<issue>)`. Types: fix, feat, refactor, docs, test, chore.
No attribution lines. Reference function and file names, not line numbers.
