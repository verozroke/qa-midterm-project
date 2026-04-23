#!/usr/bin/env bash
# run_performance.sh — executes all four performance scenarios sequentially.
#
# Prereqs:
#   - app running on localhost:8080 (python -m app.main)
#   - k6 installed  (curl -s https://dl.k6.io/key.gpg | sudo apt-key add -)
#                   OR use locust (pip install locust)
#
# Output: JSON summaries in experimental/performance/results/

set -e
cd "$(dirname "$0")"

mkdir -p results

if ! command -v k6 &> /dev/null; then
    echo "!! k6 not installed — falling back to locust."
    echo "   Install k6:  https://k6.io/docs/getting-started/installation/"
    FALLBACK=1
fi

BASE_URL="${BASE_URL:-http://localhost:8080}"

# Check app is up
if ! curl -sf "${BASE_URL}/api/health" > /dev/null; then
    echo "✗ App not reachable at ${BASE_URL}. Start it first:"
    echo "    cd ../.. && python -m app.main &"
    exit 1
fi
echo "✓ App is up at ${BASE_URL}"

if [[ -z "$FALLBACK" ]]; then
    echo ""
    echo "=== [1/4] Normal Load ==="
    k6 run --env BASE_URL="$BASE_URL" k6/normal_load.js || true

    echo ""
    echo "=== [2/4] Peak Load ==="
    k6 run --env BASE_URL="$BASE_URL" k6/peak_load.js || true

    echo ""
    echo "=== [3/4] Spike Load ==="
    k6 run --env BASE_URL="$BASE_URL" k6/spike_load.js || true

    echo ""
    echo "=== [4/4] Endurance (shortened — set K6_DURATION_MULTIPLIER=3 for full run) ==="
    k6 run --env BASE_URL="$BASE_URL" --env K6_DURATION_MULTIPLIER=0.25 k6/endurance.js || true
else
    # Locust fallback
    cd locust
    mkdir -p ../results

    echo "=== [1/4] Normal Load (locust, 20 users, 2m) ==="
    locust -f locustfile.py --headless -u 20 -r 5 -t 2m \
           --host "$BASE_URL" --csv=../results/normal || true

    echo "=== [2/4] Peak Load (locust, 100 users, 5m) ==="
    locust -f locustfile.py --headless -u 100 -r 20 -t 5m \
           --host "$BASE_URL" --csv=../results/peak || true

    echo "=== [3/4] Spike Load (locust, 200 users, 2m) ==="
    locust -f locustfile.py --headless -u 200 -r 50 -t 2m \
           --host "$BASE_URL" --csv=../results/spike || true

    echo "=== [4/4] Endurance (locust, 50 users, 10m) ==="
    locust -f locustfile.py --headless -u 50 -r 10 -t 10m \
           --host "$BASE_URL" --csv=../results/endurance || true
fi

echo ""
echo "✓ All performance runs complete. Results in experimental/performance/results/"
