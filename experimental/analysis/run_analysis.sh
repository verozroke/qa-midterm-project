#!/usr/bin/env bash
# run_analysis.sh — Regenerate every figure and the analysis report.
#
# Reads:  experimental/{performance,mutation,chaos}/results/*
# Writes: experimental/analysis/figures/*.png
#         experimental/analysis/analysis_report.md
#
# Prereq: matplotlib, pandas, numpy installed in the active Python env.
#         If missing, run from project root:
#             pip install -r experimental/analysis/requirements.txt
#         (Inside a venv recommended; otherwise add --break-system-packages
#         on Debian/Ubuntu 24.04+.)
#
# Usage from project root:
#     bash experimental/analysis/run_analysis.sh
# Or from this folder:
#     bash run_analysis.sh

set -e

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "═══════════════════════════════════════════════════════════════"
echo "  Assignment 4 — Analysis Pipeline"
echo "═══════════════════════════════════════════════════════════════"
echo

# Check deps without trying to install (respects venv / system policies)
if ! python -c "import matplotlib, pandas, numpy" >/dev/null 2>&1; then
    echo "✗ Required packages missing (matplotlib / pandas / numpy)."
    echo
    echo "  Install them once with one of:"
    echo "    pip install -r $HERE/requirements.txt                 # in a venv"
    echo "    pip install -r $HERE/requirements.txt --user"
    echo "    pip install -r $HERE/requirements.txt --break-system-packages"
    echo
    echo "  Then re-run this script."
    exit 1
fi

echo "[1/2] Generating figures..."
python "$HERE/generate_figures.py"

echo
echo "[2/2] Generating Markdown analysis report..."
python "$HERE/generate_report.py"

echo
echo "═══════════════════════════════════════════════════════════════"
echo "  Done."
echo
echo "  Figures:  $HERE/figures/"
echo "  Report:   $HERE/analysis_report.md"
echo "═══════════════════════════════════════════════════════════════"
