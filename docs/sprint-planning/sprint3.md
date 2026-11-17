# Sprint 3: Locations, residence verification, hostel-aware duplicates

**Dates:** 25 Oct to 31 Oct 2026
**Scrum lead:** Taksh Chauhan
**Author:** Yash
**Source for status:** Sprint 3 review document, issued 1 Nov 2026 (state of `main`, all PRs and branches).

## 1. Sprint goal

Give every complaint and student a real location: a hostel, wing and floor structure, student residence declaration with staff verification, and located complaints. Build the hostel feed foundation and make duplicate suggestions hostel-aware.

## 2. Sprint backlog

| Task | Owner | Deliverable |
|---|---|---|
| S3-01 to S3-05 | Rushil | Location tables, residence table, repository, complaint `floor_id`, hostel CSV importer |
| S3-06 to S3-11 | Dhaval | Admin metrics routes (carryover), create schema, locations and residence routes, route security tests |
| S3-12 to S3-15 | Yashvi | Residence service, creation rules, resolution metrics by hostel, concurrency tests |
| S3-16 to S3-19 | Taksh | API contract v3, feed service and routes, reviews and integration |
| S3-20 to S3-22 | Shrey | Location picker, residence profile, tests |
| S3-23 to S3-25 | Nishtha | Residence verification queue, hostel filter on staff queue, tests |
| S3-26 to S3-28 | Dev | Admin metrics page (carryover), feed page, tests |
| S3-29 to S3-31 | Krish | Threshold evaluation (carryover), hostel-aware duplicates, benchmark |
| S3-32 to S3-34 | Deep | Visibility, privacy and acceptance tests |
| S3-35 to S3-38 | Yash | Labelled pairs (carryover), Sprint 2 docs (carryover), HMC hostel list, Sprint 3 docs |
| S3-39 to S3-41 | Utkarsh | Sprint 2 QA carryover, Model 2 end-to-end scenarios, demo script |

## 3. User stories and acceptance criteria

**US-6: Declare residence.** As a student, I want to declare my hostel, wing and floor so my complaints are located correctly.
- A student can declare a residence, which starts as pending.
- Re-declaring after a decision returns it to pending.

**US-7: Verify residence.** As Hostel staff, I want to approve or reject residence declarations.
- A queue lists pending residences, filterable by hostel.
- A decision can carry a per-row remark.
- Only authorised staff or admin can decide.

**US-8: Located complaints.** As a student, I want to attach a location to my complaint.
- Complaint creation accepts a `floor_id` from the location picker.
- Locations come from the hostel structure tables.

**US-9: Hostel feed.** As a verified resident, I want to see public complaints from my hostel.
- Hostel feed visible to the right residents and hidden from others; department feed visible to everyone.
- No feed response contains description, creator id or email.

**US-10: Hostel-aware duplicates.** As a student, I want duplicate suggestions that respect privacy and hostel.
- Suggestions never show another student's private complaint or another hostel's complaint.
- A 1,000-complaint benchmark is recorded.

## 4. What was delivered

Merge dates are from GitHub (UTC). Sprint 3 closed 31 Oct.

**Merged during the sprint (25 to 31 Oct)**

| Story | Delivered | PR(s) |
|---|---|---|
| US-6 Declare residence | Location hierarchy and residence schema (26-27 Oct), verified HMC feeds, residence routes and service (30 Oct), query layer (31 Oct), student location picker and residence profile (30 Oct) | #47, #48, #46, #57, #52, #53 |
| US-7 Verify residence | Staff residence verification queue and hostel filter on the staff queue (30 Oct) | #50, #51 |
| US-8 Located complaints | `floor_id` migration 0010 (inside #49, 27 Oct); location picker and complaint submission | #49, #52 |
| US-9 Hostel feed | Sprint 3 API contract v3 (27 and 30 Oct), verified HMC feeds, demo seed (30 Oct) | #43, #55, #46, #54 |
| US-10 Hostel-aware duplicates | Duplicate suggestion service with benchmark docs (26 Oct) and hostel-aware suggestions (27 Oct) | #44, #49 |
| Metrics | Resolution metrics by hostel (30 Oct) | #56 |

**Sprint 3 work merged after the sprint closed (1 to 6 Nov)**

| Task | Delivered | PR | Merged |
|---|---|---|---|
| Campus feed page (S3-27) | Public complaint feed with privacy protection and filters | #59 | 1 Nov |
| S3-04 | Safe complaint floor backfill (new migration 0013) | #60 | 2 Nov |
| S3-05 | Safe hostel structure CSV importer | #62 | 3 Nov |
| S3-32, 33, 34 | Feed visibility, privacy and Sprint 3 acceptance tests | #64, #65, #66 | 5-6 Nov |
| S3-06, S3-26 | Admin metrics endpoints and admin dashboard | #63, #58 | 6 Nov |

**Still open at the time of writing:** residence concurrency tests (S3-15), real HMC hostel list (S3-37), QA run and demo script (S3-39 to S3-41). Status as of 7 Nov; check the repository before submitting. These are Sprint 4 tasks.

## 5. Review notes

- **Takeover:** some tasks were completed by someone other than the owner (feed service by Dhaval in #46; admin metrics page and feed page by Shrey; fixes and demo seed by Taksh). Credit goes to whoever completed the work.
- **Duplicate threshold:** the code used 0.70 while the evaluation selected 0.10; at 0.70 recall on the 205-pair set was 0.333. Fixed in Sprint 4 (PR #61, threshold 0.375). The 205-pair data was not reproducible from the repo.
- **Process:** PR #44 was merged without review, and a merged migration (0010) was nearly edited. Rule going forward: never edit a merged migration; nobody merges their own PR.
- **Contribution:** members with no Sprint 3 commits carried their tasks into Sprint 4 with fixed deadlines.
