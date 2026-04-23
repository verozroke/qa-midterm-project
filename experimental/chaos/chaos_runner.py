"""chaos_runner.py — orchestrates all chaos scenarios and produces the
final metrics table required by the assignment.

Scenarios run sequentially with small cooldown gaps so each starts from a
clean baseline. Output is both pretty-printed and saved to
experimental/chaos/results/chaos_report.json — the report.md consumes this.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Make scenarios importable.
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from scenarios import api_downtime, db_failure, network_latency, resource_exhaustion  # noqa: E402


RESULTS_DIR = HERE / "results"


def banner(title: str):
    print("\n" + "═" * 70)
    print(f"  {title}")
    print("═" * 70)


def run_all(base_url: str = "http://localhost:8080", skip_api_kill: bool = False):
    results = {}
    start = time.time()

    # 1. DB latency (safest — doesn't take down the app)
    banner("1/4  DB Latency")
    try:
        results["db_latency"] = db_failure.run_db_latency(base_url=base_url)
    except Exception as e:
        results["db_latency"] = {"error": str(e)}
    time.sleep(2)

    # 2. Network latency
    banner("2/4  Network Latency & Packet Loss")
    try:
        results["network_latency"] = network_latency.run(base_url=base_url)
    except Exception as e:
        results["network_latency"] = {"error": str(e)}
    time.sleep(2)

    # 3. Resource exhaustion (CPU — memory is optional)
    banner("3/4  CPU Exhaustion")
    try:
        results["cpu_exhaustion"] = resource_exhaustion.run_cpu(base_url=base_url)
    except Exception as e:
        results["cpu_exhaustion"] = {"error": str(e)}
    time.sleep(2)

    # 4. API Downtime — LAST because it kills the app. The script restarts
    # it, but if that fails we don't want subsequent scenarios to fail too.
    if skip_api_kill:
        banner("4/4  API Downtime   [SKIPPED via --skip-api-kill]")
        results["api_downtime"] = {"skipped": True}
    else:
        banner("4/4  API Downtime")
        try:
            results["api_downtime"] = api_downtime.run(base_url=base_url)
        except Exception as e:
            results["api_downtime"] = {"error": str(e)}

    elapsed = time.time() - start

    # ── Summary table ──────────────────────────────────────────────────
    banner(f"CHAOS TESTING SUMMARY    (elapsed: {elapsed:.1f}s)")
    rows = _summary_rows(results)
    _print_table(rows)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / "chaos_report.json"
    out.write_text(json.dumps({
        "elapsed_s": round(elapsed, 1),
        "base_url": base_url,
        "summary": rows,
        "details": results,
    }, indent=2, default=str))
    print(f"\n  ✓ JSON report: {out.relative_to(HERE.parent.parent)}")

    return results


def _summary_rows(results: dict) -> list[dict]:
    """Extract the core metrics per scenario into a flat table."""
    rows = []
    for key, r in results.items():
        if not isinstance(r, dict) or "error" in r or r.get("skipped"):
            rows.append({
                "scenario": key,
                "availability_pct": "n/a",
                "mttr_s": "n/a",
                "impact": r.get("error") or "skipped" if isinstance(r, dict) else str(r),
            })
            continue
        rows.append({
            "scenario": r.get("scenario", key),
            "availability_pct": r.get("availability_pct",
                                      r.get("write_availability_pct",
                                            r.get("degraded_avg_ms", "—"))),
            "mttr_s": r.get("mttr_s", "—"),
            "impact": (r.get("impact") or "")[:50],
        })
    return rows


def _print_table(rows: list[dict]):
    if not rows: return
    headers = ["Scenario", "Availability / Metric", "MTTR (s)", "Impact"]
    widths = [
        max(len(str(r["scenario"])) for r in rows),
        max(len(str(r["availability_pct"])) for r in rows),
        max(len(str(r["mttr_s"])) for r in rows),
        max(len(str(r["impact"])) for r in rows),
    ]
    widths = [max(w, len(h)) for w, h in zip(widths, headers)]

    def fmt_row(cells):
        return "  " + " │ ".join(str(c).ljust(w) for c, w in zip(cells, widths))

    print(fmt_row(headers))
    print("  " + "─┼─".join("─" * w for w in widths))
    for r in rows:
        print(fmt_row([r["scenario"], r["availability_pct"], r["mttr_s"], r["impact"]]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8080")
    parser.add_argument("--skip-api-kill", action="store_true",
                       help="Skip the API-kill scenario (won't restart app).")
    args = parser.parse_args()
    run_all(base_url=args.base_url, skip_api_kill=args.skip_api_kill)
