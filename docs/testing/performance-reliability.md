# Performance and Reliability Testing Report (S5-36)

Owner: Yashvi (S5-36 handed over from Utkarsh by Taksh on 22 Nov 2026) · Reviewer: Dhaval

This report lists only runs that actually happened, with their commit and environment. Empty rows are runs that have not happened yet.

## 1. Target

**NFR-2:** pages respond in about 2 seconds. A run passes when **p95 latency ≤ 2000 ms** for every endpoint and the **error rate is below 1%**.

## 2. Method

- **Tool:** Locust 2.31.8, script [`perf/locustfile.py`](../../perf/locustfile.py) (how to run: [`perf/README.md`](../../perf/README.md)).
- **Workload:** a student browsing: own complaints, department feed, department list, duplicate check, department suggestion, health. Read-only, so staging data is not changed.
- **Profiles:** smoke (1 user, 1 min), load (20 users, 6 min), progressive (10 → 100 users, +10 every 30 s), spike (10 → 100 → 10 users).
- **Sign-in:** a pool of at most 10 student accounts signs in once, because of the 15-sign-ins-per-minute limit.
- **Target environment:** staging only (`https://ccms-staging-api.onrender.com`). Never production. Taksh is told before each run.

## 3. Script check (local, not a performance result)

Before any staging run, the script was run once against a local throwaway backend to make sure it works. These numbers come from SQLite on a laptop with one user, so they say nothing about staging performance.

| Date | Commit | Environment | Profile | Requests | Failures | Avg | Max |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 22 Nov 2026 | `main` @ `7f64a8b` + `perf/` | Local uvicorn, SQLite, 1 user | smoke (1 min) | 30 | 0 (0%) | 9 ms | 14 ms |

The check found and fixed two bugs in the script itself: `/departments` needs a signed-in user, and the department feed answers 400 `hostel_feed_required` for the Hostel department by design, so Hostel is excluded from that task.

## 4. Staging results

| Date / time | Commit on staging | Profile | Requests | Avg (ms) | p95 (ms) | Max (ms) | Error rate | Peak req/s | Meets NFR-2? |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| | | smoke | | | | | | | |
| | | load | | | | | | | |
| | | progressive | | | | | | | |
| | | spike | | | | | | | |

Per-endpoint p95 and the Locust CSVs for each run go in `perf/results/` and are linked here.

### Bottlenecks

To be filled from the staging runs: the slowest endpoints at p95, the number of users at which errors or latency start to rise, and the likely cause (for example the free-tier Render instance, Supabase connection limits, or the TF-IDF duplicate check).

## 5. Reliability (uptime)

The plan asks for an UptimeRobot monitor on staging `/health` from Fri 20 Nov to Wed 2 Dec. **It was not set up on 20 Nov**, because the task had no owner until the handover on 22 Nov, so monitoring starts late.

| Item | Value |
| --- | --- |
| Monitor | UptimeRobot HTTP(s), `https://ccms-staging-api.onrender.com/health/ready`, every 5 min |
| Period | from the day the monitor is created (fill in) to Wed 2 Dec 2026 |
| Uptime % | |
| Incidents | |

Known before monitoring started: on 21 Nov 2026 a manual request to `/health/ready` returned `200 {"ready": true, "database": "operational"}`. Render's free tier sleeps when idle, so the first request after a pause can be slow or time out. Any incident that matches that pattern should be reported as a cold start, not an outage.
