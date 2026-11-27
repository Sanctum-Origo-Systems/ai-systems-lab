# ai-systems-lab

Small, working versions of common AI system designs. Each one has real code, runs on
one PC with a single 24 GB GPU, and can deploy to AWS with Terraform. Each one ends
with measured trade-offs, not just a diagram.

## What it teaches

| # | Workstream | What it shows | Status |
|---|---|---|---|
| 00 | Foundation | One layout, one config, one gate, so adding a workstream is copy-and-fill | in progress |
| 01 | Inference serving | An open-weights LLM behind an admission layer: what admission control buys under overload, and what it costs | planned |
| 02 | Distributed job scheduler | Leases, retries, a dead-letter queue and DAG dependencies on Postgres: what "at least once" means when workers die | planned |
| 03 | GPU scheduling | Bin-packing, gang scheduling, preemption and quotas, compared on one workload trace | planned |
| 04 | Chatbot | A chat app on the 01 serving layer: the cost and latency of conversation state, context and retrieval | planned |
| 05 | Cloud IDE | One sandboxed browser workspace per user, with fast suspend and resume (local only) | planned |

Every workstream gets a `README.md` (design and trade-offs) and a `RESULTS.md`
(measured numbers and what they mean). This table links to them as they land.

## Quick start

Requires Python 3.13 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
./scripts/verify.sh   # lint, format check, tests: the same gate CI runs
```

## License

MIT. See [LICENSE](LICENSE).
