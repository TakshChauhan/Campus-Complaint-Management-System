# CCMS Backend

The backend is the part of CCMS that decides who can sign in, what each user is allowed to do, and how complaints are saved and retrieved. It is written in **Python with FastAPI**, uses **SQLAlchemy** for database access and **Alembic** to keep the database schema in step with the source code.

This guide describes the Sprint 1 backend now merged into `main`. The application is run locally; the API is not publicly deployed.

## What is implemented

- Student account registration and email/password login.
- JWT bearer authentication and role checks for students, staff and administrators.
- Optional Google Sign-In using OAuth 2.0/OpenID Connect, PKCE and single-use handoff tickets.
- Active campus department listing.
- Student complaint submission and student-only complaint history (`limit` and `offset` pagination).
- Department suggestions using a **keyword-based advisory heuristic**.
- SQLAlchemy models, transaction/session handling, database constraints and Alembic migrations.
- Automated tests covering authentication, database, complaint and department behavior.

Staff and administrator accounts exist, but staff complaint assignment, resolution and status updates are not implemented in this Sprint 1 API. A trained ML classifier is not called by the current suggestion service.

## Project layout

```text
backend/
├── app/
│   ├── api/v1/endpoints/   Auth, users, departments and complaint routes
│   ├── core/               Settings, JWT/password security and rate limiting
│   ├── db/                 SQLAlchemy base, engine and session dependency
│   ├── dependencies/       Logged-in user and role checks
│   ├── models/             User, Department, Complaint and OAuth tables
│   ├── schemas/            Pydantic request and response types
│   ├── services/           Authentication, complaints and suggestion logic
│   ├── scripts/            Local development seeding and OAuth cleanup
│   └── main.py             FastAPI application and health endpoint
├── alembic/                Database migration environment and revisions
├── tests/                  pytest suite
├── .env.example            Safe example local configuration
├── requirements.txt        Python dependencies
└── README.md
```

## Quick start: local SQLite

**Requirements:** Python 3.12, `pip`, Git. You don't need Docker or a Supabase account for this setup.

On macOS/Linux, from the `backend/` directory:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python -m alembic upgrade head
python -m app.scripts.seed_departments
python -m uvicorn app.main:app --reload --port 8000
```

On Windows PowerShell, from `backend/`:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -m alembic upgrade head
python -m app.scripts.seed_departments
python -m uvicorn app.main:app --reload --port 8000
```

`backend/.env.example` defaults to `DATABASE_URL=sqlite:///./ccms.db`, so this creates a local database in your working directory. Keep `.env` out of Git.

Open [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) for the development API explorer. The health endpoint, [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health), reports whether the service can reach its configured database; it may report `degraded` if it cannot.

### Optional local development accounts

After seeding departments, you can create example staff and admin users **only in your disposable development database**:

```bash
python -m app.scripts.seed_dev_users
```

The script uses configurable `DEV_ADMIN_*` and `DEV_STAFF_*` settings. The example configuration includes demonstration passwords—change them for any non-disposable environment, and never put seeded test credentials into a shared or production database.

## PostgreSQL and Supabase

PostgreSQL is the intended relational database for CCMS, and **Supabase can provide a hosted PostgreSQL instance**. FastAPI still owns the API, authentication, validation and authorization; the React frontend must not connect directly to PostgreSQL.

To use a PostgreSQL database, set `DATABASE_URL` privately in `backend/.env` to the connection string supplied by your database administrator. The application uses the **Psycopg 3** driver (`postgresql+psycopg://...`) and SQLAlchemy engine/session handling. For Supabase transaction-pooler connections, the session module contains compatibility handling that disables Psycopg prepared statements where appropriate.

Example *format only* (not real credentials):

```dotenv
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/DBNAME?sslmode=require
```

Run migrations only on a database you control and have permission to modify:

```bash
python -m alembic current
python -m alembic upgrade head
```

**Supabase verification:** On 15 October 2026, a local FastAPI development environment successfully connected to Supabase PostgreSQL, applied all four Alembic migrations and seeded seven departments. This does not mean the FastAPI application is publicly deployed.

