#!/bin/sh
set -e

echo "[PMS] Running Alembic migrations..."
alembic upgrade head

echo "[PMS] Starting server..."
exec "$@"
