# CCMS Backend — Supabase & PostgreSQL Deployment Guide

This document specifies the database architecture, Supabase configuration, connection management, migration workflow, and deployment readiness for the **Campus Complaint Management System (CCMS)** backend.

---

## 1. Database Architecture & Schema Overview

CCMS uses **PostgreSQL 16** (hosted on Supabase) with **SQLAlchemy 2.0** ORM and **Alembic** migrations.

### Core Tables & Referential Integrity

| Table | Primary Key | Description | Key Foreign Keys & Constraints |
| :--- | :--- | :--- | :--- |
| `departments` | `id` (SERIAL) | Academic and administrative complaint categories | Unique `name`, indexed `is_active` |
| `users` | `id` (SERIAL) | Registered students, staff, and administrators | Unique `email`, CHECK constraint `role IN ('student', 'staff', 'admin')`, `department_id` references `departments.id (ON DELETE SET NULL)` |
| `complaints` | `id` (SERIAL) | Student grievances and issue reports | `department_id` references `departments.id (ON DELETE RESTRICT)`, `created_by_id` references `users.id (ON DELETE RESTRICT)`, composite index on `(created_by_id, created_at)` |
| `user_external_identities` | `id` (SERIAL) | Google OAuth SSO provider mappings | `user_id` references `users.id (ON DELETE CASCADE)`, unique on `(provider, provider_user_id)` |
| `oauth_transactions` | `id` (SERIAL) | PKCE state and verifier store (short-lived) | Unique `state_hash`, indexed `expires_at` |
| `oauth_handoff_tickets` | `id` (SERIAL) | Single-use tickets for secure frontend auth handoff | `user_id` references `users.id (ON DELETE CASCADE)`, unique `ticket_hash` |

### Critical Referential Integrity Rules
1. **Complaint Audit Preservation (`ON DELETE RESTRICT`)**:
   - `complaints.created_by_id` is configured with `ON DELETE RESTRICT` at the SQL level, and `cascade="all, delete-orphan"` is strictly removed from the SQLAlchemy `User.complaints` relationship.
   - Deleting a user account who has lodged complaints is rejected with an `IntegrityError`.
   - **Recommended Lifecycle**: User offboarding is handled by soft-deactivation (`user.is_active = False`). Complaint history is permanently preserved for audit and institutional compliance.
2. **Department Preservation (`ON DELETE RESTRICT`)**:
   - Departments cannot be deleted while complaints reference them. Inactive departments are marked `is_active = False` to prevent new complaint submissions while retaining historic records.
3. **Staff Department Unlink (`ON DELETE SET NULL`)**:
   - If a department is archived, staff user accounts have their `department_id` set to `NULL` without deleting the staff account.

---

## 2. Supabase Connection Modes & URL Configuration

Supabase provides three distinct connection options. CCMS natively supports all three via `psycopg` (v3).

### Mode A: Direct PostgreSQL Connection (Recommended for Migrations & Single-Server Deployments)
- **Port**: `5432`
- **Host**: `db.[PROJECT_REF].supabase.co`
- **Syntax**:
  ```text
  postgresql+psycopg://postgres:[ENCODED_PASSWORD]@db.[PROJECT_REF].supabase.co:5432/postgres?sslmode=require
  ```
- **Use Case**: Direct IPv6/IPv4 connection. Required for Alembic DDL migrations (`alembic upgrade head`) and seed operations.

### Mode B: Session Pooler (Supavisor Port 5432)
- **Port**: `5432`
- **Host**: `aws-0-[REGION].pooler.supabase.com`
- **Username**: `postgres.[PROJECT_REF]`
- **Syntax**:
  ```text
  postgresql+psycopg://postgres.[PROJECT_REF]:[ENCODED_PASSWORD]@aws-0-[REGION].pooler.supabase.com:5432/postgres?sslmode=require
  ```
- **Use Case**: Supports prepared statements and session-level features while multiplexing connections. Compatible with both migrations and web workers.

### Mode C: Transaction Pooler (Supavisor Port 6543)
- **Port**: `6543`
- **Host**: `aws-0-[REGION].pooler.supabase.com`
- **Username**: `postgres.[PROJECT_REF]`
- **Syntax**:
  ```text
  postgresql+psycopg://postgres.[PROJECT_REF]:[ENCODED_PASSWORD]@aws-0-[REGION].pooler.supabase.com:6543/postgres?sslmode=require
  ```