## Data model and migrations

The schema defines the main `users`, `departments` and `complaints` tables, plus tables for Google OAuth identities, transactions and handoff tickets. Alembic tracks applied schema revisions in `alembic_version`.

| Migration | Purpose |
| --- | --- |
| `0001_initial_sprint1_schema.py` | Initial user, department and complaint tables |
| `0002_add_history_index_and_role_check.py` | Complaint-history query index and user-role constraint |
| `0003_google_oauth_and_email_verification.py` | Verified-email fields and OAuth support tables |
| `0004_restrict_complaint_delete.py` | Restricts deleting a user when complaint records depend on them |

Migrations are designed to preserve relationships and prevent inconsistent data. Avoid downgrading a database that contains data you want to keep; schema rollbacks can be destructive or fail because of newer records.

## API overview

All application routes below use `/api/v1`:

| Method | Path | Access |
| --- | --- | --- |
| `POST` | `/auth/register` | Public student registration |
| `POST` | `/auth/login` | Public login |
| `POST` | `/auth/google/start` | Optional Google sign-in initiation |
| `GET` | `/auth/google/callback` | Google redirect callback |
| `POST` | `/auth/google/exchange` | Optional Google handoff-ticket exchange |
| `GET` | `/users/me` | Authenticated user |
| `GET` | `/departments` | Authenticated user |
| `POST` | `/departments/suggest` | Student; advisory heuristic |
| `POST` | `/complaints` | Student only |
| `GET` | `/complaints/mine` | Student only |

The complaint router also includes `POST /api/v1/complaints/suggest`. The unversioned `GET /health` is used for health reporting. Full examples are in [`docs/API_CONTRACT.md`](../docs/API_CONTRACT.md).

When students submit complaints, the service checks the department, associates the complaint with the logged-in student and creates an initial `submitted` record. Only the submitting student can retrieve that history through `/complaints/mine`.

## Authentication notes

Email/password authentication uses bcrypt for password hashing and signed JWT access tokens. Protected requests look up the user and current role from the database. The backend also applies rate limits to selected authentication routes.

Google Sign-In is **disabled by default**. Enabling it requires a properly configured Google OAuth application, callback URL, encryption key and allowed origins. The frontend uses the Google handoff-ticket flow; never expose Google client secrets or a Supabase database password in the frontend.

## Testing

From `backend/`, with the Python environment active:

```bash
python -m pytest -q
```

To focus on the database:

```bash
python -m pytest tests/test_database_integrity.py tests/test_migration.py -q
```

A previous assembled backend snapshot reported **128 passing tests and one skipped** on 13 October 2026. That is historical context, **not a verified test result for the latest integrated revision**. Run the full suite again and put the actual results in the final PR.

## Common problems

| Issue | What to check |
| --- | --- |
| `ModuleNotFoundError: app` | Run commands inside the `backend/` folder with the virtual environment active |
| Database connection error | Confirm `DATABASE_URL`, credentials and database availability; use SQLite for a simple local start |
| CORS error from React | Add the actual Vite origin to `CORS_ORIGINS` in your local `.env` |
| Google Sign-In unavailable | Confirm backend `GOOGLE_AUTH_ENABLED`, OAuth credentials and matching frontend flag |
| `401` or `403` | Check Bearer token, current role and whether the account is active |
| Migrations fail | Check the current revision and use a disposable test database before attempting recovery |

## Sprint 1 contributions

The final backend was assembled through [Taksh's database PR #9](https://github.com/TakshChauhan/Campus-Complaint-Management-System/pull/9), [Dhaval's authentication PR #11](https://github.com/TakshChauhan/Campus-Complaint-Management-System/pull/11) and [Yashvi's complaint/API PR #18](https://github.com/TakshChauhan/Campus-Complaint-Management-System/pull/18), merged into `backend-v2/integration`. These V2 commits include imports from a shared earlier backend baseline; subsequent changes and original authorship should be interpreted from the actual source and PR history.

See the [main README](../README.md) for project context and the [contribution guide](../CONTRIBUTING.md) for the Git workflow.
