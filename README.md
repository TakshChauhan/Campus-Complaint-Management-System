# Campus Complaint Management System (CCMS)

A campus complaint management project for students, staff and administrators at DAU / DA-IICT. CCMS brings common campus issues—hostel maintenance, internet connectivity, library facilities, dining, sports and similar concerns—into one place, instead of leaving students to find the right contact or follow up across different channels.

This repository contains the work prepared for **Sprint 1** of our Software Engineering project. It includes a FastAPI backend, a React frontend being assembled by the UI team, and datasets and UML documentation prepared by the ML/documentation team.

## What we are building

The student-facing flow is straightforward: sign in, describe an issue, choose a department, submit a complaint and view its status later. The backend stores complaints with an owner, department, creation time and an initial status. Students may ask for a suggested department, but the final selection remains theirs.

CCMS also defines staff and administrator accounts. The current Sprint 1 API focuses on identity, basic role protection and student complaint submission; staff triage, assignment and resolution workflows belong to later work.

### Sprint 1 scope

| Area | Included in the Sprint 1 source | Important boundary |
| --- | --- | --- |
| Accounts | Student registration, password login, JWT-based sessions and current-user profile | Demo staff/admin accounts are local-development utilities |
| Google Sign-In | Backend OAuth/OIDC flow and React client support | Disabled by default; requires valid Google OAuth configuration and end-to-end testing |
| Complaints | Submit a complaint and view one's own history | Status starts at `submitted`; staff resolution workflows are not part of this API |
| Departments | Active department list and advisory suggestions | Suggestions use a **keyword heuristic**, not a trained ML model |
| Data | SQLAlchemy models, Alembic migrations and PostgreSQL/Supabase-compatible connection handling | A live Supabase connection is optional and is not proof of deployment |
| Frontend | Authentication and student-workflow components in the frontend integration branch | Final routing, styling and full build must be verified before calling the UI complete |
| ML/documentation | Complaint datasets and software design diagrams | The ML branch does not establish that a trained classifier is integrated into FastAPI |

**The project is being developed and demonstrated locally; deployment is not part of the current team handoff.**

## Technology stack

| Layer | Tools |
| --- | --- |
| Frontend | React 18, TypeScript, Vite, CSS |
| Backend | Python, FastAPI, Pydantic |
| Data | SQLAlchemy ORM, Alembic, PostgreSQL, Psycopg 3 |
| Optional hosted database | Supabase PostgreSQL |
| Local database/testing | SQLite, pytest, FastAPI TestClient |
| Authentication | JWT, bcrypt, Google OAuth 2.0 / OpenID Connect |
| Collaboration | Git, GitHub branches and pull requests |

The browser talks to FastAPI through HTTP APIs. It **does not connect directly to the Supabase database**. The backend handles identity, permissions, validation and database operations.

## Repository guide

```text
Campus-Complaint-Management-System/
├── backend/                FastAPI application, database models, migrations and tests
├── frontend/               React/TypeScript source and frontend tests
├── ml/                     Complaint datasets and ML-team materials
├── docs/                   API contracts, handoff notes and UML documentation
├── Documents/              Requirements and Software Engineering deliverables
├── README.md               Project overview and local development entry point
└── CONTRIBUTING.md         Team branching and pull-request workflow
```

Each area has its own guide: [Backend](backend/README.md), [Frontend](frontend/README.md), [ML datasets](ml/README.md) and [Documentation index](docs/README.md).

> **Repository status:** Sprint 1 work has been brought together in `backend-v2/integration`, `frontend-v2/integration` and `ml-v2/integration`. Until the final reviewed PRs are merged, `main` may still contain only the earlier project structure. Use the relevant integration branch for code that has not yet reached `main`.

## Run locally

The steps below assume the Backend and Frontend source have both been merged into your working checkout. Use **Python 3.12** and a current **Node.js LTS** release. The default backend example uses a local SQLite database; you do not need Supabase credentials to start.

### 1. Start the backend

From the repository root:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python -m alembic upgrade head
python -m app.scripts.seed_departments
python -m uvicorn app.main:app --reload --port 8000
```

On Windows PowerShell, create/activate the environment with `py -3.12 -m venv .venv` and `.\.venv\Scripts\Activate.ps1`. Copy the example with `Copy-Item .env.example .env`. See [backend setup](backend/README.md) for details.

The API runs at `http://127.0.0.1:8000`. The development API explorer is at [localhost:8000/docs](http://localhost:8000/docs), and `GET /health` checks whether the backend can access its database.

