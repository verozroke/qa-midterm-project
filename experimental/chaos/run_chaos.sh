#!/usr/bin/env bash
# run_chaos.sh — one-shot runner for the chaos suite.
#
# Usage:
#   ./run_chaos.sh                  # full suite (kills and restarts the app)
#   ./run_chaos.sh --skip-api-kill  # safer — won't take the app down

set -e
cd "$(dirname "$0")/../.."

if ! curl -sf http://localhost:8080/api/health > /dev/null 2>&1; then
    echo "✗ App is not running at localhost:8080."
    echo "  Start it:  python -m app.main &"
    exit 1
fi
echo "✓ App is up."

python experimental/chaos/chaos_runner.py "$@"
