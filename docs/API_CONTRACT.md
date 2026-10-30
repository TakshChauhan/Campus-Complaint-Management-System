# CCMS API Contract — v3 (Sprint 3)

**Reviewed:** 30 October 2026 (section 7 synchronized with merged PRs #46, #52 and #53)\
**Code baseline:** `main` at commit `75dbef90fe561cf34ab2b5b3df09e68ffcc8f821` (merge of PR #53)\
**API route version:** `v1` (still `/api/v1`; contract v3 does **not** imply `/api/v3`)\
**Local API origin:** `http://localhost:8000`\
**Versioned API base:** `http://localhost:8000/api/v1`\
**OpenAPI:** `http://localhost:8000/openapi.json` and `/docs` when `ENABLE_API_DOCS` is enabled\
**Contract status:** v3 was merged in PR #43. This revision documents the Sprint 3 routes as implemented on `main` (PRs #46, #52, #53). `[MAIN]` routes exist at the commit above; the only remaining `[S3-PLANNED]` route is `GET /admin/metrics/resolution` (7.9). Where the code differs from the v3 plan, the section says so and points to the Sprint 4 decision in section 11.

## 1. Source and availability rules

This document was prepared by reading the route, schema and service code on `main`, not by a running-server or deployment smoke test.

- **[MAIN]** Route and schema exist on `main` at the commit above. A working deployment also requires correct configuration, database migrations (`alembic upgrade head`, currently through `0012`) and other dependencies.
- **[S3-PLANNED]** Agreed Sprint 3 interface (section 7). **Not implemented on `main`.** Frontend may build against it behind a flag, but must not ship it as working until the route is merged.
- **[DECISION-PENDING]** Intended behavior requires explicit team agreement before treating it as final. *(No design decisions are open in this revision; see section 11.)*

**Authoritative sources:**

- [Current contract](https://github.com/TakshChauhan/Campus-Complaint-Management-System/blob/main/docs/API_CONTRACT.md)
- [Backend router](https://github.com/TakshChauhan/Campus-Complaint-Management-System/blob/main/backend/app/api/v1/router.py)
- [Auth endpoints](https://github.com/TakshChauhan/Campus-Complaint-Management-System/blob/main/backend/app/api/v1/endpoints/auth.py)
- [Student complaint endpoints](https://github.com/TakshChauhan/Campus-Complaint-Management-System/blob/main/backend/app/api/v1/endpoints/complaints.py)
- [Staff complaint endpoints](https://github.com/TakshChauhan/Campus-Complaint-Management-System/blob/main/backend/app/api/v1/endpoints/staff.py)
- [Complaint lifecycle service](https://github.com/TakshChauhan/Campus-Complaint-Management-System/blob/main/backend/app/services/complaint_lifecycle_service.py)
- [Existing schemas](https://github.com/TakshChauhan/Campus-Complaint-Management-System/tree/main/backend/app/schemas)

## 2. API-wide conventions

- JSON request/response bodies unless explicitly marked HTML (Google OAuth callback). Send `Content-Type: application/json` for JSON requests.
- Protected endpoints require `Authorization: Bearer <access_token>`. Roles are `student`, `staff`, `admin`. A deactivated account receives `403` on every protected route.
- Authentication failures normally return `401`, role/assignment failures `403`, and hidden/out-of-scope complaint IDs `404` (do not reveal another department's or student's complaint existence).
- Time fields are ISO 8601 datetime strings. Parse them as dates, rather than requiring a particular textual UTC suffix.
- Success arrays are JSON arrays `[]`, **not** `{items: [...]}` unless explicitly stated.
- Paginated list routes return the total number of matching records (after filters, before pagination) in the `X-Total-Count` header.
- The frontend's `VITE_API_BASE_URL` should be the backend **origin**, e.g. `http://localhost:8000`, because `frontend/src/api/client.ts` adds `/api/v1` itself.
- CORS on `main` allows `GET`, `POST`, `PATCH`, `OPTIONS`, `HEAD`, and the frontend client's `method` type accepts `'GET' | 'POST' | 'PATCH'`. Every Sprint 3 route uses one of these methods, so no CORS or client method change is needed (`PATCH /users/me/residence` in 7.3 is already supported).
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
| MAIN | POST | `/api/v1/complaints/duplicate-suggestions` | Student | Advisory similar-complaint matches; `200` |
| MAIN | POST | `/api/v1/complaints` | Student | Create complaint; `201` |
| MAIN | GET | `/api/v1/complaints/mine` | Student | Search/filter own complaints; `200` |
| MAIN | GET | `/api/v1/complaints/{complaint_id}` | Student (owner only) | Detailed own complaint; `200` |
| MAIN | POST | `/api/v1/complaints/{complaint_id}/reopen` | Student (owner only) | Reopen a resolved complaint; `200` |
| MAIN | GET | `/api/v1/complaints/{complaint_id}/history` | Student owner / same-department staff / admin | Status event array; `200` |
| MAIN | GET | `/api/v1/staff/complaints` | Staff with assigned department | Department queue; `200` |
| MAIN | GET | `/api/v1/staff/complaints/{complaint_id}` | Staff, same department | Department complaint detail; `200` |
| MAIN | PATCH | `/api/v1/staff/complaints/{complaint_id}/status` | Staff, same department | Status transition with remark; `200` |
| MAIN | GET | `/api/v1/locations/hostels` | Any authenticated role | Active hostel → wing → floor tree; `200` |
| MAIN | GET | `/api/v1/users/me/residence` | Student | Own residence and verification state; `200` / `404` |
| MAIN | PATCH | `/api/v1/users/me/residence` | Student | Set or change own residence (→ `pending`); `200` |
| MAIN | GET | `/api/v1/staff/residences` | Hostel-department staff, admin | Residence verification queue; `200` |
| MAIN | POST | `/api/v1/staff/residences/{residence_id}/decision` | Hostel-department staff, admin | Approve/reject a residence; `200` |
| MAIN | POST | `/api/v1/complaints` *(change)* | Student | Adds `floor_id`; response adds `location` and publication fields; see 7.6 |
| MAIN | GET | `/api/v1/feeds/departments/{department_id}` | Any authenticated role | Published feed of a non-Hostel department; `200` |
| MAIN | GET | `/api/v1/feeds/hostel` | Verified HMC-group student, Hostel-department staff, admin | HMC-group student feed / Hostel staff and admin view; `200` |
| MAIN | GET | `/api/v1/feeds/items/{complaint_id}` | Any authenticated role (visibility-scoped) | One feed item the caller may see; `200` / `404` |
| MAIN | GET | `/api/v1/hmc/publication-requests` | Admin, designated HMC moderator | Pending publication queue; `200` |
| MAIN | POST | `/api/v1/hmc/publication-requests/{complaint_id}/decision` | Admin, moderator of the responsible group | Approve/reject publication; `200` |
| MAIN | POST | `/api/v1/hmc/complaints/{complaint_id}/unpublish` | Admin; moderator of the responsible group for HMC complaints | Remove a published complaint from feeds; `200` |
| MAIN | GET | `/api/v1/hmc/complaints/{complaint_id}/audiences` | Admin, moderator of the responsible group | HMC groups a complaint is shared with; `200` |
| MAIN | POST | `/api/v1/hmc/complaints/{complaint_id}/audiences` | Admin, moderator of both groups | Share with another group on the same floor level; `200` |
| MAIN | POST | `/api/v1/hmc/complaints/{complaint_id}/audiences/{group_id}/revoke` | Admin, moderator of both groups | Withdraw a shared-floor audience; `200` |
| MAIN | GET | `/api/v1/hmc/groups` | Admin, designated HMC moderator | HMC groups and their floors; `200` |
| MAIN | PATCH | `/api/v1/hmc/groups/{group_id}/moderators/{user_id}` | Admin | Designate or remove an HMC moderator; `200` |
| S3-PLANNED | GET | `/api/v1/admin/metrics/resolution` | Admin | Rolling resolution metrics; `200` |

There are **41 merged routes** (39 under `/api/v1` plus 2 health routes) and **1 planned route**. The Sprint 3 merges added 16 routes (2 residence, 2 staff residence, 1 location, 3 feed, 8 HMC) and changed `POST /api/v1/complaints`.

**Not on `main`:** no admin complaint-management routes and no metrics route. `calculate_rolling_resolution_metrics` and `ResolutionMetricsResponse` exist in services/schemas only. `get_public_complaints_feed` and `PublicComplaintFeedItem` also still exist but are not used by any route; the feed routes use `FeedItem` / `HostelFeedItem` (7.1). **`PublicComplaintFeedItem` includes `description` and must not be exposed** (see section 8).

## 4. Shared schemas (TypeScript reference)

These represent response-model fields, not necessarily all usable request fields. Fields with defaults can appear as `null`/default values. Do not inject read-only fields into request bodies.

```ts
type Role = 'student' | 'staff' | 'admin';

type ComplaintStatus = 'submitted' | 'in_progress' | 'resolved' | 'reopened';
// Response `status` fields are plain strings in Pydantic; these four values are the ones
// the lifecycle service writes. Staff queue `status` filter accepts exactly these four.

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

interface DuplicateSuggestionsResponse {
  matches: {
    id: number;
    title: string;
    department_id: number;
    department_name: string;
    status: string;
    similarity_score: number; // 0..1, rounded to 4 decimals
  }[];
  threshold: number; // currently 0.15 (provisional)
  disclaimer: string;
}

// Returned by POST /complaints and GET /complaints/{id}
interface ComplaintDetail {
  id: number;
  title: string;
  description: string;
  department_id: number;
  department_name: string;
  created_by_id: number;
  status: string;
  created_at: string;
  is_public: boolean;
  hostel: string | null;
  wing: string | null;
  floor: string | null;
  reopen_count: number;
  updated_at: string | null;
  resolved_at: string | null;
}

interface MyComplaintListItem {
  id: number;
  title: string;
  description_preview: string; // first 160 characters
  department_id: number;
  department_name: string;
  status: string;
  created_at: string;
}

interface ComplaintReopenResponse {
  id: number;
  status: string; // 'reopened' on success
  reopen_count: number;
  updated_at: string;
  resolved_at: string | null; // null after reopen
}

interface StaffComplaintQueueItem {
  id: number;
  title: string;
  description_preview: string; // first 160 characters
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
  actor_id: number; // no actor name or email
  remark: string | null;
  created_at: string;
}
```

Sprint 3 schemas are in section 7.1.

## 5. Merged APIs — authentication, profile, departments

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

**`POST /api/v1/departments/suggest`** and **`POST /api/v1/complaints/suggest`** — Both return the same `SuggestionResponse`; only students can call them (`403` otherwise). Body:

```json
{"title":"Hostel Wi-Fi unavailable","description":"Internet access is failing in the hostel study area."}
```

The engine is **keyword-based advisory logic**, not a trained ML classifier; a suggestion never automatically determines the complaint's chosen department. Valid title 3–120 chars, description 10–2000 chars. Suggestions can be empty for uncertain or fallback results.

## 6. Merged APIs — complaints, lifecycle and staff

### 6.1 `POST /api/v1/complaints` — [MAIN]

Student only; `201 ComplaintDetail`. Accepted request properties (extra keys are rejected with `422`):

```json
{
  "title": "Hostel Wi-Fi not working",
  "description": "The campus internet has not worked since last night in my room.",
  "department_id": 2,
  "is_public": false,
  "hostel": "Hostel A",
  "wing": "East",
  "floor": "2"
}
```

- `title` 3–120 and `description` 10–2000 characters after trim; `department_id` positive and must identify an active department.
- `is_public` optional, default `false`.
- `hostel` (≤100), `wing` (≤50), `floor` (≤20) are optional **free-text** strings on `main`; blank values become `null`. They are not validated against any location table (Sprint 3 replaces this with `floor_id`, see 7.6).
- New complaint status is `submitted`. The complaint and its initial status-history event (`from_status: null`, `to_status: "submitted"`) are written in one transaction.
- Errors: `400` inactive department, `404` missing department, `403` wrong role, `422` invalid body, `500` transaction failure.
- **Do not submit** `status`, `created_by_id`, `reopen_count` or timestamp fields.

### 6.2 `GET /api/v1/complaints/mine` — [MAIN]

Student only; returns `MyComplaintListItem[]`, with `X-Total-Count`. Supported optional query parameters:

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

### 6.3 `GET /api/v1/complaints/{complaint_id}` — [MAIN]

Student owner only; returns `ComplaintDetail`. A complaint owned by another student (or nonexistent ID) returns `404`. Non-students get `403`.

### 6.4 `POST /api/v1/complaints/duplicate-suggestions` — [MAIN]

Student only (`403` otherwise); `200 DuplicateSuggestionsResponse`. Body (extra keys rejected):

```json
{"title":"Hostel Wi-Fi not working","description":"The internet has been down in my room since last night."}
```

`title` 3–120, `description` 10–2000 characters. TF-IDF cosine similarity against a corpus of **public complaints plus the caller's own complaints only**; another student's private complaint is never compared or returned. At most 3 matches with `similarity_score >= threshold` (currently `0.15`, provisional), ordered by score descending, then `id` descending. Matches carry no description or creator fields. Advisory only: the student can still submit.

### 6.5 `POST /api/v1/complaints/{complaint_id}/reopen` — [MAIN]

Student owner only. Optional body (may be omitted entirely; extra keys rejected):

```json
{"remark":"The internet issue returned after two days."}
```

`remark` ≤2000 characters; blank becomes `null`, and the history event then records `"Student requested complaint reopen."`. Rules: complaint must currently be `resolved`, reopened **at most 2 times**, and **within 7 days** of `resolved_at`. On success the status becomes `reopened`, `reopen_count` increments, `resolved_at` is cleared and a history event is written atomically. Response `200 ComplaintReopenResponse`.

Errors: `404` not found / not owned, `409` not currently `resolved` (or changed concurrently — refresh and retry), `400` reopen limit reached, window expired, or missing resolution timestamp, `403` non-student, `422` invalid ID/body.

### 6.6 `GET /api/v1/complaints/{complaint_id}/history` — [MAIN]

Any authenticated role, scoped server-side:

- **Student:** only complaints they created.
- **Staff:** only complaints in their assigned department; staff without a department see nothing.
- **Admin:** any existing complaint. **Confirmed** as the intended policy (Sprint 3 decision); this matches `main`.

Out-of-scope or missing IDs return `404`. Returns `ComplaintStatusHistoryItem[]` in chronological order (`created_at ASC`, then `id ASC`), no pagination. Exposes `actor_id` but never actor name or email.

```json
[
  {"id":1001,"from_status":null,"to_status":"submitted","actor_id":11,"remark":null,"created_at":"2026-10-20T10:00:00Z"},
  {"id":1002,"from_status":"submitted","to_status":"in_progress","actor_id":4,"remark":"Assigned to the IT support team.","created_at":"2026-10-20T12:00:00Z"}
]
```

Complaints created before migration `0007` received a backfilled initial event from that migration; complaints created after it get one from the creation transaction (6.1).

### 6.7 `GET /api/v1/staff/complaints` — [MAIN]

Role `staff` only (admins and students get `403`). Staff with no assigned department get `403`. Lists **only** complaints in the caller's department as `StaffComplaintQueueItem[]` plus `X-Total-Count`, newest first (`created_at DESC, id DESC`).

| Query | Type | Default | Notes |
| --- | --- | --- | --- |
| `status` | `submitted`, `in_progress`, `resolved`, `reopened` | absent | Optional exact status filter; other values `422` |
| `limit` | integer 1–100 | `50` | Page size |
| `offset` | integer >= 0 | `0` | Number skipped |

Example: `GET /api/v1/staff/complaints?status=submitted&limit=20&offset=0`.

### 6.8 `GET /api/v1/staff/complaints/{complaint_id}` — [MAIN]

Role `staff` only, assigned department required (`403`). Response `StaffComplaintDetail`. Complaints outside the caller's department return `404`.

### 6.9 `PATCH /api/v1/staff/complaints/{complaint_id}/status` — [MAIN]

Role `staff` only, assigned department required (`403`), complaint must be in the caller's department (`404` otherwise). Body (extra keys rejected):

```json
{"status":"in_progress","remark":"Assigned to the IT support team."}
```

`status` must be `in_progress` or `resolved`; `remark` required, 1–2000 non-whitespace characters. Reopening is **not** done here (see 6.5). Permitted transitions:

| From | To |
| --- | --- |
| `submitted` | `in_progress` |
| `in_progress` | `resolved` |
| `reopened` | `in_progress` |

The status, `updated_at`, `resolved_at` (set on `resolved`, cleared otherwise) and a history event with the remark are written atomically. Response `200 StaffComplaintDetail`.

Errors: `409` disallowed transition (message lists permitted targets) or concurrent change, `404` out of department, `403` wrong role / no department, `422` invalid body.

## 7. Sprint 3 — API contract v3 (as implemented)

**Every route in this section is [MAIN] at the code baseline except 7.9, which is still [S3-PLANNED].** All require a bearer token (`401` without one; `403` for a deactivated account). Unless stated, validation errors use the standard `422` shape (section 10). Where a sub-section differs from the v3 plan, it carries the line *Differs from v3 plan; see Sprint 4 decision* (section 11).

**Hostel department** below means the active department whose name is `Hostel` (trimmed, case-insensitive). **Hostel-department staff** are users with role `staff` whose `department_id` is that department. A **designated HMC moderator** is an active `staff` user that an admin has assigned to an HMC group (7.11.8). Department membership, including the Hostel department, grants no publication or moderation rights.

**Canonical location and HMC groups (as implemented):** the only physical hierarchy is `Hostel → HostelWing → HostelFloor` (`hostels`, `hostel_wings`, `hostel_floors`, migration `0008`). An HMC group (`hmc_groups`) belongs to one hostel and one floor level (`floor_code`); `hmc_group_floors` maps one or two canonical floors to it, in different wings, all at that floor code. A floor maps to at most one group. A group is **valid** only while it is active, its hostel is active, and every mapped floor and wing is active and belongs to that hostel and floor code; an invalid group grants nothing. A student's HMC group is derived from their residence (7.3) only while it is `verified`, its verifier is still an active staff/admin account, and its floor is active and mapped to a valid group. Legacy free-text `hostel`/`wing`/`floor` columns are display/backfill fields and are never used for authorization.

**Location-specific complaints are HMC-scoped whatever their department.** A public complaint with a `floor_id`, with legacy location text, or assigned to the Hostel department is HMC-scoped (`visibility_scope = hmc_group_public`) and never appears in a department feed. `is_public` is only a request: a complaint appears in a feed only when `publication_status = published`, and an HMC-scoped complaint additionally needs an audience row for the viewer's group. 7.11 lists how each publication status is assigned.

**Error codes:** where this section names a `code`, the body is `{"detail": {"code": "<code>", "message": "<human-readable>"}}`, passed through unchanged by the HTTP exception handler. Clients must branch on `detail.code`, not on the message text. All other errors in this section use a plain string `detail`.

### 7.1 Sprint 3 schemas

```ts
interface FloorNode { id: number; code: string; name: string; }
interface WingNode { id: number; code: string; name: string; floors: FloorNode[]; }
interface HostelNode { id: number; code: string; name: string; wings: WingNode[]; }

type ResidenceStatus = 'pending' | 'verified' | 'rejected';

interface MyResidence {
  floor_id: number; // canonical HostelFloor.id; HMC group is server-derived
  hostel: string; // display name
  wing: string;
  floor: string;
  status: ResidenceStatus;
  remark: string | null; // staff remark from the latest decision
}

interface StaffResidenceItem extends MyResidence {
  id: number;            // residence ID used by the decision route
  student_id: number;
  student_name: string;  // Hostel staff/admin only; never in feeds (see 7.4)
  student_email: string; // Hostel staff/admin only; never in feeds (see 7.4)
  submitted_at: string;
  decided_at: string | null; // time of the latest approve/reject; null while pending
}

interface ComplaintLocation { hostel: string; wing: string; floor: string; }

type PublicationStatus = 'private' | 'pending_review' | 'pending_mapping' | 'published' | 'rejected';

// Fields added to ComplaintDetail (section 4) by Sprint 3; returned by
// POST /complaints and GET /complaints/{complaint_id} to the owner only (7.6).
// The three state fields are plain strings in Pydantic; the values below are
// the ones the service and database check constraints allow.
interface ComplaintDetailSprint3Fields {
  floor_id: number | null;
  location: ComplaintLocation | null;
  visibility_scope: string;   // 'private' | 'department_public' | 'hmc_group_public'
  feed_review_status: string; // 'not_required' | 'pending' | 'approved' | 'auto_approved' | 'rejected'
  publication_status: string; // PublicationStatus
}
// MyComplaintListItem (section 4) also adds `publication_status: string`.

// Structured Sprint 3 errors: {"detail": {"code": Sprint3ErrorCode, "message": string}}
type Sprint3ErrorCode =
  | 'hostel_feed_required'        // 400, department feed (7.7)
  | 'residence_not_verified'      // 403, hostel feed (7.8)
  | 'hostel_selection_forbidden'  // 403, hostel feed: student sent hostel_id (7.8)
  | 'hostel_not_found';           // 404, hostel feed: unknown/inactive hostel_id (7.8)

interface ApiCodedErrorDetail { code: Sprint3ErrorCode; message: string; }

interface FeedItem {
  id: number;
  title: string;
  department_id: number;
  department_name: string;
  status: string;
  created_at: string;
  updated_at: string;
  reopen_count: number;
}

interface HostelFeedItem extends FeedItem {
  // Display names resolved from the complaint's canonical floor_id; null when
  // the complaint has no floor_id. Never inferred from legacy text.
  hostel: string | null;
  wing: string | null;
  floor: string | null;
}
```

HMC moderation schemas are in 7.11.

> **Differs from v3 plan; see Sprint 4 decision.** v3 also listed `residence_location_incomplete` (`422`) and `hostel_selection_unavailable` (`503`). No route on `main` returns either code.

### 7.2 `GET /api/v1/locations/hostels` — [MAIN]

**Access:** any authenticated role.\
**Request:** no parameters.\
**Response:** `200 HostelNode[]`. Active hostels only, each with its active wings and their active floors. Hostels are ordered by `name`, wings and floors by `code` (then `id`). A hostel with no active wings has `wings: []`; a wing with no active floors has `floors: []`.

```json
[
  {"id":1,"code":"HA","name":"Hostel A","wings":[
    {"id":3,"code":"E","name":"East Wing","floors":[
      {"id":12,"code":"2","name":"Second Floor"}
    ]}
  ]}
]
```

**Errors:** `401`.

### 7.3 `GET` / `PATCH /api/v1/users/me/residence` — [MAIN]

**`GET`** — **Access:** student (`403` other roles).\
**Response:** `200 MyResidence`, or `404` (`"No residence has been set."`) if the student has not set a residence.

```json
{"floor_id":12,"hostel":"Hostel A","wing":"East Wing","floor":"Second Floor","status":"pending","remark":null}
```

**`PATCH`** — **Access:** student (`403` other roles).\
**Request:** `{"floor_id": 12}` (positive integer; extra keys rejected).\
**Behavior:** creates or replaces the caller's single residence and sets `status` to `pending`. **This also applies when changing an existing `verified` or `rejected` residence**: the previous decision, remark and verifier are cleared, and HMC feed access (7.8) stops until staff verify the residence again.\
**Response:** `200 MyResidence` (with `status: "pending"`).\
**Errors:** `422` (`"Unknown or inactive floor_id."`) when the floor, its wing or its hostel is unknown or inactive; `422` invalid body; `403` wrong role.

`PATCH` is already allowed by the backend CORS configuration and the frontend API client (section 2).

### 7.4 `GET /api/v1/staff/residences` — [MAIN]

**Access:** Hostel-department staff and admin. Other staff and students get `403`.\
**Query:**

| Query | Type | Default | Notes |
| --- | --- | --- | --- |
| `status` | `pending`, `verified`, `rejected` | `pending` | Exact status filter |
| `limit` | integer 1–100 | `20` | Page size |
| `offset` | integer >= 0 | `0` | Number skipped |

**Response:** `200 StaffResidenceItem[]`, oldest submission first (`submitted_at ASC, id ASC`), with `X-Total-Count`.\
**Errors:** `403`, `422` invalid query.

**Student identity (confirmed):** items include `student_name` and `student_email` so staff can identify the student being verified. These fields are returned only to authorized Hostel-department staff and admins on this route and the decision route (7.5), and never appear in any public feed.

### 7.5 `POST /api/v1/staff/residences/{residence_id}/decision` — [MAIN]

**Access:** Hostel-department staff and admin (`403` otherwise).\
**Request:**

```json
{"decision":"reject","remark":"Room allotment list shows a different floor."}
```

`decision` is `approve` or `reject` (extra keys rejected). `remark` is at most 2000 characters; it is trimmed and a blank value becomes `null`. It is required for `reject` and optional for `approve` (stored when given). Approve sets `status` to `verified`; reject sets `rejected`. Both record the deciding user and set `decided_at`.\
**Response:** `200 StaffResidenceItem` after the decision.\
**Errors:** `422` invalid body, including a missing remark on reject (checked first, by request validation); then `403`; `404` unknown residence ID; `409` residence is not `pending` (already decided, or changed concurrently).

### 7.6 `POST /api/v1/complaints` — Sprint 3 change [MAIN]

Extends 6.1. The complaint lifecycle and department routing are unchanged: every complaint still goes to its chosen department, whatever its publication state.

- **Request adds optional `floor_id`** (positive integer identifying a canonical `HostelFloor`). It is the floor where the issue occurred, not the reporter's residence. An unknown floor, or one whose floor, wing or hostel is inactive, returns `422` (`"Invalid or inactive floor_id."`).
- **`floor_id` is optional for Hostel-department complaints by default.** It is required only when the server setting `HOSTEL_COMPLAINT_REQUIRES_FLOOR_ID` is `true` (default `false`); then a Hostel complaint without it returns `422` (`"floor_id is required for Hostel complaints."`). With the default, an unlocated public Hostel complaint is accepted and becomes `pending_mapping` (7.11).
- A `floor_id` on a complaint for **any other department** is kept and makes the complaint HMC-scoped; it never enters the department feed. A non-Hostel public complaint with no `floor_id` and no location text is published to its department feed.
- **Legacy location fields:** `hostel`, `wing` and `floor` text are still accepted. When `floor_id` is given, the stored and returned text is replaced with the canonical names. Without `floor_id`, the text is stored as sent (blank → `null`); a public complaint with only text becomes `pending_mapping`, and the text is never matched to a floor.
- **Response** (`201`, and also `GET /complaints/{complaint_id}`) adds `floor_id`, `location` (canonical names; `null` without `floor_id`), `visibility_scope`, `feed_review_status` and `publication_status` (7.1). These are server-derived, returned only to the owner and never in feeds. They are not request fields (extra keys → `422`).
- `GET /complaints/mine` items add `publication_status`.
- Publication is decided at creation, using the table in 7.11. When a complaint auto-publishes to the reporter's own HMC group, the group's audience row is written in the same transaction as the complaint.

```json
{"title":"Water leak near washroom","description":"Water has been leaking near the second-floor washroom since morning.","department_id":1,"is_public":true,"floor_id":12}
```

> **Differs from v3 plan; see Sprint 4 decision.** v3 made `floor_id` mandatory for Hostel-department complaints. On `main` it is mandatory only when `HOSTEL_COMPLAINT_REQUIRES_FLOOR_ID=true`.

### 7.7 `GET /api/v1/feeds/departments/{department_id}` — [MAIN]

**Access:** any authenticated role.\
**Path:** `department_id`, integer 1–2147483647.\
**Query:** `status` (optional, one of the four complaint statuses), `limit` 1–100 (default `20`), `offset` >= 0 (default `0`).\
**Response:** `200 FeedItem[]` with `X-Total-Count`, `created_at DESC, id DESC`. Only complaints of that department that are public, `publication_status = published`, `visibility_scope = department_public`, have no `floor_id` and no legacy location text. HMC-scoped complaints are excluded even when assigned to IT or Maintenance.\
**Errors:**

- `400` with code `hostel_feed_required` if `department_id` is the Hostel department (use 7.8).
- `404` (`"Department not found."`) if the department does not exist or is inactive.
- `422` invalid path/query.

### 7.8 `GET /api/v1/feeds/hostel` — [MAIN]

**Purpose:** a student sees only complaints published for **their own verified HMC group**. There is no `scope` parameter and no hostel-wide student view. The client cannot choose a different group, wing or hostel to widen access.

**Query:**

| Query | Type | Default | Notes |
| --- | --- | --- | --- |
| `hostel_id` | integer 1–2147483647 | absent | Hostel-department staff/admin only; a student who supplies it receives `403 hostel_selection_forbidden` |
| `status` | one of the four complaint lifecycle statuses | absent | Optional exact filter |
| `limit` | integer 1–100 | `20` | Page size |
| `offset` | integer >= 0 | `0` | Number skipped |

**Access and visibility** (after authentication and query validation, checks run in this order):

| Caller / condition | Result |
| --- | --- |
| Any caller, when no active Hostel department exists | `404` (`"Hostel department not found."`) |
| Student who supplies `hostel_id` | `403 hostel_selection_forbidden` |
| Student without a verified residence mapped to a valid HMC group | `403 residence_not_verified`; no fallback to a wider view |
| Student with a valid group | Published HMC-scoped complaints that have an audience row for the student's group and are located on a floor at that group's hostel and floor level. The assigned department can be any department |
| Hostel-department staff or admin, no `hostel_id` | Every published HMC-scoped complaint that has at least one audience row, across all hostels |
| Hostel-department staff or admin, with `hostel_id` | The same, restricted to floors of that hostel; an unknown or inactive hostel returns `404 hostel_not_found` |
| Any other staff | `403` (string `detail`) |

A complaint reaches a group's feed only through an explicit audience row: the responsible group's row is written on auto-publish or approval, and sharing with another group on the same floor level is a separate moderator decision (7.11.5). Nothing is broadcast to every group on a floor. Moderation (review, unpublish, audiences) is in 7.11 and is not granted by Hostel-department membership.

**Response:** `200 HostelFeedItem[]`, ordered by `created_at DESC, id DESC`, with `X-Total-Count`. No description, reporter identity or moderation notes. Every item on this route has a `floor_id`, so `hostel`, `wing` and `floor` are always the canonical names here.

**Errors:** `401`; `403 residence_not_verified`; `403 hostel_selection_forbidden`; `403` other staff; `404` missing/inactive Hostel department; `404 hostel_not_found`; `422` malformed query.

**Fail closed:** any authorization, mapping or input error returns no feed data and never falls back to a wider audience.

> **Differs from v3 plan; see Sprint 4 decision.** The agreed Model 2 plan was a hostel-wide student feed with `scope=hostel|wing|floor`. `main` has no `scope` parameter and limits students to their verified HMC group's published complaints. Staff/admin `hostel_id` filtering is live, so `503 hostel_selection_unavailable` is never returned, and `residence_location_incomplete` is not used.

### 7.9 `GET /api/v1/admin/metrics/resolution` — [S3-PLANNED]

**Not implemented:** no route exists on `main` at the baseline commit. Only the service and schema exist.

**Access:** admin only (`403` otherwise).\
**Query:** `window_days` (positive integer, default `30`), `department_id` (optional positive integer).\
**Response:** `200 ResolutionMetricsResponse`, wrapping the existing `calculate_rolling_resolution_metrics` service. Only complaints with `resolved_at` inside the window count; duration is `resolved_at - created_at`; negative durations are excluded. All averages are `null` when `resolved_count` is `0`.

```json
{"window_days":30,"department_id":null,"resolved_count":12,"average_resolution_hours":24.5,"average_resolution_days":1.02,"median_resolution_hours":18.0,"min_resolution_hours":2.5,"max_resolution_hours":72.0}
```

**Errors:** `403`, `422` invalid query (`window_days <= 0`; the service itself also rejects it with `400`).

### 7.10 Feed rules (apply to 7.7, 7.8 and `GET /feeds/items/{complaint_id}` in 7.11.9)

- Item fields: `id`, `title`, `department_id`, `department_name`, `status`, `created_at`, `updated_at`, `reopen_count`. Hostel feed and feed-item responses also include `hostel`, `wing`, `floor` (each `string | null`; resolved from `floor_id`, never invented).
- Feeds **never** include `description`, a description preview, `created_by_id`, any user name or email, moderation notes or the publication state fields.
- **Only public complaints with `publication_status = published` appear;** `is_public = true` alone is insufficient. HMC-scoped complaints also need an audience row for the viewer's group (students) or any audience row (Hostel staff/admin). Private, pending, rejected, unmapped and other groups' items never appear.
- Complaints in an inactive department are excluded.
- List order: `created_at DESC, id DESC`.
- `limit` 1–100, default `20`; `offset` >= 0, default `0`.
- List routes return the total matching count in `X-Total-Count`.

### 7.11 HMC publication and moderation [MAIN]

#### Publication status

`publication_status` is one of `private`, `pending_review`, `pending_mapping`, `published`, `rejected`. It is separate from the complaint lifecycle `status`: a complaint is handled by its department whatever its publication state.

| How the complaint gets it | `publication_status` | `visibility_scope` / `feed_review_status` |
| --- | --- | --- |
| Created with `is_public: false` | `private` | `private` / `not_required` |
| Created public, non-Hostel department, no `floor_id`, no legacy location text | `published` (department feed, 7.7) | `department_public` / `not_required` |
| Created public, HMC-scoped, with no valid responsible group: a Hostel complaint without `floor_id`, a text-only location, or a `floor_id` not mapped to a valid HMC group | `pending_mapping` | `hmc_group_public` / `pending` |
| Created public with a `floor_id` mapped to a valid group, by a student who is **not** a verified member of that group | `pending_review` | `hmc_group_public` / `pending` |
| Created public with a `floor_id` mapped to a valid group, by a verified member of that group (auto-publish; responsible audience row written) | `published` | `hmc_group_public` / `auto_approved` |
| A pending request approved by an admin or moderator (7.11.2); needs a valid responsible group; responsible audience row written | `published` | unchanged / `approved` |
| A pending request rejected by an admin or moderator (7.11.2) | `rejected` | unchanged / `rejected` |
| A published complaint unpublished (7.11.3) | `rejected` | unchanged / `rejected` |

Outside the API: migration `0011` backfilled existing rows (public, unlocated, non-Hostel → `published`; every other public complaint → `pending_mapping`), and `backend/scripts/import_hmc_assignments.py --stage-legacy-complaints` moves text-only `pending_mapping` complaints that name exactly one canonical floor to `pending_review`. No route moves a `rejected` complaint back to `published`.

#### Access

All routes below use the bearer token of any active role and authorize in the service:

- **Admin:** an active `admin`. Can act on every group and sees unmapped (`pending_mapping`) requests.
- **Moderator of group G:** an active `staff` user with a moderator assignment for G (7.11.8). A route that involves two groups (7.11.5, 7.11.6) requires assignments for both. Staff cannot act on a complaint that has no valid responsible group.
- Everyone else, including Hostel-department staff without an assignment, gets `403` (string `detail`).

Every review, unpublish and audience change writes a `complaint_publication_audit` row.

#### Schemas

```ts
// Internal moderation queue only; never in feeds.
interface FeedReviewQueueItem {
  id: number;
  title: string;
  description: string;
  department_id: number;
  department_name: string;
  status: string;
  floor_id: number | null;
  hostel: string | null; // canonical names when floor_id is set, otherwise legacy text
  wing: string | null;
  floor: string | null;
  responsible_hmc_group_id: number | null; // null when unmapped
  created_at: string;
  publication_status: 'pending_review' | 'pending_mapping';
  reporter_id: number;
  reporter_name: string | null;
  reporter_email: string | null;
}

interface FeedReviewRequest {
  decision: 'approved' | 'rejected'; // note: not 'approve'/'reject' as in 7.5
  note?: string | null;              // <= 1000 chars; trimmed, blank -> null; required to reject
}

interface FeedReviewResult {
  id: number;
  feed_review_status: 'approved' | 'rejected';
  publication_status: 'published' | 'rejected';
  feed_reviewed_at: string;
  message: string;
}

interface UnpublishRequest { note: string; }                          // 3–1000 chars after trim
interface AudienceGrantRequest { hmc_group_id: number; note: string; } // id > 0; note 3–1000 chars after trim
interface AudienceRevokeRequest { note: string; }                     // 3–1000 chars after trim
interface ModeratorAssignmentRequest { assigned?: boolean; }          // default true

interface ModerationActionResult {
  complaint_id: number | null;
  user_id: number | null;
  hmc_group_id: number | null;
  publication_status: string | null;
  message: string;
}

interface AudienceItem {
  hmc_group_id: number;
  hmc_group_name: string;
  source: 'responsible_group' | 'shared_floor';
  decided_by_id: number;
  created_at: string;
}

// Group configuration; contains no student data.
interface HMCGroupSummary {
  id: number;
  name: string;
  hostel_id: number;
  hostel_name: string;
  floor_code: string;
  floor_ids: number[]; // sorted
  is_active: boolean;
  is_valid: boolean;
}
```

All request bodies reject extra keys. Path IDs (`complaint_id`, `group_id`, `user_id`) are integers 1–2147483647. Body, path and query validation errors (`422`) are returned before any of the checks listed below.

#### 7.11.1 `GET /api/v1/hmc/publication-requests`

**Access:** admin, or staff designated as a moderator of at least one group. Other callers, and staff with no assignment, get `403`.\
**Query:** `department_id` (optional, positive integer), `limit` 1–100 (default `50`), `offset` >= 0 (default `0`).\
**Response:** `200 FeedReviewQueueItem[]`, oldest first (`created_at ASC, id ASC`), with `X-Total-Count`. Contains public complaints with `publication_status` `pending_review` or `pending_mapping` in active departments. Admins see all of them, including unmapped ones; a moderator sees only those whose floor maps to a valid group they moderate. Items include the full description and reporter identity for review.\
**Errors:** `403`.

#### 7.11.2 `POST /api/v1/hmc/publication-requests/{complaint_id}/decision`

**Access:** admin, or a moderator of the complaint's responsible group.\
**Request:**

```json
{"decision":"rejected","note":"Duplicate of an existing published report."}
```

**Behavior:** `approved` sets `publication_status` to `published` and writes the responsible group's audience row; it does not share with any other group. `rejected` sets it to `rejected`; the complaint stays in its department workflow.\
**Response:** `200 FeedReviewResult`.\
**Errors (checked in this order):** `404` complaint missing, not public or not HMC-scoped; `403` not an admin or a moderator of the responsible group; `409` no longer `pending_review`/`pending_mapping`; `422` `rejected` without a `note`; `409` `approved` while the floor has no valid HMC group mapping; `409` concurrent decision.

#### 7.11.3 `POST /api/v1/hmc/complaints/{complaint_id}/unpublish`

**Access:** for an HMC-scoped complaint, admin or a moderator of its responsible group; for a department-wide complaint, admin only.\
**Request:** `{"note":"Contains personal details of another student."}` (required).\
**Behavior:** a `published` complaint becomes `rejected` and leaves every feed.\
**Response:** `200 ModerationActionResult`:

```json
{"complaint_id":42,"user_id":null,"hmc_group_id":null,"publication_status":"rejected","message":"Complaint unpublished. The moderation action was recorded in the audit trail."}
```

**Errors:** `404` complaint missing or not public; `403` (non-admin on a department-wide complaint, or not a moderator of the responsible group); `409` not currently `published`.

#### 7.11.4 `GET /api/v1/hmc/complaints/{complaint_id}/audiences`

**Access:** admin, or a moderator of the complaint's responsible group.\
**Response:** `200 AudienceItem[]` in the order they were added. The complaint must be public and HMC-scoped but need not be published; a pending complaint returns `[]`.\
**Errors:** `404` complaint missing, not public or not HMC-scoped; `403`.

#### 7.11.5 `POST /api/v1/hmc/complaints/{complaint_id}/audiences`

**Access:** admin, or a moderator of both the responsible group and the target group.\
**Request:** `{"hmc_group_id": 7, "note": "Shared washroom used by both wings."}`.\
**Behavior:** shares a published complaint with another valid group on the same hostel and floor level (`source = shared_floor`).\
**Response:** `200 AudienceItem[]` (the complaint's full audience list after the change).\
**Errors (checked in this order):** `404` complaint missing, not public or not HMC-scoped; `403`; `409` complaint not `published`; `409` the complaint's floor has no valid responsible group; `404` target group missing or not valid; `422` target is the responsible group or is not on the same hostel floor level; `409` target is already an audience.

#### 7.11.6 `POST /api/v1/hmc/complaints/{complaint_id}/audiences/{group_id}/revoke`

**Access:** admin, or a moderator of both the responsible group and `group_id`.\
**Request:** `{"note":"Issue confirmed to affect only the East wing."}`.\
**Response:** `200 AudienceItem[]` after removal.\
**Errors:** `404` complaint missing, not public or not HMC-scoped; `403`; `404` `group_id` is not an audience of the complaint; `409` `group_id` is the responsible group (unpublish instead).

#### 7.11.7 `GET /api/v1/hmc/groups`

**Access:** admin, or staff designated as a moderator of at least one group (`403` otherwise).\
**Response:** `200 HMCGroupSummary[]` for every group, including inactive and invalid ones, ordered by `hostel_id`, `floor_code`, `name`. No pagination.\
**Errors:** `403`.

#### 7.11.8 `PATCH /api/v1/hmc/groups/{group_id}/moderators/{user_id}`

**Access:** admin only (`403` otherwise).\
**Request:** a JSON body is required; `{"assigned": true}` designates and `{"assigned": false}` removes the assignment (`{}` means `true`). Repeating a call is harmless.\
**Behavior:** the user must be an active `staff` account; the route does not check the user's department.\
**Response:** `200 ModerationActionResult`:

```json
{"complaint_id":null,"user_id":15,"hmc_group_id":3,"publication_status":null,"message":"HMC moderator assignment updated."}
```

**Errors:** `403`; `404` group missing or inactive; `404` user is not an active staff account.

#### 7.11.9 `GET /api/v1/feeds/items/{complaint_id}`

**Access:** any authenticated role; the feed visibility rules decide what each caller can see.\
**Response:** `200 HostelFeedItem` (7.10 fields; `hostel`, `wing`, `floor` are `null` for department-wide items). The complaint is returned when any of these hold:

- it is a published department-wide complaint (7.7), for any role;
- the caller is a student with a valid HMC group, and it would appear in that student's hostel feed (7.8);
- the caller is an admin or Hostel-department staff, and it is a published HMC-scoped complaint with at least one audience row.

**Errors:** `404` (`"Feed complaint not found."`) for a missing ID and for any complaint the caller may not see. A student without a verified group gets `404` for HMC items, not `403`.

## 8. Privacy rules

1. A private complaint is visible only to its creator, authorized staff of its assigned department and admins. It never appears in a student/public feed or in another student's duplicate suggestions.
2. A non-Hostel complaint with **no hostel-specific location** may appear in its authenticated campus-wide department feed only after publication. Any complaint affecting a hostel location stays HMC-scoped **even when assigned to IT or another department**. Hostel-department complaints, including ones missing a location, must never be published to a campus-wide department feed.
3. A student sees HMC-scoped published complaints **only for their own valid, verified HMC group**. A group covers at most two wings on the same floor level. Other groups' complaints are inaccessible even by guessing IDs or searching duplicates. Unknown, ambiguous, text-only or unverified locations fail closed.
4. A report about the student's own mapped group can auto-publish; a report about another group needs review. A report with no valid group mapping stays `pending_mapping`. Wing-less shared-floor reports require a deliberate group audience decision before sharing across groups.
5. Public feeds and duplicate suggestions never expose `description`, `created_by_id`, reporter name/email or internal moderation notes; the backend may use descriptions internally *only after* applying visibility filters. Do not reuse the existing `PublicComplaintFeedItem` (which includes `description`) as the student-facing DTO.
6. Complaint status history exposes `actor_id` only, not actor names/email. A requested out-of-scope complaint ID returns `404` rather than confirming the record exists.
7. HMC moderation access is limited to admins and explicitly designated HMC-group moderators. Department staff membership by itself does not grant HMC publication authority. Student identity is shown only in independently authorized internal verification/moderation workflows.



## 9. System health responses

`GET /health` returns HTTP 200 with fields:

```json
{"status":"healthy","project":"CCMS","version":"1.0.0","environment":"development","database":"operational"}
```

When DB is unavailable, response still has HTTP 200, but `status` is `degraded` and `database` is `unavailable`. Other fields reflect server configuration.

`GET /health/ready` returns HTTP 200 when DB reachable and HTTP 503 otherwise, with:

```json
{"ready":true,"database":"operational"}
```

## 10. Error representation

The app's global HTTP exception handler returns `{ "detail": <exc.detail> }`. Usually `detail` is a human-readable string. Validation errors returned through its request-validation handler use:

```json
{"detail":[{"field":"body -> title","message":"...","type":"value_error"}]}
```

Clients must therefore handle `detail` as a **string**, an **array** (validation), or, from Sprint 3, an **object** `{code, message}` (section 7).

**Integration note:** `frontend/src/api/client.ts` currently handles string and array `detail` only, not object-shaped `detail`. Object-detail handling (reading `detail.code` and `detail.message`) must be implemented as part of **S3-21**.

Some manual `422` errors (e.g. reversed `date_from`/`date_to`) use a string `detail`. OAuth callback is HTML rather than the standard JSON error model. Rate-limited auth endpoints may yield `429` and a `Retry-After` header. Account email delivery errors can yield `502`. Unhandled errors return `500` with a generic message.

## 11. Decisions and integration checklist

**Resolved Sprint 3 decisions:**

- **Admin history access** (6.6): confirmed; admins may read any complaint's history.
- **Residence queue identity fields** (7.4): `student_name` and `student_email` are included, for authorized Hostel staff and admins only.
- **Legacy location fields** (7.6): text columns kept for compatibility; clients send `floor_id`; server fills display names; columns not dropped before the final release.
- **Residence update method** (7.3): `PATCH`, which CORS and the frontend client already support.
- **Incomplete verified residence location** (7.8): do not grant any HMC feed access; treat as `403 residence_not_verified` until mapped and re-verified. The old student `scope=wing/floor` option is removed.
- **Verified residence without a valid hostel** (7.8): `403` with code `residence_not_verified` (fail closed).
- **Missing or inactive Hostel department** (7.8): `404`.
- **Staff/admin `hostel_id`** (7.8): never ignored. The location hierarchy is integrated on `main`, so it filters by canonical hostel; `503 hostel_selection_unavailable` is not used.
- **Student-supplied `hostel_id`** (7.8): a well-formed value returns `403` with code `hostel_selection_forbidden`; malformed values get the standard `422`.
- **Unknown or inactive staff/admin `hostel_id`** (7.8): `404` with code `hostel_not_found`.
- **Error precedence** (7.8): the order implemented on `main` is listed in the 7.8 access table; clients should still branch on each condition rather than on order. Every case fails closed.
- **Nullable hostel feed locations** (7.1, 7.8): `hostel`, `wing`, `floor` are `string | null` for legacy complaints; canonical IDs stay authoritative.
- **Legacy complaints without canonical IDs** (7.8): excluded from student HMC feeds; records preserved for verified backfill and never used to infer group membership.

**Integration decisions that were open before the PR #46 merge, as resolved on `main`:** (a) the canonical v3 `/feeds/...` routes are implemented; the `/complaints/feed...` routes were not merged; (b) residences, complaints and HMC groups use the PR #47 `Hostel/HostelWing/HostelFloor` hierarchy, with no separate building/floor/wing tables; (c) Hostel-department staff and admins read the hostel feed, while publication moderation is a separate admin/designated-moderator permission (7.11); (d) nothing is shared with other groups automatically; sharing a complaint with another group on the same floor level needs an explicit audience decision (7.11.5). The Sprint 4 decision below replaces (c) and (d) and the HMC-group basis of the student feed.

**Sprint 4 decision** (agreed; not yet implemented — 7.6, 7.8 and 7.11 describe `main` as it is today):

- **Hostel feed (7.8):** changes to the agreed **Model 2**. Verified residents see public complaints from their own hostel, with `scope=hostel|wing|floor`.
- **Publication (7.6, 7.11):** a verified resident's public complaint about their own hostel publishes immediately; every other public hostel complaint goes to Hostel-department staff/admin review.
- **Unpublish (7.11.3):** stays.
- **Out of product scope:** HMC group, audience and moderator-designation routes: `GET /hmc/groups`, `PATCH /hmc/groups/{group_id}/moderators/{user_id}`, `GET`/`POST /hmc/complaints/{complaint_id}/audiences` and `POST /hmc/complaints/{complaint_id}/audiences/{group_id}/revoke`.
- Request, response and error details for these changes will be specified in the contract revision that accompanies the Sprint 4 implementation.

**Implementation TODOs** (work still to do; these are not open design decisions):

1. **Object-shaped error `detail`:** add handling for `{"detail":{"code","message"}}` to `frontend/src/api/client.ts` as part of S3-21 (section 10). This includes every Sprint 3 code returned on `main`: `hostel_feed_required`, `residence_not_verified`, `hostel_selection_forbidden` and `hostel_not_found`.
2. **Residence integration:** done. Residences are stored in `student_residences` (migration `0009`) and verified through 7.5. A student without a verified residence mapped to a valid HMC group still receives `403 residence_not_verified` from the hostel feed.
3. **Canonical location integration:** done. Alembic order is `0008` (hostel hierarchy) → `0009` (student residences) → `0010` (complaint `floor_id`) → `0011` (publication fields and audit) → `0012` (complaint HMC audiences), single head. No separate `buildings`/`floors`/`wings` tables are created. Run `alembic upgrade head` before depending on these tables.
4. **Feed schema/publication:** use a DTO matching 7.10 and filter on publication status plus authorized HMC group before fetching student feed details or similarity candidates; never expose `PublicComplaintFeedItem` as-is.
5. **Test against runtime:** after each Sprint 3 merge, regenerate OpenAPI from the deployment and compare paths, schemas, authorization, CORS, errors and examples against this document. Run `alembic upgrade head` on the target DB before depending on new tables/columns.
6. **Documentation synchronization:** update `docs/FRONTEND_HANDOFF.md` and `docs/README.md` links as needed, without duplicating this contract. The route namespace stays `/api/v1`.

## 12. Change control

- **This document becomes the canonical Sprint 3 API contract only once PR #43 is approved and merged.** Until then it is a proposed amendment for team review. Contract changes are made through a PR approved by Taksh; no route, request/response field, access rule or error code is final until merged.
- When a `[S3-PLANNED]` route merges, the same PR (or a follow-up docs PR approved by Taksh) changes its tag to `[MAIN]` and corrects any detail that differs from the implementation.
- Backend route owners confirm paths, bodies, schemas, permissions, filters and errors against code and OpenAPI; frontend owners add typed API functions and screens only when the matching backend route is `[MAIN]`.
