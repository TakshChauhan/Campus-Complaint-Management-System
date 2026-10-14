# CCMS Frontend

The CCMS frontend is where students interact with the complaint system. It uses **React, TypeScript and Vite** to provide the login and registration screens, complaint forms, submission receipts and personal complaint history. Rather than storing complaints in the browser, it calls the FastAPI backend and displays the responses.

This README describes the Sprint 1 frontend now merged into `main`. Run the build and browser tests to verify the integrated application.

## What is in the source

- Authentication UI with student registration and email/password login.
- Google Sign-In UI and popup/handoff support, subject to backend configuration.
- A shared API client that attaches Bearer tokens and interprets validation errors.
- Complaint submission form, active department picker and optional advisory suggestion.
- Complaint receipt with reference ID and submission details.
- A personal complaint-history list with refresh and empty/error states.
- Existing simulated tests for parts of the Google OAuth/PKCE flow.

The source does not establish a full staff complaint-resolution or admin management workflow for Sprint 1.

## Folder guide

```text
frontend/
├── src/
│   ├── api/                HTTP client and auth, department, complaint requests
│   ├── components/         Auth page, complaint form, receipt and history list
│   ├── context/            Authentication state and Google popup flow
│   ├── utils/              PKCE and supporting utilities
│   ├── types.ts            TypeScript API response/request types
│   └── main.tsx            Browser entry point
├── tests/                  Frontend authentication-flow tests
├── package.json            Development scripts and dependencies
├── package-lock.json       Locked npm dependencies
└── vite.config.ts          Vite local dev server settings
```

## Getting started

Install a current Node.js LTS release and `npm`, then open a terminal in `frontend/`:

```bash
npm ci
npm run dev
```

The configured Vite port is `5173`: [http://localhost:5173](http://localhost:5173).

To point React at your local FastAPI server, create `frontend/.env` on your machine (do not commit it):

```dotenv
VITE_API_BASE_URL=http://localhost:8000
VITE_GOOGLE_AUTH_ENABLED=false
```

These variables are read by Vite at build/dev time. **They are not a place for secrets.** Google OAuth client secrets and PostgreSQL/Supabase database credentials belong only in secure backend configuration. `VITE_GOOGLE_AUTH_ENABLED=false` hides the Google button until the backend is configured for that flow.

Start the backend separately at `http://localhost:8000` and make sure its `CORS_ORIGINS` includes `http://localhost:5173`.

### Current integration caveat

At the revision reviewed, `src/main.tsx` imports `./App` and `./index.css`, but those two files were not present in `frontend-v2/integration`. If you see an unresolved import or missing-file error, **check that the final frontend integration PR has been merged** rather than assuming `npm` is broken.

## How the frontend talks to the backend

| UI action | Backend endpoint |
| --- | --- |
| Student registers | `POST /api/v1/auth/register` |
| User logs in | `POST /api/v1/auth/login` |
| Google login starts/exchanges ticket | `POST /api/v1/auth/google/start`, `POST /api/v1/auth/google/exchange` |
| Load profile | `GET /api/v1/users/me` |
| Populate departments | `GET /api/v1/departments` |
| Suggest a department | `POST /api/v1/departments/suggest` |
| Submit complaint | `POST /api/v1/complaints` |
| View submitted complaints | `GET /api/v1/complaints/mine` |

The suggestion endpoint is a **keyword heuristic** in Sprint 1, not an ML model. It is advisory; users may choose a different department. Department IDs must be loaded from the API rather than hardcoded into React.

The API client stores the JWT in browser `localStorage` in the current source. This works for the local development workflow, but a security review should consider the risks of token theft through client-side script injection. Do not render complaint text using unsafe raw HTML.

## Build and tests

From `frontend/`:

```bash
npm ci
npm test
npm run build
```

The existing `npm test` script uses Node's test runner with `tests/auth_flow.test.mjs`. Those checks simulate aspects of PKCE and popup message validation; they **do not prove** that a real Google account can sign in or that the complete UI works against FastAPI. Verify end-to-end registration, login, complaint submission and history in the browser once all members' changes are combined.

## Sprint 1 ownership and integration

The frontend was integrated through PRs #14, #17 and #20, followed by the final merge into `main` through PR #23.

For shared API contracts and expected error handling, see [`docs/FRONTEND_HANDOFF.md`](../docs/FRONTEND_HANDOFF.md). For backend setup, see [`backend/README.md`](../backend/README.md).
