#!/usr/bin/env bash
# Polls <base URL>/api/health until it reports status ok, or fails once the window closes.
# The window covers a cold start. Used by the Deploy workflow (docs/deployment.md section 5).
#   scripts/smoke-test.sh https://hr-assist.naveenmanjappa.com [window seconds, default 300]
set -euo pipefail

base_url=${1:?usage: smoke-test.sh <base URL> [window seconds]}
window=${2:-300}
url="${base_url%/}/api/health"
deadline=$((SECONDS + window))

while true; do
  body=$(curl --silent --show-error --max-time 30 "$url" 2>&1) || true
  echo "$body"
  if [ "$(echo "$body" | jq -r .status 2>/dev/null)" = "ok" ]; then
    echo "Smoke test passed: $url"
    exit 0
  fi
  if [ "$SECONDS" -ge "$deadline" ]; then
    echo "::error::$url did not return status ok within ${window}s."
    exit 1
  fi
  sleep 10
done
