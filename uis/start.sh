#!/usr/bin/env bash

set -u

website_pid=""
backoffice_pid=""

cleanup() {
  if [[ -n "$website_pid" ]]; then
    kill "$website_pid" 2>/dev/null || true
  fi
  if [[ -n "$backoffice_pid" ]]; then
    kill "$backoffice_pid" 2>/dev/null || true
  fi
  wait 2>/dev/null || true
}

trap cleanup INT TERM EXIT

(cd /app/website && npm run dev -- --hostname 0.0.0.0 --port 3000) &
website_pid=$!

(cd /app/backoffice && npm run dev -- --hostname 0.0.0.0 --port 3001) &
backoffice_pid=$!

set +e
wait -n "$website_pid" "$backoffice_pid"
exit_code=$?
set -e

exit "$exit_code"