### 2. Start the frontend

Open a second terminal from the repository root:

```bash
cd frontend
npm ci
npm run dev
```

The Vite dev server uses [localhost:5173](http://localhost:5173). If necessary, create `frontend/.env` with:

```dotenv
VITE_API_BASE_URL=http://localhost:8000
VITE_GOOGLE_AUTH_ENABLED=false
```

Google Sign-In is off in this example because the backend also defaults to `GOOGLE_AUTH_ENABLED=False`. Enable both sides only after configuring Google credentials privately. **Never commit real `.env` files.**

If the UI build reports a missing `App.tsx` or `index.css`, the final frontend application-integration work has not yet reached that branch. See [Frontend README](frontend/README.md) before proceeding.

### 3. Run tests

```bash
# Inside backend/ with the virtual environment active
python -m pytest -q

# Inside frontend/
npm ci
npm test
npm run build
```

Run these commands in their respective folders. Report the output from the **current integrated revision**, rather than reusing a test count from an earlier snapshot.

## Key API routes

| Method | Route | Purpose |
| --- | --- | --- |
| `POST` | `/api/v1/auth/register` | Register a student |
| `POST` | `/api/v1/auth/login` | Sign in using email and password |
| `POST` | `/api/v1/auth/google/start` | Begin optional Google Sign-In |
| `GET` | `/api/v1/auth/google/callback` | Receive Google's OAuth callback |
| `POST` | `/api/v1/auth/google/exchange` | Exchange a single-use Google handoff ticket |
| `GET` | `/api/v1/users/me` | View the signed-in user's profile |
| `GET` | `/api/v1/departments` | List active departments |
| `POST` | `/api/v1/departments/suggest` | Get an advisory keyword-based suggestion |
| `POST` | `/api/v1/complaints` | Submit a student complaint |
| `GET` | `/api/v1/complaints/mine` | View a student's own complaint history |
| `GET` | `/health` | Check service/database health |

The complete request and response shapes are documented in [API Contract](docs/API_CONTRACT.md) and [Frontend Handoff](docs/FRONTEND_HANDOFF.md). Treat live generated OpenAPI output as authoritative if older examples differ.

## Sprint 1 team contributions

The backend work was reviewed through three member branches:

| Area | Contributor | Reviewed PR |
| --- | --- | --- |
| Database, SQLAlchemy, migrations and Supabase compatibility | [TakshChauhan](https://github.com/TakshChauhan) | [#9](https://github.com/TakshChauhan/Campus-Complaint-Management-System/pull/9) |
| Authentication, JWT and Google OAuth | [Dhaval1306](https://github.com/Dhaval1306) | [#11](https://github.com/TakshChauhan/Campus-Complaint-Management-System/pull/11) |
| Complaints, departments, suggestions and API integration | [yashvidoshi](https://github.com/yashvidoshi) | [#18](https://github.com/TakshChauhan/Campus-Complaint-Management-System/pull/18) |

Other reviewed contributions include frontend authentication [#14](https://github.com/TakshChauhan/Campus-Complaint-Management-System/pull/14), student complaint UI [#17](https://github.com/TakshChauhan/Campus-Complaint-Management-System/pull/17), and ML/documentation PRs [#12](https://github.com/TakshChauhan/Campus-Complaint-Management-System/pull/12), [#15](https://github.com/TakshChauhan/Campus-Complaint-Management-System/pull/15), and [#16](https://github.com/TakshChauhan/Campus-Complaint-Management-System/pull/16).

Some Sprint 1 modules were **imported from an earlier shared project baseline** and then split into member-owned branches for review. A Git commit or PR records who submitted that change; it does not, by itself, establish who originally authored every imported line.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the process followed by collaborators.

## Project boundaries and next steps

Sprint 1 provides the foundations for reporting and tracking complaints. Remaining or future work includes staff-side status updates and assignment, notifications, analytics, ML model training/evaluation and integration of any trained classifier. Those items should not be presented as shipped until implementation and tests support that claim.

This is an academic team project. The department catalog is provisional, and campus stakeholders should validate department ownership before relying on it operationally.
