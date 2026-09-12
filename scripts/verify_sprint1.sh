#!/usr/bin/env bash
# Sprint 1 walking-skeleton end-to-end verification (docs/DESIGN.md's
# acceptance criterion: one fake payment.failed event reaches
# CASE_CLOSED in under a minute).
#
# Assumes:
#   - `docker compose up -d` is already running (Temporal + Postgres).
#   - db/migrations/0001_init.sql has already been applied to the `app`
#     database.
#   - The virtualenv is already activated (this script does not
#     activate one itself -- it just checks the package is importable).
#
# Starts the worker and API itself, POSTs a fake payment.failed event,
# approves it via the CLI, polls until CASE_CLOSED, asserts elapsed time
# is under 60s, then confirms directly against cases/audit_events.

set -euo pipefail

cd "$(dirname "$0")/.."

if ! python -c "import payment_failure_remediation_agent" >/dev/null 2>&1; then
    echo "ERROR: payment_failure_remediation_agent is not importable." >&2
    echo "Activate the venv first: source .venv/bin/activate" >&2
    exit 1
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

API_HOST="127.0.0.1"
API_PORT="8000"
API_URL="http://${API_HOST}:${API_PORT}"

WORKER_LOG="$(mktemp -t sprint1-worker.XXXXXX.log)"
API_LOG="$(mktemp -t sprint1-api.XXXXXX.log)"
WORKER_PID=""
API_PID=""

cleanup() {
    echo "==> Cleaning up worker/API processes..."
    [[ -n "$WORKER_PID" ]] && kill "$WORKER_PID" 2>/dev/null || true
    [[ -n "$API_PID" ]] && kill "$API_PID" 2>/dev/null || true
}
trap cleanup EXIT

echo "==> Checking docker compose services are up..."
RUNNING_SERVICES="$(docker compose ps --status running --services 2>/dev/null || true)"
for svc in temporal postgres; do
    if ! grep -qx "$svc" <<< "$RUNNING_SERVICES"; then
        echo "ERROR: '$svc' service is not running. Run 'docker compose up -d' first." >&2
        exit 1
    fi
done

echo "==> Starting worker (log: ${WORKER_LOG})..."
python -m payment_failure_remediation_agent.worker > "$WORKER_LOG" 2>&1 &
WORKER_PID=$!

echo "==> Starting API (log: ${API_LOG})..."
uvicorn payment_failure_remediation_agent.api.main:app --host "$API_HOST" --port "$API_PORT" \
    > "$API_LOG" 2>&1 &
API_PID=$!

echo "==> Waiting for API to become reachable..."
API_UP=""
for _ in $(seq 1 30); do
    if curl -sf "${API_URL}/docs" > /dev/null 2>&1; then
        API_UP=1
        break
    fi
    sleep 0.5
done
if [[ -z "$API_UP" ]]; then
    echo "ERROR: API never became reachable at ${API_URL}" >&2
    echo "----- api log -----"; cat "$API_LOG"
    exit 1
fi

echo "==> Giving the worker a moment to connect to Temporal..."
sleep 2

START_TIME=$(date +%s)

IDEMPOTENCY_KEY="verify-sprint1-$(date +%s)-$$"
echo "==> POSTing fake payment.failed event (idempotency_key=${IDEMPOTENCY_KEY})..."
RESPONSE=$(curl -sf -X POST "${API_URL}/events/payment-failed" \
    -H "Content-Type: application/json" \
    -d "{\"idempotency_key\": \"${IDEMPOTENCY_KEY}\", \"payload\": {\"error_code\": \"card_declined\"}}")
echo "$RESPONSE" | jq .

CASE_ID=$(echo "$RESPONSE" | jq -r .case_id)
echo "==> case_id=${CASE_ID}"

echo "==> Approving via CLI..."
python -m payment_failure_remediation_agent.cli approve "$CASE_ID" --approver verify-sprint1

echo "==> Polling GET /cases/${CASE_ID} until CASE_CLOSED..."
STATUS=""
for _ in $(seq 1 120); do
    STATUS=$(curl -sf "${API_URL}/cases/${CASE_ID}" | jq -r .status)
    if [[ "$STATUS" == "CASE_CLOSED" ]]; then
        break
    fi
    sleep 0.5
done

END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))

echo "==> Final status: ${STATUS}, elapsed: ${ELAPSED}s"

if [[ "$STATUS" != "CASE_CLOSED" ]]; then
    echo "FAIL: case did not reach CASE_CLOSED (last status: ${STATUS})" >&2
    echo "----- worker log -----"; cat "$WORKER_LOG"
    echo "----- api log -----"; cat "$API_LOG"
    exit 1
fi

if (( ELAPSED >= 60 )); then
    echo "FAIL: took ${ELAPSED}s, expected under 60s" >&2
    exit 1
fi

echo "==> Confirming directly against Postgres..."
PGPASSWORD="${POSTGRES_PASSWORD}" psql -h localhost -U "${POSTGRES_USER}" -d app \
    -c "SELECT id, status, attempt_count FROM cases WHERE id = '${CASE_ID}';"
PGPASSWORD="${POSTGRES_PASSWORD}" psql -h localhost -U "${POSTGRES_USER}" -d app \
    -c "SELECT from_status, to_status, created_at FROM audit_events WHERE case_id = '${CASE_ID}' ORDER BY created_at;"

echo ""
echo "PASS: case ${CASE_ID} reached CASE_CLOSED in ${ELAPSED}s."
echo "Temporal UI: http://localhost:8080/namespaces/default/workflows/case-${CASE_ID}"
