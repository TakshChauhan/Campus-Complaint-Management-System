# Campus Complaint Management System (CCMS) — Comprehensive Viva Defense Guide

**Candidate:** Dev Thakkar (Student ID: `202401225`, Email: `202401225@dau.ac.in`)  
**Course:** IT314 Software Engineering | **Group:** 22 | **Institution:** Dhirubhai Ambani University (DAU)  
**Assigned Sprint Responsibilities:** S4-07 (Hostel Coverage Gaps), S3-15 (Residence Concurrency Testing), S4-23/27 (QA, ML Hold-Out Evaluation, Fullstack DevOps)

---

## 1. System Architecture & Engineering Stack

```
[ Frontend: React 18 + TypeScript + Vite + Nginx ]
                        │
                        ▼ (HTTP REST + Bearer JWT)
[ Backend: FastAPI (Python 3.12) + Pydantic v2 + Uvicorn ]
                        │
       ┌────────────────┴────────────────┐
       ▼                                 ▼
[ SQLAlchemy 2.0 ORM ]         [ ML Duplicate Engine (TF-IDF + Cosine) ]
       │
       ▼
[ PostgreSQL 16 (Staging/Prod) / SQLite (Unit Tests) ]
       │
[ Alembic Schema Migrations (Strictly Append-Only) ]
```

### Why these technology choices?
- **FastAPI vs Django/Flask:** FastAPI provides asynchronous request handling, automatic OpenAPI/Swagger documentation generation, and native type-validation via Pydantic v2 with C-speed parsing.
- **SQLAlchemy 2.0 + Alembic:** Declarative mapping provides full type safety, query optimization via `joinedload()`, and append-only version-controlled database migrations preventing drift across environments.
- **Vite + React 18:** Near-instantaneous Hot Module Replacement (HMR), tree-shaking, and lightweight bundle footprint compared to Create React App.

---

## 2. Core Modules Implemented by Dev Thakkar

