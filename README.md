# Campus Complaint Management System (CCMS)

CCMS is our B.Tech Software Engineering course project (IT314) at DAU (formerly DA-IICT).

On campus, students often report issues such as Wi-Fi problems, water supply, hostel maintenance and library facilities through different channels. It becomes difficult to know whom to contact, whether someone has already reported the issue and what its current status is.

We built CCMS to bring this process into one platform where students can raise and track complaints, staff can work on issues within their department, and administrators can monitor the overall complaint resolution process.

## Current progress

**Sprint 5 is in progress (28 November 2026).** The features below are based on the integrated source code on `main` as of commit `5594351`. Work that is still under review is listed separately.

- **Student:** Register using a university email, verify the account, log in, raise complaints, get department and duplicate suggestions, track status history, reopen resolved complaints when eligible, declare hostel residence and browse permitted public feeds.
- **Staff:** View complaints in the assigned department, update complaint status with remarks and view complaint details. Hostel staff can handle complaints and verify residence declarations within their assigned hostels.
- **Admin:** View complaint counts and resolution metrics, manage staff–hostel assignments and identify hostels that have open complaints but no assigned staff.

### Features we have implemented

| Feature | Description |
| --- | --- |
| Authentication | Email verification, password-based login, JWT authentication and optional Google Sign-In |
| Complaint lifecycle | Submitted, in progress, resolved and reopened states with validated transitions and status history |
| Department suggestion | Keyword-based recommendation; the student makes the final choice |
| Duplicate detection | TF-IDF and cosine similarity to suggest similar existing complaints before submission |
| Hostel locations | Structured hostel, wing and floor information, with student residence verification |
| Privacy and access control | Role-based and hostel-scoped permissions, private complaints and controlled public feed visibility |
| Campus feed | Browse published complaints with department, status and location-related filters as permitted |
| Admin dashboard | Complaint statistics, resolution metrics, staff–hostel assignments and coverage gaps |

A student can still submit a complaint even if a duplicate suggestion is shown. The system does not automatically merge complaints or treat a similarity score as proof that two issues are the same.

## Sprint-wise development

| Sprint | Main work |
| --- | --- |
| Sprint 1 | Project requirements, user stories, initial UML diagrams, database setup, authentication and student complaint submission |
| Sprint 2 | Email verification, staff complaint handling, status history, reopening rules and the foundation for duplicate detection and analytics |
| Sprint 3 | Hostel location hierarchy, residence verification, hostel-aware public feeds and duplicate matching; remaining Sprint 2 work was also integrated |
| Sprint 4 | Hostel-scoped staff access, staff assignment, admin coverage gaps, feed improvements, duplicate detector evaluation and user documentation |
| Sprint 5 | Database migrations for comments, feedback and password resets, deployment preparation, integration, testing and final documentation |

Some planned tasks were completed in later sprints. See the [sprint planning documents](docs/sprint-planning/) for detailed backlogs, delivered work and review notes.

### Sprint 5 work under review

The following features and deliverables are not yet fully integrated on `main`:

