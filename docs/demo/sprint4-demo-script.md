# Sprint 4 Demonstration Script (CCMS)

**Project:** Campus Complaint Management System (CCMS)  
**Sprint:** Sprint 4 Final Review  
**Group:** IT314 Group 22  
**Target Environment:** Staging Server / Local Development Build  

---

## 1. Demo Objectives & Deliverables

Sprint 4 delivers cross-domain team features, Model 2 hostel feed scoping, staff-to-hostel assignments, and administrator gap monitoring:
1. **Model 2 Hostel Feed:** Verified students filter public hostel complaints by `scope=hostel`, `scope=wing`, or `scope=floor` (`GET /api/v1/feeds/hostel`).
2. **Staff Hostel Assignments:** Assigning staff members to specific hostels (`GET /admin/staff` & `PUT /admin/staff/{id}/hostels`).
3. **Hostel Coverage Gaps:** Admin overview of unassigned hostels that have open complaints (`GET /api/v1/admin/coverage-gaps`).
4. **Admin Metrics Dashboard:** Summary of complaint counts by status, active departments, and rolling resolution times.
5. **Concurrency Robustness:** Conflicting updates on complaints or residences return `409 Conflict` without data corruption.

---

## 2. Test Accounts & Personas

| Persona | Account Email | Role | Scope / Assignment |
| :--- | :--- | :--- | :--- |
| **Super Admin** | `admin.main@campus.edu` | `admin` | Full system access across all departments |
| **Hostel Staff 1** | `staff.hostel1@campus.edu` | `staff` | Assigned to Old Hostel for Men (OHM) |
| **Hostel Staff 2** | `staff.hostel2@campus.edu` | `staff` | Assigned to New Hostel for Men (NHM) |
| **Unassigned Staff**| `staff.unassigned@campus.edu`| `staff` | Hostel department staff with no hostels assigned |
| **Student (Wing A)**| `student.ohm.a@dau.ac.in` | `student` | Verified in OHM, Wing A, Floor 1 |
| **Student (Wing B)**| `student.ohm.b@dau.ac.in` | `student` | Verified in OHM, Wing B, Floor 1 |

---

## 3. Demonstration Flow

### Step 1: Model 2 Hostel Feed Scoping (Student View)
1. **Login as Student (Wing A):** `student.ohm.a@dau.ac.in`.
2. **Navigate to Campus Feed -> Hostel Tab.**
3. **Toggle `scope=floor`:**
   - Shows only public complaints submitted on OHM Wing A Floor 1.
4. **Toggle `scope=wing`:**
   - Shows all complaints across all floors of Wing A.
5. **Toggle `scope=hostel`:**
   - Shows complaints across both Wing A and Wing B in OHM.
6. **Expected Result:** Feed updates dynamically without showing complaints from NHM or HFW.

### Step 2: Hostel Staff Scope Isolation (Staff View)
1. **Login as Hostel Staff 1:** `staff.hostel1@campus.edu` (assigned to OHM).
2. **Open Staff Complaint Queue:**
   - Only complaints located in OHM appear.
   - Complaints located in NHM are hidden.
3. **Attempt direct access to an NHM complaint ID:**
   - Staff 1 calls `GET /api/v1/staff/complaints/{nhm_complaint_id}`.
   - Returns **`404 Not Found`** (out-of-scope fails closed rather than revealing record existence).

### Step 3: Admin Coverage Gaps Detection (Admin View)
1. **Login as Super Admin:** `admin.main@campus.edu`.
2. **Open Admin Dashboard -> Coverage Gaps Panel (`GET /api/v1/admin/coverage-gaps`):**
   - Displays a list of active hostels that have open complaints (`submitted`, `in_progress`, or `reopened`) but **no staff assigned**.
3. **Observe Hostels:**
   - OHM (assigned to Staff 1) is **not** in the coverage gaps list.
   - An unstaffed hostel with open complaints is listed with its `open_count`.
4. **Resolution via Staff Assignment:**
   - Admin assigns `staff.unassigned@campus.edu` to the unstaffed hostel (`PUT /api/v1/admin/staff/{id}/hostels`).
   - Refresh Coverage Gaps panel: the hostel immediately disappears from the gaps list.

### Step 4: Admin Metrics Summary
1. **Navigate to Metrics Overview (`GET /api/v1/admin/metrics/summary`):**
   - Displays total complaint counts.
   - Status cards: `Submitted`, `In Progress`, `Resolved`, `Reopened`.
   - Department breakdown: Complaint volume across IT Services, Hostel, Library, etc.
   - Rolling 30-day average resolution duration (in hours and days).

### Step 5: Concurrency Safety Test
1. **Staff 1 and Staff 2 simultaneously update Complaint #12:**
   - Staff 1 updates status to `in_progress` -> **HTTP 200 OK**.
   - Staff 2 attempts concurrent status transition -> **HTTP 409 Conflict**.
2. **Residence Decision Concurrency:**
   - Re-evaluating a verified student residence returns **HTTP 409 Conflict**, preventing duplicate or conflicting decisions.
