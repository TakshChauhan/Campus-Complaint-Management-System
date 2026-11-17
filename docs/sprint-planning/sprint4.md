# Sprint 4: Hostel access, staff assignment and ML evaluation

**Period:** November 2026  
**Scrum lead:** Taksh Chauhan  
**Original draft:** Krish, 9 Nov 2026 (commit \`10c5658\`)  
**Restoration and status reconciliation:** 17 Nov 2026  
**Status source:** GitHub pull-request merge states and branches checked on 17 Nov 2026. Open work is not counted as delivered.

## 1. Sprint goal

Complete hostel-aware access and staff-assignment workflows; improve complaint-feed and location reliability; and close duplicate-detection ML work with a reproducible threshold, an independent hold-out evaluation, and documented privacy limitations.

## 2. Sprint backlog and status

| Task / area | Owner(s) | Deliverable | Status as of 17 Nov |
|---|---|---|---|
| S4-01 | Rushil | Staff–hostel assignment backend | Merged in #67 |
| S4-02 | Rushil | PostgreSQL migration testing flow in CI | Merged in #68 |
| S4-03 | Rushil | Centralised hostel location lookups | Merged in #69 |
| S4-04 / S4-06 | Shrey / Taksh | Hostel-scoped staff access and service | Merged in #78 and #82 |
| S4-05 | Nishtha | Staff–hostel assignment API integration / contract work | Backend routes merged in #83; consult code and contract for task-level completion |
| S4-07 | Dev | Admin coverage-gaps backend and tests | Backend merged in #75; counting fix still open in #103 |
| S4-08 | Deep | PostgreSQL concurrency test | Merged in #93 |
| S4-09 | Taksh | Model 2 hostel feed | Merged in #74 |
| S4-12 | Dhaval | Feed scope, pagination and filters | PR #102 open |
| S4-13b | Dhaval | Residence change flow | PR #101 open |
| S4-14 / S4-15 | Yashvi | Hostel-scoped staff frontend and tests | Merged in #99 |
| S4-16 / S4-17 | Krish | Duplicate-threshold correction and evaluation close-out | Merged in #61 |
| S4-18 | Krish | Independent hold-out evaluation and final ML section | PR #90 open; results require reproduction before merger |
| S4-21 | Krish | Admin staff–hostel assignment management screen | Merged in #84 |
| S4-22 / S4-23 | Dev (reassigned from Utkarsh) | Admin coverage-gaps screen and tests | Not merged; work on branch \`sprint-4/dev-s4-23-coverage-tests\` and needs integration PR |
| S4-24 | Krish + Yash | Sprint 4 planning/review | Original draft restored in this PR; review and merge pending |
| S4-25 | Dev | Staging QA | Not completed; staging was not deployed as of 17 Nov. Replaced by the actual UAT on deployed staging in Sprint 5 |
| S4-26 | Dev | Demo script | PR #89 open; retain useful script material but correct any unverified QA claims |
| S4-27 | Yash | Independent hold-out pair dataset | Merged in #79 |
| S3-15 carryover | Dev | Residence concurrency | PR #92 open; CI workflow must be repaired before merge |
| S3-37 carryover | Yash / Dev | Confirmed hostel structure and aligned seeds | PR #81 (draft) and #105 open; merge in that order |

The status table distinguishes merged changes from open PRs, branch-only work and deferred work. The precise original task descriptions should remain linked to the Sprint 4 planning materials; a merged dependency is not proof of every related acceptance criterion.

## 3. User stories and acceptance criteria

**US-11: Hostel-scoped staff access.** As a staff member, I want access restricted to my authorised department and hostel scope.

- Staff access follows configured department and hostel assignments.
- Users outside scope cannot read or update restricted complaints.
- Access checks fail closed when assignment data is missing or invalid.

**US-12: Admin staff assignment.** As an administrator, I want to view staff and assign or change their hostel assignments.

- The admin screen displays staff, department and assigned hostels.
- Admin can assign or change hostel assignments.
- Loading, empty, error and successful-save states are handled.
- Displayed data refreshes after successful save.

**US-13: Reliable duplicate suggestions.** As a student, I want duplicate suggestions to use a reproducible similarity threshold while respecting complaint privacy.

- Production threshold is 0.375.
- Suggestions use TF-IDF and cosine similarity over complaint title and description.
- Private complaints belonging to other students and inaccessible hostel complaints are excluded.
- Creator identity is not disclosed.
- Complaint submission remains possible when suggestions are unavailable.

**US-14: Independently evaluate duplicate detection.** As a reviewer, I want an independent hold-out evaluation to understand generalisation.

- The hold-out set is separate from threshold selection.
- The threshold is not retuned using hold-out results.
- Precision, recall, F1 and the confusion matrix are reported.
- Methodology and limitations are documented.

## 4. What was delivered

### Confirmed merged PRs

GitHub merge state checked on 17 Nov 2026; dates below are calendar dates in UTC.

| PR | Delivered work | Merged |
|---|---|---|
| #61 | Duplicate threshold / evaluation alignment | 3 Nov |
| #67 | Staff–hostel assignments | 3 Nov |
| #68 | PostgreSQL migration testing in CI | 4 Nov |
| #69 | Hostel location lookup service | 5 Nov |
| #74 | Model 2 hostel feed | 6 Nov |
| #75 | Coverage-gaps contract, backend, route and tests | 6 Nov |
| #76 | Residence decision concurrency/conflict tests | 8 Nov |
| #78 | Hostel scope service and tests | 7 Nov |
| #79 | Independent hold-out pairs | 8 Nov |
| #80 | Sprint 2 and Sprint 3 documentation | 8 Nov |
| #82 | Hostel-scoped staff access | 14 Nov |
| #83 | Admin staff–hostel assignment routes | 14 Nov |
| #84 | Admin staff assignment screen | 14 Nov |
| #93 | PostgreSQL concurrency test | 14 Nov |
| #99 | Hostel-scoped staff screens and tests | 14 Nov |
| #100 | Student/staff/admin user manual | 14 Nov |

### Still open on 17 Nov (do not mark completed)

| PR / branch | Action needed |
|---|---|
| #102, then #101 | Review and merge in order after CI |
| #81 (draft), then #105 | Yash adds importer dry-run evidence; reviewer checks CSV; merge dependency first |
| #103 | Fix the pre-existing coverage-gaps test fixture and rerun CI |
| #92 | Restore the backend CI YAML; prove the PostgreSQL race test executed |
| #90 | Reproduce hold-out evaluation output and merge |
| #85 | Close if confirmed superseded by #92 |
| #86 | Correct/report the environment and only tests actually run before deciding to merge |
| #89 | Do not merge inaccurate staging/QA statements; preserve useful demo script for Sprint 5 |
| \`sprint-4/dev-s4-23-coverage-tests\` | Dev opens an integration PR for the CoverageGapsSection after resolving changes in \`frontend/src/api/admin.ts\` |
| \`sprint-4/dev-deployment-and-docs\` | Dhaval selectively carries Docker, nginx, deployment verification and guide into Sprint 5; do not merge the duplicate user manual or viva sheet |

### S4-18 independent hold-out results (from original Krish draft; pending PR #90 verification)

The proposed production threshold remains fixed at 0.375. The 40-pair hold-out dataset has 20 duplicate and 20 non-duplicate pairs.

| Metric | Reported result |
|---|---:|
| Precision | 0.667 |
| Recall | 0.500 |
| F1-score | 0.571 |
| True positives | 10 |
| False positives | 5 |
| True negatives | 15 |
| False negatives | 10 |

The earlier 100-pair threshold-selection evaluation achieved perfect results at 0.375, but because that data was used to select the threshold, it is not an independent performance estimate. The above hold-out numbers should be treated as reported, not newly reproduced, until #90 is reviewed.

## 5. Review notes and carryovers

- **Coverage UI:** The backend is merged, but admin users cannot see coverage gaps until the branch-only frontend is integrated.
- **CI:** The pending #92 PR modifies \`.github/workflows/backend-ci.yml\` incorrectly; restore the workflow and run PostgreSQL concurrency coverage before merge.
- **Data:** #81 remains a draft; its confirmed hostel CSV and dependent #105 seed updates have not landed.
- **Staging and QA:** There was no deployed staging site on 17 Nov, so no historical test report should claim staging execution. Conduct and document actual staging UAT in Sprint 5.
- **Deployment:** The Docker/nginx/guide changes are branch-only and form the basis of Sprint 5 deployment work, not a completed Sprint 4 release.
- **ML:** TF-IDF + cosine similarity is lexical; it may miss paraphrases. The offline evaluation does not itself verify production authorisation/privacy rules.
- **Documentation:** This file is restored from Krish's 9 Nov draft and updated to distinguish merged/open status. Yash and Krish should review the historical task mapping and add any missing evidence before merging.
- **Source control:** Delete merged branches only after checking that no unmerged commits remain. The abandoned \`sprint-4/dev-coverage-gaps\` branch has only a stray \`.claude/settings.json\` commit relative to main; do not confuse it with \`sprint-4/dev-s4-23-coverage-tests\`, which contains unfinished frontend work.
- **Sprint 1:** A separate \`docs/sprint-planning/sprint1.md\` is not currently present on main. That is a final-submission documentation gap, not a completed Sprint 4 item.

**Status checked:** 17 Nov 2026. This is a review document; adjust open statuses only after subsequent GitHub merges, and keep PR evidence attached.
