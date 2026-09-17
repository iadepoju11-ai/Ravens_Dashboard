# CI

`.github/workflows/test.yml` runs on every push/PR to `master`, in the
order CHECKLIST.md Phase 7 specifies: install → ruff → SQLite unit tests →
Postgres integration tests → migration upgrade test → build image → start
container → health/readiness smoke tests. Five independent jobs, so a
frontend-only or ML-only change doesn't wait on unrelated work, and a
failure in one doesn't hide failures in the others:

| Job | What it proves |
| --- | --- |
| `api-lint-and-sqlite-tests` | Fails first on the cheapest checks — ruff, then the SQLite-backed unit/integration suite. No services needed. |
| `api-postgres-tests` | The real Alembic migration path on an empty DB, then the full suite against real Postgres (this is the only job that exercises the audit hash-chain's timestamp handling for real — SQLite and Postgres round-trip `DateTime` differently, see `docs/architecture/audit-threat-model.md`). |
| `api-build-and-smoke-test` | The actual `Dockerfile`/gunicorn entrypoint works standalone — a green pytest run doesn't prove the container itself boots. Builds the image, migrates, starts it, and curls `/health` and `/health/ready`. |
| `ml-workers-lint-and-test` | `apps/workers/ml`'s ruff + unit tests, against synthetic data only — training the real Home Credit model in CI would be slow and isn't what this job is for. |
| `web-lint-typecheck-test-build` | `apps/web`: eslint, `tsc -b`, vitest, and a production build. |

## Verifying the workflow locally before relying on it

There's no `act`/local GitHub Actions runner in this environment, so this
workflow was validated by hand:

- YAML parses (`python -c "import yaml; yaml.safe_load(open('.github/workflows/test.yml'))"`).
- Every job's actual command sequence was run against matching containers
  (`python:3.12-slim` + a throwaway `postgres:16` on an isolated Docker
  network, mirroring what GitHub's own runner + service container does) —
  not just assumed correct from reading the YAML. The build-and-smoke-test
  job specifically was run end-to-end: fresh image build, migrate an empty
  database, start the container, health-check it from a separate
  container on the same network.
- One real difference from actual CI: the smoke-test job's `docker run
  --network host` reaches the Postgres service container via `localhost`,
  which works on GitHub's Linux runners but not reliably on Docker
  Desktop for Windows/Mac (no true host networking). Local verification
  used a bridge network + container-name DNS instead — same sequence,
  different addressing. This is a genuine gap between "verified locally"
  and "verified in CI" that only running it for real on a push/PR closes.

## Not yet built (CHECKLIST.md Phase 7, explicitly "Later")

Dependency vulnerability scanning, secret scanning, image scanning, and
coverage thresholds are deliberately not in this workflow yet — the
checklist itself defers them until there's more business logic worth
gating on a coverage number, and until a scanning tool is actually chosen
rather than bolted on reflexively.
