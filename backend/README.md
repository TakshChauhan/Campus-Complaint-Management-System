# CCMS Backend Service (Sprint 1)

Campus Complaint Management System backend API built with **FastAPI**, **PostgreSQL**, **SQLAlchemy ORM**, and **Alembic**.

---

## 1. Prerequisites & Supported Environment

- **Python**: `3.10`, `3.11`, `3.12`, or `3.13` (Tested and verified on Python 3.13.3)
- **Database**: PostgreSQL 14+ (or Docker to run PostgreSQL locally)
- **Package Manager**: `pip` (v24.0+)

---

## 2. Quickstart Setup Guide

### Step 2.1 — Clone & Navigate to Backend
```bash
cd backend
```

### Step 2.2 — Create & Activate Virtual Environment

**On Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**On macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Step 2.3 — Install Dependencies
```bash
pip install -r requirements.txt
```

---

## 3. Database Configuration

You can either run PostgreSQL locally using Docker or via a native PostgreSQL service.

### Option A: Using Docker (Recommended for Local Dev)
From the project root directory, run:
```bash
docker compose up -d
```
This spins up PostgreSQL on port `5432` with user `postgres`, password `postgres`, and database `ccms_db`.

### Option B: Using Native PostgreSQL
Ensure PostgreSQL is running and create the database:
```bash
# Example via psql CLI
psql -U postgres -c "CREATE DATABASE ccms_db;"
```

---

## 4. Environment Variables Configuration

Copy the example environment file:
```bash
# Inside backend/ directory
cp .env.example .env
```

Verify or update the connection settings in `backend/.env`:
```ini
PROJECT_NAME="Campus Complaint Management System (CCMS)"
ENVIRONMENT=development
DEBUG=True

# PostgreSQL connection string
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/ccms_db

# JWT settings (Minimum 32 characters for production)
JWT_SECRET=dev-insecure-jwt-secret-key-change-in-production-min-32-chars
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# Allowed CORS Origins (Frontend dev server URLs)
CORS_ORIGINS=http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173

# API Documentation toggle (enabled by default in dev/test, disabled in prod unless explicitly True)
ENABLE_API_DOCS=True

# Rate Limiting (per-minute sliding window on /auth/login and /auth/register)
RATE_LIMIT_AUTH_PER_MINUTE=10
```

---

## 5. Database Migrations

Apply the Alembic schema migrations:
```bash
alembic upgrade head
```
Migrations included:
- `0001_initial_schema`: Base tables (`users`, `departments`, `complaints`) and foreign key relationships.
- `0002_add_history_index_and_role_check`: Adds composite query index `ix_complaints_created_by_id_created_at` on `(created_by_id, created_at)` for personal complaint history, plus a named CHECK constraint `ck_users_role` enforcing `role IN ('student', 'staff', 'admin')`.

To rollback if needed:
```bash
alembic downgrade base
```

---

## 6. Seeding Data

### Step 6.1 — Seed Provisional Departments (Idempotent)
Run the department seeding script:
```bash
python -m app.scripts.seed_departments
```
*Note: This creates official campus departments (`Hostel`, `IT Services`, `Library`, `Mess & Cafeteria`, `Sports & Gymnasium`, `Campus Security`, `Medical Facility`) per the DAU IT314 specification.*

### Step 6.2 — Seed Development Staff/Admin Accounts (Optional)
To create provisional `staff` and `admin` accounts for role verification (refuses execution in production):
```bash
python -m app.scripts.seed_dev_users
```
Default development credentials:
- **Admin**: `admin@campus.edu` / `AdminSecret123!`
- **Staff (IT Services)**: `staff.it@campus.edu` / `StaffSecret123!`

---

## 7. Running the Development Server

