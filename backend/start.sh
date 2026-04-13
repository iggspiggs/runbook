#!/bin/bash
set -e

echo "Running database migrations..."
alembic upgrade head

# Seed only if the script exists — safe to skip on a clean checkout
if [ -f "/app/seed_demo.py" ]; then
    echo "Seeding demo data..."
    python seed_demo.py
else
    echo "No seed_demo.py found — skipping seed step."
fi

echo "Starting server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
