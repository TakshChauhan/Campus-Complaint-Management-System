# Deliverable 4 — Building-aware public complaint feeds (review update)

## Scope

Backend-only update. The requested-public flag (`is_public`) expresses the student's preference; `publication_status` is the canonical server-side decision about actual feed publication. The normal complaint lifecycle (`submitted`, `in_progress`, `resolved`, `reopened`) remains independent. Every complaint continues to be routed to its selected department even if feed publication is private, pending, or rejected.

## Location model

- `Building` is retained as a real, configured hostel/building entity; no synthetic “Hostel 1/2/3” records are created automatically.
- `Floor` belongs to one building and has a floor label such as `1`, `2`, or `3`.
- `Wing` belongs to a building, not one floor. Therefore Wing B can have residents on floors 1, 2, and 3.
- `HMCGroupWing` maps a particular `(building, floor, wing)` combination to an HMC group. An HMC group is configured for one building and one floor, and must manage one or two wings on that floor.
- A student's current residence is `residence_building_id + residence_floor_id + wing_id`. The assignment is trusted only when `residence_verified_at` and `residence_verified_by_id` identify an active administrator/staff verifier and the assigned location still matches active configured rows.

## Publication statuses

`private`, `pending_review`, `pending_mapping`, `published`, `rejected`.

| Request | Canonical publication status |
|---|---|
| `is_public=false` | `private` |
| Public, with no location request | `published` to the department-wide student feed |
| Public, but building/floor/wing is missing, conflicting, unknown or unmapped | `pending_mapping` |
| Public, mapped HMC location; reporter is not verified or not in the responsible group/floor | `pending_review` |
| Public, mapped HMC location; current staff-verified residence matches the responsible location | `published` (legacy review value `auto_approved`) |
| Authorized reviewer rejects/unpublishes | `rejected` |

Invalid/ambiguous user-entered location details do not stop complaint creation; the complaint remains routed to the department and publication stays hidden as `pending_mapping`. The backend does not trust a wing selected by the client as residence verification.

## Student privacy rules

Student feed/list/detail DTOs include title, department, complaint lifecycle status, necessary building/floor/wing and timestamps. They do **not** return the full description or a description preview; they also do not return reporter name, email, user ID, or moderation notes. The feed item detail endpoint repeats the same access check and deliberately remains description-free. Full descriptions and reporter identity are available only to authorized internal workflows, including the HMC review queue and existing department staff queue.

Duplicate suggestions must not use pending, rejected, private, or HMC-scoped complaints as a public suggestion side channel. The public candidate set is limited to `department_public` items whose `publication_status` is `published`; a student's own complaint may still be included by the existing owner-access rule.

## HMC reviewer authorization and audit

- An active administrator can review publication requests across locations.
- A staff account can review/unpublish HMC content only if an administrator explicitly designates that account as an HMC moderator for the affected group.
- Department assignment by itself does not confer HMC publication authority.
- A pending publication can be approved only when its physical location and active HMC mapping are valid.
- `POST /api/v1/complaints/feed/unpublish/{complaint_id}` removes a published item from student feeds and records actor, previous/new status, action and note in `complaint_publication_audit`. The complaint remains in the department workflow.

## Relevant endpoints

All are authenticated. Student feed endpoints require a student role; verification, moderator designation and moderation require the appropriate admin/moderator permission.

- `GET /api/v1/complaints/feed/locations` — configured building/floor/wing picker options that have valid HMC coverage.
- `GET /api/v1/complaints/feed?department_id=...` — published department-wide summaries.
- `GET /api/v1/complaints/feed/hmc` — summaries for the authenticated student's current, verified building/floor/wing group. No client-selected HMC group is accepted.
- `GET /api/v1/complaints/feed/items/{complaint_id}` — privacy-safe summary fields only; never the complaint description.
- `GET /api/v1/complaints/feed/review-queue` — internal pending items scoped to designated moderators or admins; includes full description and reporter identity.
- `POST /api/v1/complaints/feed/review/{complaint_id}` — approve/reject, with a reason required for rejection.
- `POST /api/v1/complaints/feed/unpublish/{complaint_id}` — unpublish a current item with an audit note.
- `POST /api/v1/complaints/feed/residence/{student_id}/verify` — admin records the current building/floor/wing assignment as verified.
- `PUT /api/v1/complaints/feed/hmc-groups/{group_id}/moderators/{user_id}` — admin designates (`{"assigned": true}`) or removes (`{"assigned": false}`) a staff HMC moderator.

## Importing real residence and HMC data

The CSV template at `docs/templates/hmc_assignment_template.csv` requires `building_name,floor_name,wing_name,hmc_group_name,student_email,moderator_email`. Rows may repeat for multiple students or moderators on the same wing/group mapping. The importer defaults to a dry run. After verifying the official roster, an administrator runs `--apply --verified-by-email <active-admin-email>`. Existing student moves require `--update-student-assignments`; changing existing mappings requires `--replace-hmc-mappings`. Do not use these flags with a partial roster.

## Migration note — read before applying

This package revises the **unmerged** Deliverable 4 migration `0008_public_feed_hmc_visibility` to use a building-aware schema. It is intended for the isolated `sprint-2/dhaval-public-feed` branch before the deliverable is committed/merged. A disposable SQLite database created with the earlier draft at revision `0008_public_feed_hmc` must be recreated before migration tests. Do not apply this revised file to a persistent database that has already recorded the earlier draft under that same revision ID. Do not apply migrations to Supabase/production as part of this local test procedure.

### Shared-floor audience rule (PR #46 review fix)

A complaint with no specific wing is not automatically visible to all HMC groups on the floor. It stays `pending_mapping` until an authorized reviewer approves it with an explicit `audience_group_ids` list. The selected audience is stored in `complaint_hmc_group_audiences` and is applied consistently to feed listing, feed detail, moderation scope, and duplicate-suggestion candidates. An empty or invalid audience fails closed.
