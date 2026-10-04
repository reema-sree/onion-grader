#!/bin/sh
set -e
echo "--- Kisan Setu: Starting up ---"

# Set PUBLIC_BASE_URL from Render's RENDER_EXTERNAL_URL if available
if [ -n "$RENDER_EXTERNAL_URL" ]; then
  export PUBLIC_BASE_URL="$RENDER_EXTERNAL_URL"
fi

# Use PORT from env or default to 8000
PORT="${PORT:-8000}"

echo "--- Seeding demo database ---"
python -c "
import sys
sys.path.insert(0, '.')
from backend.seed import seed_database
seed_database()
"

echo "--- Starting FastAPI server on port $PORT ---"
exec uvicorn backend.app.main:app --host 0.0.0.0 --port "$PORT"
