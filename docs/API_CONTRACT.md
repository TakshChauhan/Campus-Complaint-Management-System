# CCMS API Contract — v3 (Sprint 3)

**Reviewed:** 27 October 2026 (HMC privacy amendment proposed for review)\
**Code baseline:** `main` at commit `c796302ada58a6ec6792e3a6ea94d3925fca6360` (merge of PR #42)\
**API route version:** `v1` (still `/api/v1`; contract v3 does **not** imply `/api/v3`)\
**Local API origin:** `http://localhost:8000`\
**Versioned API base:** `http://localhost:8000/api/v1`\
**OpenAPI:** `http://localhost:8000/openapi.json` and `/docs` when `ENABLE_API_DOCS` is enabled\
**Contract status:** Proposed v3 amendment in PR #43, pending team review. `[MAIN]` routes refer to the documented Sprint 2 baseline; `[S3-PLANNED]` paths are target interfaces, **not claims that PR #46 currently exposes these paths**. See the integration blockers in section 11.

## 1. Source and availability rules

This document was prepared by reading the route, schema and service code on `main`, not by a running-server or deployment smoke test.

- **[MAIN]** Route and schema exist on `main` at the commit above. A working deployment also requires correct configuration, database migrations (`alembic upgrade head`, currently through `0007`) and other dependencies.
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
| S3-PLANNED | GET | `/api/v1/locations/hostels` | Any authenticated role | Active hostel → wing → floor tree; `200` |
| S3-PLANNED | GET | `/api/v1/users/me/residence` | Student | Own residence and verification state; `200` / `404` |
| S3-PLANNED | PATCH | `/api/v1/users/me/residence` | Student | Set or change own residence (→ `pending`); `200` |
| S3-PLANNED | GET | `/api/v1/staff/residences` | Hostel-department staff, admin | Residence verification queue; `200` |
| S3-PLANNED | POST | `/api/v1/staff/residences/{residence_id}/decision` | Hostel-department staff, admin | Approve/reject a residence; `200` |
| S3-PLANNED | POST | `/api/v1/complaints` *(change)* | Student | Adds `floor_id` and `location`; see 7.6 |
| S3-PLANNED | GET | `/api/v1/feeds/departments/{department_id}` | Any authenticated role | Public feed of a non-Hostel department; `200` |
| S3-PLANNED | GET | `/api/v1/feeds/hostel` | Verified HMC-group student, Hostel-department staff, admin | HMC-restricted student feed / authorized staff view; `200` |
| S3-PLANNED | GET | `/api/v1/admin/metrics/resolution` | Admin | Rolling resolution metrics; `200` |

There are **25 merged routes** (23 under `/api/v1` plus 2 health routes) and **8 new planned routes** plus one planned change to an existing route.

**Not on `main`:** no admin complaint-management routes, no public feed route and no metrics route exist yet. `get_public_complaints_feed`, `calculate_rolling_resolution_metrics`, `PublicComplaintFeedItem` and `ResolutionMetricsResponse` exist in services/schemas only. **`PublicComplaintFeedItem` includes `description` and must not be reused as-is for Sprint 3 feeds** (see section 8).

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

## 7. Sprint 3 — API contract v3 (Model 2 public feeds)

**All routes in this section are [S3-PLANNED] and do not exist on `main`.** All require a bearer token (`401` without one). Unless stated, validation errors use the standard `422` shape (section 10).

**Hostel department** below means the department seeded as `Hostel`. **Hostel-department staff** are users with role `staff` whose `department_id` is that department.

**Canonical location and HMC boundary (required for S3):** PR #47's merged physical hierarchy is `Hostel → HostelWing → HostelFloor` (`hostels`, `hostel_wings`, `hostel_floors`). Each HMC group manages **at most two wings at the same floor level**, with membership derived from a student's *verified canonical residence*, never a client-supplied wing or hostel label. Because a `HostelFloor` belongs to a particular wing, multi-wing HMC assignments must explicitly map each participating wing/floor to its group; do not grant access by text-name matching alone. Existing free-text `hostel`/`wing`/`floor` columns remain display/backfill fields, not authorization keys.

**Location-specific is not the same as Hostel-department-assigned.** A complaint about a hostel wing or floor stays HMC-scoped even when assigned to IT, Maintenance or another department. A Hostel-department complaint without a resolvable HMC location is `pending_mapping`, never department-public. `is_public` is only a request; a complaint is feed-visible only after `publication_status = published` under the correct access scope.

**Publication decisions:** private requests stay private; non-location-specific non-Hostel public requests may publish to their department feed; valid HMC-location reports from a verified member of the responsible group may auto-publish to that group; reports about another group's location need authorized review; incomplete/ambiguous locations fail closed as `pending_mapping`. HMC reviewer designation is separate from department staff assignment. No student may browse another HMC group's published reports, including through detail URLs or duplicate suggestions. A shared-floor complaint affecting multiple groups requires an explicit, reviewable audience decision; an absent wing must not silently widen visibility.

**Error codes:** where this section names a `code`, the body is `{"detail": {"code": "<code>", "message": "<human-readable>"}}`. This fits the existing HTTP exception handler, which returns `{"detail": exc.detail}` unchanged. Clients must branch on `detail.code`, not on the message text.

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
  decided_at: string | null;
}

