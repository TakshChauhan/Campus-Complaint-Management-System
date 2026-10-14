# Campus Complaint Management System (CCMS)

Campus problems are often reported through different people and channels. A hostel maintenance issue, a Wi-Fi outage or a complaint about the mess can be difficult to direct to the right department, and students may have no easy way to find their earlier reports.

**CCMS is our Software Engineering project at DAU (formerly DA-IICT).** We are building a common place for students to report campus issues and keep track of what they have submitted. Our first sprint concentrates on the foundations: accounts, complaint registration, department selection, data storage and a working connection between the frontend and backend.

This repository contains work from our **backend, frontend and ML/documentation teams**. We develop and demonstrate the application locally; deploying the application is **not** part of the current Sprint 1 scope.

## What Sprint 1 covers

A student can register or sign in, describe a complaint, select an active department, submit the complaint and retrieve their own complaint history. The application records a complaint ID, submission time, department and initial `submitted` status. There is also an optional department suggestion: it looks for keywords in the complaint and proposes a likely department, but **the student always chooses where to submit**.

| Area | What is available in the Sprint 1 source | What this does not mean |
| --- | --- | --- |
| Accounts | Student registration, email/password login, JWT access tokens and current-user profile | Staff and administrator complaint-processing workflows are not implemented |
| Google Sign-In | Google OAuth/OIDC backend endpoints and supporting frontend code | Google Sign-In is disabled by default and requires credentials and real end-to-end verification |
| Complaints | Student submission and private complaint history with pagination | Assignment, resolution and status changes are later-sprint work |
| Departments | Active department catalog and keyword-based suggestions | The suggestion logic is not a trained ML model |
| Database | SQLAlchemy models, Alembic migrations, SQLite for local development and PostgreSQL/Supabase-compatible connections | A working database connector does not mean we have deployed the app |
| Frontend | Integrated React application with authentication, complaint submission, receipts and history | Real end-to-end functionality still requires verification |
| ML and design | Complaint datasets and UML diagrams | These files do not by themselves establish a trained or integrated classifier |

We have student, staff and administrator roles in the data model and authentication system. In Sprint 1, only students can submit complaints or access their own complaint history. Staff/admin dashboards and resolution operations should be treated as future work unless a later change implements and tests them.

## Technology stack

| Part | Technologies |
| --- | --- |
| Frontend | React 18, TypeScript, Vite, CSS |
| Backend | Python, FastAPI, Pydantic |
| Database layer | SQLAlchemy, Alembic, Psycopg 3 |
| Database options | Local SQLite; PostgreSQL, including Supabase-hosted PostgreSQL |
| Authentication | JWT, bcrypt, optional Google OAuth 2.0 / OpenID Connect |
| Tests | pytest for the backend; Node's built-in test runner for existing frontend authentication tests |
| Collaboration | GitHub feature branches, integration branches, reviewed pull requests |

The React frontend communicates with FastAPI over HTTP. **Only the backend talks to the database.** Do not put PostgreSQL or Supabase database passwords in browser code.

## Repository structure

```text
Campus-Complaint-Management-System/
├── backend/              FastAPI routes, services, SQLAlchemy models and tests
├── frontend/             React/TypeScript UI, API clients and tests
├── ml/                   Complaint datasets and future ML work
├── docs/                 API contracts, UML and handoff documents
├── Documents/            Requirements and other course deliverables
├── README.md             Start here
└── CONTRIBUTING.md       How our team works with Git and PRs
```

More detail is available in the [backend guide](backend/README.md), [frontend guide](frontend/README.md), [ML guide](ml/README.md) and [documentation index](docs/README.md).

> **Sprint 1 integration status (15 October 2026):** Backend, frontend, and ML contributions have been merged into `main`.

## Running CCMS locally

These commands run the complete Sprint 1 source from `main`.

### Prerequisites

- Python 3.12 and `pip`
- A current Node.js LTS release with `npm`
- Git
- Optional: access to a PostgreSQL/Supabase database. It is **not needed** for the basic local SQLite setup.

### 1. Start the backend

From the repository root, on macOS/Linux:

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python -m alembic upgrade head
python -m app.scripts.seed_departments
python -m uvicorn app.main:app --reload --port 8000
```

On Windows PowerShell, use the following commands inside `backend/`:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -m alembic upgrade head
python -m app.scripts.seed_departments
python -m uvicorn app.main:app --reload --port 8000
```

