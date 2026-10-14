# CCMS Sprint 1 — Frontend

React 18 + TypeScript + Vite frontend for the Campus Complaint Management System.

## Local setup

Run from the `frontend` directory:

```bash
npm ci
cp .env.example .env
npm run dev
```

Default backend URL: `http://localhost:8000`. The backend runs locally; no frontend deployment is planned.

## Verify

```bash
npm run build
npm test
```

Google Sign-In UI exists, but real Google OAuth requires corresponding backend configuration and credentials. The React frontend only calls FastAPI; it must **not** connect directly to Supabase PostgreSQL or contain database secrets.

The existing staff/admin dashboards are Sprint 1 informational views, **not** staff ticket resolution workflows.

The team contribution instructions are in `FRONTEND_TEAM_HANDOFF.md` at the ZIP root.
