#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# Retail PriceGuard — Start Script
# Launches both backend (FastAPI) and frontend (Vite React)
# ═══════════════════════════════════════════════════════════════

set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Colors
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"
echo -e "${CYAN}   Retail PriceGuard — Starting Application${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"

# ── Kill any existing processes on our ports ───────────────────
echo -e "\n${YELLOW}[0/2]${NC} Cleaning up old processes..."
fuser -k 8000/tcp 2>/dev/null || true
fuser -k 5173/tcp 2>/dev/null || true
sleep 1

# ── 1. Start Backend ──────────────────────────────────────────
echo -e "\n${YELLOW}[1/2]${NC} Starting FastAPI backend..."
cd "$PROJECT_DIR/backend"

if [ ! -d "venv" ]; then
    echo -e "${RED}  ✗ No venv found. Creating...${NC}"
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

python server.py &
BACKEND_PID=$!
echo -e "${GREEN}  ✓ Backend PID: $BACKEND_PID (http://localhost:8000)${NC}"

# Wait for backend to be ready
echo -n "  Waiting for backend..."
for i in $(seq 1 30); do
    if curl -s http://localhost:8000/api/health > /dev/null 2>&1; then
        echo -e " ${GREEN}ready!${NC}"
        break
    fi
    echo -n "."
    sleep 1
done

# ── 2. Start Frontend ────────────────────────────────────────
echo -e "\n${YELLOW}[2/2]${NC} Starting Vite frontend..."
cd "$PROJECT_DIR"
npm run dev &
FRONTEND_PID=$!
echo -e "${GREEN}  ✓ Frontend PID: $FRONTEND_PID (http://localhost:5173)${NC}"

# ── Ready ─────────────────────────────────────────────────────
sleep 2
echo -e "\n${CYAN}═══════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  ✓ App is running!${NC}"
echo -e "  ${CYAN}Frontend:${NC} http://localhost:5173"
echo -e "  ${CYAN}Backend: ${NC} http://localhost:8000"
echo -e "  ${CYAN}Health:  ${NC} http://localhost:8000/api/health"
echo -e "\n  Press ${YELLOW}Ctrl+C${NC} to stop both servers"
echo -e "${CYAN}═══════════════════════════════════════════════════${NC}\n"

# ── Cleanup on exit ───────────────────────────────────────────
cleanup() {
    echo -e "\n${YELLOW}Shutting down...${NC}"
    kill $BACKEND_PID 2>/dev/null
    kill $FRONTEND_PID 2>/dev/null
    wait $BACKEND_PID 2>/dev/null
    wait $FRONTEND_PID 2>/dev/null
    echo -e "${GREEN}✓ All processes stopped${NC}"
}
trap cleanup SIGINT SIGTERM

# Keep script alive until Ctrl+C
wait