The example `.env` uses a local SQLite database. When the server starts, check [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) for the API explorer and [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health) for a database connectivity check.

### 2. Start the frontend

Open another terminal in the repository's `frontend/` folder:

```bash
npm ci
npm run dev
```

Vite uses [http://localhost:5173](http://localhost:5173) in this project. If you need to set the backend address, create a local, untracked `frontend/.env`:

```dotenv
VITE_API_BASE_URL=http://localhost:8000
VITE_GOOGLE_AUTH_ENABLED=false
```

The example disables the Google Sign-In button to match the backend's default setting. You can configure Google sign-in separately once the callback and OAuth credentials are ready. Never commit real client secrets, JWT secrets or database URLs containing passwords.

**Frontend status:** The final frontend integration has been merged. Run `npm test` and `npm run build` to verify the current checkout.

### 3. Run tests and build

From `backend/`, with your Python environment active:

```bash
python -m pytest -q
```

From `frontend/`:

```bash
npm ci
npm test
npm run build
```

The existing frontend tests exercise parts of the Google authentication/PKCE handling in a simulated environment; they are not a substitute for a browser-to-backend end-to-end test. Test counts from earlier backend snapshots should not be reused as results for the final integrated commit.

## Main API endpoints

| Method | Endpoint | What it does |
| --- | --- | --- |
| `POST` | `/api/v1/auth/register` | Register a student account |
| `POST` | `/api/v1/auth/login` | Sign in using email and password |
| `POST` | `/api/v1/auth/google/start` | Begin optional Google Sign-In |
| `GET` | `/api/v1/auth/google/callback` | Receive the Google OAuth callback |
| `POST` | `/api/v1/auth/google/exchange` | Exchange a short-lived Google handoff ticket |
| `GET` | `/api/v1/users/me` | Read the authenticated user's profile |
| `GET` | `/api/v1/departments` | List active departments |
| `POST` | `/api/v1/departments/suggest` | Get advisory keyword-based department suggestions |
| `POST` | `/api/v1/complaints` | Submit a complaint as a student |
| `GET` | `/api/v1/complaints/mine` | View your own complaint history |
| `GET` | `/health` | Check application and database connectivity |

The complaint module also contains an advisory `POST /api/v1/complaints/suggest` route. For payloads and error responses, see [API Contract](docs/API_CONTRACT.md) and the [Frontend Handoff](docs/FRONTEND_HANDOFF.md). If a written example and the currently running API differ, check the generated OpenAPI specification and the route implementation.

## Team contributions

We used separate feature branches for each member and merged their work through team integration branches. Some source was reorganized from an earlier shared Sprint 1 backend; a PR records who imported or changed files, not necessarily who originally wrote every imported line.

| Workstream | Contributor or work | PR |
| --- | --- | --- |
| Backend database, SQLAlchemy, migrations and Supabase compatibility | [TakshChauhan](https://github.com/TakshChauhan) | [#9](https://github.com/TakshChauhan/Campus-Complaint-Management-System/pull/9) |
| Backend authentication, JWT and Google OAuth | [Dhaval1306](https://github.com/Dhaval1306) | [#11](https://github.com/TakshChauhan/Campus-Complaint-Management-System/pull/11) |
| Backend complaints, departments and FastAPI integration | [yashvidoshi](https://github.com/yashvidoshi) | [#18](https://github.com/TakshChauhan/Campus-Complaint-Management-System/pull/18) |
| Frontend authentication UI | Frontend team | [#14](https://github.com/TakshChauhan/Campus-Complaint-Management-System/pull/14) |
| Frontend student complaint workflow | Frontend team | [#17](https://github.com/TakshChauhan/Campus-Complaint-Management-System/pull/17) |
| ML datasets and UML documentation | Yash, Krish and Rushil | [#12](https://github.com/TakshChauhan/Campus-Complaint-Management-System/pull/12), [#15](https://github.com/TakshChauhan/Campus-Complaint-Management-System/pull/15), [#16](https://github.com/TakshChauhan/Campus-Complaint-Management-System/pull/16) |

This table highlights merged PRs at the time of writing; it is not a claim that unmerged or planned features are complete. See the GitHub PR history for detailed authorship and review records.

## What comes after Sprint 1?

Possible next steps include staff-side complaint assignment and resolution, better tracking and notifications, analytics and evaluation of a trained complaint classifier. These are **future directions**, not features to assume are already delivered.

The initial department list is **provisional**, and any real-world use would require the university to confirm responsible departments and data-handling rules.
