# Member 2: Authentication PR — Review and test before committing

This overlay was prepared on top of the **existing authentication code** in
`backend/sprint1-integration` after Member 1's PR #6 was merged.

Repository: https://github.com/TakshChauhan/Campus-Complaint-Management-System
Base branch HEAD when prepared: `546f39096a575ee4b0d3e183088c5dc74397d6fb`

## Included changes

- `backend/app/core/rate_limit.py`: make the existing single-process
  in-memory authentication rate limiter atomic across FastAPI worker threads.
- `backend/tests/test_auth_member2.py`: tests for concurrent limiter access,
  per-IP limits, register-without-auto-login contract, and Google-only
  accounts refusing password login.

No changes to database models, migrations, Supabase connection files,
frontend files, or cloud deployments.

## Workflow

1. Clone the actual repository, fetch and check out `backend/sprint1-integration`.
2. Create `backend/auth` **from this branch**.
3. Extract this ZIP *into the repository root*, not inside `backend/`.
4. Review `git diff -- backend/app/core/rate_limit.py` and the added test file.
5. Run tests using Python 3.12/3.13 from `backend/`:
   `python -m pytest tests/test_auth_member2.py tests/test_auth.py tests/test_google_auth.py -q`
   and then `python -m pytest -q`.
6. Stage **only the intended changed paths**, verify secrets are absent, commit,
   push `backend/auth`, and open PR targeting `backend/sprint1-integration`.

These changes are a proposed starting contribution, **not a claim that Member 2
already implemented or verified them**. Member 2 must review and test them, and
may amend them before committing. Don't claim live Google OAuth testing based
on mocked tests.

Known functional gap: password registration sets `email_verified=False`, but
there is not yet a live email-verification delivery flow. Decide this policy
with the backend team before restricting login or claiming verified accounts.

The rate limiter remains in-memory and per process: it is not distributed
across workers/servers. Edge or shared-store limits are needed at scale.
