#!/usr/bin/env bash
# Runs the backend (http://localhost:8000) and the frontend (http://localhost:4200) together.
# Ctrl-C stops both, and if either one exits the other is stopped too.
#   scripts/dev.sh
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)

# Stop every process this script started, including the reloader and ng children.
trap 'trap - EXIT INT TERM; kill 0 2>/dev/null' EXIT INT TERM

if [ ! -d "$root/frontend/node_modules" ]; then
  (cd "$root/frontend" && npm install)
fi

(cd "$root/backend" && exec uv run uvicorn hr_assist.api.app:create_app --factory --reload) &
backend=$!
(cd "$root/frontend" && exec npm start) &
frontend=$!

# macOS ships bash 3.2, which has no `wait -n`, so poll until one of them exits.
while kill -0 "$backend" 2>/dev/null && kill -0 "$frontend" 2>/dev/null; do
  sleep 1
done
