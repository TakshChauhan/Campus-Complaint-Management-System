# Sprint 3 Demonstration Script (CCMS)

**Project:** Campus Complaint Management System (CCMS)  
**Sprint:** Sprint 3 Demo Walkthrough  
**Group:** IT314 Group 22  
**Target Environment:** Local SQLite Development / Demo Database (`app.scripts.seed_sprint3_demo`)  

---

## 1. Demo Objectives & Verified Deliverables

This script walks through all Sprint 3 demo capabilities delivered across PRs #46, #47, #48, #49, #50, #51, #52, #53, #54, #56, and #57:
1. **Canonical Location Hierarchy:** Active Hostel → Wing → Floor tree (`GET /api/v1/locations/hostels`).
2. **Student Residence Lifecycle:** Student declaration, verification queue, and approval/rejection (`/users/me/residence` & `/staff/residences`).
3. **Located Complaint Creation:** Attaching canonical `floor_id` to complaints (`POST /api/v1/complaints`).
4. **Hostel & Department Public Feeds:** Feed visibility rules, auto-publishing, and isolation across hostels.
5. **Privacy Enforcement:** Zero exposure of description, creator email, or reporter ID in public feeds.
6. **Hostel Resolution Metrics:** Aggregated resolution durations grouped by hostel.

---

## 2. Demo Seed Accounts

Run the database reset and demo seed:
```bash
python -m app.scripts.seed_sprint3_demo
```

| Role | Email | Password | Assigned Scope / Location |
| :--- | :--- | :--- | :--- |
| **Admin** | `admin.demo@campus.edu` | `LocalDemoOnly123!` | Campus-wide Administrator |
| **Hostel Staff** | `demo.staff.hostel@campus.edu` | `LocalDemoOnly123!` | Hostel Department Staff |
| **IT Staff** | `demo.staff.it@campus.edu` | `LocalDemoOnly123!` | IT Services Department Staff |
| **Student 1** | `demo3.h1.student1@dau.ac.in` | `LocalDemoOnly123!` | Old Hostel for Men (OHM), Wing A, Floor 1 (Verified) |
| **Student 2** | `demo3.h1.student2@dau.ac.in` | `LocalDemoOnly123!` | Old Hostel for Men (OHM), Wing A, Floor 1 (Verified) |
| **Student 3** | `demo3.h2.student@dau.ac.in` | `LocalDemoOnly123!` | Hostel for Women (HFW), Wing A, Floor 1 (Verified) |
| **New Student** | `newcomer.student@dau.ac.in` | `LocalDemoOnly123!` | Unassigned (Pending Residence Declaration) |

---

## 3. Step-by-Step Walkthrough

### Scenario 1: Canonical Location Tree Inspection
- **Actor:** Any authenticated user (e.g., Student 1)
- **Action:** Open the location picker or call `GET /api/v1/locations/hostels`.
- **Expected Result:**
  - Returns hierarchical JSON of active hostels (OHM, NHM, HFW), wings, and floors.
  - Deactivated floors or wings are omitted.
  - No internal user IDs or HMC secret mappings are revealed.

### Scenario 2: Student Residence Declaration
- **Actor:** New Student (`newcomer.student@dau.ac.in`)
- **Action:** Navigate to **Profile Page**, select `Hostel for Women -> Wing A -> Floor 1`, and submit declaration (`PATCH /api/v1/users/me/residence`).
- **Expected Result:**
  - Status immediately reflects `pending` with `remark: null`.
  - Calling `GET /api/v1/feeds/hostel` returns `403 residence_not_verified` (fails closed).

### Scenario 3: Hostel Staff Queue & Verification
- **Actor:** Hostel Staff (`demo.staff.hostel@campus.edu`)
- **Action:**
  1. Navigate to **Staff Dashboard -> Residence Verification Queue** (`GET /api/v1/staff/residences?status=pending`).
  2. Locate New Student's declaration.
  3. Click **Approve** (`POST /api/v1/staff/residences/{id}/decision` with `{"decision": "approve"}`).
- **Expected Result:**
  - Residence status changes to `verified`, stamping `decided_at` and `verified_by_id`.
  - Attempting to click "Approve" or "Reject" again returns **`409 Conflict`** (Concurrency protection).
  - New Student can now access their hostel feed (`200 OK`).

### Scenario 4: Located Complaint Creation & Feed Isolation
- **Actor:** Student 1 (`demo3.h1.student1@dau.ac.in`)
- **Action:** Raise a public hostel complaint titled *"Water cooler leaking on Floor 1"* with `floor_id` set to OHM-A-F1.
- **Expected Result:**
  - Complaint is created with `visibility_scope: "hmc_group_public"` and published.
  - **Student 2** (same hostel OHM) calls `GET /api/v1/feeds/hostel` and sees the complaint.
  - **Student 3** (different hostel HFW) calls `GET /api/v1/feeds/hostel` and **does NOT** see Student 1's complaint.

### Scenario 5: Privacy Boundary Validation
- **Actor:** Student 2 viewing the feed item.
- **Inspection:** Inspect JSON payload of `GET /api/v1/feeds/hostel` and `GET /api/v1/feeds/items/{id}`.
- **Expected Result:**
  - Returns `title`, `department_name`, `status`, `created_at`, `hostel`, `wing`, `floor`.
  - `description`, `created_by_id`, student name, and student email are **strictly absent**.

### Scenario 6: Resolution Metrics by Hostel
- **Actor:** Administrator (`admin.demo@campus.edu`)
- **Action:** Request `GET /api/v1/admin/metrics/resolution/by-hostel?window_days=30`.
- **Expected Result:**
  - Returns rolling resolution averages grouped by hostel ID and name.
  - Resolves correctly and excludes negative durations.