- Complaint comments: backend [#115](../../pull/115) and frontend [#123](../../pull/123).
- Resolution feedback: student UI [#119](../../pull/119) and admin rating summary [#116](../../pull/116); the student feedback API still needs to be integrated.
- Forgot, reset and change password: [#117](../../pull/117).
- System and object design diagrams: [#109](../../pull/109).
- User manual updates: [#118](../../pull/118) and [#125](../../pull/125).
- Playwright GUI tests: [#121](../../pull/121) and [#124](../../pull/124).
- Locust performance tests and reliability report: [#122](../../pull/122).

The database schema for comments, feedback and password reset tokens was added in [#110](../../pull/110). Having these tables does not mean the complete user-facing features are available yet.

## Technology stack

| Part | Technology |
| --- | --- |
| Frontend | React, TypeScript, Vite, CSS |
| Backend | Python, FastAPI, Pydantic |
| Database | PostgreSQL (Supabase), SQLite for local development |
| ORM and migrations | SQLAlchemy, Alembic, Psycopg 3 |
| Authentication | JWT, bcrypt, Google OAuth 2.0 / OpenID Connect |
| Email | Resend or SMTP |
| Text similarity | scikit-learn, TF-IDF, cosine similarity |
| Testing | pytest, Vitest, React Testing Library |
| Deployment | Vercel (frontend), Render (backend), Supabase (database) |
| Version control and CI | GitHub, GitHub Actions |

## How the system works

```text
Student / Staff / Admin
          |
          v
    React frontend
          | HTTP / JSON
          v
     FastAPI backend
          |
    Services and access checks
          |
    SQLAlchemy / PostgreSQL
```

The frontend communicates with the backend through REST APIs. The backend handles validation, authentication, permissions, complaint processing and database access. Email delivery and Google authentication are handled through their respective services.

## Duplicate detection

We use TF-IDF to represent complaint titles and descriptions as vectors and cosine similarity to find related complaints. The current threshold is `0.375`. The candidate complaints are filtered according to the student's access permissions before matching.

We evaluated the approach on labelled complaint pairs and a separate hold-out dataset. The method has limitations, especially when the same issue is described using very different words. Our department suggestion is keyword-based, not a trained classification model.

See the [ML documentation](ml/README.md) for the dataset, evaluation method, results and limitations.

## Repository structure

```text
Campus-Complaint-Management-System/
├── backend/           API, services, database models, migrations and tests
├── frontend/          React application, API clients and tests
├── ml/                Complaint datasets and evaluation scripts
├── docs/              API contract, sprint details, UML and user manual
├── Documents/         Requirements, stakeholder analysis and user stories
├── .github/workflows/ CI and deployment recording
├── CONTRIBUTING.md
└── README.md
```

## Running locally

### Prerequisites

- Python 3.12
- Node.js 20.19+ (a current supported LTS version is recommended) and npm
- Git
- PostgreSQL is optional for local development; the example backend configuration uses SQLite.

Clone the repository:

```bash
git clone https://github.com/TakshChauhan/Campus-Complaint-Management-System.git
cd Campus-Complaint-Management-System
```

### 1. Backend

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

On Windows PowerShell, use `py -3.12 -m venv .venv`, `.\.venv\Scripts\Activate.ps1` and `Copy-Item .env.example .env` instead.

Review `backend/.env` before starting. The default email provider requires configuration. For real email verification, configure Resend with an appropriate sending domain or SMTP. For local email testing, SMTP with Mailpit is an option. Keep Google Sign-In disabled unless the OAuth credentials and callback URL are configured.

```bash
python -m alembic upgrade head
python -m app.scripts.seed_departments
python -m uvicorn app.main:app --reload --port 8000
```

For local development only, the optional `python -m app.scripts.seed_dev_users` command creates demo accounts using the development configuration. Never enable demo seeding in a production environment.

### 2. Frontend

Open another terminal from the repository root:

```bash
cd frontend
npm ci
cp .env.example .env
npm run dev
```

Check that `frontend/.env` contains:

```dotenv
VITE_API_BASE_URL=http://localhost:8000
VITE_GOOGLE_AUTH_ENABLED=false
```

Make sure the frontend origin is included in the backend's `CORS_ORIGINS`.

| Service | Local URL |
| --- | --- |
| Frontend | http://localhost:5173 |
| Backend | http://localhost:8000 |
| API documentation | http://localhost:8000/docs |
| Health check | http://localhost:8000/health |
| Database readiness | http://localhost:8000/health/ready |

Never commit real `.env` files, API keys, OAuth secrets or database credentials.

## Testing

Backend tests:

```bash
cd backend
source .venv/bin/activate
python -m pytest -q
```

Frontend tests and build:

```bash
cd frontend
npm ci
npm test
npm run build
```

GitHub Actions runs the backend and frontend checks, including PostgreSQL migration and concurrency testing on the backend. Our tests cover authentication, complaint lifecycle, access control, public feed privacy, hostel assignments and other implemented features.

GUI and load testing are under review as part of Sprint 5. Final coverage, mutation testing and non-functional testing reports are still to be completed. We will record actual results rather than assume that passing CI means every requirement has been tested.

## Deployment

We are using Vercel for the frontend, Render for the backend and Supabase for PostgreSQL.

- [Frontend deployment](https://campus-complaint-management-system-gamma.vercel.app/login)
- [Staging API readiness](https://ccms-staging-api.onrender.com/health/ready)

These are development/staging deployment links. Final deployment verification is part of Sprint 5; the live version may not contain every feature listed as under review.

## Project documents

- [Requirements, epics, stakeholder analysis and user stories](Documents/)
- [UML diagrams](docs/architecture/uml/)
- [Sprint 2](docs/sprint-planning/sprint2.md), [Sprint 3](docs/sprint-planning/sprint3.md) and [Sprint 4](docs/sprint-planning/sprint4.md)
- [API contract](docs/API_CONTRACT.md)
- [User manual](docs/user-manual.md)
- [ML evaluation](ml/README.md)
- [Contribution and Git workflow](CONTRIBUTING.md)

## Team and contributions

We divided work across backend, frontend, database, ML, testing and documentation. Team members develop on separate branches and submit pull requests for review and integration.

Our initial Sprint 1 contributions are recorded in PRs [#9](../../pull/9), [#11](../../pull/11), [#12](../../pull/12), [#14](../../pull/14), [#15](../../pull/15), [#16](../../pull/16), [#17](../../pull/17), [#18](../../pull/18) and [#20](../../pull/20). The integration PRs are [#19](../../pull/19), [#21](../../pull/21), [#23](../../pull/23) and [#24](../../pull/24). Later contributions and task handovers are recorded in the sprint documents and the [pull request history](../../pulls?q=is%3Apr).

We use GitHub for version control and code reviews, and Slack for team communication. Individual contributions for the final evaluation will be based on the actual work delivered and supporting evidence, not just the original task assignments.

## Pending work and future scope

Our immediate focus is to complete Sprint 5 integration, testing, final design documents and deployment verification.

Possible future improvements include linking related complaints into common incidents, prioritising issues based on impact and waiting time, recurring-problem detection and proactive notifications. These are proposed features, not part of the currently integrated application.

---

Developed as part of IT314 – Software Engineering, DAU, Autumn 2026.
