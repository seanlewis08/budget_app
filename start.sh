#!/bin/bash
# Budget App — One-click launcher for development
# Starts backend (FastAPI) + frontend (Vite) + Electron window

cd "$(dirname "$0")"

cleanup() {
  echo "Shutting down..."
  # Kill child processes
  [ -n "$BACKEND_PID" ] && kill "$BACKEND_PID" 2>/dev/null
  [ -n "$FRONTEND_PID" ] && kill "$FRONTEND_PID" 2>/dev/null
  wait 2>/dev/null
  echo "Done."
  exit 0
}
trap cleanup INT TERM EXIT

# Start backend
echo "Starting backend..."
uv run uvicorn backend.main:app --port 8000 --reload &
BACKEND_PID=$!

# Start frontend (run in subshell so cd doesn't affect parent)
echo "Starting frontend..."
(cd frontend && npm run dev) &
FRONTEND_PID=$!

# Wait for both to be ready
echo "Waiting for services..."
for i in $(seq 1 30); do
  if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "  Backend ready"
    break
  fi
  sleep 1
done

for i in $(seq 1 30); do
  if curl -s http://localhost:5173 > /dev/null 2>&1; then
    echo "  Frontend ready"
    break
  fi
  sleep 1
done

# Launch Electron
echo "Launching app..."
NODE_ENV=development npx electron .

# Electron closed — cleanup runs via trap
