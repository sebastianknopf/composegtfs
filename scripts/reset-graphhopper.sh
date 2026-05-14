#!/usr/bin/env bash
# reset-graphhopper.sh
# Stops the GraphHopper service, removes its data volume, and restarts it.
# Run from the project root or any subdirectory.

set -euo pipefail

# Resolve project root (one level up from this script's directory)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

echo "==> Stopping GraphHopper service..."
docker compose --profile graphhopper stop graphhopper

echo "==> Removing GraphHopper container..."
docker compose --profile graphhopper rm -f graphhopper

echo "==> Removing GraphHopper data volume..."
# Docker Compose prefixes volume names with the project name (directory name by default).
PROJECT_NAME="$(basename "$PROJECT_ROOT" | tr '[:upper:]' '[:lower:]')"
docker volume rm "${PROJECT_NAME}_graphhopper_data" 2>/dev/null \
    || docker volume rm graphhopper_data 2>/dev/null \
    || echo "Warning: volume not found, continuing."

echo "==> Starting GraphHopper service..."
docker compose --profile graphhopper up -d graphhopper

echo "==> Done. GraphHopper is starting up."
echo "    Follow logs with: docker compose --profile graphhopper logs -f graphhopper"
