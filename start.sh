#!/bin/bash
# ============================================================
# Retail PriceGuard — Start Script
# Starts both the backend API server and the frontend dev server
# ============================================================

set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"

echo "============================================================"
echo "  RETAIL PRICEGUARD — Starting Services"
echo "============================================================"

# 1. Setup backend virtual environment & install deps
echo ""
echo "[1/3] Setting up backend..."
cd "$BACKEND_DIR"
if [ ! -d "venv" ]; then
  echo "  Creating virtual environment..."
  python3 -m venv venv
fi
source venv/bin/activate
pip install -r requirements.txt --quiet 2>/dev/null

# 2. Start backend server (background)
echo "[2/3] Starting backend API server on port 8000..."
cd "$BACKEND_DIR"
python server.py &
BACKEND_PID=$!
echo "  Backend PID: $BACKEND_PID"

# Wait for backend to start
sleep 3

# 3. Start frontend dev server
echo "[3/3] Starting frontend dev server..."
cd "$ROOT_DIR"
npm run dev &
FRONTEND_PID=$!
echo "  Frontend PID: $FRONTEND_PID"

echo ""
echo "============================================================"
echo "  Backend:  http://localhost:8000  (API docs: /docs)"
echo "  Frontend: http://localhost:5173"
echo "============================================================"
echo "  Press Ctrl+C to stop both servers"
echo ""

# Trap Ctrl+C to kill both
cleanup() {
    echo ""
    echo "Shutting down..."
    kill $BACKEND_PID 2>/dev/null
    kill $FRONTEND_PID 2>/dev/null
    exit 0
}
trap cleanup SIGINT SIGTERM

# Wait for either process to exit
wait
