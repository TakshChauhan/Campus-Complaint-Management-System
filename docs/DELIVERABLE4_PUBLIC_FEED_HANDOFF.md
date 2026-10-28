# Deliverable 4 — Public complaint feeds and HMC visibility (integrated)

Originally written for PR #46 (Dhaval). This version describes the design after it was integrated with the canonical hostel schema (Rushil, PR #47/#48) and canonical complaint locations and duplicate suggestions (Krish, PR #49). The API details live in [`API_CONTRACT.md`](API_CONTRACT.md) sections 7 and 7.11.

## Scope

Backend only. `is_public` is the student's request; `publication_status` is the server's decision about whether a complaint appears in a feed. The complaint lifecycle (`submitted`, `in_progress`, `resolved`, `reopened`) is independent: every complaint still goes to its chosen department, whatever its publication state.

## Location model

- The only physical hierarchy is `hostels → hostel_wings → hostel_floors` (migration `0008`). PR #46's `buildings`, `floors` and `wings` tables are **not** created.
- A `HostelFloor` belongs to one wing, so "Wing B, floor 2" and "Wing B, floor 3" are different canonical floors.
- An HMC group (`hmc_groups`) belongs to one hostel and one floor level (`floor_code`). `hmc_group_floors` maps one or two canonical floors to it, in different wings, all with that floor code. A floor belongs to at most one group. A group that breaks any of these rules, or has an inactive hostel, wing or floor, is invalid and grants nothing.
- A student's residence is their `student_residences` row (migration `0009`). It counts for HMC membership only while `status = 'verified'`, it was verified by an active staff/admin account, and its floor is active and mapped to a valid group. Students submit or change residences with `PATCH /users/me/residence` (→ `pending`); Hostel-department staff or admins decide with `POST /staff/residences/{id}/decision`.
- A complaint's affected location is its own `floor_id` (migration `0010`), never the reporter's residence. Legacy `hostel`/`wing`/`floor` text is kept for display and backfill but never used for authorization.

## Publication statuses

`private`, `pending_review`, `pending_mapping`, `published`, `rejected`.

| Request | Publication status |
|---|---|
| `is_public=false` | `private` |
| Public, no location, non-Hostel department | `published` to that department's feed |
| Public Hostel complaint without `floor_id`, text-only location, or a floor with no valid HMC group | `pending_mapping` |
| Public, `floor_id` mapped to a group; reporter is not a verified member of that group | `pending_review` |
| Public, `floor_id` mapped to a group; reporter is a verified member of that group | `published` for that group (legacy review value `auto_approved`) |
| Authorized reviewer rejects or unpublishes | `rejected` |

A complaint with a `floor_id` is HMC-scoped **whichever department it is assigned to** (IT, Maintenance, ...). It never appears in a department feed.

## Explicit audiences (shared floors)

A published HMC complaint is visible to an HMC group only through a `complaint_hmc_audiences` row (migration `0012`):

- auto-publish or moderator approval writes the **responsible group's** row (`source = responsible_group`);
- sharing the complaint with another group on the **same hostel floor level**, for example a common area used by two groups, is a separate audited decision (`POST /hmc/complaints/{id}/audiences`, `source = shared_floor`) by an admin or a moderator of both groups. It can be withdrawn with `.../audiences/{group_id}/revoke`.

**Change from the PR #46 ZIP:** that version showed a wing-less "floor-common" complaint to every group on the floor automatically. The integrated version never does this. A canonical floor always has a wing, and any wider audience needs an explicit row.

## Student privacy rules

Feed items and feed-item detail contain title, department, lifecycle status, timestamps, reopen count and (for the hostel feed) canonical hostel/wing/floor names. They never include the description, a description preview, reporter ID/name/email or moderation notes. Full descriptions and reporter identity are available only in the HMC moderation queue and the existing department staff queue.

Duplicate suggestions use only: the student's own complaints, published department-wide complaints, and published complaints with an audience row for the student's verified group. Private, pending, rejected, unmapped and other groups' complaints are never compared or returned. Krish's TF-IDF/cosine algorithm and the `0.70` threshold are unchanged.

## HMC moderation and audit

- Active admins can review, unpublish and share across all groups, and see unmapped requests.
- Staff can moderate only for groups an admin designated them for (`PATCH /hmc/groups/{group_id}/moderators/{user_id}`). Belonging to the complaint's department, including the Hostel department, grants no publication authority.
- Approval requires a valid canonical floor and group mapping.
- Every review, unpublish and audience change is written to `complaint_publication_audit`.

## Routes (all under `/api/v1`, authenticated)

| PR #46 route | Integrated route |
|---|---|
| `GET /complaints/feed/locations` | `GET /locations/hostels` (canonical tree) |
| `GET /complaints/feed?department_id=` | `GET /feeds/departments/{department_id}` |
| `GET /complaints/feed/hmc` | `GET /feeds/hostel` (also Hostel staff/admin, with `hostel_id`) |
| `GET /complaints/feed/items/{id}` | `GET /feeds/items/{id}` |
| `GET /complaints/feed/review-queue` | `GET /hmc/publication-requests` |
| `POST /complaints/feed/review/{id}` | `POST /hmc/publication-requests/{id}/decision` |
| `POST /complaints/feed/unpublish/{id}` | `POST /hmc/complaints/{id}/unpublish` |
| `POST /complaints/feed/residence/{student_id}/verify` | `PATCH /users/me/residence` + `POST /staff/residences/{id}/decision` |
| `PUT /complaints/feed/hmc-groups/{g}/moderators/{u}` | `PATCH /hmc/groups/{g}/moderators/{u}` |
| — | `GET`/`POST /hmc/complaints/{id}/audiences`, `POST .../audiences/{group_id}/revoke`, `GET /hmc/groups` |

## Importing real residence and HMC data

`backend/scripts/import_hmc_assignments.py` reads [`templates/hmc_assignment_template.csv`](templates/hmc_assignment_template.csv) with columns `hostel_code,wing_code,floor_code,hmc_group_name,student_email,moderator_email`. The canonical hostels, wings and floors must already exist; the importer never creates locations. It is a dry run by default. After checking the official roster, an administrator runs it with `--apply --verified-by-email <active-admin-email>`, which records each listed student's residence as verified by that admin. Moving existing students requires `--update-student-assignments`; remapping a floor to a different group requires `--replace-hmc-mappings`. `--stage-legacy-complaints` attaches an unambiguous canonical floor to legacy text-only `pending_mapping` complaints and moves them to `pending_review` (a moderator must still approve them). Do not use these flags with a partial roster.

## Migration note

Alembic order: `0008_hostel_locations` → `0009_student_residences` → `0010_complaint_floor_location` → `0011_public_feed_hmc` → `0012_complaint_hmc_audiences` (single head). `0011` replaces PR #46's unmerged `0009_public_feed_hmc`. A disposable database that recorded that draft revision must be recreated. `0011` backfills existing rows conservatively: only public, unlocated, non-Hostel complaints become `published`; every other public request becomes `pending_mapping`. Do not apply migrations to Supabase/production as part of local testing.
