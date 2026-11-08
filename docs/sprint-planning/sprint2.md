# Sprint 2: Complaint lifecycle, privacy-safe feed, duplicate warning

**Dates:** 19 Oct to 24 Oct 2026 (code freeze 23 Oct, 22:00; planned review 24 Oct)
**Scrum lead:** Taksh Chauhan
**Author:** Yash

## 1. Sprint goal

Deliver the complete complaint lifecycle (staff handling, status history, reopen), a privacy-safe public feed with hostel/wing/floor filters, admin resolution metrics and a TF-IDF duplicate warning. The category classifier was dropped from scope. The duplicate warning is the project's ML component (pending TA confirmation, see allocation doc).

## 2. Sprint backlog

| Area | Owner | Deliverable | Buddy |
|---|---|---|---|
| Scrum lead | Taksh | Issues, PR reviews and merges, API contract sign-off, integration, demo run | n/a |
| Database | Rushil | Migration 0007 (public flag, location text, timestamps, reopen count, status history table) and demo seed | Deep |
| Backend routes | Dhaval | Staff, history, reopen, feed, admin and duplicate routes with role guards | Yashvi |
| Backend services | Yashvi | Lifecycle state machine, atomic history, reopen rules, rolling average, feed query | Dhaval |
| ML | Krish | TF-IDF duplicate service and threshold evaluation | Yash |
| Data and docs | Yash | Cleaned dataset, about 100 labelled pairs, Sprint 2 documentation | Krish |
| Student frontend | Shrey | Raise Complaint additions, duplicate warning, history timeline, Reopen | Nishtha |
| Staff frontend | Nishtha | Staff dashboard: queue, detail, status update | Shrey |
| Admin + feed frontend | Dev | Admin metrics page, campus feed page | Utkarsh |
| Backend tests | Deep | 10+ new pytest cases | Rushil |
| QA | Utkarsh | End-to-end checklist, bug log, screenshots, demo script | Dev |

## 3. User stories and acceptance criteria

**US-1: Staff handle complaints.** As a staff member, I want to see my department's complaints and update their status with a remark.
- Staff see only their own department's complaints; other departments return 404, not 403.
- Allowed transitions: submitted to in_progress to resolved; resolved to reopened to in_progress. Anything else is rejected.
- A status change and its history row are written in one transaction.

**US-2: Students track and reopen.** As a student, I want to see my complaint's status history and reopen a resolved complaint.
- Students see only their own private complaints.
- The history timeline shows every status change.
- Reopen is available to the owner only, and the button shows only when allowed.

**US-3: Public feed.** As a student, I want to browse public complaints so I can see what others have raised.
- The feed shows public complaints only, filterable by department and hostel/wing/floor.
- No student name or email is ever returned.

**US-4: Duplicate warning.** As a student, I want a warning when my complaint resembles an existing one.
- The top 3 matches with scores are shown, with title, department and status but never the creator.
- Matches come only from public complaints and the student's own.
- "Submit anyway" is always available, and if the service fails submission still works.

**US-5: Admin metrics.** As an admin, I want complaint counts and resolution times.
- Counts by status and department are shown.
- Rolling average resolution time over the last 30 days is shown with its definition on screen.

## 4. What was delivered

Merge dates are from GitHub (UTC). The code freeze was 23 Oct 22:00 and the sprint was due to end on 24 Oct.

| Story | Delivered | PR(s) |
|---|---|---|
| US-1 Staff handle complaints | Department-scoped staff routes and lifecycle scaffold; state machine with atomic history; stale-update and privacy fix. Staff dashboard UI merged 25 Oct. | #31, #33, #38; UI: #41, #42 |
| US-2 Students track and reopen | Reopen rules and student reopen endpoint. Student workflow UI merged 25 Oct: #40 adds the status history timeline component and the reopen API call on the complaint detail page. | #33, #34; UI: #40, #42 |
| US-3 Public feed | Not delivered in Sprint 2. Delivered in Sprint 3 as the verified hostel feed (see sprint3.md). | none |
| US-4 Duplicate warning | Service, labelled pairs and benchmark docs merged 26 Oct, after the sprint end. The duplicate warning component on the student side came in #40 (25 Oct) and falls back to no suggestions if the service is unavailable. | #40 (UI, 25 Oct), #44 (service, 26 Oct) |
| US-5 Admin metrics | Resolution metrics logic delivered in the lifecycle service. Admin routes and page merged 6 Nov. | #33; later #63, #58 |

Merged 19 to 24 Oct:

| Date | PR | Work | Author |
|---|---|---|---|
| 20 Oct | #28, #29 | Sprint 1 final backend and frontend sync | Dhaval, Taksh |
| 21 Oct | #30 | Sprint 2 lifecycle migration and demo seed | Rushil |
| 22 Oct | #32 | API contract updated for Sprint 2 | Taksh |
| 22 Oct | #33 | State machine, atomic history, reopen rules, resolution metrics | Yashvi |
| 22 Oct | #36 | Removed stray `.DS_Store` | Taksh |
| 23 Oct | #31 | Department-scoped staff routes and lifecycle scaffold | Dhaval |
| 23 Oct | #34 | Student reopen endpoint | Dhaval |
| 23 Oct | #38 | Stale-update and privacy fix | Taksh |
| 23 Oct | #39 | Sprint 2 acceptance tests | Deep |
| 24 Oct | #37 | CONTRIBUTING guide updated for Sprint 2 | Taksh |

Merged just after the sprint end (25 Oct, 08:43 UTC): #40 student workflow enhancements (Shrey), #41 staff dashboard (Nishtha), #42 backend, student and staff integration (Taksh).

Items carried into Sprint 3: admin metrics routes (S3-06), admin metrics page (S3-26), threshold evaluation (S3-29), labelled pairs (S3-35), Sprint 2 documentation (S3-36), QA run, bug issues and demo script (S3-39, S3-40).

## 5. Review notes

No separate review notes were recorded for Sprint 2. The notes below come from the Sprint 3 review document of 1 Nov 2026, which looked back at Sprint 2 status.

- Process: the 1 Nov Sprint 3 review recorded that no bug issues had ever been filed on GitHub.
- Decision agreed in the allocation doc: region-based access, combined regions and the verified hostel roster moved to Sprint 3.