### 2.1 Hostel Coverage Gaps Service (S4-07)
- **Problem:** Hostels may receive student grievances but have no active staff assigned to inspect and resolve them, causing complaints to languish unattended.
- **Engineering Implementation:**
  - Endpoint: `GET /api/v1/admin/coverage-gaps` (Restricted to `admin` role).
  - Business Logic:
    1. Fetch all active hostels.
    2. Query open complaints (status in `submitted`, `in_progress`, `reopened`).
    3. Query staff assignments strictly filtering for active staff (`User.is_active == True` and `User.role == 'staff'`).
    4. If an active hostel has open complaints and zero active staff members assigned, it is returned as a **Coverage Gap**.
    5. Inactive staff assignments do **not** grant coverage (fixed per PR #75 review feedback).

### 2.2 Residence Concurrency Verification (S3-15)
- **Problem:** Multiple hostel wardens or staff opening the same student residence declaration simultaneously could trigger race conditions or duplicate conflicting approvals/rejections.
- **Engineering Implementation:**
  - Multi-session concurrency test: `test_concurrent_simultaneous_decisions_with_separate_sessions`.
  - Uses `threading.Barrier(2)` and two independent database sessions (`TestingSessionLocal()`).
  - Releases both transactions into the database at the exact same millisecond.
  - Verifies database-level isolation: exactly **one transaction succeeds (HTTP 200)** and the simultaneous competing transaction is blocked with **HTTP 409 Conflict**.

### 2.3 ML Duplicate Detection Hold-Out Generalization (S4-27)
- **Problem:** The Sprint 2 similarity threshold of `0.375` was evaluated on the same 100 pairs used for threshold exploration. An unseen test set was required to verify whether this threshold generalizes without overfitting.
- **Engineering Implementation:**
  - Constructed `ml/data/holdout_pairs.csv` with 40 balanced, unseen complaint pairs (20 duplicates, 20 non-duplicates).
  - Included hard lexical edge cases: synonyms/paraphrases (e.g. "air conditioner" vs "AC") and lexical distractors (e.g. same problem in Room 204 vs Room 308).
  - Generalization benchmark showed `0.375` achieved **100% Precision (0 False Positives)** and **90% Recall**, confirming production safety.

---

## 3. Database Schema & Normalization (3NF)

- **1NF:** All attributes contain atomic values; composite addresses decomposed into `hostel`, `wing`, `floor_id`.
- **2NF:** All non-key attributes fully depend on the primary key. Many-to-many associations decomposed via junction tables:
  - `staff_hostel_assignments`: (`user_id`, `hostel_id`) with unique constraint.
  - `hmc_group_floors`: (`group_id`, `floor_id`).
- **3NF:** No transitive dependencies. Department metadata lives in `departments`, user credentials live in `users`, and complaints reference foreign keys with explicit `ondelete="RESTRICT"`.

---

## 4. Top 25 Viva Questions & Word-for-Word Model Answers

#### Q1: What was your exact role and contribution to Group 22?
> **Answer:** "I am Dev Thakkar, responsible for core backend and DevOps deliverables. In Sprint 4, I designed and implemented the Hostel Coverage Gaps detection service (S4-07), built multi-session concurrency test harnesses verifying race-condition safety (S3-15), authored the held-out generalization benchmark for duplicate detection (S4-27), and authored the multi-container Docker deployment suite."

#### Q2: What happens if two staff members try to approve the same residence request at the exact same time?
> **Answer:** "We prevent double-decisions at both application and database layers. When a decision is submitted, the record's current state is validated within an atomic transaction. If another transaction modifies the status first, the second session encounters a state conflict and is rejected with an HTTP 409 Conflict status. Our S3-15 test suite proves this using `threading.Barrier` across separate PostgreSQL and SQLite sessions."

#### Q3: Why does your coverage gaps service ignore deactivated staff?
> **Answer:** "A hostel is only genuinely covered if an employee is currently active and capable of taking action. If a staff member resigns or their account is deactivated by an administrator, any historical assignment remains in the database for audit integrity, but cannot resolve complaints. Filtering by `is_active == True` ensures administrators see the real operational gap."

#### Q4: How does your system prevent SQL Injection?
> **Answer:** "We use SQLAlchemy ORM with fully parameterized queries. User input is never concatenated into raw SQL strings. For fuzzy search (`LIKE`), we built a custom escaping helper that escapes SQL wildcards (`%`, `_`, `\`) before passing them to parameterized expressions."

#### Q5: How do you prevent Cross-Site Scripting (XSS)?
> **Answer:** "Inputs are stored as inert text data in PostgreSQL. When rendered in the React 18 frontend, JSX automatically encodes HTML entities, preventing browser script execution. We have an automated test asserting that `<script>alert('xss')</script>` is safely persisted and returned without execution."

#### Q6: Why did you choose a TF-IDF threshold of 0.375 for duplicate detection?
> **Answer:** "In our Sprint 2 benchmark, non-duplicate pairs had a maximum similarity of 0.1417, while duplicate pairs had a minimum similarity of 0.7429. Setting the threshold at 0.375 placed it safely in the score gap. In Sprint 4, our 40-pair holdout test set proved that 0.375 maintained 100% precision (zero false duplicate alarms)."

#### Q7: What is the difference between a student residence and a complaint location?
> **Answer:** "A student residence is where a student permanently lives on campus (e.g. Hostel OHM, Floor 2). A complaint location is where the physical problem actually occurred (e.g. water leakage in Library 1st floor). Keeping these entities separate ensures students can report campus-wide issues while maintaining verified residential access."

#### Q8: How does your system manage database schema changes in a team of 11 developers?
> **Answer:** "We enforce append-only Alembic migrations. Once a migration script is merged into `main`, it is immutable. Any new changes require a subsequent migration script with `alembic revision --autogenerate`. This prevents merge conflicts and database state corruption."

#### Q9: What happens if the duplicate detection ML engine fails or crashes?
> **Answer:** "The duplicate suggestion endpoint fails safely: if TF-IDF calculation throws an exception or fails, it catches the error, logs it to our structured logger, and returns an empty match array `[]`. The student is never blocked from lodging their complaint."

#### Q10: How do you ensure passwords and tokens are never leaked in logs?
> **Answer:** "We implemented a custom `SensitiveQueryFilter` inside Python's logging pipeline that redacts query parameters containing `code=` or `state=` from HTTP access logs. Passwords are never serialized into Pydantic response models."
