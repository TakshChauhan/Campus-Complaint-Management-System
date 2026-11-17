# Sprint 3 QA Test Run & Validation Report

**Tester:** QA / Dev Thakkar (Group 22)  
**Execution Date:** 17 November 2026  
**Environment:** Disposable PostgreSQL Test Database (`postgresql+psycopg://postgres:postgres@localhost:5432/ccms_test`) on PostgreSQL 16  
**Execution Commit SHA:** `1c61c6f` (Merge remote-tracking branch 'origin/main' into sprint-3/dev-qa-run)  
**Git Baseline:** PR #46, PR #47, PR #48, PR #50, PR #51, PR #52, PR #53, PR #56, PR #60, PR #92  

---

## 1. Test Execution Summary

| Test Area | Planned Steps | Passed | Failed / Action | Status |
| :--- | :---: | :---: | :---: | :---: |
| **Database Migrations (0008-0013)** | 4 | 4 | 0 | **PASS** |
| **Demo Seed & Data Idempotency** | 3 | 3 | 0 | **PASS** |
| **Location Hierarchy & Residence Lifecycle** | 6 | 6 | 0 | **PASS** |
| **Located Complaints with Floor ID** | 4 | 4 | 0 | **PASS** |
| **Hostel Feed Isolation & Scoping** | 5 | 5 | 0 | **PASS** |
| **Privacy Boundary & Data Leak Prevention** | 4 | 4 | 0 | **PASS** |
| **Concurrency & Duplicate Detection** | 3 | 2 | 1 | **ACTION LOGGED** |
| **Total** | **29** | **28** | **1** | **96.6% PASS** |

---

## 2. Reproduction Commands & Test Execution

All tests were executed against an isolated PostgreSQL 16 test database instance:

```bash
# 1. Provision isolated disposable PostgreSQL database
psql -h localhost -U postgres -d ccms_db -c "DROP DATABASE IF EXISTS ccms_test;"
psql -h localhost -U postgres -d ccms_db -c "CREATE DATABASE ccms_test;"

# 2. Run PostgreSQL migration upgrade / downgrade flow
export DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/ccms_db"
export ENVIRONMENT=testing
export JWT_SECRET=test_secret_key_for_ci_pipeline_minimum_32_characters_long
python scripts/test_migration_flow.py --db-url "$DATABASE_URL"

# 3. Run Sprint 3 test suites against disposable PostgreSQL database
export DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/ccms_test"
export CCMS_DISPOSABLE_TEST_POSTGRES_URL="postgresql+psycopg://postgres:postgres@localhost:5432/ccms_test"
export TEST_POSTGRESQL_URL="postgresql+psycopg://postgres:postgres@localhost:5432/ccms_test"

pytest -v -rs \
  tests/test_migration_0011_0012_public_feed.py \
  tests/test_sprint3_residence_concurrency.py \
  tests/test_sprint3_acceptance.py \
  tests/test_sprint3_privacy.py \
  tests/test_sprint3_public_feeds.py \
  tests/test_sprint3_residences.py \
  tests/test_sprint3_visibility_matrix.py \
  tests/test_sprint3_demo_seed.py
```

---

## 3. Detailed Step-by-Step Execution Results (29 Steps)

### Group 1: Database Migration Chain & Integrity (4 Steps)
- **Step 1.1: Migration upgrade from 0007 to 0013 head on PostgreSQL**
  - **Command:** `python scripts/test_migration_flow.py --db-url "$DATABASE_URL"`
  - **Result:** `PASS`. Tables `hostels`, `hostel_wings`, `hostel_floors`, `student_residences`, `hmc_groups`, `hmc_group_floors`, and `complaint_hmc_audiences` created cleanly on PostgreSQL.
- **Step 1.2: Check foreign keys & constraints on `hostel_floors`**
  - **Result:** `PASS`. Unique constraint `uq_hostel_floors_wing_code` enforced; duplicate or invalid floor codes rejected by schema.
- **Step 1.3: Migration 0013 backfill validation**
  - **Command:** `pytest tests/test_migration_0011_0012_public_feed.py -k test_0013_backfill`
  - **Result:** `PASS`. Existing complaints with matching hostel, wing, and floor text received canonical `floor_id` links without corrupting legacy location fields.
- **Step 1.4: Migration downgrade to 0007 and re-upgrade flow**
  - **Result:** `PASS`. Clean downgrade drops Sprint 3 tables cleanly; subsequent re-upgrade restores full schema without error.

### Group 2: Demo Seeding & Data Idempotency (3 Steps)
- **Step 2.1: Initial database seeding on PostgreSQL**
  - **Command:** `python -m app.scripts.seed_sprint3_demo`
  - **Result:** `PASS`. Successfully seeded 3 hostels (OHM, NHM, HFW), 14 wings, 46 floors, student accounts, verified residence mappings, and sample located complaints.
- **Step 2.2: Re-running demo seed (idempotency verification)**
  - **Command:** `python -m app.scripts.seed_sprint3_demo`
  - **Result:** `PASS`. Script detects pre-existing rows and avoids duplicate key collisions or integrity errors.
- **Step 2.3: Password hashing & authentication validation**
  - **Result:** `PASS`. All demo accounts configured with valid password hashes; login via `POST /api/v1/auth/login` issues valid JWT access tokens.

### Group 3: Location Hierarchy & Residence Lifecycle (6 Steps)
- **Step 3.1: `GET /api/v1/locations/hostels` (Unauthenticated)**
  - **Result:** `PASS`. Unauthenticated request returns HTTP 401 Unauthorized.