interface ComplaintLocation { hostel: string; wing: string; floor: string; }

// Structured Sprint 3 errors: {"detail": {"code": Sprint3ErrorCode, "message": string}}
type Sprint3ErrorCode =
  | 'hostel_feed_required'          // 400, department feed (7.7)
  | 'residence_not_verified'        // 403, hostel feed (7.8)
  | 'hostel_selection_forbidden'    // 403, hostel feed: student sent hostel_id (7.8)
  | 'hostel_not_found'              // 404, hostel feed: unknown/inactive hostel_id (7.8)
  | 'residence_location_incomplete' // 422, hostel feed (7.8)
  | 'hostel_selection_unavailable'; // 503, hostel feed before location integration (7.8)

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
  // Display names. Complaints created with floor_id get values resolved from the
  // canonical location hierarchy; legacy complaints may be null. Never inferred.
  hostel: string | null;
  wing: string | null;
  floor: string | null;
}
```

### 7.2 `GET /api/v1/locations/hostels` — [S3-PLANNED]

**Access:** any authenticated role.\
**Request:** no parameters.\
**Response:** `200 HostelNode[]` — active hostels only, each with its active wings and their active floors.

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

### 7.3 `GET` / `PATCH /api/v1/users/me/residence` — [S3-PLANNED]

**`GET`** — **Access:** student (`403` other roles).\
**Response:** `200 MyResidence`, or `404` if the student has not set a residence.

```json
{"floor_id":12,"hostel":"Hostel A","wing":"East Wing","floor":"Second Floor","status":"pending","remark":null}
```

**`PATCH`** — **Access:** student (`403` other roles).\
**Request:** `{"floor_id": 12}` (positive integer; extra keys rejected).\
**Behavior:** creates or replaces the caller's residence and sets `status` to `pending`. **This also applies when changing an existing `verified` or `rejected` residence**: a changed residence must be re-verified, and the previous decision remark is cleared.\
**Response:** `200 MyResidence` (with `status: "pending"`).\
**Errors:** `422` unknown or inactive floor (or a floor whose wing/hostel is inactive), `422` invalid body, `403` wrong role.

`PATCH` is already allowed by the backend CORS configuration and the frontend API client (section 2).

### 7.4 `GET /api/v1/staff/residences` — [S3-PLANNED]

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

### 7.5 `POST /api/v1/staff/residences/{residence_id}/decision` — [S3-PLANNED]

**Access:** Hostel-department staff and admin (`403` otherwise).\
**Request:**

```json
{"decision":"reject","remark":"Room allotment list shows a different floor."}
```

`decision` is `approve` or `reject`. `remark` is required for `reject` (1–2000 non-whitespace characters) and optional for `approve`. Approve sets `status` to `verified`; reject sets `rejected`.\
**Response:** `200 StaffResidenceItem` after the decision.\
**Errors:** `409` residence is not `pending` (already decided), `404` unknown residence ID, `422` missing remark on reject or invalid body, `403`.

### 7.6 `POST /api/v1/complaints` — change for Sprint 3 [S3-PLANNED]

Extends 6.1 while retaining existing complaint lifecycle, department routing and legacy display fields.

- **Request adds `floor_id`** (positive integer identifying a canonical `HostelFloor`). It is required for a new complaint assigned to the Hostel department; missing, unknown or inactive `floor_id` returns `422`.
- For a complaint assigned to **any other department**, a supplied `floor_id` must **not be discarded**. It means the complaint affects a hostel location and must follow HMC publication/access rules instead of the campus-wide department feed. A non-Hostel complaint with no location remains eligible for department-wide publication.
- **Response adds `location`**: `ComplaintLocation` resolved from the canonical floor when a mapped location is supplied, and `null` for non-location-specific complaints. The publication state remains separate from `is_public` and normal complaint status.

```json
{"title":"Water leak near washroom","description":"Water has been leaking near the second-floor washroom since morning.","department_id":1,"is_public":true,"floor_id":12}
```

**Legacy location fields:** the current `hostel`, `wing` and `floor` text columns remain for compatibility. New clients send `floor_id` for located complaints, and the server supplies display names from the canonical hierarchy. An older record with only ambiguous free text must never become visible to a student HMC feed through a guessed match. Such records need verified backfill/mapping; do not drop the original text values.

### 7.7 `GET /api/v1/feeds/departments/{department_id}` — [S3-PLANNED]

**Access:** any authenticated role.\
**Query:** `status` (optional, one of the four complaint statuses), `limit` 1–100 (default `20`), `offset` >= 0 (default `0`).\
**Response:** `200 FeedItem[]` — **published, non-location-specific, department-public** complaints of that department only, `created_at DESC, id DESC`, with `X-Total-Count`. Exclude every HMC-scoped complaint even if its assigned department is IT or Maintenance.\
**Errors:**

- `400` with code `hostel_feed_required` if `department_id` is the Hostel department (use 7.8).
- `404` if the department does not exist or is inactive.
- `422` invalid path/query.

### 7.8 `GET /api/v1/feeds/hostel` — [S3-PLANNED]

**Purpose:** a student's public feed is determined by **verified HMC-group membership**, not hostel-wide access. The client cannot choose a different HMC group, wing or hostel to broaden access.

**Query:**

| Query | Type | Default | Notes |
| --- | --- | --- | --- |
| `hostel_id` | positive integer | absent | Hostel-department staff/admin only; students who supply it receive `403 hostel_selection_forbidden` |
| `status` | one of the four complaint lifecycle statuses | absent | Optional exact filter |
| `limit` | integer 1–100 | `20` | Page size |
| `offset` | integer >= 0 | `0` | Number skipped |

The earlier `scope=hostel/wing/floor` student query is **removed**: a whole-hostel student feed would expose other HMC groups' complaints. If a narrower view is added later, it may only reduce the current student's permitted group results.

**Access and visibility:**

| Caller | Sees |
| --- | --- |
| Student with a current verified residence and a valid HMC assignment | Only `published` HMC-scoped complaints affecting their **own HMC group**, including assigned non-Hostel departments; never other groups |
| Student who supplies a well-formed `hostel_id` | `403 hostel_selection_forbidden` |
| Student without verified residence or without a valid group mapping | `403 residence_not_verified`; no fallback to a whole-hostel view |
| Hostel-department staff and admin, no `hostel_id` | Published HMC-scoped summaries across hostels, subject to authorized internal access; no student identities/descriptions in this public DTO |
| Hostel-department staff and admin, with `hostel_id` | Published HMC-scoped summaries of that canonical hostel only; unknown/inactive hostel returns `404 hostel_not_found` after complaint-location integration |
| Any other staff | `403` |

**HMC mapping:** use a server-verified residence and the authoritative `Hostel → HostelWing → HostelFloor` IDs to derive HMC group membership. A group may cover one or two wings at a common floor level. A report is visible only where its resolved location is assigned to the viewer's group and the publication was authorized for that group. An unresolved complaint, a pending/rejected publication, or a report for another HMC group is excluded. Floor-common items must not be broadcast to multiple groups solely because `wing_id` is absent; explicit group coverage/approval is required. Publication status and group restrictions also apply to feed-item details and duplicate candidate selection.

**Hostel selection (`hostel_id`):** students never select it. For staff/admin, a supplied ID must restrict results, never be ignored. The merged PR #47 hierarchy exists, but PR #46's complaint and residence columns are not yet linked to it. Until that canonical complaint-location integration is complete, a staff/admin `hostel_id` returns `503 hostel_selection_unavailable` (rather than unrestricted data). Once integrated, an unknown/inactive ID returns `404 hostel_not_found`, and legacy text-only records do not match an ID filter.

**Internal moderation is separate:** publication review/unpublish may be performed by admins or staff explicitly appointed to the affected HMC group. Simply belonging to the complaint's assigned department does **not** grant HMC publication authority.

**Response:** `200 HostelFeedItem[]`, ordered by `created_at DESC, id DESC`, with `X-Total-Count`. No description, reporter identity or moderation notes. `hostel`, `wing` and `floor` can be null on retained legacy records where permitted for authorized internal views; student authorization never infers IDs from such text.

**Errors:** `401` unauthenticated; `403 residence_not_verified` without a valid verified group; `403 hostel_selection_forbidden` for a student-supplied `hostel_id`; `403` for unauthorized staff; `404` inactive/missing Hostel department or `404 hostel_not_found` for an invalid staff/admin hostel ID after integration; `422` malformed query; `503 hostel_selection_unavailable` for staff/admin ID filters before canonical complaint location integration.

**Fail closed:** any authorization, mapping or input error returns no feed data and never falls back to a wider audience. Authentication/validation error precedence is not guaranteed when more than one error applies.

**Integration note:** PR #46 currently implements `GET /api/v1/complaints/feed/hmc` (student-only) and `GET /api/v1/complaints/feed?department_id=...`, **not** the two target `/feeds/...` routes above. The target paths and the planned Hostel staff/admin public read interface remain an explicit contract/implementation decision before PR #46 can be considered fully aligned. Do not assume the route names are aliases until tested.

### 7.9 `GET /api/v1/admin/metrics/resolution` — [S3-PLANNED]

**Access:** admin only (`403` otherwise).\
**Query:** `window_days` (positive integer, default `30`), `department_id` (optional positive integer).\
**Response:** `200 ResolutionMetricsResponse`, wrapping the existing `calculate_rolling_resolution_metrics` service. Only complaints with `resolved_at` inside the window count; duration is `resolved_at - created_at`; negative durations are excluded. All averages are `null` when `resolved_count` is `0`.

```json
{"window_days":30,"department_id":null,"resolved_count":12,"average_resolution_hours":24.5,"average_resolution_days":1.02,"median_resolution_hours":18.0,"min_resolution_hours":2.5,"max_resolution_hours":72.0}
```

**Errors:** `403`, `422` invalid query (`window_days <= 0`; the service itself also rejects it with `400`).

### 7.10 Feed rules (apply to 7.7 and 7.8)

- Item fields: `id`, `title`, `department_id`, `department_name`, `status`, `created_at`, `updated_at`, `reopen_count`. Hostel feed items also include `hostel`, `wing`, `floor` (each `string | null`; `null` only for legacy complaints, never invented).
- Feeds **never** include `description`, `created_by_id`, or any user name or email.
- **Only `publication_status = published` complaints appear;** `is_public = true` alone is insufficient. Private, pending, rejected, unmapped or unauthorized HMC items never appear.
- Order: `created_at DESC, id DESC`.
- `limit` 1–100, default `20`; `offset` >= 0, default `0`.
- Total matching count is in `X-Total-Count`.

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
- **Staff/admin `hostel_id`** (7.8): never ignored; `503` with code `hostel_selection_unavailable` until the location hierarchy is integrated, canonical hostel filtering afterwards.
- **Student-supplied `hostel_id`** (7.8): a well-formed value returns `403` with code `hostel_selection_forbidden`; malformed values get the standard `422`.
- **Unknown or inactive staff/admin `hostel_id`** (7.8): `404` with code `hostel_not_found`, once the location hierarchy is integrated.
- **Error precedence** (7.8): no global ordering is guaranteed; behavior is specified per condition and always fails closed.
- **Nullable hostel feed locations** (7.1, 7.8): `hostel`, `wing`, `floor` are `string | null` for legacy complaints; canonical IDs stay authoritative.
- **Legacy complaints without canonical IDs** (7.8): excluded from student HMC feeds; records preserved for verified backfill and never used to infer group membership.

**Open integration decisions — confirmation required before PR #46 merge:** (a) implement the canonical v3 `/feeds/...` routes or formally amend their names to PR #46's `/complaints/feed...` endpoints; (b) map Dhaval's Building/Floor/Wing and verified-residence storage to the already merged PR #47 `Hostel/HostelWing/HostelFloor` hierarchy instead of maintaining two independent physical sources; (c) confirm staff/admin public feed access versus separately authorized HMC moderation; (d) choose explicit allowed audience semantics for floor-common/wing-less complaints. These are not resolved by passing CI.

**Implementation TODOs** (work still to do; these are not open design decisions):

1. **Object-shaped error `detail`:** add handling for `{"detail":{"code","message"}}` to `frontend/src/api/client.ts` as part of S3-21 (section 10). This includes every Sprint 3 code: `hostel_feed_required`, `residence_not_verified`, `hostel_selection_forbidden`, `hostel_not_found`, `residence_location_incomplete` and `hostel_selection_unavailable`.
2. **Residence integration:** until the residence repository (S3-03) is merged, the server has no verified-residence source and every student receives `403 residence_not_verified` from the hostel feed (fail closed).
3. **Canonical location integration:** PR #47's `0008_hostel_locations` already added `hostels`, `hostel_wings` and `hostel_floors`. PR #46's `0009_public_feed_hmc` now follows `0008` in Alembic order but still introduces separate `buildings`, `floors` and `wings` tables. Align complaint, HMC and residence foreign keys to the canonical location model and coordinate subsequent migration revision numbers (including the planned residence work) before deploying persistent data. Until linked, staff/admin `hostel_id` filtering must fail closed with `503`.
4. **Feed schema/publication:** use a DTO matching 7.10 and filter on publication status plus authorized HMC group before fetching student feed details or similarity candidates; never expose `PublicComplaintFeedItem` as-is.
5. **Test against runtime:** after each Sprint 3 merge, regenerate OpenAPI from the deployment and compare paths, schemas, authorization, CORS, errors and examples against this document. Run `alembic upgrade head` on the target DB before depending on new tables/columns.
6. **Documentation synchronization:** update `docs/FRONTEND_HANDOFF.md` and `docs/README.md` links as needed, without duplicating this contract. The route namespace stays `/api/v1`.

## 12. Change control

- **This document becomes the canonical Sprint 3 API contract only once PR #43 is approved and merged.** Until then it is a proposed amendment for team review. Contract changes are made through a PR approved by Taksh; no route, request/response field, access rule or error code is final until merged.
- When a `[S3-PLANNED]` route merges, the same PR (or a follow-up docs PR approved by Taksh) changes its tag to `[MAIN]` and corrects any detail that differs from the implementation.
- Backend route owners confirm paths, bodies, schemas, permissions, filters and errors against code and OpenAPI; frontend owners add typed API functions and screens only when the matching backend route is `[MAIN]`.
