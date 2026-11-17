# Sprint 3 Demonstration Script (CCMS)

**Project:** Campus Complaint Management System (CCMS)  
**Sprint:** Sprint 3 Demo Walkthrough  
**Group:** IT314 Group 22  
**Target Environment:** Local development/testing with SQLite only (`app.scripts.seed_sprint3_demo`)

---

## 1. Demo Objectives & Verified Deliverables

This script walks through the Sprint 3 demo capabilities:
1. **Canonical Location Hierarchy:** Active Hostel → Wing → Floor tree (`GET /api/v1/locations/hostels`).
2. **Student Residence Lifecycle:** Student declaration, verification queue, and approval/rejection (`/users/me/residence` & `/staff/residences`).
3. **Located Complaint Creation:** Attaching canonical `floor_id` to complaints (`POST /api/v1/complaints`).
4. **Hostel & Department Public Feeds:** Feed visibility rules, auto-publishing, and isolation across hostels.
5. **Privacy Enforcement:** No exposure of description, creator email, or reporter ID in public feeds.
6. **Hostel Resolution Metrics:** Aggregated resolution durations grouped by hostel.

---

## 2. Local SQLite Setup & Demo Accounts

The Sprint 3 seed is restricted to a development/testing SQLite database. It refuses non-SQLite database sessions and does not support PostgreSQL for this demo.

From the backend directory, configure the local `.env`/environment with:
- `ENVIRONMENT=development` (or `testing`)
- `DATABASE_URL=sqlite:///./ccms.db` (use your intended local SQLite file)
- `DEV_STUDENT_PASSWORD` (required; choose a local demo password)

The admin and IT staff credentials are configured by `DEV_ADMIN_EMAIL`, `DEV_ADMIN_PASSWORD`, `DEV_STAFF_EMAIL`, and `DEV_STAFF_PASSWORD`. If not overridden, the settings defaults are:
- Admin: `admin@campus.edu` / `AdminSecret123!`
- IT Staff: `staff.it@campus.edu` / `StaffSecret123!`

The Sprint 3 seed creates the hostel staff account `demo.staff.hostel@dau.ac.in` using `DEV_STAFF_PASSWORD`, and student accounts using `DEV_STUDENT_PASSWORD`:
- Student 1: `demo3.h1.student1@dau.ac.in` — OHM, Wing A, Floor 1 (verified)
- Student 2: `demo3.h1.student2@dau.ac.in` — OHM, Wing A, Floor 1 (verified)
- Student 3: `demo3.h2.student@dau.ac.in` — HFW, **Wing J**, Floor 1 (verified)
- Pending Student: `demo3.pending.student@dau.ac.in` — NHM, Wing L, Floor 1 (pending)

Admin and IT staff are created by the development-user seed; the Sprint 3 seed reuses the configured admin and creates the hostel staff account. The script does not create a separate `demo.staff.it@campus.edu` account. Passwords are supplied through local configuration and are not printed by the seed script.

Run these commands in order from the backend directory:
```bash
python -m app.scripts.seed_departments
python -m app.scripts.seed_dev_users
python -m app.scripts.seed_sprint3_demo
```

---

## 3. Step-by-Step Walkthrough

### Scenario 1: Canonical Location Tree Inspection
- **Actor:** Any authenticated user (e.g., Student 1)
- **Action:** Open the location picker or call `GET /api/v1/locations/hostels`.
- **Expected Result:**
  - Returns hierarchical JSON of active hostels (OHM, NHM, HFW), wings, and floors.
  - Deactivated floors or wings are omitted.
  - No internal user IDs or HMC secret mappings are revealed.

### Scenario 2: Student Residence & Verification Queue
- **Actor:** Pending Student (`demo3.pending.student@dau.ac.in`)
- **Action:**
  1. Confirm the seeded residence appears as `pending` in **Staff Dashboard → Residence Verification Queue** (`GET /api/v1/staff/residences?status=pending`).
  2. Hostel Staff (`demo.staff.hostel@dau.ac.in`) locates the request and approves it using `POST /api/v1/staff/residences/{id}/decision` with `{"decision": "approve"}`.
- **Expected Result:**
  - Residence status changes to `verified`, recording `verified_at` and `verified_by_id`.
  - Attempting to approve or reject the same request again returns **`409 Conflict`** (concurrency protection).
  - The student can now access the hostel feed (`200 OK`).

### Scenario 3: Located Complaint Creation & Feed Isolation
- **Actor:** Student 1 (`demo3.h1.student1@dau.ac.in`)
- **Action:** Raise a public hostel complaint titled *"Water cooler on OHM Wing A first floor not cooling"* with `floor_id` set to OHM-A-F1.
- **Expected Result:**
  - Complaint is created with `visibility_scope: "hmc_group_public"` and published.
  - **Student 2** (same hostel OHM) calls `GET /api/v1/feeds/hostel` and sees the complaint.
  - **Student 3** (HFW, Wing J) calls `GET /api/v1/feeds/hostel` and does **not** see Student 1's complaint.

### Scenario 4: Privacy Boundary Validation
- **Actor:** Student 2 viewing the feed item.
- **Inspection:** Inspect JSON payload of `GET /api/v1/feeds/hostel` and `GET /api/v1/feeds/items/{id}`.
- **Expected Result:**
  - Returns `title`, `department_name`, `status`, `created_at`, `hostel`, `wing`, `floor`.
  - `description`, `created_by_id`, student name, and student email are absent.

### Scenario 5: Resolution Metrics by Hostel
- **Actor:** Administrator (configured `DEV_ADMIN_EMAIL`)
- **Action:** Request `GET /api/v1/admin/metrics/resolution/by-hostel?window_days=30`.
- **Expected Result:**
  - Returns rolling resolution averages grouped by hostel ID and name.
  - Resolves correctly and excludes negative durations.
