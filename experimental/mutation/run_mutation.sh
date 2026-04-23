#!/usr/bin/env bash
# run_mutation.sh — runs custom mutation testing.
# Prereqs: midterm venv active (pytest, flask, etc. installed).
# NOTE: the app does NOT need to be running — tests use Flask's test_client
# or spin up their own. Only the API tests hit localhost:8080, which is why
# we also run with the server up if it is.

set -e
cd "$(dirname "$0")/../.."

# If the app is up, API tests will exercise more code paths — better.
# If not, we'll still run unit tests.
if curl -sf http://localhost:8080/api/health > /dev/null 2>&1; then
    echo "✓ App is up at localhost:8080 — API tests will run against it."
else
    echo "⚠ App NOT running. Only unit tests will provide mutation coverage."
    echo "  For a fuller run, in another terminal:  python -m app.main"
    echo "  Continuing anyway..."
fi

python experimental/mutation/custom_mutation.py
