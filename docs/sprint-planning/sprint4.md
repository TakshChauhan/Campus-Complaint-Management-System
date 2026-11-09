# Sprint 4: Hostel access, staff assignment and ML evaluation

**Period:** November 2026
**Scrum lead:** Taksh Chauhan
**Author:** Krish
**Status source:** Git history on 9 Nov 2026 and current Sprint 4 work.

## 1. Sprint goal

Complete the hostel-aware access and staff assignment workflows, improve the reliability of the complaint feed and location services, and close the duplicate-detection ML work with a reproducible threshold, independent hold-out evaluation and documented privacy limitations.

## 2. Sprint backlog

| Task | Owner | Deliverable | Status |
|---|---|---|---|
| S4-01, S4-02 | Rushil | Staff hostel assignment and location-related backend work | Merged |
| S4-04, S4-06 | Shrey / Taksh | Hostel-scoped staff access and access-scope service | Merged |
| S4-05 | Nishtha | Staff hostel assignment API contract and mock helpers | Merged / dependency |
| S4-16, S4-17 | Krish | Duplicate threshold correction, reproducible evaluation data, behaviour tests and PR review close-out | Completed; PR #61 |
| S4-18 | Krish | ML final report section: methodology, data, privacy, threshold justification, limitations and independent hold-out results | In progress |
| S4-21 | Krish | Admin staff hostel assignment screen, loading/empty/error states, save refresh and frontend tests | Implemented; review pending |
| S4-24 | Krish (part) | Sprint 4 planning and review documentation | This document |
| S4-27 | Yash | Independent hold-out duplicate pairs | Merged; PR #79 |

## 3. User stories and acceptance criteria

**US-11: Hostel-scoped staff access.** As a staff member, I want access restricted to my authorised department and hostel scope.
- Staff access follows the configured department and hostel assignments.
- Users outside the authorised scope cannot access restricted complaints.
- Access checks fail closed when required assignment information is missing or invalid.

**US-12: Admin staff assignment.** As an administrator, I want to view staff and assign or change their hostel assignments.
- The admin screen displays staff, department and assigned hostels.
- An administrator can assign or change hostel assignments.
- Loading, empty, error and successful-save states are handled.
- The displayed data refreshes after a successful save.

**US-13: Reliable duplicate suggestions.** As a student, I want duplicate suggestions to use a reproducible similarity threshold while respecting complaint privacy.
- Production threshold is 0.375.
- Suggestions use TF-IDF and cosine similarity over complaint title and description.
- Private complaints belonging to other students and inaccessible hostel complaints are excluded.
- Suggestions do not reveal complaint creator identity.
- Submission remains possible even when suggestions are unavailable.

**US-14: Independently evaluate duplicate detection.** As a project reviewer, I want an independent hold-out evaluation to understand generalisation.
- The hold-out dataset is separate from threshold selection.
- The selected threshold is not retuned using hold-out results.
- Precision, recall, F1 and confusion-matrix counts are reported.
- Evaluation methodology and limitations are documented.

## 4. What was delivered

### Merged during Sprint 4

| Task / Area | Delivered | PR |
|---|---|---|
| S4-16 / S4-17 | Duplicate threshold correction to 0.375 and evaluation/behaviour-test close-out | #61 |
| Staff-hostel assignment backend | Staff hostel assignment routes | #67 |
| PostgreSQL CI | PostgreSQL CI integration | #68 |
| Location lookup | Location lookup functionality | #69 |
| Model 2 feed | Model 2 hostel feed work | #74 |
| Coverage | Test coverage improvements | #75 |
| Residence concurrency | Residence concurrency tests | #76 |
| Hostel scope | Hostel-scoped access implementation and fixes | #78 |
| S4-27 | Independent 40-pair hold-out dataset | #79 |

### Krish's current branch work (not yet confirmed merged)

| Task | Delivered work | Commit / PR |
|---|---|---|
| S4-18 | Independent hold-out evaluation script, ML methodology, privacy boundaries and limitations in ML documentation | 067509b, 48376ad; PR pending |
| S4-21 | Admin staff hostel assignment management screen | d3a38b5; review pending |
| S4-24 | Sprint 4 documentation | Current document |

### S4-18 independent hold-out results

The production threshold remains fixed at 0.375. The 40-pair hold-out dataset contains 20 duplicate and 20 non-duplicate pairs. The threshold was not retuned on this dataset.

| Metric | Result |
|---|---:|
| Precision | 0.667 |
| Recall | 0.500 |
| F1-score | 0.571 |
| True positives | 10 |
| False positives | 5 |
| True negatives | 15 |
| False negatives | 10 |

The earlier 100-pair threshold-selection evaluation achieved perfect results at 0.375, but that dataset was also used for threshold selection. Those results are therefore optimistic and should not be treated as independent performance estimates.

## 5. Review notes

- **Threshold selection:** The threshold of 0.375 was selected using labelled evaluation pairs. The independent hold-out results provide a more realistic estimate of generalisation.
- **Hold-out performance:** Recall of 0.500 indicates that half of the duplicate pairs in the hold-out set were missed. Further tuning should use a separate development dataset, not this hold-out set.
- **Evaluation pipeline:** The evaluator and production service share TF-IDF configuration, including English stop-word removal, but their vectorizer fitting contexts differ.
- **Privacy:** Production candidate filtering is applied before complaint text is read. The offline evaluator does not independently test database access-control rules; backend privacy tests remain necessary.
- **ML limitations:** TF-IDF and cosine similarity are lexical methods. They may miss semantically similar complaints with different wording.
- **Process:** Merged migrations must not be edited. PRs should be reviewed and merged by someone other than their author.
- **Status accuracy:** S4-18 and S4-21 branch commits must not be counted as merged deliverables until their PRs are merged.

**Status recorded:** 9 Nov 2026. Update PR numbers, merge dates and remaining task status before final Sprint 4 submission.