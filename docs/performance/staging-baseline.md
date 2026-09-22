# Performance baseline: staging `/score`

CHECKLIST.md Phase 7C. A measured concurrency/latency/throughput baseline
for `POST /score` against the real staging deployment
(`docker-compose.staging.yml`), captured with `tests/load/load_test_score.py`
against the local staging stack on this machine (single host, all
containers on one Docker network — not a distributed deployment). Every
number below is from a real run recorded while writing this doc, not
estimated.

## How to reproduce

```
pip install -r tests/load/requirements.txt
docker compose -f docker-compose.staging.yml --env-file .env.staging up -d
python tests/load/load_test_score.py --concurrency 10 --total-requests 200
```

(`make staging-load-test` runs the same command with its defaults.) The
script registers/approves/deploys its own dedicated model version per
run (resolves to `PlaceholderRuntime` — no trained artifact needed), so
it's safe to run against any staging deployment without prior setup
beyond `staging-up` + `staging-seed`. Every request carries a fresh
`request_id`, so this measures the cost of creating new decisions, not
idempotent-replay lookups (a much cheaper, different code path — see
`ScoringService._find_existing`).

## Results

All three runs against the same staging stack, back to back, same
machine, same already-warm JIT/connection pools (5 warm-up requests
before each timed run).

| Concurrency | Requests | Wall clock | Throughput (req/s) | Client p50 | Client p95 | Client max | Server-side p50 | Server-side p95 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 5  | 100 | 1.61s | 62.2 | 81.7 ms  | 96.1 ms  | 101.1 ms | 7.8 ms | 20.3 ms |
| 10 | 200 | 2.84s | 70.4 | 139.9 ms | 158.3 ms | 169.0 ms | 7.7 ms | 17.7 ms |
| 25 | 250 | 5.97s | 41.8 | 548.5 ms | 814.8 ms | 858.6 ms | 8.8 ms  | 23.4 ms |

Zero request failures across all three runs (550 requests total).

## Reading these numbers

**The gap between client-observed and server-observed latency is the
real story, not a discrepancy to explain away.** "Server-observed"
(`GET /api/v1/monitoring/observability`'s `scoring.duration`) times only
`ScoringService.score()`'s own execution — DB writes, the placeholder
inference call, explanation generation, governance/review evaluation, and
outbox enqueueing. It stays essentially flat (~8ms p50, ~20ms p95) across
all three concurrency levels, because the application logic being timed
genuinely takes about the same time to run regardless of how many other
requests are queued behind it.

"Client-observed" latency includes everything server-observed doesn't:
network round-trip, OIDC/JWT verification, Flask request dispatch, and —
this is the actual finding — **queueing time behind other requests**,
because `apps/api/Dockerfile`'s gunicorn command has no `--workers` flag
and defaults to a single synchronous worker process (already documented
as a known limitation in `docs/runbooks/deployment.md`'s Observability
section, Phase 7B). One worker means the container handles exactly one
request at a time; every other concurrently-arriving request sits in
gunicorn's own accept queue.

This explains the shape of the table directly:
- At concurrency 5 and 10, throughput is nearly identical (62–70 req/s)
  and client p50 roughly doubles (82ms → 140ms) — consistent with
  requests queueing for a single worker rather than the work itself
  getting slower.
- At concurrency 25, throughput actually *drops* (to 42 req/s) and client
  p50 jumps to 548ms (6.7× the concurrency-5 number) while server-side
  p50 barely moves (8.8ms) — the queue has grown long enough that
  time-to-be-served, not time-to-be-processed, dominates the client's
  experience. Zero requests failed even here; the single worker degrades
  by getting slower, not by dropping or erroring requests, at least up to
  this concurrency level.

## What this baseline means for capacity planning

**~70 req/s is this staging deployment's practical ceiling for /score**,
and it is a single-worker ceiling, not a ceiling on `ScoringService`
itself (which server-side timing shows has headroom well beyond that).
Two independent levers exist, not exercised in this pass (no product or
infrastructure changes made — CHECKLIST.md Phase 7C is measurement and
resilience testing only):

1. **`gunicorn --workers N`** — the obvious first lever. Already flagged
   as a trade-off in `docs/runbooks/deployment.md`: `GET /metrics`'s
   in-process counters would become per-worker rather than per-container
   once more than one worker exists, requiring `prometheus_client`'s
   multiprocess mode (a shared directory + different wiring) to keep
   `GET /metrics` and `GET /api/v1/monitoring/observability` accurate.
   Changing worker count without also making that change would silently
   under-report the very metrics this baseline relies on.
2. **Horizontal scaling** (more `api` containers behind a load balancer)
   — explicitly listed as unexamined in `docs/runbooks/deployment.md`'s
   "Known limitations" (no load-balancing/scaling exists in this stack
   today), and would need the outbox/audit-chain's per-tenant
   sequential-write assumptions checked before relying on it.

Neither is implemented here — this document's job is to measure and
record the ceiling that exists today, not to raise it.

## Scope notes

- This is a **single-host, same-machine** measurement: client, API,
  Postgres, and Kafka all share one machine's CPU and network stack.
  Numbers on a real multi-host deployment (with actual network latency,
  and without competing for CPU with the load generator itself) will
  differ — this baseline is useful for detecting *regressions* on this
  same machine/stack shape, not as an absolute production capacity
  number.
- All three runs used `PlaceholderRuntime` (no real trained model
  artifact) — a real SHAP `TreeExplainer` call would add real, currently
  unmeasured latency to the server-observed `model_inference`/
  `explanation` duration histograms (both already instrumented, Phase
  7B) on top of what's measured here.
- Kafka publishing is not on this path at all (`KAFKA_ENABLED=false` by
  default, and even when enabled, publishing is a separate
  `flask events publish-outbox` invocation, not part of the `/score`
  request) — this baseline says nothing about outbox-drain throughput.
