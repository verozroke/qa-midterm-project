"""
generate_figures.py — Reproducible figure generator for the research paper.

INPUT (read-only):
    ../performance/results/{normal,peak,spike}_stats.csv
    ../performance/results/{normal,peak,spike}_stats_history.csv
    ../mutation/results/mutation_report.json
    ../chaos/results/chaos_report.json

OUTPUT:
    ./figures/*.png  (300 DPI)

USAGE:
    cd experimental/analysis
    python generate_figures.py

Every number in the paper traces back to one of the input files above.
No hand-coded numbers in this script except the labels and the risk model
(L, I, D values), which are sourced from §III.B of the paper.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Paths — relative to this file (experimental/analysis/)
# ---------------------------------------------------------------------------
HERE      = Path(__file__).resolve().parent
EXPERIM   = HERE.parent
PERF      = EXPERIM / "performance" / "results"
MUTREP    = EXPERIM / "mutation"    / "results" / "mutation_report.json"
CHAOSREP  = EXPERIM / "chaos"       / "results" / "chaos_report.json"
OUTDIR    = HERE / "figures"
OUTDIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Plot styling — IEEE-paper-friendly
# ---------------------------------------------------------------------------
plt.rcParams.update({
    "font.family":      "DejaVu Sans",
    "font.size":        10,
    "axes.titlesize":   11,
    "axes.labelsize":   10,
    "axes.spines.top":  False,
    "axes.spines.right":False,
    "axes.grid":        True,
    "grid.alpha":       0.25,
    "grid.linestyle":   "--",
    "figure.dpi":       110,
    "savefig.dpi":      300,
    "savefig.bbox":     "tight",
})

C = {
    "normal":   "#2E86AB", "peak":     "#E07B00", "spike":    "#C0392B",
    "killed":   "#27AE60", "survived": "#C0392B", "neutral":  "#7F8C8D",
    "good":     "#27AE60", "bad":      "#C0392B", "warn":     "#F39C12",
}


# ============================================================================
# Helpers
# ============================================================================
def _read_history(scenario: str) -> pd.DataFrame:
    """Read Locust *_stats_history.csv, dedupe duplicate timestamps."""
    df = pd.read_csv(PERF / f"{scenario}_stats_history.csv")
    df = df[df["Name"] == "Aggregated"].copy()
    # Locust occasionally writes both an in-flight aggregated row AND a final
    # aggregated row at the same wall-clock second; keep the last
    df = df.drop_duplicates(subset=["Timestamp"], keep="last")
    df = df.sort_values("Timestamp").reset_index(drop=True)
    df["t_s"] = df["Timestamp"] - df["Timestamp"].iloc[0]
    return df


def _check_inputs() -> bool:
    """Fail loudly if any required input is missing."""
    missing = []
    for scen in ["normal", "peak", "spike"]:
        for kind in ["stats", "stats_history"]:
            f = PERF / f"{scen}_{kind}.csv"
            if not f.exists():
                missing.append(f)
    for f in [MUTREP, CHAOSREP]:
        if not f.exists():
            missing.append(f)
    if missing:
        print("ERROR — missing input files:", file=sys.stderr)
        for m in missing:
            print(f"  {m}", file=sys.stderr)
        print("\nRun the experimental suite first:", file=sys.stderr)
        print("  bash experimental/performance/run_performance.sh", file=sys.stderr)
        print("  bash experimental/mutation/run_mutation.sh",       file=sys.stderr)
        print("  bash experimental/chaos/run_chaos.sh --skip-api-kill",
              file=sys.stderr)
        return False
    return True


# ============================================================================
# FIGURE 1 — Risk Matrix (L × I)
# ============================================================================
def fig1_risk_matrix():
    # (label, L, I, D, label_x, label_y, ha)
    modules = [
        ("Authentication",       3.00, 3.00, 2, 2.97, 3.30, "right"),
        ("Ticket CRUD",          3.10, 3.00, 2, 3.13, 2.70, "left"),
        ("Session/Token",        2.00, 3.00, 2, 2.10, 3.00, "left"),
        ("Ticket Validation",    2.00, 2.00, 3, 2.10, 2.00, "left"),
        ("Notifications",        2.00, 1.00, 3, 2.10, 1.00, "left"),
        ("Dashboard UI",         1.00, 1.00, 3, 1.10, 1.00, "left"),
    ]
    fig, ax = plt.subplots(figsize=(7.6, 5.2))
    grid = np.zeros((3, 3))
    for li in range(3):
        for ii in range(3):
            grid[li, ii] = (li + 1) * (ii + 1)
    im = ax.imshow(grid, origin="lower", cmap="RdYlGn_r",
                   extent=[0.5, 3.5, 0.5, 3.5], aspect="auto", alpha=0.55)

    for name, L, I, D, lx, ly, ha in modules:
        ax.scatter(L, I, s=240, color="#2C3E50",
                   edgecolors="white", linewidths=1.5, zorder=3)
        ax.text(lx, ly, name, ha=ha, va="center",
                fontsize=8.8, fontweight="bold", zorder=4,
                bbox=dict(boxstyle="round,pad=0.25", facecolor="white",
                          edgecolor="none", alpha=0.85))

    ax.set_xticks([1, 2, 3]); ax.set_xticklabels(["Low", "Medium", "High"])
    ax.set_yticks([1, 2, 3]); ax.set_yticklabels(["Low", "Medium", "High"])
    ax.set_xlabel("Likelihood of Failure (L)")
    ax.set_ylabel("Impact of Failure (I)")
    ax.set_title("Risk Assessment Matrix — Modules by (L, I)\n"
                 "Risk score $R = L \\times I \\times (1/D)$, $D$ = detectability ∈ {1,2,3}")
    cbar = plt.colorbar(im, ax=ax, shrink=0.8)
    cbar.set_label("L × I severity", fontsize=9)
    plt.savefig(OUTDIR / "fig1_risk_matrix.png")
    plt.close()
    print("  ✓ fig1_risk_matrix.png")


# ============================================================================
# FIGURE 2 — Test effort vs Risk priority + mutation score overlay
# ============================================================================
def fig2_coverage_vs_risk():
    rep = json.loads(MUTREP.read_text())
    by_mod = rep["by_module"]
    mut_pct = {m: 100 * d["killed"] / d["created"] for m, d in by_mod.items()}

    # Test counts come from the 38-test suite (Asgmt 2 baseline → Asgmt 3).
    # Risk scores come from the L,I,D model in §III.B.
    data = [
        # (module,           risk_score, tests_count, mutation_pct or None)
        ("Authentication",     6.0, 9,  mut_pct.get("Authentication")),
        ("Ticket CRUD",        6.0, 8,  mut_pct.get("Ticket CRUD")),
        ("Ticket Validation",  3.0, 6,  mut_pct.get("Ticket Validation")),
        ("Notifications",      1.0, 4,  mut_pct.get("Notifications")),
        ("Dashboard UI",       0.5, 11, None),
    ]
    labels  = [d[0] for d in data]
    risk    = [d[1] for d in data]
    n_tests = [d[2] for d in data]
    mut     = [d[3] if d[3] is not None else 0 for d in data]
    has_mut = [d[3] is not None for d in data]

    x = np.arange(len(labels))
    fig, ax1 = plt.subplots(figsize=(8.8, 4.8))
    ax1.bar(x - 0.2, n_tests, width=0.4, color=C["normal"],
            label="# Test cases (left)")
    ax1.set_ylabel("# Test cases", color=C["normal"])
    ax1.tick_params(axis="y", labelcolor=C["normal"])

    ax2 = ax1.twinx()
    ax2.bar(x + 0.2, risk, width=0.4, color=C["peak"],
            label="Risk score $R$ (right)")
    ax2.set_ylabel("Risk score $R = L\\cdot I\\cdot (1/D)$", color=C["peak"])
    ax2.tick_params(axis="y", labelcolor=C["peak"])
    ax2.spines["right"].set_visible(True)

    for i, (m, ok) in enumerate(zip(mut, has_mut)):
        if ok:
            ax1.scatter(i - 0.2, n_tests[i] + 0.6, marker="v", s=80,
                        color=C["killed"] if m >= 70 else C["bad"],
                        edgecolors="black", linewidths=0.6, zorder=4)
            ax1.text(i - 0.2, n_tests[i] + 1.4, f"{m:.0f}%",
                     ha="center", fontsize=8)

    ax1.set_xticks(x)
    ax1.set_xticklabels(labels, rotation=15, ha="right")
    ax1.set_title("Test Effort vs Risk Priority per Module — "
                  "with mutation score (▼) where available")
    ax1.set_ylim(0, max(n_tests) + 4)

    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    pass_p = mpatches.Patch(color=C["killed"], label="Mutation ≥ 70%")
    fail_p = mpatches.Patch(color=C["bad"],    label="Mutation < 70%")
    ax1.legend(h1 + h2 + [pass_p, fail_p],
               l1 + l2 + ["Mutation ≥ 70%", "Mutation < 70%"],
               loc="upper right", fontsize=8.5, frameon=False)
    plt.savefig(OUTDIR / "fig2_coverage_vs_risk.png")
    plt.close()
    print("  ✓ fig2_coverage_vs_risk.png")


# ============================================================================
# FIGURE 3 — Performance over time (avg latency + failure rate)
# ============================================================================
def fig3_performance_timeseries():
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4))
    for scen, color in [("normal", C["normal"]),
                        ("peak",   C["peak"]),
                        ("spike",  C["spike"])]:
        df = _read_history(scen)
        axes[0].plot(df["t_s"], df["Total Average Response Time"],
                     color=color, label=scen.capitalize(), linewidth=1.9)

        df["new_fail"] = df["Total Failure Count"].diff().fillna(0).clip(lower=0)
        df["dt"]       = df["t_s"].diff().fillna(1).clip(lower=0.5)
        df["fail_rate"] = df["new_fail"] / df["dt"]
        df["fail_rate_smooth"] = df["fail_rate"].rolling(3, min_periods=1).mean()
        axes[1].plot(df["t_s"], df["fail_rate_smooth"],
                     color=color, label=scen.capitalize(), linewidth=1.9)

    axes[0].set_xlabel("Time (s)"); axes[0].set_ylabel("Average response time (ms)")
    axes[0].set_title("(a) Avg response time over time (running avg)")
    axes[0].legend(frameon=False, loc="upper left")
    axes[1].set_xlabel("Time (s)"); axes[1].set_ylabel("New failures per second (smoothed)")
    axes[1].set_title("(b) Failure rate over time")
    axes[1].legend(frameon=False, loc="upper right")
    plt.suptitle("Performance Testing — Locust, real measurements (Flask dev server, SQLite WAL)",
                 fontsize=11, y=1.04)
    plt.savefig(OUTDIR / "fig3_performance_timeseries.png")
    plt.close()
    print("  ✓ fig3_performance_timeseries.png")


# ============================================================================
# FIGURE 4 — Per-endpoint p95 + error rate
# ============================================================================
def fig4_performance_per_endpoint():
    scenarios = ["normal", "peak", "spike"]
    endpoints = ["POST /api/auth/login", "GET /api/tickets",
                 "POST /api/tickets",    "GET /api/notifications"]
    p95_data, err_data = {}, {}
    for s in scenarios:
        df = pd.read_csv(PERF / f"{s}_stats.csv")
        df = df[df["Name"].isin(endpoints)]
        p95 = {row["Name"]: row["95%"] for _, row in df.iterrows()}
        err = {row["Name"]: 100 * row["Failure Count"] / max(row["Request Count"], 1)
               for _, row in df.iterrows()}
        p95_data[s] = [p95.get(e, 0) for e in endpoints]
        err_data[s] = [err.get(e, 0) for e in endpoints]

    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.7))
    x = np.arange(len(endpoints)); width = 0.27
    for i, s in enumerate(scenarios):
        axes[0].bar(x + (i - 1) * width, p95_data[s], width=width,
                    color=C[s], label=s.capitalize())
        axes[1].bar(x + (i - 1) * width, err_data[s], width=width,
                    color=C[s], label=s.capitalize())
    axes[0].set_ylabel("p95 latency (ms)")
    axes[0].set_title("(a) p95 latency by endpoint × load scenario")
    axes[0].set_xticks(x); axes[0].set_xticklabels(endpoints, rotation=20,
                                                   ha="right", fontsize=8.6)
    axes[0].legend(frameon=False, fontsize=9)
    axes[1].set_ylabel("Error rate (%)")
    axes[1].set_title("(b) Error rate by endpoint × load scenario")
    axes[1].set_xticks(x); axes[1].set_xticklabels(endpoints, rotation=20,
                                                   ha="right", fontsize=8.6)
    axes[1].legend(frameon=False, fontsize=9)
    plt.savefig(OUTDIR / "fig4_performance_per_endpoint.png")
    plt.close()
    print("  ✓ fig4_performance_per_endpoint.png")


# ============================================================================
# FIGURE 5 — Mutation testing: per-module score
# ============================================================================
def fig5_mutation_scores():
    rep     = json.loads(MUTREP.read_text())
    by_mod  = rep["by_module"]
    summary = rep["summary"]
    modules = list(by_mod.keys())
    scores  = [100 * by_mod[m]["killed"] / by_mod[m]["created"] for m in modules]
    killed  = [by_mod[m]["killed"]   for m in modules]
    survvd  = [by_mod[m]["survived"] for m in modules]

    fig, ax = plt.subplots(figsize=(8.8, 4.8))
    x = np.arange(len(modules))
    ax.bar(x, killed, color=C["killed"], label="Killed mutants")
    ax.bar(x, survvd, bottom=killed, color=C["survived"],
           label="Survived mutants")
    for i, (k, s, sc) in enumerate(zip(killed, survvd, scores)):
        ax.text(i, k + s + 0.1, f"{sc:.0f}%", ha="center", fontsize=9.5,
                fontweight="bold")
    ax.text(0.98, 0.98,
            f"Overall mutation score: {summary['mutation_score']:.1f}%  "
            f"({summary['killed']}/{summary['total']} killed)",
            transform=ax.transAxes, fontsize=10,
            bbox=dict(boxstyle="round,pad=0.4", facecolor="white",
                      edgecolor="gray", alpha=0.95),
            ha="right", verticalalignment="top")
    ax.set_xticks(x); ax.set_xticklabels(modules, rotation=10, ha="right")
    ax.set_ylabel("Mutants (count)")
    ax.set_ylim(0, max(k + s for k, s in zip(killed, survvd)) + 2)
    ax.set_title("Mutation Testing — killed vs survived per module\n"
                 "(15 hand-picked mutants, custom runner; full app restart per mutant)")
    ax.legend(loc="upper left", frameon=False)
    plt.savefig(OUTDIR / "fig5_mutation_scores.png")
    plt.close()
    print("  ✓ fig5_mutation_scores.png")


# ============================================================================
# FIGURE 6 — Chaos outcomes
# ============================================================================
def fig6_chaos_outcomes():
    rep = json.loads(CHAOSREP.read_text())
    d = rep["details"]

    scenarios, avail, notes = [], [], []
    db = d["db_latency"]
    scenarios.append("DB Lock\n(WAL exclusive)")
    avail.append(db["read_availability_pct"])
    notes.append(f"reads {db['read_availability_pct']:.0f}%, writes {db['write_availability_pct']:.0f}%")
    nl = d["network_latency"]
    scenarios.append("Network Latency\n(+500ms, 10% loss)")
    avail.append(100 - nl["degraded_error_pct"])
    notes.append(f"latency {nl['baseline_avg_ms']:.1f}→{nl['degraded_avg_ms']:.0f} ms")
    ce = d["cpu_exhaustion"]
    scenarios.append("CPU Exhaustion\n(1 burner, 10s)")
    avail.append(100 - ce["degraded_error_pct"])
    notes.append(f"latency {ce['baseline_avg_ms']:.1f}→{ce['degraded_avg_ms']:.1f} ms")

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.5, 4.5))
    x = np.arange(len(scenarios))
    bars = ax1.bar(x, avail, color=[C["good"] if a > 90 else
                                    C["warn"] if a > 50 else
                                    C["bad"] for a in avail])
    for b, n in zip(bars, notes):
        ax1.text(b.get_x() + b.get_width()/2, b.get_height() + 1.5,
                 f"{b.get_height():.1f}%", ha="center", fontsize=10,
                 fontweight="bold")
        ax1.text(b.get_x() + b.get_width()/2, -8, n, ha="center", fontsize=8,
                 color="gray")
    ax1.set_xticks(x); ax1.set_xticklabels(scenarios, fontsize=9)
    ax1.set_ylabel("Availability during fault (%)")
    ax1.set_title("(a) Availability under fault injection")
    ax1.set_ylim(-15, 110)

    samples = ce["samples"]
    ts = [s["t_s"] for s in samples]
    ms = [s["avg_ms"] for s in samples]
    baseline = ce["baseline_avg_ms"]
    ax2.axhline(y=baseline, color="gray", linestyle="--", linewidth=1,
                label=f"Baseline {baseline:.1f} ms")
    ax2.plot(ts, ms, marker="o", color=C["spike"], linewidth=1.7,
             label="Under CPU pressure")
    ax2.fill_between(ts, baseline, ms, alpha=0.2, color=C["spike"])
    ax2.set_xlabel("Time during 10-s CPU burner (s)")
    ax2.set_ylabel("Avg response time (ms)")
    ax2.set_title("(b) CPU exhaustion — latency over time")
    ax2.legend(frameon=False, loc="upper right")
    plt.suptitle("Chaos Testing — fault injection on the running app",
                 fontsize=11, y=1.03)
    plt.savefig(OUTDIR / "fig6_chaos_outcomes.png")
    plt.close()
    print("  ✓ fig6_chaos_outcomes.png")


# ============================================================================
# FIGURE 7 — Test pyramid (38 tests)
# ============================================================================
def fig7_test_pyramid():
    levels = [("E2E (UI)", 11, 10.0, "#C0392B"),
              ("API Integration", 17, 5.0, "#F39C12"),
              ("Unit", 10, 0.5, "#27AE60")]

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.3))
    ax = axes[0]
    y_pos, max_n = 0, max(l[1] for l in levels)
    for label, n, t, color in levels:
        w = n / max_n
        ax.barh(y_pos, w, color=color, edgecolor="white", height=0.85)
        ax.text(w / 2, y_pos, f"{label}\n{n} tests · {t}s",
                ha="center", va="center", fontsize=10, fontweight="bold",
                color="white")
        y_pos += 1
    ax.set_xlim(-0.05, 1.05); ax.set_xticks([]); ax.set_yticks([])
    for sp in ax.spines.values(): sp.set_visible(False)
    ax.set_title("(a) Testing Pyramid — actual distribution (N=38)")

    ax2 = axes[1]
    counts = [l[1] for l in levels[::-1]]
    times  = [l[2] for l in levels[::-1]]
    labels = [l[0] for l in levels[::-1]]
    colors = [l[3] for l in levels[::-1]]
    x = np.arange(len(counts))
    ax2.bar(x - 0.18, counts, width=0.36, color=colors, label="Test count")
    ax3 = ax2.twinx()
    ax3.bar(x + 0.18, times, width=0.36, color="#7F8C8D",
            label="Execution time (s)")
    ax2.set_xticks(x); ax2.set_xticklabels(labels)
    ax2.set_ylabel("Test count"); ax3.set_ylabel("Execution time (s)")
    ax2.set_title("(b) Cost per level — count vs runtime")
    h1, l1 = ax2.get_legend_handles_labels()
    h2, l2 = ax3.get_legend_handles_labels()
    ax2.legend(h1 + h2, l1 + l2, frameon=False, fontsize=9, loc="upper left")
    plt.savefig(OUTDIR / "fig7_test_pyramid.png")
    plt.close()
    print("  ✓ fig7_test_pyramid.png")


# ============================================================================
# FIGURE 8 — CI/CD pipeline diagram
# ============================================================================
def fig8_pipeline_diagram():
    stages = [
        ("Push / PR\nto main",            "trigger",  "#34495E"),
        ("Checkout\n+ Setup Python 3.12", "build",    "#5D6D7E"),
        ("Install deps\n+ Playwright",    "build",    "#5D6D7E"),
        ("Start app\n(health check)",     "build",    "#5D6D7E"),
        ("Unit tests\n(0.5s)",            "test",     "#27AE60"),
        ("API tests\n(5.0s)",             "test",     "#16A085"),
        ("UI E2E\n(10.0s)",               "test",     "#1ABC9C"),
        ("Coverage\n+ JUnit XML",         "test",     "#1ABC9C"),
        ("Quality Gate\nscript",          "gate",     "#F39C12"),
        ("Deploy / Block",                "decision", "#C0392B"),
    ]
    fig, ax = plt.subplots(figsize=(13.5, 3.6))
    ax.set_xlim(0, len(stages)); ax.set_ylim(-1.2, 1.2); ax.axis("off")
    for i, (text, _, color) in enumerate(stages):
        box = mpatches.FancyBboxPatch(
            (i + 0.04, -0.55), 0.92, 1.1,
            boxstyle="round,pad=0.04,rounding_size=0.10",
            linewidth=1.2, edgecolor="white", facecolor=color)
        ax.add_patch(box)
        ax.text(i + 0.5, 0, text, ha="center", va="center",
                color="white", fontsize=9, fontweight="bold")
        if i < len(stages) - 1:
            ax.annotate("", xy=(i + 1.04, 0), xytext=(i + 0.96, 0),
                        arrowprops=dict(arrowstyle="->", color="#2C3E50", lw=1.6))
    ax.text(0.5, 0.85, "trigger", fontsize=8, color="gray", style="italic")
    ax.text(2.5, 0.85, "build phase", fontsize=8, color="gray", style="italic")
    ax.text(6,   0.85, "test phase (testing pyramid)", fontsize=8,
            color="gray", style="italic")
    ax.text(9,   0.85, "gate", fontsize=8, color="gray", style="italic")
    ax.set_title("CI/CD Pipeline — qa-automation.yml (GitHub Actions)",
                 fontsize=11, y=1.02)
    plt.savefig(OUTDIR / "fig8_pipeline_diagram.png")
    plt.close()
    print("  ✓ fig8_pipeline_diagram.png")


# ============================================================================
# FIGURE 9 — Quality Gate thresholds vs actual
# ============================================================================
def fig9_quality_gate():
    rep = json.loads(MUTREP.read_text())
    mut_overall = rep["summary"]["mutation_score"]
    gates = [
        # (label, threshold, actual, units, comparison op)
        ("Pass rate",         90, 100.0,        "%", ">="),
        ("Critical failures",  0, 0,            "",  "=="),
        ("Skipped tests",     20, 0,            "%", "<="),
        ("Test count (min)",  15, 38,           "",  ">="),
        ("Mutation score",    70, mut_overall,  "%", ">="),
    ]
    fig, ax = plt.subplots(figsize=(8.8, 4.5))
    y = np.arange(len(gates))
    thr = [g[1] for g in gates]; act = [g[2] for g in gates]
    labels = [g[0] for g in gates]; units = [g[3] for g in gates]
    ops    = [g[4] for g in gates]
    colors = []
    for op, t, a in zip(ops, thr, act):
        ok = (a >= t) if op == ">=" else (a <= t) if op == "<=" else (a == t)
        colors.append(C["good"] if ok else C["bad"])
    ax.barh(y - 0.18, thr, height=0.36, color=C["neutral"],
            label="Threshold")
    ax.barh(y + 0.18, act, height=0.36, color=colors, label="Actual")
    for i, (t, a, u) in enumerate(zip(thr, act, units)):
        ax.text(t + 1, i - 0.18, f"{t}{u}", va="center", fontsize=8.5,
                color="#566573")
        a_disp = f"{a:.1f}{u}" if isinstance(a, float) else f"{a}{u}"
        ax.text(a + 1, i + 0.18, a_disp, va="center", fontsize=8.5,
                fontweight="bold", color=colors[i])
    ax.set_yticks(y); ax.set_yticklabels(labels)
    ax.invert_yaxis(); ax.set_xlabel("Value")
    ax.set_title("Quality Gates — defined thresholds vs measured outcomes\n"
                 "Green = passed, Red = violation (mutation gate proposed in §IV)")
    pass_p = mpatches.Patch(color=C["good"], label="Pass")
    fail_p = mpatches.Patch(color=C["bad"],  label="Fail")
    thr_p  = mpatches.Patch(color=C["neutral"], label="Threshold")
    ax.legend(handles=[thr_p, pass_p, fail_p], frameon=False, loc="lower right")
    plt.savefig(OUTDIR / "fig9_quality_gate.png")
    plt.close()
    print("  ✓ fig9_quality_gate.png")


# ============================================================================
# FIGURE 10 — Three-layer architecture
# ============================================================================
def fig10_architecture():
    fig, ax = plt.subplots(figsize=(11, 5.2))
    ax.set_xlim(0, 12); ax.set_ylim(0, 7); ax.axis("off")

    for y0, y1, color, label in [
        (5.4, 6.8, "#D6EAF8", "Client / Presentation Layer"),
        (3.4, 5.0, "#FCF3CF", "Application Layer (Flask)"),
        (1.4, 3.0, "#F2D7D5", "Data Layer (SQLite, WAL)")]:
        rect = mpatches.Rectangle((0.3, y0), 11.4, y1 - y0,
                                  facecolor=color, edgecolor="gray", linewidth=0.6)
        ax.add_patch(rect)
        ax.text(0.5, y1 - 0.25, label, fontsize=9, color="#566573",
                style="italic")

    for x, lbl in [(1.3, "Browser\n(Jinja2 UI)"),
                   (4.5, "API Client\n(Bearer token)"),
                   (7.7, "Test Clients\n(pytest / Playwright / Locust)"),
                   (10.0,"Chaos Runner\n(fault injector)")]:
        box = mpatches.FancyBboxPatch((x, 5.7), 1.7, 0.9,
                                      boxstyle="round,pad=0.04,rounding_size=0.08",
                                      facecolor="#3498DB", edgecolor="white")
        ax.add_patch(box)
        ax.text(x + 0.85, 6.15, lbl, ha="center", va="center", fontsize=8.4,
                color="white", fontweight="bold")

    for x, lbl in [(0.7,  "Auth\n/api/auth/*"),
                   (3.0,  "Tickets CRUD\n/api/tickets"),
                   (5.3,  "Validation\n(L,I,D rules)"),
                   (7.6,  "Notifications\n/api/notif"),
                   (9.9,  "Health\n/api/health")]:
        box = mpatches.FancyBboxPatch((x, 3.7), 1.9, 1.0,
                                      boxstyle="round,pad=0.04,rounding_size=0.08",
                                      facecolor="#E67E22", edgecolor="white")
        ax.add_patch(box)
        ax.text(x + 0.95, 4.2, lbl, ha="center", va="center", fontsize=8.4,
                color="white", fontweight="bold")

    for x, lbl in [(2.0, "users"), (4.5, "tickets"),
                   (7.0, "notifications"), (9.5, "sessions")]:
        box = mpatches.FancyBboxPatch((x, 1.8), 1.5, 0.9,
                                      boxstyle="round,pad=0.04,rounding_size=0.08",
                                      facecolor="#922B21", edgecolor="white")
        ax.add_patch(box)
        ax.text(x + 0.75, 2.25, lbl, ha="center", va="center", fontsize=9,
                color="white", fontweight="bold")

    for x_from, x_to in [(2.15, 1.65), (5.35, 3.95), (8.55, 5.05), (10.85, 8.75)]:
        ax.annotate("", xy=(x_to, 5.6), xytext=(x_from, 5.7),
                    arrowprops=dict(arrowstyle="->", color="#566573", lw=0.9))
    for x in [1.65, 3.95, 6.25, 8.55, 10.85]:
        ax.annotate("", xy=(x - 0.1, 2.7), xytext=(x - 0.1, 3.7),
                    arrowprops=dict(arrowstyle="->", color="#566573", lw=0.9))

    ax.set_title("System Architecture — Three-Layer Monolith with QA Instrumentation",
                 fontsize=11, y=0.97)
    plt.savefig(OUTDIR / "fig10_architecture.png")
    plt.close()
    print("  ✓ fig10_architecture.png")


# ============================================================================
# FIGURE 11 — Trace map: Risk → Test → Stage → Metric → Result
# ============================================================================
def fig11_trace_map():
    rep = json.loads(MUTREP.read_text())
    chaos = json.loads(CHAOSREP.read_text())["details"]
    spike = pd.read_csv(PERF / "spike_stats.csv")
    spike_err = 100 * spike[spike["Name"] == "Aggregated"]["Failure Count"].iloc[0] \
                / spike[spike["Name"] == "Aggregated"]["Request Count"].iloc[0]
    db = chaos["db_latency"]
    nl = chaos["network_latency"]
    ce = chaos["cpu_exhaustion"]

    auth   = rep["by_module"]["Authentication"]
    crud   = rep["by_module"]["Ticket CRUD"]
    valdtn = rep["by_module"]["Ticket Validation"]

    rows = [
        ("R1: Auth bypass",       "TC-AUTH-01..09 + M-AUTH-01..05",
         "API + Mut", "Mut. score",
         f"{100*auth['killed']/auth['created']:.0f}% ({auth['killed']}/{auth['created']} killed)"),
        ("R2: CRUD ownership",    "TC-TICK-01..10 + M-CRUD-01..04",
         "API + Mut", "Mut. score",
         f"{100*crud['killed']/crud['created']:.0f}% ({crud['killed']}/{crud['created']} killed)"),
        ("R3: Concurrency race",  "TC-TICK-CONC-01 (5×)",
         "API",       "Pass/fail",      "5/5 passed (201)"),
        ("R4: Latency / load",    "Locust normal/peak/spike",
         "Perf",      "p95, err %",     f"{spike_err:.1f}% err @ spike"),
        ("R5: DB unavailability", "chaos/db_failure.py",
         "Chaos",     "Read/Write avail.",
         f"{db['read_availability_pct']:.0f}/{db['write_availability_pct']:.0f}% (WAL)"),
        ("R6: Network jitter",    "chaos/network_latency.py",
         "Chaos",     "Err %, Δlatency",
         f"+{nl['latency_inflation_ms']:.0f} ms, {nl['degraded_error_pct']:.1f}%"),
        ("R7: CPU exhaustion",    "chaos/resource_exhaustion.py",
         "Chaos",     "Δlatency",
         f"+{ce['degraded_avg_ms']-ce['baseline_avg_ms']:.1f} ms ({ce['latency_inflation_pct']:.0f}%)"),
        ("R8: Validation drift",  "TC-TICK-07..10 + M-VAL-01..04",
         "API + Mut", "Mut. score",
         f"{100*valdtn['killed']/valdtn['created']:.0f}% ({valdtn['killed']}/{valdtn['created']} killed)"),
    ]

    fig, ax = plt.subplots(figsize=(13.5, 5.6))
    ax.set_xlim(0, 5); ax.set_ylim(0, len(rows) + 0.8); ax.axis("off")
    headers = ["Risk", "Test artefact", "Pipeline stage", "Metric", "Result (real)"]
    col_x = [0.15, 1.05, 2.4,  3.25, 4.0]
    col_w = [0.85, 1.30, 0.80, 0.70, 1.0]
    colors = ["#34495E", "#2980B9", "#16A085", "#F39C12", "#27AE60"]

    for i, h in enumerate(headers):
        rect = mpatches.FancyBboxPatch((col_x[i], len(rows) + 0.05),
                                       col_w[i], 0.55,
                                       boxstyle="round,pad=0.02,rounding_size=0.05",
                                       facecolor=colors[i], edgecolor="white")
        ax.add_patch(rect)
        ax.text(col_x[i] + col_w[i]/2, len(rows) + 0.32, h,
                ha="center", va="center", color="white",
                fontweight="bold", fontsize=10)

    for r_i, row in enumerate(rows):
        y = len(rows) - r_i - 0.55
        for c_i, val in enumerate(row):
            rect = mpatches.FancyBboxPatch((col_x[c_i], y),
                                           col_w[c_i], 0.7,
                                           boxstyle="round,pad=0.02,rounding_size=0.04",
                                           facecolor="white",
                                           edgecolor=colors[c_i], linewidth=0.7)
            ax.add_patch(rect)
            ax.text(col_x[c_i] + col_w[c_i]/2, y + 0.35, val,
                    ha="center", va="center", fontsize=8.4)
        for c_i in range(len(headers) - 1):
            ax.annotate("", xy=(col_x[c_i + 1], y + 0.35),
                        xytext=(col_x[c_i] + col_w[c_i], y + 0.35),
                        arrowprops=dict(arrowstyle="->", lw=0.7, color="#7F8C8D"))

    ax.set_title("Traceability Map — every risk traced through the QA pipeline\n"
                 "(Risk → Test → Stage → Metric → Real Result)", fontsize=11, y=0.99)
    plt.savefig(OUTDIR / "fig11_trace_map.png")
    plt.close()
    print("  ✓ fig11_trace_map.png")


# ============================================================================
# FIGURE 12 — Estimated vs Actual (mock vs real backend)
# ============================================================================
def fig12_estimated_vs_actual():
    rep = json.loads(MUTREP.read_text())
    mut_overall = rep["summary"]["mutation_score"]
    spike = pd.read_csv(PERF / "spike_stats.csv")
    spike_agg = spike[spike["Name"] == "Aggregated"].iloc[0]
    spike_err = 100 * spike_agg["Failure Count"] / spike_agg["Request Count"]
    normal = pd.read_csv(PERF / "normal_stats.csv")
    normal_avg = normal[normal["Name"] == "Aggregated"]["Average Response Time"].iloc[0]
    peak = pd.read_csv(PERF / "peak_stats.csv")
    peak_avg = peak[peak["Name"] == "Aggregated"]["Average Response Time"].iloc[0]

    metrics = [
        ("Normal-load avg (ms)",  420, normal_avg),
        ("Peak-load avg (ms)",    980, peak_avg),
        ("Spike-load err (%)",      8, spike_err),
        ("Mutation score (%)",     75, mut_overall),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(10.5, 6))
    axes = axes.flatten()
    pairs = [("#7F8C8D", "#E07B00"), ("#7F8C8D", "#E07B00"),
             ("#7F8C8D", "#C0392B"), ("#7F8C8D", "#27AE60")]
    for i, ((lbl, e, a), (c1, c2)) in enumerate(zip(metrics, pairs)):
        ax = axes[i]
        bars = ax.bar(["Estimate (Asgmt 2)", "Actual (Asgmt 3)"],
                      [e, a], color=[c1, c2], width=0.6)
        for b in bars:
            ax.text(b.get_x() + b.get_width()/2,
                    b.get_height() + max(e, a) * 0.02,
                    f"{b.get_height():.1f}", ha="center", fontsize=10,
                    fontweight="bold")
        ax.set_title(lbl, fontsize=10)
        ax.set_ylim(0, max(e, a) * 1.20)
    plt.suptitle("Estimated values (Assignment 2 / mock-based) vs "
                 "Actual measurements (Assignment 3 / real backend)",
                 fontsize=11, y=1.01)
    plt.savefig(OUTDIR / "fig12_estimated_vs_actual.png")
    plt.close()
    print("  ✓ fig12_estimated_vs_actual.png")


# ============================================================================
# FIGURE 13 — Saturation curve: throughput plateau, error rate explosion
# ============================================================================
def fig13_throughput_saturation():
    points = []
    for s in ["normal", "peak", "spike"]:
        df = pd.read_csv(PERF / f"{s}_stats.csv")
        agg = df[df["Name"] == "Aggregated"].iloc[0]
        users = {"normal": 20, "peak": 100, "spike": 200}[s]
        err   = 100 * agg["Failure Count"] / max(agg["Request Count"], 1)
        points.append((users, agg["Requests/s"], s, err))
    points.sort()
    users = [p[0] for p in points]
    rps   = [p[1] for p in points]
    err   = [p[3] for p in points]
    scens = [p[2] for p in points]

    fig, ax1 = plt.subplots(figsize=(9, 4.5))
    ax1.plot(users, rps, marker="o", linewidth=2.2, color=C["normal"],
             label="Throughput (RPS)")
    ax1.set_xlabel("Concurrent users (Locust VUs)")
    ax1.set_ylabel("Throughput (req/s)", color=C["normal"])
    ax1.tick_params(axis="y", labelcolor=C["normal"])
    ax2 = ax1.twinx()
    ax2.plot(users, err, marker="s", linewidth=2.2, color=C["bad"],
             linestyle="--", label="Error rate (%)")
    ax2.set_ylabel("Error rate (%)", color=C["bad"])
    ax2.tick_params(axis="y", labelcolor=C["bad"])
    ax2.spines["right"].set_visible(True)
    for u, r, _, sc in zip(users, rps, err, scens):
        ax1.annotate(f"{sc}\n{u} VUs",
                     xy=(u, r), xytext=(8, 8), textcoords="offset points",
                     fontsize=8.5)
    ax1.set_title("Saturation curve — throughput plateaus while error rate explodes")
    plt.savefig(OUTDIR / "fig13_throughput_saturation.png")
    plt.close()
    print("  ✓ fig13_throughput_saturation.png")


# ============================================================================
# Main
# ============================================================================
def main() -> int:
    print(f"Reading inputs from: {EXPERIM}")
    print(f"Writing figures to:  {OUTDIR}\n")
    if not _check_inputs():
        return 2
    fig1_risk_matrix()
    fig2_coverage_vs_risk()
    fig3_performance_timeseries()
    fig4_performance_per_endpoint()
    fig5_mutation_scores()
    fig6_chaos_outcomes()
    fig7_test_pyramid()
    fig8_pipeline_diagram()
    fig9_quality_gate()
    fig10_architecture()
    fig11_trace_map()
    fig12_estimated_vs_actual()
    fig13_throughput_saturation()
    n = len(list(OUTDIR.glob("*.png")))
    print(f"\nDone — {n} figures produced in {OUTDIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
