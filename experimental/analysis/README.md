# Analysis Pipeline (Assignment 4 / Endterm)

This folder turns the raw experimental data produced by Assignment 3 into
the figures and tables the research paper needs.

## What it does

It reads the JSON / CSV files that the experimental suite already wrote to
`experimental/{performance,mutation,chaos}/results/`, and produces:

1. **13 publication-ready PNG figures** in `figures/` (300 DPI, IEEE-paper
   styled). Used directly in the paper.
2. **One Markdown report** `analysis_report.md` with every quantitative
   number the paper references — performance tables per scenario, mutation
   per-module breakdown, chaos availability / MTTR, derived insights
   (saturation point, latency inflation, mock-vs-real comparison).

The Markdown report is the **single source of truth** for the Results
section of the paper. Every number traces back to a file in
`experimental/*/results/`. No values are hand-coded.

## Folder contents

```
experimental/analysis/
├── README.md                   # this file
├── generate_figures.py         # produces figures/*.png
├── generate_report.py          # produces analysis_report.md
├── run_analysis.sh             # runs both, in order, with deps install
├── requirements.txt            # matplotlib + pandas + numpy
├── __init__.py                 # marks as a Python package
└── figures/                    # output — committed for convenience
    ├── fig1_risk_matrix.png
    ├── fig2_coverage_vs_risk.png
    ├── fig3_performance_timeseries.png
    ├── fig4_performance_per_endpoint.png
    ├── fig5_mutation_scores.png
    ├── fig6_chaos_outcomes.png
    ├── fig7_test_pyramid.png
    ├── fig8_pipeline_diagram.png
    ├── fig9_quality_gate.png
    ├── fig10_architecture.png
    ├── fig11_trace_map.png
    ├── fig12_estimated_vs_actual.png
    └── fig13_throughput_saturation.png
```

## How to run

The figures are already pre-generated and checked in, so **you do not need
to run anything to use them in the paper**. The pipeline exists for
reproducibility — anyone (the grader, a co-author, future you) can rerun
it and get byte-identical outputs.

If you do want to regenerate everything from scratch:

```bash
# From the project root
bash experimental/analysis/run_analysis.sh
```

The script:

1. Installs the three Python deps (matplotlib, pandas, numpy) into the
   current environment.
2. Runs `generate_figures.py` → 13 PNG files.
3. Runs `generate_report.py` → `analysis_report.md`.

Or step-by-step:

```bash
pip install -r experimental/analysis/requirements.txt
python experimental/analysis/generate_figures.py
python experimental/analysis/generate_report.py
```

## Inputs (read-only — never modified)

| File                                                      | Used for                  |
|-----------------------------------------------------------|---------------------------|
| `experimental/performance/results/normal_stats.csv`       | Fig 4, 12, 13; report §1.1|
| `experimental/performance/results/peak_stats.csv`         | Fig 4, 12, 13; report §1.2|
| `experimental/performance/results/spike_stats.csv`        | Fig 4, 12, 13; report §1.3|
| `experimental/performance/results/*_stats_history.csv`    | Fig 3                     |
| `experimental/mutation/results/mutation_report.json`      | Fig 2, 5, 9, 11, 12; §2   |
| `experimental/chaos/results/chaos_report.json`            | Fig 6, 11; report §3      |

If any of these files is missing, `generate_figures.py` prints exactly
which file is missing and how to regenerate it (by re-running the
relevant `experimental/*/run_*.sh` script).

## Why this folder exists (research-paper context)

Assignment 4 grading explicitly requires:

> Reproducibility — How can someone reproduce your results?

and

> Consistency — same metrics across Methodology, Results, and Discussion.

Embedding numbers directly in the paper text (or in spreadsheets that
nobody else can rerun) violates both. This pipeline solves that:

* Every number in the paper is sourced from one Markdown file.
* That Markdown file is sourced from version-controlled raw data.
* The pipeline is one shell command and three Python deps.

## Troubleshooting

**`ModuleNotFoundError: matplotlib` (or pandas, numpy)**
Run `pip install -r experimental/analysis/requirements.txt`.

**`ERROR — missing input files: …`**
The experimental suite hasn't been run yet. Run:

```bash
bash experimental/performance/run_performance.sh
bash experimental/mutation/run_mutation.sh
bash experimental/chaos/run_chaos.sh --skip-api-kill
```

**Figures look slightly different from the ones in the paper**
That's expected if the experiments were re-run on a different machine —
absolute latencies depend on the host. The shape of the curves and the
relative rankings (which mutants survive, which scenarios saturate)
should be identical.
