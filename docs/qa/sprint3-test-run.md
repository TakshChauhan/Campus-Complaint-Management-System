# Sprint 3 QA Test Run & Validation Report

**Tester:** QA / Dev Thakkar (Group 22)  
**Execution Date:** 5 November 2026  
**Environment:** Local SQLite Test Engine & Sprint 3 Demo Database  
**Git Baseline:** PR #46, PR #47, PR #48, PR #50, PR #51, PR #52, PR #53, PR #56, PR #60  

---

## 1. Test Execution Summary

The totals below count only the explicitly numbered execution cases in Section 2. No additional planned-but-undocumented checks are included.

| Test Area | Documented Steps | Passed | Failed | Status |
| :--- | :---: | :---: | :---: | :---: |
| **Database Migration Chain & Integrity** | 4 | 4 | 0 | **PASS** |
| **Demo Seed & Idempotency** | 3 | 3 | 0 | **PASS** |
| **Location Tree & Residence Lifecycle** | 6 | 6 | 0 | **PASS** |
| **Located Complaint Creation** | 1 | 1 | 0 | **PASS** |
| **Hostel Feed Isolation & Access** | 3 | 3 | 0 | **PASS** |
| **Privacy Boundary Validation** | 3 | 3 | 0 | **PASS** |
| **Duplicate Detection Threshold** | 1 | 0 | 1 | **ACTION LOGGED** |
| **Total** | **21** | **20** | **1** | **95.2% PASS** |

---

## 2. Detailed Step-by-Step Execution Results

### Group 1: Database Migration Chain & Integrity
- **Step 1.1: Migration upgrade from 0007 to 0013 head**
  - **Result:** `PASS`. Tables `hostels`, `hostel_wings`, `hostel_floors`, `student_residences`, `hmc_groups`, `hmc_group_floors`, and `complaint_hmc_audiences` created cleanly.
- **Step 1.2: Check foreign keys & constraints on `hostel_floors`**
  - **Result:** `PASS`. Unique constraint `uq_hostel_floors_wing_code` enforced; invalid uppercase codes rejected.
- **Step 1.3: Migration 0013 backfill validation**
  - **Result:** `PASS`. Complaints with matching hostel/wing/floor text received canonical `floor_id` without corrupting legacy text.
- **Step 1.4: Migration downgrade to 0007 and re-upgrade**
  - **Result:** `PASS`. Downgrade clean; idempotent re-upgrade succeeds.

### Group 2: Demo Seeding (`seed_sprint3_demo.py`)
- **Step 2.1: Initial database seeding**
  - **Result:** `PASS`. Created 3 hostels (OHM, NHM, HFW), wings, floors, test accounts, student residences, and demo complaints.
- **Step 2.2: Re-running demo seed (idempotency test)**
  - **Result:** `PASS`. Script detects existing records and does not insert duplicate rows or fail with unique constraint violations.
- **Step 2.3: Password hashing verification**
  - **Result:** `PASS`. Demo accounts use bcrypt password hashes. The test fixture verifies student login using its configured test password; the seed script itself reads passwords from environment/settings and does not print them.

### Group 3: Location Tree & Residence Lifecycle
- **Step 3.1: `GET /api/v1/locations/hostels` (Unauthenticated)**
  - **Result:** `PASS`. Returns HTTP 401 Unauthorized.
- **Step 3.2: `GET /api/v1/locations/hostels` (Authenticated Student & Staff)**
  - **Result:** `PASS`. Returns full nested tree of active hostels, wings, and floors.
- **Step 3.3: `PATCH /api/v1/users/me/residence` (Declare new floor)**
  - **Result:** `PASS`. Status set to `pending`, remark reset to `null`.
- **Step 3.4: `GET /api/v1/staff/residences` queue filtering**
  - **Result:** `PASS`. Hostel staff sees pending requests; IT staff received HTTP 403 Forbidden.
- **Step 3.5: `POST /api/v1/staff/residences/{id}/decision` (Approve)**
  - **Result:** `PASS`. Status changed to `verified`, verifier user ID recorded.
- **Step 3.6: Second decision on approved residence**
  - **Result:** `PASS`. Returns HTTP 409 Conflict; original approval and timestamps left untouched.

### Group 4: Located Complaint Creation
- **Step 4.1: Create complaint with valid `floor_id`**
  - **Result:** `PASS`. Complaint linked to floor; `visibility_scope` set to `hmc_group_public`.

### Group 5: Hostel Feed Isolation & Access
- **Step 5.1: Feed visibility for resident of same hostel**
  - **Result:** `PASS`. Student in the same hostel sees the complaint in `GET /api/v1/feeds/hostel`.
- **Step 5.2: Feed isolation for resident of different hostel**
  - **Result:** `PASS`. Student in a different hostel does NOT see the complaint in their feed.
- **Step 5.3: Unverified student feed access**
  - **Result:** `PASS`. Student without verified residence receives HTTP 403 `residence_not_verified`.

### Group 6: Privacy Boundary Validation
- **Step 6.1: Description exposure in feed items**
  - **Result:** `PASS`. `description` key is stripped from all feed responses (`FeedItem` & `HostelFeedItem`).
- **Step 6.2: Student identity exposure in feeds**
  - **Result:** `PASS`. No email, student name, or `created_by_id` present in feed JSON.
- **Step 6.3: Duplicate suggestions leak test**
  - **Result:** `PASS`. Duplicate suggestions omit description, reporter name, and other hostels' complaints.

### Group 7: Duplicate Detection Threshold Verification
- **Step 7.1: Evaluate threshold setting in code**
  - **Result:** `FAIL / ISSUE RECORDED`.
  - **Observation:** `duplicate_service.py` hardcodes `PRODUCTION_THRESHOLD = 0.70`, whereas evaluation README specified `0.10` / `0.375`. A threshold of 0.70 has low recall and misses real duplicates.
  - **Issue Link:** Addressed in PR #61 (Krish).

---

## 3. Bug & Observation Log

| ID | Component | Description | Severity | Resolution / PR |
| :--- | :--- | :--- | :---: | :--- |
| **BUG-01** | `duplicate_service.py` | Production similarity threshold set to 0.70 instead of optimal 0.375 gap score. | Medium | Corrected in PR #61 |
| **OBS-02** | `staff_residences` | Double-decision on same residence requires explicit 409 handling. | Low | Verified in S3-15 concurrency tests |
| **OBS-03** | `locations` | Deactivated floors must be excluded from location picker tree. | Low | Handled in PR #46 / verified |
