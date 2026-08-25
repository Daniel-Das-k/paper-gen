#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_dir="$(cd "$script_dir/.." && pwd)"

if ! command -v python >/dev/null 2>&1; then
  echo "Python is required. Activate the ques-gen environment first."
  exit 1
fi
if ! command -v npm >/dev/null 2>&1; then
  echo "Node.js and npm are required for the demo frontend."
  exit 1
fi
if ! python -c "import fastapi, fitz, pydantic_ai" >/dev/null 2>&1; then
  echo "Backend packages are missing. Activate the ques-gen environment and run:"
  echo "  cd backend && pip install -e '.[dev]'"
  exit 1
fi
if [[ ! -f "$repo_dir/backend/.env" ]]; then
  echo "backend/.env is missing. Copy backend/.env.example and add Bedrock credentials."
  exit 1
fi
if [[ ! -d "$repo_dir/frontend/node_modules" ]]; then
  echo "Frontend packages are missing. Run: cd frontend && npm install"
  exit 1
fi

cleanup() {
  trap - INT TERM EXIT
  kill "$backend_pid" "$frontend_pid" 2>/dev/null || true
}
trap cleanup INT TERM EXIT

echo "Starting REC Question Paper Studio local demo"
echo "Frontend: http://127.0.0.1:5173"
echo "Backend:  http://127.0.0.1:8000/docs"

(cd "$repo_dir/backend" && uvicorn question_paper_gen.api:app --host 127.0.0.1 --port 8000) &
backend_pid=$!
(cd "$repo_dir/frontend" && npm run dev -- --host 127.0.0.1) &
frontend_pid=$!

wait "$backend_pid" "$frontend_pid"

