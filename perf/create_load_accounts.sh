#!/usr/bin/env bash
# Create the verified student accounts the S5-36 load test signs in with.
#
# Uses the S5-02 provisioning CLI, so the normal registration rules apply and
# no email is sent. Safe to run twice: existing accounts are left unchanged.
#
#   export DATABASE_URL='postgresql+psycopg://...'   # staging only, never production
#   export CCMS_NEW_USER_PASSWORD='...'              # shared password, never commit it
#   perf/create_load_accounts.sh [count]             # default 10, max 10
set -euo pipefail

COUNT="${1:-10}"
if ! [[ "$COUNT" =~ ^[0-9]+$ ]] || (( COUNT < 1 || COUNT > 10 )); then
  echo "count must be 1-10 (the load test signs in at most 10 accounts)" >&2
  exit 1
fi
: "${DATABASE_URL:?Set DATABASE_URL to the staging database}"
: "${CCMS_NEW_USER_PASSWORD:?Set CCMS_NEW_USER_PASSWORD}"

cd "$(dirname "$0")/../backend"
PY="${PERF_PYTHON:-.venv/bin/python}"

emails=()
for i in $(seq -w 1 "$COUNT"); do
  email="ccms.loadtest${i}@dau.ac.in"
  "$PY" -m app.scripts.create_staff_user --role student --email "$email" --name "Load Test ${i}"
  emails+=("$email")
done

echo
echo "Done. Use these accounts for the load test:"
echo "export CCMS_ACCOUNTS=\"$(IFS=,; echo "${emails[*]}")\""
