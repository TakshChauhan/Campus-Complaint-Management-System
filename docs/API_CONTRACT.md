# CCMS API Contract — Sprint 2 Working Draft

**Reviewed:** 22 October 2026  
**API route version:** `v1` (still `/api/v1`; Sprint 2 does **not** imply `/api/v2`)  
**Local API origin:** `http://localhost:8000`  
**Versioned API base:** `http://localhost:8000/api/v1`  
**OpenAPI:** `http://localhost:8000/openapi.json` and `/docs` when `ENABLE_API_DOCS` is enabled  
**Contract status:** Code-reviewed draft for team coordination, **not** a claim that pending routes are deployed.  

## 1. Source and availability rules

This document separates the **merged implementation** from the **unmerged Sprint 2 candidate**. It was prepared by reading the GitHub code, not by conducting a running-server or deployment smoke test.

- **[MAIN]** Route and schema exist on `main` at commit `712e047e9d86b8082df3dbfd1accc16de2396a9d` (including merged PR #30). A working deployment also requires correct configuration, database migrations and other dependencies.
- **[PR31-DRAFT]** Route and schema exist on the `sprint-2/backend-dhaval` branch, PR #31, head `97776a1079eb76ffa19014c2e52d975f4eea2cb8`. **Not yet merged into `main`.**
- **[PR31-BLOCKED]** Endpoint exists in that branch, but intentionally returns HTTP `501 Not Implemented` for an authorized in-scope request until the lifecycle service is completed.
- **[DECISION-PENDING]** Intended behavior requires explicit team agreement before treating it as final.

**Authoritative sources:**

- [Current contract](https://github.com/TakshChauhan/Campus-Complaint-Management-System/blob/main/docs/API_CONTRACT.md)
- [Backend router](https://github.com/TakshChauhan/Campus-Complaint-Management-System/blob/main/backend/app/api/v1/router.py)
- [Auth endpoints](https://github.com/TakshChauhan/Campus-Complaint-Management-System/blob/main/backend/app/api/v1/endpoints/auth.py)
- [Student complaint endpoints](https://github.com/TakshChauhan/Campus-Complaint-Management-System/blob/main/backend/app/api/v1/endpoints/complaints.py)
- [Existing schemas](https://github.com/TakshChauhan/Campus-Complaint-Management-System/tree/main/backend/app/schemas)
- [Sprint 2 migration, merged PR #30](https://github.com/TakshChauhan/Campus-Complaint-Management-System/pull/30)
- [Sprint 2 staff/history routes, draft PR #31](https://github.com/TakshChauhan/Campus-Complaint-Management-System/pull/31)

## 2. API-wide conventions

- JSON request/response bodies unless explicitly marked HTML (Google OAuth callback). Send `Content-Type: application/json` for JSON requests.
- Protected endpoints require `Authorization: Bearer <access_token>`. Roles are `student`, `staff`, `admin`.
- Authentication failures normally return `401`, role/assignment failures `403`, and hidden/out-of-scope complaint detail IDs `404` (do not reveal another department/student's complaint existence).
- Time fields are ISO 8601 datetime strings. Parse them as dates, rather than requiring a particular textual UTC suffix.
- Success arrays are JSON arrays `[]`, **not** `{items: [...]}` unless explicitly stated.
- For paginated `GET /complaints/mine` and draft `GET /staff/complaints`, read the `X-Total-Count` header for the total number of matching records before pagination.
- The frontend's `VITE_API_BASE_URL` should be the backend **origin**, e.g. `http://localhost:8000`, because `frontend/src/api/client.ts` adds `/api/v1` itself.
- Default response status on unannotated `GET` routes is HTTP 200.
- No server-side logout endpoint is implemented; current frontend removes its stored token on sign-out.

## 3. Endpoint index

| Status | Method | Full path (local) | Access | Purpose / success |
| --- | --- | --- | --- | --- |
| MAIN | GET | `/health` | Public | API liveness + DB state; `200` even if degraded |
| MAIN | GET | `/health/ready` | Public | Readiness; `200` ready or `503` unavailable |
| MAIN | POST | `/api/v1/auth/register` | Public | Create student account; `201` |
| MAIN | POST | `/api/v1/auth/verify-email` | Public | Consume email verification token; `200` |
| MAIN | POST | `/api/v1/auth/resend-verification` | Public | Request verification email resend; `200` |
| MAIN | POST | `/api/v1/auth/login` | Public | Password login; `200` |
| MAIN | POST | `/api/v1/auth/google/start` | Public | Start Google sign-in with client challenge; `200` |
| MAIN | GET | `/api/v1/auth/google/callback` | Public / Google redirect | OAuth callback; HTML `200` |
| MAIN | POST | `/api/v1/auth/google/exchange` | Public | Redeem Google handoff ticket; `200` |
| MAIN | POST | `/api/v1/auth/google/link/start` | Authenticated user | Start account linking; `200` |
| MAIN | POST | `/api/v1/auth/google/link/exchange` | Authenticated user | Complete account linking; `200` |
| MAIN | GET | `/api/v1/auth/google/status` | Authenticated user | Linked status; `200` |
| MAIN | GET | `/api/v1/users/me` | Any authenticated role | Current safe profile; `200` |
| MAIN | GET | `/api/v1/departments` | Any authenticated role | Active departments; `200` |
| MAIN | POST | `/api/v1/departments/suggest` | Student | Advisory keyword suggestions; `200` |
| MAIN | POST | `/api/v1/complaints/suggest` | Student | Alias for advisory suggestion; `200` |
| MAIN | POST | `/api/v1/complaints` | Student | Create complaint; `201` |
| MAIN | GET | `/api/v1/complaints/mine` | Student | Search/filter own complaints; `200` |
| MAIN | GET | `/api/v1/complaints/{complaint_id}` | Student (owner only) | Detailed own complaint; `200` |
| PR31-DRAFT | GET | `/api/v1/staff/complaints` | Staff with department | Department queue; `200` |
| PR31-DRAFT | GET | `/api/v1/staff/complaints/{complaint_id}` | Staff, same department | Department complaint detail; `200` |
| PR31-BLOCKED | PATCH | `/api/v1/staff/complaints/{complaint_id}/status` | Staff, same department | **Currently 501** until lifecycle service integrated |
| PR31-DRAFT | GET | `/api/v1/complaints/{complaint_id}/history` | Student owner / same-dept staff / admin (admin policy pending) | Status event array; `200` |

There are **19 merged routes** and **4 additional proposed PR #31 routes** in this index. PR #30 is a database migration, not a new HTTP endpoint.

## 4. Shared schemas (TypeScript reference)

These represent response-model fields, not necessarily all usable request fields. Fields with defaults can appear as `null`/default values. Do not inject read-only fields into request bodies.

```ts
type Role = 'student' | 'staff' | 'admin';

type ComplaintStatusForStaffFilter = 'submitted' | 'in_progress' | 'resolved' | 'reopened';
// General complaint response `status` is currently a plain string in Pydantic.
// Do NOT impose a closed TypeScript union on every response until lifecycle policy is finalized.

interface UserSafeResponse {
  id: number;
  name: string;
  email: string;
  role: Role;
  is_active: boolean;
  email_verified: boolean;
  email_verified_at: string | null;
  email_verification_required: boolean;
  google_linked: boolean;
  department_id: number | null;
  created_at: string;
  message: string | null;
}

interface TokenResponse {
  access_token: string;
  token_type: string; // usually 'bearer'
  expires_in: number; // seconds; currently default 86400, config-dependent
  user: UserSafeResponse;
}

interface DepartmentResponse {
  id: number;
  name: string;
  description: string | null;
  is_active: boolean;
}

interface SuggestionResponse {
  status: 'provisional_advisory' | 'uncertain' | 'error_fallback';
  version: string;
  suggestions: {
    department_id: number;
    department_name: string;
    confidence_score: number; // 0..1
    rationale: string | null;
  }[];
  disclaimer: string;
}

interface ComplaintDetail {
  id: number;
  title: string;
  description: string;
  department_id: number;
  department_name: string;
  created_by_id: number;
  status: string;
  created_at: string;
}

interface MyComplaintListItem {
  id: number;
  title: string;
  description_preview: string;
  department_id: number;
  department_name: string;
  status: string;
  created_at: string;
}

// Draft PR #31 only
interface StaffComplaintQueueItem {
  id: number;
  title: string;
  description_preview: string;
  department_id: number;
  department_name: string;
  status: string;
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
}

interface StaffComplaintDetail {
  id: number;
  title: string;
  description: string;
  department_id: number;
  department_name: string;
  status: string;
  is_public: boolean;
  hostel: string | null;
  wing: string | null;
  floor: string | null;
  reopen_count: number;
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
}

interface ComplaintStatusHistoryItem {
  id: number;
  from_status: string | null;
  to_status: string;
  actor_id: number;
  remark: string | null;
  created_at: string;
}
```

## 5. Merged APIs — request details and examples

### 5.1 Authentication

**`POST /api/v1/auth/register`** — No auth; `201 UserSafeResponse`. Student role is server-assigned. Registration requires an allowed campus email domain as configured (`ALLOWED_EMAIL_DOMAINS`), e.g. `dau.ac.in` / `daiict.ac.in` by default. Name: 2–100 characters after trim; password: 8–100 characters *and* no more than 72 UTF-8 bytes; email must be valid. Extra request fields are forbidden.

```json
{"name":"Aarav Patel","email":"aarav.patel@dau.ac.in","password":"ExamplePass123!"}
```

On successful registration, profile indicates email verification is required; **registration does not grant a JWT**. A `502` can mean the account was created but sending its verification email failed; the frontend should offer *resend verification*, not blindly re-register. Common other errors: `409` duplicate email, `422` invalid input, `429` rate limiting.

**`POST /api/v1/auth/verify-email`** — Public, `200`:

```json
{"token":"single-use-token-from-email-link"}
```

Response: `{"message":"Your email address has been verified successfully. You may now sign in.","email":"aarav.patel@dau.ac.in"}`. Failure `400` for invalid/expired/used token. The **frontend email link** opens `/verify-email?token=...` on the configured frontend origin; the frontend then calls this **POST** API. This is *not* a GET backend verification route.

**`POST /api/v1/auth/resend-verification`** — Public, `200`:

```json
{"email":"aarav.patel@dau.ac.in"}
```

Response contains a neutral `message` regardless of account existence; rate limiting may return `429`, delivery failure may return `502`.

**`POST /api/v1/auth/login`** — Public, `200 TokenResponse`:

```json
{"email":"aarav.patel@dau.ac.in","password":"ExamplePass123!"}
```

Password login for accounts requiring email verification is blocked with `403` until verified. Other responses: `401` incorrect credentials, `403` inactive user, `429` limiter. Token lifetime is configurable (`ACCESS_TOKEN_EXPIRE_MINUTES`, default 1440).

**`POST /api/v1/auth/google/start`** — Public; requires permitted frontend `Origin` and a client-generated `client_challenge` (10–128 characters). Response: `{"authorization_url":"https://accounts.google.com/...","state":"..."}`. Google auth requires server configuration.

**`GET /api/v1/auth/google/callback`** — Query: Google `code`, `state`, optional `error`. Returns HTML containing a secure `window.opener.postMessage` handoff, **not JSON**. Popup messages have type `CCMS_GOOGLE_AUTH_SUCCESS` or `CCMS_GOOGLE_AUTH_ERROR`. On success frontend gets single-use `ticket` and then exchanges it.

**`POST /api/v1/auth/google/exchange`** — Public, allowed `Origin`, body `{ "ticket":"...", "client_verifier":"..." }`. Successful response `TokenResponse`; `400` invalid/replayed/expired proof, `403` origin/user mismatch, `503` Google disabled.

**`POST /api/v1/auth/google/link/start`** — Authenticated, same body shape as Google start; begins linking Google to the current authenticated account. Response contains `authorization_url` and `state`.

**`POST /api/v1/auth/google/link/exchange`** — Authenticated, `{ "ticket":"...", "client_verifier":"..." }`; response `{ "message": string, "user": UserSafeResponse }`. **Not** `TokenResponse`; session remains the authenticated user.

**`GET /api/v1/auth/google/status`** — Authenticated; response `{ "linked": boolean, "email": string | null }`.

### 5.2 Profile, departments and suggestions

**`GET /api/v1/users/me`** — Bearer (any active role); returns `UserSafeResponse` defined above.

**`GET /api/v1/departments`** — Bearer (any active role); returns `DepartmentResponse[]`, active entries sorted alphabetically. Do not hard-code department IDs in the UI.

**`POST /api/v1/departments/suggest`** and **`POST /api/v1/complaints/suggest`** — Both currently return the same `SuggestionResponse`; only students can call them. Body:

```json
{"title":"Hostel Wi-Fi unavailable","description":"Internet access is failing in the hostel study area."}
```

The engine is **keyword-based advisory logic**, not a trained ML classifier; a suggestion never automatically determines the complaint's chosen department. Valid title 3–120 chars, description 10–2000 chars. Suggestions can be empty for uncertain or fallback results.

### 5.3 Student complaint APIs

**`POST /api/v1/complaints`** — Student only; `201 ComplaintResponse`. Creates a complaint assigned to an active department. Every complaint remains in that department's staff workflow, regardless of feed visibility. Accepted request fields include `title`, `description`, `department_id`, `is_public` (default `false`), and optional normalized location IDs `affected_floor_id` / `affected_wing_id`. `is_public`, location IDs, visibility scope, and moderation state do not alter `department_id` routing.

When `is_public=false`, the server sets visibility to `private`. When `is_public=true` and no structured location is supplied, the server sets `department_public`. When `is_public=true` with a configured floor or wing, the server sets `hmc_group_public`. If the authenticated reporter's current HMC group covers the affected wing (or the reporter lives on the affected floor for a floor-common-area report), the item is `auto_approved` and immediately enters the relevant HMC feed. Otherwise it is `pending` until authorized staff approve it. Students may report any configured location; the server derives scope/review state from authenticated membership and location mapping. Clients cannot submit a chosen visibility scope or HMC group ID.

Prefer configured IDs from `GET /api/v1/complaints/feed/locations`. The legacy `hostel` text field is deprecated and is not used to determine location. Legacy wing/floor labels are accepted only when they uniquely match configured records. Invalid or mismatched locations return `422`; inactive departments return `400`; unknown departments return `404`; invalid-role attempts return `403`.

Example department-public request:

```json
{"title":"Campus Wi-Fi outage","description":"Wi-Fi is unavailable in the common study area.","department_id":2,"is_public":true}
```

Example HMC-targeted public request (publication is automatic only if the reporter belongs to the relevant HMC group; otherwise pending):

```json
{"title":"Wing A water supply issue","description":"There is no water in the Wing A common washroom.","department_id":3,"is_public":true,"affected_wing_id":4}
```

The creation response includes the server-derived `visibility_scope` and `feed_review_status` for the submitter's own receipt. `auto_approved` means the current HMC assignment matched the affected wing/floor; `pending` means staff review is required. These fields must not be reused as public feed entries.


**`GET /api/v1/complaints/mine`** — Student only; returns `MyComplaintListItem[]`, with `X-Total-Count`. Supported optional query parameters:

| Parameter | Type | Default | Meaning |
| --- | --- | --- | --- |
| `limit` | integer 1–100 | `50` | Page size |
| `offset` | integer >= 0 | `0` | Skip matching items |
| `q` | string length <= 120 | absent | Search complaint reference (`CMP-12`, `#12`, `12`), title, or description |
| `department_id` | positive integer | absent | Filter to one department |
| `date_from` | `YYYY-MM-DD` | absent | Include submissions on/after this UTC calendar date |
| `date_to` | `YYYY-MM-DD` | absent | Include submissions on/before this UTC calendar date |
| `sort` | `newest` or `oldest` | `newest` | Submission-time order (ID breaks ties) |

The total count is **after filters but before pagination**. `date_from > date_to` returns `422`. Example: `GET /api/v1/complaints/mine?q=wifi&sort=oldest&limit=10&offset=0`.

**`GET /api/v1/complaints/{complaint_id}`** — Student owner only; returns `ComplaintDetail`. A complaint owned by another student (or nonexistent ID) returns `404`.

## 6. Sprint 2 draft APIs — from PR #31 ONLY

**IMPORTANT:** These are code-reviewed proposed interfaces. They are **not available on `main` until PR #31 or equivalent changes are merged and deployed**. All require bearer auth. `GET` list/detail routes have explicit staff role restrictions. Unassigned staff receive `403`; cross-department complaint details return `404`.

### 6.1 `GET /api/v1/staff/complaints` — [PR31-DRAFT]

Staff can list **only complaints belonging to their assigned department**. Successful response is a plain `StaffComplaintQueueItem[]` plus `X-Total-Count`, newest first (`created_at DESC, id DESC`).

| Query | Type | Default | Notes |
| --- | --- | --- | --- |
| `status` | `submitted`, `in_progress`, `resolved`, `reopened` | absent | Optional exact status filter |
| `limit` | integer 1–100 | `50` | Page size |
| `offset` | integer >= 0 | `0` | Number skipped |

Example: `GET /api/v1/staff/complaints?status=submitted&limit=20&offset=0`.

Example response (illustrative values):

```json
[
  {
    "id": 42,
    "title": "Hostel Wi-Fi not working",
    "description_preview": "The campus internet has not worked since last night in my room.",
    "department_id": 2,
    "department_name": "IT Services",
    "status": "submitted",
    "created_at": "2026-10-20T10:00:00Z",
    "updated_at": "2026-10-20T10:00:00Z",
    "resolved_at": null
  }
]
```

### 6.2 `GET /api/v1/staff/complaints/{complaint_id}` — [PR31-DRAFT]

Staff only, must match caller's department. Response `StaffComplaintDetail`. Example:

```json
{
  "id": 42,
  "title": "Hostel Wi-Fi not working",
  "description": "The campus internet has not worked since last night in my room.",
  "department_id": 2,
  "department_name": "IT Services",
  "status": "submitted",
  "is_public": false,
  "hostel": null,
  "wing": null,
  "floor": null,
  "reopen_count": 0,
  "created_at": "2026-10-20T10:00:00Z",
  "updated_at": "2026-10-20T10:00:00Z",
  "resolved_at": null
}
```

### 6.3 `PATCH /api/v1/staff/complaints/{complaint_id}/status` — [PR31-BLOCKED]

Staff only; department scoped. Intended body:

```json
{"status":"in_progress","remark":"Assigned to the IT support team."}
```

Schema permits target status **only** `in_progress` or `resolved` and requires `remark` of 1–2000 non-whitespace characters. Reopening is **not** performed by this endpoint. Intended eventual `200` response type: `StaffComplaintDetail`. A disallowed transition is planned to yield `409`, but this must be implemented in the shared lifecycle service.

**Current PR #31 behavior:** valid in-department request reaches the stub service and returns **`501`**:

```json
{"detail":"Staff status updates are not enabled until the shared complaint lifecycle service is implemented and integrated."}
```

No status changes or history records are written by this stub. The authorization and input-validation checks run before the stub: bad body can be `422`, out-of-department ID can be `404`, wrong role can be `403`. **Frontend must not advertise working status updates yet.** Once the real service is merged, review this endpoint's transition rules and success example again.

### 6.4 `GET /api/v1/complaints/{complaint_id}/history` — [PR31-DRAFT]

Returns `ComplaintStatusHistoryItem[]` in **chronological order** (`created_at ASC`, then `id ASC`). No pagination in current draft. Missing ID, wrong student owner, or out-of-department staff access returns `404`.

Proposed access scope: student owner; assigned-department staff; administrator (global read access **[DECISION-PENDING]**). Staff without assigned department cannot access any history. The response exposes `actor_id` but not actor name or email.

```json
[
  {
    "id": 1001,
    "from_status": null,
    "to_status": "submitted",
    "actor_id": 11,
    "remark": null,
    "created_at": "2026-10-20T10:00:00Z"
  }
]
```

An empty `[]` currently means no events stored. **See the initial-history gap below:** new complaints made after migration `0007` are not guaranteed an initial submitted event under the existing creation service.

## 7. System health responses

`GET /health` returns HTTP 200 with fields:

```json
{"status":"healthy","project":"CCMS","version":"1.0.0","environment":"development","database":"operational"}
```

When DB is unavailable, response still has HTTP 200, but `status` is `degraded` and `database` is `unavailable`. Other fields reflect server configuration.

`GET /health/ready` returns HTTP 200 when DB reachable and HTTP 503 otherwise, with:

```json
{"ready":true,"database":"operational"}
```

## 8. Error representation

The app's global FastAPI HTTP exception handler typically uses `{ "detail": "human-readable message" }`. Validation errors returned through its request-validation handler use:

```json
{"detail":[{"field":"body -> title","message":"...","type":"value_error"}]}
```

Note: some **manual** `422` errors (e.g., reversed `date_from`/`date_to`) use a **string** `detail`, so the client should handle **both string and array**. OAuth callback is HTML rather than the standard JSON error model; not every OAuth failure is communicated via a 4xx JSON response. Rate-limited auth endpoints may yield `429` and a `Retry-After` header. Account email delivery errors can yield `502`.

## 9. Team decisions, blockers, and integration checklist

1. **History event on new complaint (implementation gap on `main`):** Migration `0007` inserts initial status-history rows for preexisting complaints, but current `backend/app/services/complaint_service.py::create_student_complaint` commits a new complaint without creating its initial `complaint_status_history` row. Assign this fix to backend/lifecycle owners; add a regression test. Ideally write the initial event and complaint atomically.
2. **Status update not implemented (PR #31):** `backend/app/services/complaint_lifecycle_service.py::update_department_complaint_status` is a deliberate `501` stub. Implement permitted state transitions, atomic status + history write, remark handling, `updated_at`/`resolved_at`, and failed-transition responses **before** declaring PATCH ready.
3. **Admin history permission (policy pending):** Decide explicitly whether an admin should have global read access to status history; update tests and documentation if changed.
4. **Frontend HTTP client:** `frontend/src/api/client.ts::RequestOptions.method` on main currently accepts only `'GET' | 'POST'`. Add `'PATCH'` before implementing the staff status-change screen. CORS also needs to include PATCH (PR #31 proposes that change).
5. **Student Sprint 2 fields:** DB columns for `is_public`, `hostel`, `wing`, `floor`, `updated_at`, `resolved_at`, `reopen_count` do not automatically enlarge the accepted POST body. Agree student form and backend schema changes separately.
6. **No unverified API claims:** Staff screens on main are informational placeholders. No admin complaint-management endpoints were found in `main` or PR #31, and no working student reopen route was found in the reviewed code.
7. **Test against runtime:** After merge, regenerate OpenAPI from the actual deployment and compare paths, schemas, authorization, CORS, errors, and examples. This document is a static source-code review, not execution verification. Also run migration `alembic upgrade head` on the target DB before depending on new columns.
8. **Documentation synchronization:** After team approval, replace `docs/API_CONTRACT.md` in a docs-only PR; update `docs/FRONTEND_HANDOFF.md` and `docs/README.md` links/descriptions as needed, without duplicating the entire contract into multiple places. The API route namespace stays `/api/v1`.

## 10. Suggested ownership and change control

- **Backend route owners:** confirm paths, bodies, response schemas, permissions, filters, and errors by reviewing actual code and OpenAPI.
- **Lifecycle/DB owner:** resolve history initialization and status-transition behavior; confirm migration prerequisites.
- **Frontend owners:** add typed API functions, DTOs, PATCH capability and screens only when matching backend routes are ready.
- **Team lead:** finalize ambiguous admin history policy and approve documentation before calling it final.
- Create a docs-only branch such as `docs/sprint2-api-contract`; send the PR link in the team channel and make the versioned document the sole canonical endpoint reference.

## 11. Deliverable 4 — Building-aware department and HMC feeds

Student feed items and item-detail responses expose only title, department, complaint lifecycle status, necessary building/floor/wing, and timestamps. They never expose complaint descriptions or previews, reporter identity, or moderation notes. Full descriptions and reporter identity are internal-only for authorized department staff and designated HMC moderators/admins.

- `GET /api/v1/complaints/feed/locations` returns configured building/floor/wing choices with valid HMC coverage.
- `GET /api/v1/complaints/feed?department_id=...` returns published department-wide summaries without location-specific complaint content.
- `GET /api/v1/complaints/feed/hmc` derives membership from the student's current staff-verified building + floor + wing tuple. Wing B can be mapped independently to groups on floors 1, 2, and 3; the client never chooses an HMC group.
- `GET /api/v1/complaints/feed/items/{complaint_id}` repeats authorization and returns the privacy-safe summary only.
- `GET /api/v1/complaints/feed/review-queue` returns pending requests to administrators or explicitly designated moderators for the affected HMC group. Department staff status alone is not publication authority.
- `POST /api/v1/complaints/feed/review/{complaint_id}` approves/rejects publication; rejection requires a reason.
- `POST /api/v1/complaints/feed/unpublish/{complaint_id}` removes a published item and records actor, previous/new status, action, time, and note in the audit table.
- `POST /api/v1/complaints/feed/residence/{student_id}/verify` records an administrator-verified building/floor/wing assignment.
- `PUT /api/v1/complaints/feed/hmc-groups/{group_id}/moderators/{user_id}` designates/removes a staff HMC moderator.

`is_public` records the student's request. Actual publication is tracked independently in `publication_status`: `private`, `pending_review`, `pending_mapping`, `published`, or `rejected`. Normal complaint lifecycle status remains independent and every complaint is still routed to its selected department. Unmapped or ambiguous requests are created but remain hidden as `pending_mapping`. Immediate HMC publication requires both a valid HMC location mapping and a current staff-verified matching residence.

`Building` is a real entity and must not be removed. Floors are building-specific; wings belong to buildings and may span multiple floors; HMC assignment is on the `(building, floor, wing)` tuple. Floor common-area complaints are visible only to valid HMC groups managing wings on the same building/floor.

Duplicate suggestions must only use the student's own complaints, published department-wide complaints, and published HMC complaints for the student's verified group/floor. Pending, rejected, private, or other-group HMC complaints must not enter the similarity corpus or appear in suggestions.

## Importing official residence and HMC mapping data

Use `docs/templates/hmc_assignment_template.csv` with columns `building_name,floor_name,wing_name,hmc_group_name,student_email,moderator_email`. The importer defaults to dry-run; `--apply` requires `--verified-by-email` for an active administrator. Existing student moves require `--update-student-assignments`, and reassigning a location requires `--replace-hmc-mappings` only after reviewing the entire official roster. Never use a partial roster with these flags.

## Migration note — read before applying

This is a revision of the **unmerged** Deliverable 4 migration `0008_public_feed_hmc_visibility`, intended for the isolated `sprint-2/dhaval-public-feed` branch before commit/merge. It replaces the earlier unmerged 0008 draft; local disposable databases already recorded at that revision must be recreated. Do not apply this migration to Supabase/production as part of local verification.
