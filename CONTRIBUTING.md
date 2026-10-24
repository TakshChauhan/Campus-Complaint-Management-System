# Contributing to CCMS

CCMS is a team project. Keep contributions **small, reviewable, tested where applicable, and attributable to the person who made them**. Team members with collaborator access can create branches in this repository without forking it.

This guide describes the **current Sprint 2 workflow**. The Sprint 1 integration branches remain part of the project history, but are **not the default base for new work**.

## 1. Get started

Clone once, or update an existing clone:

```bash
git clone https://github.com/TakshChauhan/Campus-Complaint-Management-System.git
cd Campus-Complaint-Management-System
git fetch origin
```

If the repository is already cloned, skip `git clone` and `cd` into that existing folder instead.

Set your own Git identity in your local clone:

```bash
git config user.name "Your Name"
git config user.email "your-github-email@example.com"
```

Use your own GitHub account and credentials, never a teammate's.

## 2. Branch from the right place (Sprint 2)

**For new Sprint 2 tasks, branch from the latest `origin/main` unless the team lead explicitly specifies a different, up-to-date integration branch.** Do not start new work from the historical `backend-v2/integration`, `frontend-v2/integration`, or `ml-v2/integration` branches by default.

```bash
git fetch origin
git switch -c sprint-2/your-name-short-task origin/main
```

Choose a descriptive and unique branch name, for example:

- `sprint-2/backend-yourname-status-history`
- `sprint-2/frontend-yourname-staff-queue`
- `sprint-2/ml-yourname-evaluation`
- `docs/sprint2-api-contract`

These are **examples**, not fixed branch names. Avoid making unrelated changes on another member's feature branch. If a task depends on an unmerged PR, coordinate with its owner and explicitly record that dependency; do not assume the work already exists in `main`.

## 3. Use the current API contract

Before implementing or integrating API-dependent UI, review:

- [Sprint 2 API contract](docs/API_CONTRACT.md) — routes, methods, payloads, response schemas, roles, and implementation status.
- [Backend API routes](backend/app/api/v1/endpoints/) and [schemas](backend/app/schemas/) — actual behavior in the checked-out branch.
- [Frontend API client](frontend/src/api/) — client methods and types.

**The URL prefix remains `/api/v1`**; the sprint number does not change it to `/api/v2`.

The contract distinguishes routes merged into `main` from candidate or blocked Sprint 2 routes. **Do not treat unmerged or `501 Not Implemented` endpoints as available**. Coordinate request/response changes across frontend, backend, and documentation. If a PR changes an endpoint, update the contract in the same PR or explicitly track the follow-up.

FastAPI's `/docs` and `/openapi.json` can be used when API docs are enabled locally. They describe the **running code on that branch**, not necessarily every proposed feature.

## 4. Commit only related changes

```bash
git status
git add path/to/changed-file
git diff --cached --check
git diff --cached --stat
git commit -m "docs: describe Sprint 2 workflow"
```

Useful prefixes include `feat:`, `fix:`, `test:`, `docs:`, and `chore:`. Describe what actually changed. Review staged files before committing; avoid blindly staging unrelated files with `git add .`.

If code was imported or adapted from shared work, acknowledge its origin instead of claiming it as newly authored.

## 5. Test before requesting review

Run relevant checks for the files changed. From `backend/` (after installing the project dependencies in your local environment):

```bash
python -m pytest -q
```

From `frontend/`:

```bash
npm ci
npm test
npm run build
```

For schema or migration changes, also check Alembic migration behavior **against a local or explicitly approved test database**, not a teammate's Supabase instance. Test authorization, department scoping, status transitions, history, and response shapes when those areas change.

For ML, datasets, and diagrams, document their origin, validation/evaluation results (where applicable), and privacy checks. Never upload confidential complaint records or personal data without approval.

For documentation-only changes, check Markdown, links, examples, and `git diff --check`. Do not claim application tests were run if they were not.

If a test cannot run, state why in the PR.

## 6. Open a pull request

```bash
git push -u origin sprint-2/your-name-short-task
```

On GitHub, open a PR with **base: `main`** and **compare: your feature branch**, unless a different target was explicitly agreed for that task.

In the PR description, explain:

- What changed, why it was needed, and which module it affects.
- Tests or manual checks performed, including their results and limitations.
- Dependencies on unmerged PRs or decisions still pending.
- Any changes to APIs, database schema, frontend types, or documentation.
- Whether code was newly implemented or imported/adapted from earlier shared work.

Request a teammate's review. Address feedback on the **same branch**, and do not merge until relevant checks pass and any blockers or dependencies are resolved. Prefer a merge strategy consistent with team policy; never rewrite authorship to manipulate contributor history.

## 7. Keep the repository and data safe

Never commit `.env` files, API keys, OAuth secrets, access tokens, passwords, database connection secrets, virtual environments, `node_modules`, caches, generated builds, or private datasets. Use safe example files such as `.env.example` for configuration documentation.

Do not run migrations, destructive SQL, resets, or demo seeding on a shared Supabase database without explicit authorization. Do not add secrets to frontend code or PR screenshots.

Ask before force-pushing, rewriting shared history, deleting branches used by others, or making destructive changes. Keep `main` usable for the team.

## 8. Sprint 1 history

The old `backend-v2/integration`, `frontend-v2/integration`, and `ml-v2/integration` branches were used to assemble **Sprint 1**. They can still be consulted for historical context, but Sprint 2 contributors should normally work from the updated `main` and use individual feature branches and reviewable PRs.

If the team later adopts a shared Sprint 2 integration branch, update this guide to document that decision rather than silently switching PR bases.