Start the FastAPI application with auto-reload:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The server will be available at:
- **API Base URL**: [http://localhost:8000](http://localhost:8000)
- **Interactive Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs) (configurable via `ENABLE_API_DOCS`)
- **ReDoc Documentation**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **OpenAPI JSON Schema**: [http://localhost:8000/openapi.json](http://localhost:8000/openapi.json)
- **Health Check**: [http://localhost:8000/health](http://localhost:8000/health)

---

## 8. Hardened Security & Architecture Details

1. **Authentication & JWT**:
   - Access tokens contain minimized claims: `sub`, `iat`, `exp`, and `role`.
   - Authoritative user identity and role are re-verified from the database on every protected request.
   - Defense-in-depth: bcrypt 72 UTF-8 byte boundary strictly enforced; passwords >72 bytes rejected safely without silent truncation.
   - Pre-auth password policy leaks removed from `LoginRequest` (bounds: 1–256 characters); invalid login responses return identical generic 401.
   - Module-level dummy bcrypt hash eliminates account enumeration timing differences for unknown emails.
   - Logout is client-side removal of the Bearer token (stateless JWT; no server-side token revocation).
2. **Google OpenID Connect (OIDC) & PKCE**:
   - Full Authorization Code flow with PKCE S256 (`code_challenge` / `code_verifier`).
   - Server-side transaction state table (`oauth_transactions`) with cryptographically hashed state tokens and encrypted PKCE secrets (`GOOGLE_OAUTH_ENCRYPTION_KEY` using Fernet).
   - Single-use, short-lived handoff tickets (`oauth_handoff_tickets`) exchanged with client PKCE verifier proof.
   - Google ID token validation: strict issuer check (`accounts.google.com`), audience/azp verification against `GOOGLE_OAUTH_CLIENT_ID`, expiration/iat checks, nonce match, and strict Boolean `email_verified: true`.
   - Domain restriction: Configurable Google Workspace `hd` claim enforcement (`GOOGLE_ALLOWED_HOSTED_DOMAINS`).
   - Account collision safety: Existing password users are never automatically linked by email alone. A clear 409 conflict requires standard password login.
   - Hardened minimal callback HTML with strict CSP, `no-referrer`, `no-store`, and exact `window.opener.postMessage(payload, exactTargetOrigin)` communication.
3. **In-Process Rate Limiting**:
   - Sliding-window rate limiter protects `/api/v1/auth/login`, `/api/v1/auth/register`, and `/api/v1/auth/google/start`.
   - Exceeding the threshold returns HTTP 429 with `Retry-After` header.
4. **Log Sanitization & Reverse Proxy Precautions**:
   - `SensitiveQueryFilter` strips and redacts `code=` and `state=` query strings from application and uvicorn access logs.
   - **Production Reverse Proxy Note**: External proxies (Render, Cloudflare, Nginx, AWS ALB) must be configured to omit query strings from access logs on OAuth callback paths (`/api/v1/auth/google/callback`).

---

## 9. Google Cloud Console Configuration Guide

To enable Google Sign-In:

1. **Create/Select Project**: In the [Google Cloud Console](https://console.cloud.google.com/), select or create a project.
2. **Configure OAuth Consent Screen**:
   - User Type: **External** (or Internal for Google Workspace domain).
   - App Name: `Campus Complaint Management System (CCMS)`.
   - User support email: Enter admin email.
   - Scopes: Request `openid`, `email`, and `profile`.
   - Test Users: If in "Testing" mode, add all developer/tester Google emails.
3. **Create OAuth Client ID**:
   - Navigate to **Credentials** → **Create Credentials** → **OAuth client ID**.
   - Application Type: **Web application**.
   - **Authorized JavaScript origins**:
     - `http://localhost:5173`
     - `http://localhost:3000`
     - `https://your-production-domain.com` (Production)
   - **Authorized redirect URIs**:
     - `http://localhost:8000/api/v1/auth/google/callback` (Local Development)
     - `https://your-api-domain.com/api/v1/auth/google/callback` (Production)
4. **Generate Server Encryption Key**:
   Generate an independent 32-byte URL-safe base64 key for encrypting transient PKCE verifiers:
   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```
5. **Configure Environment Variables**:
   ```ini
   GOOGLE_AUTH_ENABLED=True
   GOOGLE_OAUTH_CLIENT_ID=your-client-id.apps.googleusercontent.com
   GOOGLE_OAUTH_CLIENT_SECRET=your-client-secret
   GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8000/api/v1/auth/google/callback
   GOOGLE_ALLOWED_HOSTED_DOMAINS=campus.edu,dau.ac.in
   GOOGLE_OAUTH_ENCRYPTION_KEY=your-generated-fernet-key
   ```
   *Note: If `GOOGLE_ALLOWED_HOSTED_DOMAINS` is left empty, any verified Google email will be accepted.*

---

## 10. Supabase & PostgreSQL Deployment Guide

### Connection Pooler Modes
Supabase provides three connection methods via its Connection Settings:
1. **Direct Connection** (`port 5432`):
   - Direct connection to PostgreSQL engine. Requires direct IPv4 routing or dual-stack support.
   - URL: `postgresql+psycopg://postgres:[PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres?sslmode=require`
2. **Session Pooler** (`port 5432` via Supavisor / PgBouncer):
   - Persistent per-worker pool suitable for FastAPI long-running processes. Supports prepared statements.
   - URL: `postgresql+psycopg://postgres.[PROJECT-REF]:[PASSWORD]@aws-0-[REGION].pooler.supabase.com:5432/postgres?sslmode=require`
3. **Transaction Pooler** (`port 6543` via Supavisor):
   - Best for serverless functions (AWS Lambda). Reallocates connections per transaction.
   - **Important**: Transaction pooling does NOT support prepared statements. If used with Psycopg 3, set `prepare_threshold=None` in engine connect args.

### Production TLS Enforcement
When `ENVIRONMENT=production`, the CCMS configuration validator strictly enforces `sslmode=require` (or `verify-ca` / `verify-full`) in `DATABASE_URL`. Connections without explicit TLS will fail to start.

### Preventing Supabase Data API (PostgREST) Bypass
CCMS handles authentication and role authorization entirely within FastAPI application logic. By default, Supabase exposes tables in schema `public` via its built-in PostgREST API (REST and GraphQL endpoints).
To prevent unauthorized read/write access via the Supabase Data API:
1. **Option A (Recommended)**: Revoke default permissions from PostgREST roles:
   ```sql
   REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon, authenticated;
   ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM anon, authenticated;
   ```
2. **Option B (Schema Isolation)**: Move application tables to a dedicated unexposed schema (e.g. `ccms`) not listed in Supabase `db_schemas`.

---

## 11. Alembic Migration Compatibility & Rollback

### Migration Revision History
- `0001_initial_sprint1_schema`: Initial schema for users, departments, and complaints.
- `0002_history_idx_role_check` (formerly `0002_history_index_and_role_check`): Added composite index and role CHECK constraint.
- `0003_google_oauth_and_email_verification`: Made `password_hash` nullable, added `email_verified` and `email_verified_at`, and created `user_external_identities`, `oauth_transactions`, and `oauth_handoff_tickets` tables.

### 32-Character Alembic Version Column Compatibility
The original revision `0002_history_index_and_role_check` (33 characters) exceeds PostgreSQL's default 32-character `alembic_version.version_num` column.
The CCMS migration engine automatically reconciles this in `backend/alembic/env.py`:
- Checks and widens `alembic_version.version_num` to `VARCHAR(64)` on PostgreSQL if needed.
- Transparently reconciles any database stamped with the legacy 33-char identifier to the canonical `0002_history_idx_role_check`.
- Fully supports fresh databases, databases at `0001`, and databases stamped with either `0002` variation.

### Commands
```bash
alembic current
alembic heads
alembic upgrade head
```

### Rollback Limitations
Alembic downgrade (`alembic downgrade -1`) safely drops OAuth tables and restores non-nullable `password_hash`. However, downgrading will fail if Google-only users (with `password_hash IS NULL`) exist in the database, preventing accidental corruption or deletion of real user accounts.

---

## 12. OAuth State Pruning Utility

OAuth transactions expire in 10 minutes, and handoff tickets expire in 60 seconds. To prune expired records periodically:
```bash
python -m app.scripts.cleanup_oauth_state
```
Recommended crontab configuration (every 15 minutes):
```cron
*/15 * * * * cd /path/to/ccms/backend && .venv/bin/python -m app.scripts.cleanup_oauth_state >> /var/log/ccms_cleanup.log 2>&1
```

---

## 13. Running Automated Tests

Run the test suite using `pytest`:
```bash
pytest -q
```
Current test execution status:
- **101 passed, 1 skipped** (PostgreSQL-specific concurrency safeguard skipped unless `TEST_POSTGRESQL_URL` is set).
- To run with local PostgreSQL container:
  ```bash
  TEST_POSTGRESQL_URL=postgresql+psycopg://postgres:postgres@localhost:5432/ccms_test pytest -v
  ```

---

## 14. Troubleshooting & FAQ

| Problem | Cause | Solution |
| :--- | :--- | :--- |
| `psycopg.OperationalError: connection failed` | PostgreSQL is not running or incorrect credentials | Ensure Docker container is running (`docker compose ps`) or verify PostgreSQL service is active on `localhost:5432`. |
| `ModuleNotFoundError: No module named 'app'` | `PYTHONPATH` does not include `backend/` | Ensure commands are run from the `backend/` directory or run scripts with `python -m app.scripts.<script_name>`. |
| `CORS Error in Browser` | Frontend origin is missing from `CORS_ORIGINS` | Add your frontend port (e.g. `http://localhost:5173`) to `CORS_ORIGINS` in `backend/.env` and restart uvicorn. |
| `Google Sign-in returns 403 Origin Not Permitted` | Browser Origin header does not match CORS origins | Ensure initiating URL origin is listed in `CORS_ORIGINS`. |
| `Google Sign-in returns 409 Account Link Required` | User previously registered with password | Direct user to standard email/password login. Future releases will support authenticated OAuth linking. |
| `401 Unauthorized` | Missing or expired Bearer token | Include header `Authorization: Bearer <your_access_token>`. |
| `429 Too Many Requests` | Exceeded rate limit on login/register | Wait for the duration specified in the `Retry-After` response header. |




## Sprint 2 email verification addition

`POST /api/v1/auth/register` now creates a non-logged-in, unverified student and
sends a verification link. `POST /api/v1/auth/verify-email` with `{ "token": "..." }`
verifies ownership and `POST /api/v1/auth/resend-verification` with
`{ "email": "..." }` resends a fresh one-use link. New password accounts cannot
log in until verified. Existing users are grandfathered by migration 0005;
no preexisting user is automatically falsely marked verified.

Set `EMAIL_PROVIDER=resend` with `RESEND_API_KEY` and a verified sender domain,
or set `EMAIL_PROVIDER=smtp` with local Mailpit/Mailtrap. Copy the new lines from
`backend/.env.example`. See root `MERGE_NOTES.md`.
