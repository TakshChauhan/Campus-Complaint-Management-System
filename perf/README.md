# CCMS load tests (S5-36)

Locust load tests for the CCMS API. Results go in [`docs/testing/performance-reliability.md`](../docs/testing/performance-reliability.md).

## Rules (Sprint 5 plan)

- **Never run against production.**
- **Tell Taksh before every staging run**, with the profile and the time.
- The script only reads. It creates no complaints, comments or accounts, so staging data is not polluted.

## Setup

```bash
cd perf
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

You need up to 10 **student** accounts on the target environment that share one password. The API allows only 15 sign-ins per minute per IP, so the run signs in each account once and every simulated user reuses those sessions.

Create them once with the S5-02 provisioning CLI (no email is sent; running it again changes nothing):

```bash
export DATABASE_URL='postgresql+psycopg://...'   # the staging database, never production
export CCMS_NEW_USER_PASSWORD='...'
perf/create_load_accounts.sh 10                  # run from the repo root
```

It prints the `export CCMS_ACCOUNTS=...` line to use below.

## Run

```bash
export CCMS_ACCOUNTS="student1@dau.ac.in,student2@dau.ac.in"   # at most 10
export CCMS_PASSWORD='...'                                         # never commit it
CCMS_PROFILE=smoke .venv/bin/locust -f locustfile.py --headless \
  --host https://ccms-staging-api.onrender.com --csv results/smoke-$(date +%Y%m%d-%H%M)
```

| `CCMS_PROFILE` | Users over time | Length |
| --- | --- | --- |
| `smoke` | 1 | 1 min |
| `load` | ramps to 20 (1 per second), then holds | 6 min |
| `progressive` | 10 → 100, +10 every 30 s, then holds at 100 | 5.5 min |
| `spike` | 10, then 100 for 1 min, back to 10 | 3 min |

Commit only the CSVs of runs you report (`perf/results/` is ignored by default). Run `smoke` first; if it has any failures, stop and fix them before a bigger profile.
Render's free tier sleeps when idle, so the first requests after a pause can take ~30–60 s. Call `/health/ready` once and wait for it before starting a run.

## Record the results

```bash
python perf/summarize.py results/load-20261124-1830 --profile load --commit <commit on staging>
```

This prints the row for the staging results table in `docs/testing/performance-reliability.md`, a per-endpoint p95 table, and whether the run meets NFR-2. Copy them into the report, and commit the CSVs of that run with `git add -f perf/results/<run>*`.

## What each simulated user does

A student browsing, with a 1–3 s pause between actions (weights in brackets):
`GET /complaints/mine` (4), `GET /feeds/departments/{id}` (3, Hostel excluded because it uses the hostel feed), `GET /departments` (2), `POST /complaints/duplicate-suggestions` (2), `POST /departments/suggest` (1), `GET /health/ready` (1).