- **Step 3.2: `GET /api/v1/locations/hostels` (Authenticated Student & Staff)**
  - **Result:** `PASS`. Returns canonical nested tree of active hostels, wings, and floors with codes and labels.
- **Step 3.3: `PATCH /api/v1/users/me/residence` (Declare new floor)**
  - **Result:** `PASS`. Student residence declaration sets status to `pending` with `remark: null` and invalidates previous feed access.
- **Step 3.4: `GET /api/v1/staff/residences` queue filtering**
  - **Result:** `PASS`. Hostel staff sees pending residence declarations; non-hostel department staff receives HTTP 403 Forbidden.
- **Step 3.5: `POST /api/v1/staff/residences/{id}/decision` (Approve)**
  - **Result:** `PASS`. Status updates to `verified`, stamping `verified_by_id` and timestamp `decided_at`.
- **Step 3.6: Second decision on decided residence**
  - **Result:** `PASS`. Attempting a second decision returns HTTP 409 Conflict with original approval and timestamps left untouched.

### Group 4: Located Complaints with Floor ID (4 Steps)
- **Step 4.1: Create complaint with valid `floor_id`**
  - **Command:** `POST /api/v1/complaints` with `floor_id`
  - **Result:** `PASS`. Complaint successfully created and linked to target floor; `visibility_scope` set to `hmc_group_public`.
- **Step 4.2: Create complaint with non-existent `floor_id`**
  - **Result:** `PASS`. Validation returns HTTP 422 Unprocessable Entity ("Invalid floor_id").
- **Step 4.3: Create complaint without `floor_id` (general department complaint)**
  - **Result:** `PASS`. General complaints without floor reference route directly to department scope without hostel locking.
- **Step 4.4: Inactive floor validation**
  - **Result:** `PASS`. Complaints attempting to attach to a deactivated floor or wing are rejected with HTTP 422.

### Group 5: Hostel Feed Isolation & Scoping (5 Steps)
- **Step 5.1: Same hostel feed visibility**
  - **Command:** `GET /api/v1/feeds/hostel`
  - **Result:** `PASS`. Student resident in the same hostel sees the published located complaint in their feed.
- **Step 5.2: Cross-hostel feed isolation**
  - **Command:** `GET /api/v1/feeds/hostel` from student in different hostel
  - **Result:** `PASS`. Student in a different hostel does NOT see complaints from other hostels in their feed.
- **Step 5.3: Unverified student feed access boundary**
  - **Result:** `PASS`. Student with unverified or pending residence receives HTTP 403 `residence_not_verified` (fails closed).
- **Step 5.4: Campus public feed aggregation**
  - **Command:** `GET /api/v1/feeds/campus`
  - **Result:** `PASS`. Public non-hostel complaints appear on campus feed while unapproved hostel complaints remain hidden.
- **Step 5.5: Hostel staff queue scoping**
  - **Result:** `PASS`. Hostel staff can only access queues and complaints for hostels assigned to their user profile.

### Group 6: Privacy Boundary & Data Leak Prevention (4 Steps)
- **Step 6.1: Complaint description stripped from feed payloads**
  - **Result:** `PASS`. Feed endpoints omit `description` field in both `FeedItem` and `HostelFeedItem` schemas.
- **Step 6.2: Student identity protection in public feeds**
  - **Result:** `PASS`. No student email, full name, or `created_by_id` is exposed in feed JSON.
- **Step 6.3: Duplicate suggestions leak prevention**
  - **Result:** `PASS`. Suggestions endpoint omits raw complaint descriptions and complainant identity of existing complaints.
- **Step 6.4: Cross-user direct complaint detail access**
  - **Result:** `PASS`. `GET /api/v1/complaints/{id}` strictly restricts private complaint inspection to owner, assigned staff, and administrators.

### Group 7: Concurrency & Duplicate Detection (3 Steps)
- **Step 7.1: Evaluate duplicate similarity threshold setting**
  - **Result:** `ACTION LOGGED`.
  - **Observation:** `duplicate_service.py` originally hardcoded `PRODUCTION_THRESHOLD = 0.70`, whereas ML evaluation specified optimal gap score of 0.375.
  - **Resolution:** Updated and resolved in PR #61.
- **Step 7.2: Simultaneous decision concurrency under PostgreSQL**
  - **Command:** `pytest tests/test_sprint3_residence_concurrency.py`
  - **Result:** `PASS`. Two simultaneous decision requests executed concurrently in separate PostgreSQL transactions; exactly one succeeds (HTTP 200) and the second receives HTTP 409 Conflict.
- **Step 7.3: Near-duplicate detection response check**
  - **Result:** `PASS`. Creating near-duplicate complaint (C5 vs C7) triggers the duplicate warning prompt with similarity score while permitting intentional submission.

---

## 4. Observations & Resolution Log

| ID | Component | Description | Severity | Resolution / Reference |
| :--- | :--- | :--- | :---: | :--- |
| **BUG-01** | `duplicate_service.py` | Similarity threshold set to 0.70 instead of optimal 0.375 gap score. | Medium | Corrected in PR #61 |
| **OBS-02** | `staff_residences` | Simultaneous decision race conditions require PostgreSQL row-level locks. | Medium | Validated and locked in PR #92 / S3-15 |
| **OBS-03** | `locations` | Deactivated floors must be excluded from location picker tree. | Low | Enforced in PR #46 / verified |