- **Special Handling**:
  - CCMS automatically disables prepared statements (`prepare_threshold: None`) when port `6543` or `pooler.supabase.com` is detected in `DATABASE_URL`.
  - Do NOT run schema migrations through port 6543; use direct connection (Port 5432) for migrations.

### Special Character Encoding in Passwords
If the Supabase database password contains characters such as `@`, `:`, `#`, `%`, `&`, or `?`, they must be percent-encoded:
- `@` $\rightarrow$ `%40`
- `#` $\rightarrow$ `%23`
- `:` $\rightarrow$ `%3A`
- `%` $\rightarrow$ `%25`

---

## 3. Production Environment Checklist

Before deploying the backend service, set the following environment variables in the cloud hosting provider (e.g., Render, Railway, AWS):

```dotenv
# Core
PROJECT_NAME="Campus Complaint Management System (CCMS)"
ENVIRONMENT=production
DEBUG=False
ENABLE_API_DOCS=False

# Database (Supabase PostgreSQL with TLS)
DATABASE_URL=postgresql+psycopg://postgres:[ENCODED_PASSWORD]@db.[PROJECT_REF].supabase.co:5432/postgres?sslmode=require
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=5
DB_POOL_TIMEOUT=30
DB_POOL_RECYCLE=1800

# Security
JWT_SECRET=[GENERATE_MIN_32_CHARS_VIA_SECRETS_TOKEN_URLSAFE]
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# CORS
CORS_ORIGINS=https://ccms-frontend.vercel.app

# Email Domain Whitelist
ALLOWED_EMAIL_DOMAINS=dau.ac.in,daiict.ac.in

# Google OAuth (if enabled)
GOOGLE_AUTH_ENABLED=True
GOOGLE_OAUTH_CLIENT_ID=[CLIENT_ID].apps.googleusercontent.com
GOOGLE_OAUTH_CLIENT_SECRET=[CLIENT_SECRET]
GOOGLE_OAUTH_REDIRECT_URI=https://ccms-backend.onrender.com/api/v1/auth/google/callback
GOOGLE_ALLOWED_HOSTED_DOMAINS=dau.ac.in,daiict.ac.in
GOOGLE_OAUTH_ENCRYPTION_KEY=[32_BYTE_BASE64_KEY]

# Production Safety
ALLOW_DEMO_SEEDING=False
```

---

## 4. Alembic Migration Sequence

All schema migrations are version-controlled under `backend/alembic/versions/`:

1. `0001_initial_sprint1_schema.py`
   - Creates `departments`, `users`, and `complaints` tables.
2. `0002_add_history_index_and_role_check.py`
   - Adds composite index `ix_complaints_created_by_id_created_at`.
   - Adds CHECK constraint `ck_users_role` (`role IN ('student', 'staff', 'admin')`).
3. `0003_google_oauth_and_email_verification.py`
   - Adds `email_verified` and `email_verified_at` to `users`.
   - Makes `password_hash` nullable (for OAuth accounts).
   - Creates `user_external_identities`, `oauth_transactions`, and `oauth_handoff_tickets`.
4. `0004_restrict_complaint_delete.py`
   - Enforces `ON DELETE RESTRICT` on `complaints.created_by_id`.
   - Guarantees student complaint audit trail cannot be wiped out.

### Applying Migrations to Supabase

Run the cloud migration automator using a direct connection:

```bash
cd backend
python scripts/migrate_and_seed_cloud.py --db-url "postgresql+psycopg://postgres:[PASSWORD]@db.[PROJECT_REF].supabase.co:5432/postgres?sslmode=require"
```

The script will:
1. Verify connectivity and display masked connection info.
2. Run `alembic upgrade head`.
3. Idempotently seed active campus departments (`IT Services`, `Hostel`, `Maintenance`, `Library`, etc.).
4. Safely skip demo account seeding for production environments.

---

## 5. Post-Deployment Verification

Once deployed, run the end-to-end verification script against the live URL:

```bash
cd backend
python scripts/verify_deployment.py --url https://your-backend.onrender.com
```

The script performs 10 comprehensive verification steps:
1. System health check (`GET /health`)
2. Student registration (`POST /api/v1/auth/register`)
3. Student login & JWT acquisition (`POST /api/v1/auth/login`)
4. Current profile validation (`GET /api/v1/users/me`)
5. Department catalog listing (`GET /api/v1/departments`)
6. Department advisory suggestion (`POST /api/v1/departments/suggest`)
7. Complaint registration (`POST /api/v1/complaints`)
8. Student own-history verification (`GET /api/v1/complaints/mine`)
9. Unauthorized access rejection guard (HTTP 401)
10. Data persistence check across requests
