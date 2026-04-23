# Assignment 3 — Experimental Testing

This folder contains Performance, Mutation, and Chaos testing implementations
for the midterm Ticket Management System.

## Layout

```
experimental/
├── performance/
│   ├── k6/                       # k6 JavaScript load tests (primary)
│   │   ├── common.js             # shared helpers (login, CRUD flow, metrics)
│   │   ├── normal_load.js        # 20 VUs, 2 min
│   │   ├── peak_load.js          # 100 VUs, 5 min
│   │   ├── spike_load.js         # 10→200 VU spike, 2 min
│   │   └── endurance.js          # 50 VUs, ~10 min
│   ├── locust/locustfile.py      # Python alternative to k6
│   ├── run_performance.sh        # runs all 4 scenarios
│   └── results/                  # JSON summaries from k6
├── mutation/
│   ├── custom_mutation.py        # 15 hand-picked mutants, self-contained
│   ├── setup.cfg                 # mutmut config (backup option)
│   ├── run_mutation.sh
│   └── results/mutation_report.json
├── chaos/
│   ├── scenarios/
│   │   ├── api_downtime.py       # kill + restart the app
│   │   ├── db_failure.py         # DB unavailable / exclusive lock
│   │   ├── network_latency.py    # TCP proxy adds delay + packet loss
│   │   └── resource_exhaustion.py # CPU / memory hog
│   ├── chaos_runner.py           # orchestrates all scenarios
│   ├── run_chaos.sh
│   └── results/chaos_report.json
├── requirements-experimental.txt
└── README.md                     # this file
```

## Prerequisites

From the project root:

```bash
# 1. Virtualenv (re-use the one from the midterm)
python3 -m venv .venv
source .venv/bin/activate

# 2. Dependencies
pip install -r requirements.txt
pip install -r experimental/requirements-experimental.txt

# 3. k6 (skip if you only use locust)
# macOS:     brew install k6
# Linux:     sudo apt-get install k6   (after adding the repo — see CI yml)
# Windows:   winget install k6
```

## Running everything — step by step

### Terminal 1 — start the app

```bash
python -m app.main
# leave this running. Should print: Running on http://0.0.0.0:8080
```

### Terminal 2 — run the tests

```bash
# 1. Performance (~15 minutes for full suite)
bash experimental/performance/run_performance.sh

# 2. Mutation testing (~2-5 minutes, 15 mutants × ~10s each)
bash experimental/mutation/run_mutation.sh

# 3. Chaos testing (~2 minutes)
#    --skip-api-kill avoids the scenario that kills the app.
#    Drop it when you want the full test.
bash experimental/chaos/run_chaos.sh --skip-api-kill
```

### Run just one scenario

```bash
# k6 single scenario
k6 run experimental/performance/k6/normal_load.js

# Single chaos scenario
python experimental/chaos/scenarios/db_failure.py --mode latency
python experimental/chaos/scenarios/network_latency.py
python experimental/chaos/scenarios/resource_exhaustion.py
```

## Results produced

| File                                             | Contents                                     |
|--------------------------------------------------|----------------------------------------------|
| `performance/results/normal_load_summary.json`   | k6 metrics — latency, throughput, errors     |
| `performance/results/peak_load_summary.json`     | same                                         |
| `performance/results/spike_load_summary.json`    | same                                         |
| `performance/results/endurance_summary.json`     | same                                         |
| `mutation/results/mutation_report.json`          | mutants, kill/survive, per-module score      |
| `chaos/results/chaos_report.json`                | availability, MTTR, error propagation        |

These are the files the report draws its numbers from — no hard-coded values.

## Design choices worth knowing about

**Why a custom mutation runner instead of pure mutmut?**  mutmut is fine, but
it bakes in a lot of assumptions about project layout and uses SQLite state
files in the working dir. The custom runner has a fixed, version-controlled
mutant list (15 mutations chosen from the risk analysis) so the mutation
score is reproducible across machines. `mutmut` is still installed as a
backup if a reviewer wants to cross-check.

**Why not use `tc` / `iptables` for network chaos?**  Both need root and
`NET_ADMIN`, which fail in most CI runners and sandboxes. The in-process
TCP proxy in `network_latency.py` is less realistic but portable.

**Why run chaos LAST in the CI workflow?**  Some chaos scenarios kill and
restart the app. If they fail to restart, subsequent steps would all fail.
Running them last localises the blast radius. In local runs we default to
`--skip-api-kill` for the same reason.

**Why a separate CI workflow?**  Performance + mutation + chaos runs take
30+ minutes. Running them on every push burns CI minutes and annoys
reviewers with slow feedback. `experimental.yml` is manual-trigger only
(or on `experimental-*` tags).

## Troubleshooting

- **`k6: command not found`** — install k6, or use the locust fallback
  (`run_performance.sh` detects this automatically).
- **Mutation baseline fails** — the pytest suite must pass against the
  unmodified code before mutation starts. Fix the test suite first.
- **Chaos `lsof: command not found`** — the API-downtime scenario needs
  `lsof` to find the app PID. On Ubuntu: `sudo apt-get install lsof`.
  On minimal containers, skip with `--skip-api-kill`.
- **`Address already in use` on the proxy port** — something else grabbed
  port 8088. Change `proxy_port` in `network_latency.py`.
