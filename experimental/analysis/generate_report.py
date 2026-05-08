"""
generate_report.py — Compute every number the paper needs, write Markdown.

Why this exists:
    The paper's Results section needs dozens of numbers (latencies, mutation
    scores, error rates, MTTRs, etc.). Hand-typing them is error-prone and
    breaks reproducibility. This script reads the raw experimental data,
    computes everything once, and writes a single Markdown document.

INPUT (read-only):
    ../performance/results/{normal,peak,spike}_stats.csv
    ../performance/results/{normal,peak,spike}_stats_history.csv
    ../mutation/results/mutation_report.json
    ../chaos/results/chaos_report.json

OUTPUT:
    ./analysis_report.md   — full per-section breakdown for the paper

USAGE:
    cd experimental/analysis
    python generate_report.py
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
HERE     = Path(__file__).resolve().parent
EXPERIM  = HERE.parent
PERF     = EXPERIM / "performance" / "results"
MUTREP   = EXPERIM / "mutation"    / "results" / "mutation_report.json"
CHAOSREP = EXPERIM / "chaos"       / "results" / "chaos_report.json"
OUT      = HERE / "analysis_report.md"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
ENDPOINTS = ["POST /api/auth/login", "GET /api/tickets",
             "POST /api/tickets",    "GET /api/notifications"]


def load_perf(scenario: str) -> pd.DataFrame:
    return pd.read_csv(PERF / f"{scenario}_stats.csv")


def perf_table(scenario: str) -> str:
    """Build a Markdown row block per endpoint + Aggregated."""
    df = load_perf(scenario)
    keep = df[df["Name"].isin(ENDPOINTS) | (df["Name"] == "Aggregated")]
    rows = []
    rows.append("| Endpoint | Requests | Avg (ms) | Median (ms) | p95 (ms) | "
                "Throughput (rps) | Errors (%) |")
    rows.append("|---|---:|---:|---:|---:|---:|---:|")
    for _, r in keep.iterrows():
        err_pct = 100 * r["Failure Count"] / max(r["Request Count"], 1)
        rows.append(f"| {r['Name']} | {int(r['Request Count'])} | "
                    f"{r['Average Response Time']:.0f} | "
                    f"{r['Median Response Time']:.0f} | "
                    f"{r['95%']:.0f} | "
                    f"{r['Requests/s']:.2f} | "
                    f"{err_pct:.2f} |")
    return "\n".join(rows)


def perf_summary_row(scenario: str) -> dict:
    df = load_perf(scenario)
    agg = df[df["Name"] == "Aggregated"].iloc[0]
    err_pct = 100 * agg["Failure Count"] / max(agg["Request Count"], 1)
    return {
        "scenario":   scenario,
        "users":      {"normal": 20, "peak": 100, "spike": 200}[scenario],
        "duration_s": {"normal": 30, "peak": 60,  "spike": 30 }[scenario],
        "requests":   int(agg["Request Count"]),
        "rps":        round(float(agg["Requests/s"]), 2),
        "avg_ms":     round(float(agg["Average Response Time"]), 0),
        "median_ms":  round(float(agg["Median Response Time"]), 0),
        "p95_ms":     round(float(agg["95%"]), 0),
        "err_pct":    round(err_pct, 2),
    }


def mutation_section() -> str:
    rep = json.loads(MUTREP.read_text())
    s   = rep["summary"]
    by  = rep["by_module"]

    out = []
    out.append("## 2. Mutation Testing\n")
    out.append("**Tool:** Custom deterministic runner (full app restart per "
               "mutant). 15 hand-picked mutants from the risk model.\n")
    out.append(f"**Overall mutation score: {s['mutation_score']:.1f}%** "
               f"({s['killed']}/{s['total']} killed, "
               f"{s['survived']} survived).\n")

    out.append("### Per-module breakdown\n")
    out.append("| Module | Created | Killed | Survived | Mutation score |")
    out.append("|---|---:|---:|---:|---:|")
    for mod, d in by.items():
        score = 100 * d["killed"] / d["created"]
        out.append(f"| {mod} | {d['created']} | {d['killed']} | "
                   f"{d['survived']} | **{score:.1f}%** |")

    survivors = [r for r in rep["results"] if r["status"] == "survived"]
    if survivors:
        out.append("\n### Surviving mutants (real coverage gaps)\n")
        out.append("| ID | Module | Mutation type | Description |")
        out.append("|---|---|---|---|")
        for r in survivors:
            out.append(f"| `{r['id']}` | {r['module']} | "
                       f"{r['mutation_type']} | {r['description']} |")

    return "\n".join(out)


def chaos_section() -> str:
    rep = json.loads(CHAOSREP.read_text())
    d   = rep["details"]
    out = []
    out.append("## 3. Chaos / Fault-Injection Testing\n")
    out.append(f"Total elapsed: {rep['elapsed_s']:.1f} s. "
               f"Target: `{rep['base_url']}`.\n")

    # DB
    db = d["db_latency"]
    out.append("### 3.1 DB Latency — exclusive-lock scenario\n")
    out.append(f"- Read availability: **{db['read_availability_pct']:.0f} %**")
    out.append(f"- Write availability: **{db['write_availability_pct']:.0f} %**")
    out.append(f"- Avg write latency under lock: {db['avg_write_latency_ms']:.0f} ms")
    out.append(f"- MTTR: {db['mttr_s']} s")
    out.append(f"- Error propagation: {db['error_propagation_pct']:.0f} %")
    out.append(f"- _{db['impact']}_\n")

    # Network
    nl = d["network_latency"]
    out.append("### 3.2 Network Latency — +500 ms, 10 % packet loss\n")
    out.append(f"- Baseline avg: {nl['baseline_avg_ms']:.1f} ms → "
               f"degraded avg: **{nl['degraded_avg_ms']:.0f} ms** "
               f"(+{nl['latency_inflation_ms']:.0f} ms)")
    out.append(f"- Baseline error: {nl['baseline_error_pct']:.1f} % → "
               f"degraded error: **{nl['degraded_error_pct']:.1f} %**")
    out.append(f"- Recovery avg: {nl['recovery_avg_ms']:.1f} ms")
    out.append(f"- MTTR: {nl['mttr_s']}")
    out.append(f"- _{nl['impact']}_\n")

    # CPU
    ce = d["cpu_exhaustion"]
    out.append("### 3.3 CPU Exhaustion — 1 burner, 10 s\n")
    out.append(f"- Baseline avg: {ce['baseline_avg_ms']:.1f} ms → "
               f"degraded avg: **{ce['degraded_avg_ms']:.1f} ms** "
               f"(+{ce['latency_inflation_pct']:.0f} %)")
    out.append(f"- Recovery avg: {ce['recovery_avg_ms']:.1f} ms")
    out.append(f"- MTTR: {ce['mttr_s']:.2f} s")
    out.append(f"- Errors during fault: {ce['degraded_error_pct']:.1f} %")
    out.append(f"- _{ce['impact']}_\n")

    return "\n".join(out)


def derived_insights(perf: dict[str, dict]) -> str:
    """Compute derived numbers the paper Discussion needs."""
    out = []
    out.append("## 4. Derived Insights (for Discussion)\n")

    n, p, sp = perf["normal"], perf["peak"], perf["spike"]

    # Saturation point — where error rate diverges
    out.append("### 4.1 Saturation point\n")
    out.append(f"- Throughput is roughly the same at peak ({p['rps']} rps, "
               f"100 VUs) and spike ({sp['rps']} rps, 200 VUs) → "
               f"**throughput plateau between 100 and 200 VUs**.")
    out.append(f"- Error rate jumps from {p['err_pct']:.1f} % → "
               f"{sp['err_pct']:.1f} % over the same range → "
               f"**system saturates near 100 VUs**, then enters the "
               f"\"server queue overflow\" regime.\n")

    # Latency inflation
    out.append("### 4.2 Latency inflation\n")
    out.append(f"- Normal → peak avg latency: {n['avg_ms']:.0f} → "
               f"{p['avg_ms']:.0f} ms ({p['avg_ms']/n['avg_ms']:.2f}×).")
    out.append(f"- Peak → spike avg latency: {p['avg_ms']:.0f} → "
               f"{sp['avg_ms']:.0f} ms ({sp['avg_ms']/p['avg_ms']:.2f}×).")
    out.append(f"- Spike p95: {sp['p95_ms']:.0f} ms — "
               f"≈ {sp['p95_ms']/sp['avg_ms']:.1f}× the average; "
               f"long tail dominates.\n")

    # Mock vs Real
    out.append("### 4.3 Mock-based vs real-backend numbers\n")
    out.append("| Metric | Estimate (Asgmt 2, mock) | "
               "Actual (Asgmt 3, real) | Gap |")
    out.append("|---|---:|---:|---:|")
    for label, est, act in [
        ("Normal-load avg (ms)",  420, n["avg_ms"]),
        ("Peak-load avg (ms)",    980, p["avg_ms"]),
        ("Spike-load err (%)",      8, sp["err_pct"]),
    ]:
        gap = (act - est) / est * 100
        out.append(f"| {label} | {est} | {act:.1f} | "
                   f"{gap:+.0f} % |")

    return "\n".join(out)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    if not all(p.exists() for p in [MUTREP, CHAOSREP] +
               [PERF / f"{s}_stats.csv" for s in ["normal","peak","spike"]]):
        print("ERROR: experimental result files missing. Run experiments first.",
              file=sys.stderr)
        return 2

    perf = {s: perf_summary_row(s) for s in ["normal", "peak", "spike"]}

    md = []
    md.append("# Analysis Report — Assignment 4 / Endterm")
    md.append("")
    md.append("_Auto-generated from raw experimental data. "
              "Do not edit by hand — regenerate via "
              "`python experimental/analysis/generate_report.py`._")
    md.append("")
    md.append("This document contains every quantitative result the paper")
    md.append("references, computed directly from the JSON / CSV files in")
    md.append("`experimental/{performance,mutation,chaos}/results/`.")
    md.append("")

    # ------- Performance -------
    md.append("## 1. Performance Testing\n")
    md.append("**Tool:** Locust 2.x. Three load scenarios on the Flask dev "
              "server with SQLite (WAL).\n")
    md.append("### Aggregate summary across scenarios\n")
    md.append("| Scenario | Users | Duration | Requests | RPS | Avg (ms) "
              "| p95 (ms) | Errors (%) |")
    md.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for s in ["normal", "peak", "spike"]:
        d = perf[s]
        md.append(f"| {s.capitalize()} | {d['users']} | "
                  f"{d['duration_s']} s | {d['requests']} | {d['rps']} | "
                  f"{d['avg_ms']:.0f} | {d['p95_ms']:.0f} | "
                  f"**{d['err_pct']:.2f}** |")
    md.append("")

    md.append("### 1.1 Normal load — 20 VUs, 30 s\n")
    md.append(perf_table("normal"))
    md.append("")
    md.append("### 1.2 Peak load — 100 VUs, 60 s\n")
    md.append(perf_table("peak"))
    md.append("")
    md.append("### 1.3 Spike load — 200 VUs, 30 s\n")
    md.append(perf_table("spike"))
    md.append("")

    # ------- Mutation -------
    md.append(mutation_section())
    md.append("")

    # ------- Chaos -------
    md.append(chaos_section())
    md.append("")

    # ------- Derived -------
    md.append(derived_insights(perf))
    md.append("")

    OUT.write_text("\n".join(md))
    print(f"Wrote: {OUT}")
    print(f"Length: {len(OUT.read_text().splitlines())} lines")
    return 0


if __name__ == "__main__":
    sys.exit(main())
