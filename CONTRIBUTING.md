# Contributing to CCMS

We built Sprint 1 as a team, so we try to keep changes easy to review and easy to trace back to the person who submitted them. Our GitHub workflow is based on **individual feature branches and pull requests**. Team members who already have collaborator access can work directly with the original repository; they do not need to fork it.

## Getting started

Clone the repository once:

```bash
git clone https://github.com/TakshChauhan/Campus-Complaint-Management-System.git
cd Campus-Complaint-Management-System
git fetch origin
```

Set your Git identity to your own name and an email associated with your GitHub account:

```bash
git config user.name "Your Name"
git config user.email "you@example.com"
```

Do this in your local clone, not on another teammate's machine or account.

## Choose the right base branch

During Sprint 1, work was combined separately by team:

| Work | Integration branch |
| --- | --- |
| Backend | `backend-v2/integration` |
| Frontend | `frontend-v2/integration` |
| ML data and design documents | `ml-v2/integration` |

Before starting a task, fetch the latest changes and branch from the **appropriate team integration branch**, not automatically from `main`:

```bash
git fetch origin
git switch -c feature/short-description origin/backend-v2/integration
```

Replace the base ref with the frontend or ML integration branch for those teams, and choose a distinctive branch name. If your task starts after the final Sprint 1 integrations have been merged, new general-purpose work may branch from the updated `main` instead.

## Make changes in understandable commits

Try to keep one clear change per commit: a set of related source files, a test, or a documentation correction. Check what you are committing before you commit it.

```bash
git status
git add path/to/the/files/you/changed
git diff --cached --check
git diff --cached --stat
git commit -m "fix(api): handle empty department responses"
```

Use messages that describe **what actually changed**. `feat`, `fix`, `test`, `docs` and `chore` are useful prefixes, but they are not mandatory. Avoid staging unrelated files with `git add .` without checking the result.

Some Sprint 1 branches imported pre-existing shared code into separate module branches. Label this work as an **import**; do not present it as newly authored features. Additional fixes and improvements should have their own accurate commits.

## Push and open a pull request

Push your feature branch:

```bash
git push -u origin feature/short-description
```

Then create a PR on GitHub. For work within the Sprint 1 team workflow, select the relevant `*-v2/integration` branch as the **base** and your feature branch as the **compare** branch.

A useful PR explains:

- What changed and which module it belongs to.
- Which tests or manual checks you ran, including any that could not run.
- Any dependencies on another member's branch.
- Whether the PR imports earlier shared code or contains newly implemented work.

Ask another member to review the PR. Fix review issues on the same feature branch, then merge into the **integration branch**. The final integration branches are reviewed and merged into `main` separately.

To keep individual commits visible in history, the team can use **Create a merge commit** instead of squashing when repository policy permits. Never rewrite commit authorship merely to change how the Contributors page looks.

## Tests before review

For backend changes (from `backend/`):

```bash
python -m pytest -q
```

For frontend changes (from `frontend/`):

```bash
npm ci
npm test
npm run build
```

Some isolated feature branches may lack the shared application entry point or fixtures needed for full tests. State that limitation and run the complete checks on the integrated branch before merging to `main`.

For ML datasets and diagrams, review the files, explain their origin and purpose, and check for sensitive or personally identifying information before committing.

## Keep the repository safe

Never commit `.env` files, access tokens, OAuth secrets, database passwords, virtual environments, `node_modules`, Python caches or generated build folders. Do not put database credentials in React code. Do not run migrations or seed test accounts against someone else's Supabase database without permission.

If something goes wrong, ask before using `git reset --hard`, force-pushing, deleting a shared branch or changing `main`. Those operations can affect teammates' work.

## After Sprint 1

The Sprint 1 integration branches document how our contributions were assembled. For future changes after the full project reaches `main`, agree on the next branching convention with the team. The same principle remains: small, reviewable changes and a working default branch.
