#!/bin/bash
set -e

# ==============================================
#   WHS Webpage - Launcher (macOS / Linux)
# ==============================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/whs"

# ---------- trap: cleanup on Ctrl+C ----------
cleanup() {
    echo ""
    echo "Shutting down services..."
    [ -n "$BACKEND_PID" ] && kill "$BACKEND_PID" 2>/dev/null
    [ -n "$FRONTEND_PID" ] && kill "$FRONTEND_PID" 2>/dev/null
    wait 2>/dev/null
    echo "All services stopped."
    exit 0
}
trap cleanup SIGINT SIGTERM

echo "============================================"
echo "  WHS Webpage - Starting Services"
echo "============================================"
echo ""

# ==================== Backend ====================
echo "[1/2] Starting Backend (FastAPI)..."
cd "$BACKEND_DIR"

if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
    echo "  -> Python venv activated."
else
    echo "  [WARN] venv not found at backend/venv"
    echo "  Run: python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

uvicorn main:app --host 127.0.0.1 --port 8000 --reload &
BACKEND_PID=$!
echo "  -> Backend started (PID $BACKEND_PID) on http://127.0.0.1:8000"

# ==================== Frontend ====================
echo "[2/2] Starting Frontend (Vite)..."
cd "$FRONTEND_DIR"

if ! command -v npm &> /dev/null; then
    echo "  [ERROR] npm is not installed or not in PATH."
    exit 1
fi

echo "  -> Installing dependencies..."
npm install --silent

echo "  -> Starting Vite dev server..."
npm run dev -- --host 0.0.0.0 &
FRONTEND_PID=$!
echo "  -> Frontend started (PID $FRONTEND_PID) on http://localhost:5173"

# ==================================================
echo ""
echo "============================================"
echo "  All services running!"
echo "  Backend:   http://127.0.0.1:8000"
echo "  Frontend:  http://localhost:5173"
echo "  Press Ctrl+C to stop all services."
echo "============================================"

# Keep the script alive until Ctrl+C
wait
