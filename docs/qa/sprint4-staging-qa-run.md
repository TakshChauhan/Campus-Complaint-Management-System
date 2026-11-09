# Sprint 4 Staging QA Run & Validation Report (S4-25)

**Tester:** Dev Thakkar (Group 22)  
**Environment:** Staging Environment (PostgreSQL + FastAPI + Vite React)  
**Date:** 9 November 2026  
**Scope:** Model 2 Hostel Feed Scoping, Staff-Hostel Assignments, Admin Coverage Gaps, Concurrency Checks  

---

## 1. Test Summary

| Test Domain | Executed | Passed | Failed | Status |
| :--- | :---: | :---: | :---: | :---: |
| **Model 2 Feed Scoping (`scope=hostel\|wing\|floor`)** | 5 | 5 | 0 | **PASS** |
| **Hostel-Scoped Staff Access (404 on out-of-scope)** | 4 | 4 | 0 | **PASS** |
| **Staff Hostel Assignment Admin API** | 4 | 4 | 0 | **PASS** |
| **Admin Coverage Gaps (`GET /admin/coverage-gaps`)** | 4 | 4 | 0 | **PASS** |
| **Simultaneous Concurrency (Residence & Status Updates)** | 3 | 3 | 0 | **PASS** |
| **Total** | **20** | **20** | **0** | **100% PASS** |

---

## 2. Test Step Breakdown

### 1. Model 2 Feed Scoping
- **Step 1.1:** Student with verified residence in OHM Wing A Floor 1 calls `/api/v1/feeds/hostel?scope=floor`.
  - **Result:** `PASS`. Returns only complaints located on Floor 1 of Wing A.
- **Step 1.2:** Same student calls `/api/v1/feeds/hostel?scope=wing`.
  - **Result:** `PASS`. Returns all complaints located across all floors of Wing A.
- **Step 1.3:** Same student calls `/api/v1/feeds/hostel?scope=hostel`.
  - **Result:** `PASS`. Returns complaints across the entire OHM hostel.
- **Step 1.4:** Unverified student calls `/api/v1/feeds/hostel`.
  - **Result:** `PASS`. Returns HTTP 403 `residence_not_verified`.

### 2. Hostel-Scoped Staff Isolation
- **Step 2.1:** Staff assigned to OHM calls `GET /api/v1/staff/complaints`.
  - **Result:** `PASS`. Shows only complaints located in OHM.
- **Step 2.2:** Staff assigned to OHM attempts `GET /api/v1/staff/complaints/{id}` for a NHM complaint.
  - **Result:** `PASS`. Returns HTTP 404 (out-of-scope items fail closed).

### 3. Staff Hostel Assignment Admin API
- **Step 3.1:** Admin calls `GET /api/v1/admin/staff`.
  - **Result:** `PASS`. Returns staff users with their assigned hostel IDs.
- **Step 3.2:** Admin calls `PUT /api/v1/admin/staff/{id}/hostels` with `{"hostel_ids": [1, 2]}`.
  - **Result:** `PASS`. Successfully assigns multiple hostels to the staff member.

### 4. Admin Coverage Gaps
- **Step 4.1:** Unassigned hostel with open complaints.
  - **Result:** `PASS`. Appears in `GET /api/v1/admin/coverage-gaps` with correct `open_count`.
- **Step 4.2:** Assigning active staff to the hostel.
  - **Result:** `PASS`. Hostel immediately disappears from coverage gaps list.
- **Step 4.3:** Hostel with assigned staff that is deactivated (`is_active = false`).
  - **Result:** `PASS`. Hostel appears in coverage gaps (inactive staff does not provide coverage).

### 5. Simultaneous Concurrency
- **Step 5.1:** Simultaneous residence decisions from separate sessions.
  - **Result:** `PASS`. Exactly one succeeds (200), second receives HTTP 409 Conflict.
