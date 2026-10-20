# CCMS Team-Sharing Package — Read First

This is a **source-only, sanitized copy** of the uploaded `CCMS_Sprint1(1).zip` archive (internally `CCMS_Sprint2_Merged`). The application source was not redesigned or feature-modified while preparing the package. Two planning documents were added under `docs/sprint-planning/`.

## What was excluded

- All **actual** `.env` files and `.env.local` variants containing keys, passwords, database URLs or local settings.
- `.venv/`, `node_modules/`, compiled `dist/`, Python caches, test caches, local SQLite database (`ccms.db`), OS `__MACOSX/` metadata, `.DS_Store`, Git metadata and other machine-specific generated outputs.
- The original source ZIP is **not** a safe credentials backup; this ZIP is for team sharing. The missing dependencies and local secret files account for its much smaller size.

Template files `backend/.env.example` and `frontend/.env.example` are included and use example/development placeholders, **not configured keys**.

## Developer setup

1. Extract this ZIP; open `CCMS_Sprint2_Merged/`.
2. Create your own local configuration by copying **templates**:
   ```bash
   cp backend/.env.example backend/.env
   cp frontend/.env.example frontend/.env
   ```
   Fill **only your authorized local/test credentials**. Never commit those files. Production/shared Supabase credentials must not be distributed indiscriminately.
3. Backend in a new Terminal:
   ```bash
   cd backend
   python3.12 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   uvicorn app.main:app --reload --port 8000
   ```
4. Frontend in another Terminal (Node.js 20.19+):
   ```bash
   cd frontend
   npm ci
   npm run dev
   ```
5. Set `VITE_API_BASE_URL=http://localhost:8000` in the local frontend `.env`, and `GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8000/api/v1/auth/google/callback` in local backend `.env` if using Google OAuth. Values must also match authorized Google Cloud OAuth redirects. Restart servers after changing environment settings.
6. Run tests with `pytest -q` from `backend` (with test dependencies installed) and `npm test` / `npm run build` from `frontend`. Automated tests should use isolated databases/mock providers. **Do not apply live Supabase migrations without approval.**

## What exists vs needs work

The Staff/Admin pages are currently informational; functional department-specific complaint processing and Admin complaint analytics are not yet in this snapshot. Google account-linking routes and a centered login variant *are already in the source*, but their end-to-end behavior and migration state require verification. See the team's Sprint 2 work allocation (shared on Slack) for individual tasks, buddies and deadlines.

## Safety notes

- Gmail email verification succeeded in the team's earlier local manual test, but every teammate must configure their own authorized sender rather than copying someone else's SMTP password.
- Localhost verification links work only on a computer with the frontend running, not when clicked on another phone/device. Deployment needs public backend/frontend origins and delivery-provider policy review.
- Review real complaint CSV exports for privacy and permission before broad circulation/public GitHub use.
- The source ZIP and this sanitized ZIP may differ from teammates' uncommitted local work. Coordinate merges through reviewed feature branches; never overwrite other members' work.
