# QA Midterm Project — Centralized Ticket Management System

**Authors:** Azamatov Almaz, Takayev Askhat

A Flask + SQLite ticket management system used as the case study for
risk-based QA, automated CI/CD testing, mutation testing, performance
testing, and chaos engineering.

## Layout

```
├── app/                        # Flask application + Jinja2 templates
├── tests/                      # 38-test suite — unit + API + UI (E2E)
├── utils/                      # API client, page objects, logger
├── config/                     # settings loader
├── experimental/               # ASSIGNMENT 3 — performance / mutation / chaos
│   ├── performance/            # Locust + k6 load-test scripts + raw results
│   ├── mutation/               # custom 15-mutant runner + JSON results
│   ├── chaos/                  # fault-injection scenarios + JSON results
│   └── analysis/               # ASSIGNMENT 4 — figures + Markdown report
├── .github/workflows/          # qa-automation.yml + experimental.yml
├── quality_gate.py             # parses JUnit XML, enforces 4 thresholds
├── docker-compose.yml          # local containerised run
└── requirements.txt
```

## Quick start

```bash
# 1. Setup
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install --with-deps chromium

# 2. Run the app
python -m app.main      # http://localhost:8080  (test.user / ChangeMe123!)

# 3. Run the test suite (in a second terminal)
pytest -v               # ~15 s for all 38 tests
```

## Quality gate

```bash
pytest --junitxml=test-results/pytest-report.xml
python quality_gate.py
```

Thresholds: pass rate ≥ 90 %, 0 critical failures, ≤ 20 % skipped, ≥ 15
total tests. CI fails the build if any threshold is violated.

## Experimental suite (Assignment 3)

```bash
bash experimental/performance/run_performance.sh   # ~15 min — Locust load tests
bash experimental/mutation/run_mutation.sh         # ~3 min — 15 mutants
bash experimental/chaos/run_chaos.sh --skip-api-kill   # ~2 min — fault injection
```

See `experimental/README.md` and `experimental/REAL_RESULTS.md` for the
full breakdown.

## Analysis pipeline (Assignment 4)

```bash
bash experimental/analysis/run_analysis.sh
```

Reads the experimental results above and produces:

* `experimental/analysis/figures/*.png` — 13 figures used in the paper
* `experimental/analysis/analysis_report.md` — every quantitative result
  the paper references, computed from raw data

See `experimental/analysis/README.md` for details.
