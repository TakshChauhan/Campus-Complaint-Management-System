# Campus Complaint Management System (CCMS) — Official User Manual

**Document Version:** 1.0.0  
**Project:** IT314 Group 22  
**Target Audience:** Students, Department Maintenance Staff, and Campus Administrators  

---

## 1. System Overview & Role-Based Access

The Campus Complaint Management System (CCMS) is an enterprise grievance management platform designed for universities. CCMS provides role-segregated portals with strict access control:

| Portal | Target Users | Key Capabilities |
| :--- | :--- | :--- |
| **Student Portal** | Enrolled University Students | Lodge located complaints, track ticket progress, reopen issues, browse scoped feeds. |
| **Staff Portal** | Department & Hostel Maintenance Staff | Review assigned departmental queues, inspect hostel issues, verify student residences. |
| **Admin Portal** | University Authorities & System Admins | Audit resolution metrics, assign staff to hostels, monitor unstaffed coverage gaps. |

---

## 2. Student Portal Guide

### 2.1 Account Registration & Email Verification
1. Access the web portal and click **Register**.
2. Enter your university email address (e.g. `@dau.ac.in` or `@student.campus.edu`), full name, and password.
3. Check your student email inbox for the verification link or token.
4. Click **Verify Email** or enter the 6-character token to activate your account.

### 2.2 Residence Declaration & Profile Setup
1. Log in and navigate to the **Profile** tab (`/profile`).
2. Under **Campus Residence**, select your assigned **Hostel**, **Wing**, and **Floor**.
3. Click **Submit Declaration**.
4. Your residence status will transition to `pending`. Once approved by hostel authorities, your status will become `verified`, unlocking localized hostel feed access.

### 2.3 Raising a Complaint
1. Click **Raise Complaint** in the navigation bar.
2. Select the responsible **Department** (e.g., Hostel, IT Services, Maintenance, Library).
3. If reporting a hostel issue:
   - Your verified `floor_id` is automatically attached.
   - You can toggle whether the issue is public (visible in the hostel feed) or private.
4. Type a concise **Title** and detailed **Description**.
5. **Advisory Duplicate Warning:** If an identical issue was recently logged in your hostel or department, an advisory warning banner will appear. You may review the existing ticket or proceed with submission.

### 2.4 Tracking & Reopening Complaints
1. Navigate to **My Complaints** (`/complaints`).
2. Filter tickets by **Status** (`Submitted`, `In Progress`, `Resolved`, `Reopened`) or **Department**.
3. Click any ticket to inspect its **Status Timeline** and staff remarks.
4. **Reopening a Ticket:** If an issue marked `Resolved` recurs within 7 days, click **Reopen Complaint** and specify the reason. Complaints can be reopened up to 2 times.

### 2.5 Browsing Campus Feeds (Model 2)
1. Open the **Campus Feed** tab.
2. For non-Hostel departments, browse published campus-wide announcements.
3. For Hostel issues, verified residents can use the **Scope Toggle**:
   - **My Floor:** Issues reported strictly on your floor level.
   - **My Wing:** Issues affecting your residential wing.
   - **Whole Hostel:** All public notices and repairs across the entire hostel building.

---

## 3. Staff Portal Guide

### 3.1 Department Queue Management
1. Log in with your staff credentials and navigate to the **Staff Dashboard** (`/staff`).
2. Your queue displays all active complaints assigned to your department.
3. Use status filter pills (`Submitted`, `In Progress`, `Resolved`) to prioritize pending maintenance requests.

### 3.2 Hostel-Scoped Queue Access
1. Staff members in the Hostel department only see complaints in their assigned hostels.
2. Filter complaints by specific hostel using the **Hostel Dropdown**.
3. Attempting to view a complaint outside your assigned hostel returns a secure `404 Not Found` to prevent data leakage.

### 3.3 Residence Verification Queue
1. In the Staff Dashboard, select **Residence Queue**.
2. Review pending student residence declarations.
3. Verify student identity and room records:
   - Click **Approve** to verify the resident.
   - Click **Reject** and provide a mandatory remark explaining the mismatch (e.g., *"Student room allotment lists Wing B"*).
4. *Concurrency Safeguard:* If another staff member acts on the same student simultaneously, the system prevents duplicate approvals and returns a `409 Conflict` notice.

### 3.4 Updating Complaint Status
1. Click on a complaint to open the **Processing View**.
2. Advance status from `Submitted` → `In Progress` when dispatching technicians.
3. Upon job completion, advance to `Resolved` and enter completion remarks.
4. Staff remarks are immediately recorded in the tamper-evident audit history and displayed on the student's timeline.

---

## 4. Admin Portal Guide

### 4.1 System Overview & Infrastructure Health
1. Access the **Admin Dashboard** (`/admin`).
2. Review real-time backend indicators:
   - **API Status:** Liveness check (`/health`).
   - **Database Status:** Operational readiness (`/health/ready`).
   - **Active Departments:** Catalogue of active routing departments.

### 4.2 Resolution Performance & Metrics
1. Inspect the **Complaint Metrics Overview**:
   - Total complaints logged campus-wide.
   - Live breakdown by lifecycle status (`Submitted`, `In Progress`, `Resolved`, `Reopened`).
   - Complaint volume distributed across departments.
2. Review the **Rolling Resolution Metrics**:
   - Mean resolution duration in hours and days (calculated over a rolling 30-day window).
   - Median, minimum, and maximum turnaround times.

### 4.3 Staff-to-Hostel Assignments
1. In the Admin settings, select **Staff Hostel Coverage**.
2. Review the roster of staff members and their currently assigned hostel buildings.
3. To update assignments, select a staff member, choose one or more hostels, and click **Save Assignments** (`PUT /api/v1/admin/staff/{id}/hostels`).

### 4.4 Monitoring & Resolving Coverage Gaps
1. Scroll to the **Hostel Coverage Gaps** panel (`GET /api/v1/admin/coverage-gaps`).
2. The system automatically highlights any active hostel that satisfies both conditions:
   - Has **open complaints** awaiting attention.
   - Has **zero active staff assigned** to it.
3. The panel displays the hostel name and total open tickets.
4. Assigning an active staff member to that hostel immediately resolves the gap and updates the live dashboard.

---

## 5. Security & Privacy Guarantees

1. **Feed Anonymity:** Public feed items never expose student names, email addresses, descriptions, or internal administrative notes.
2. **Access Control:** Unauthorized attempts to access administrative endpoints return `401 Unauthorized` or `403 Forbidden`.
3. **Data Integrity:** Database foreign keys use `RESTRICT` to prevent accidental deletion of campus residences or user records tied to active tickets.
4. **Optimistic Concurrency:** All status and residence transitions are protected against race conditions, ensuring consistent database state.
