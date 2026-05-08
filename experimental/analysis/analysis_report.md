# Analysis Report — Assignment 4 / Endterm

_Auto-generated from raw experimental data. Do not edit by hand — regenerate via `python experimental/analysis/generate_report.py`._

This document contains every quantitative result the paper
references, computed directly from the JSON / CSV files in
`experimental/{performance,mutation,chaos}/results/`.

## 1. Performance Testing

**Tool:** Locust 2.x. Three load scenarios on the Flask dev server with SQLite (WAL).

### Aggregate summary across scenarios

| Scenario | Users | Duration | Requests | RPS | Avg (ms) | p95 (ms) | Errors (%) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Normal | 20 | 30 s | 111 | 4.06 | 2702 | 8300 | **0.00** |
| Peak | 100 | 60 s | 1139 | 18.77 | 2851 | 10000 | **2.55** |
| Spike | 200 | 30 s | 515 | 18.33 | 4200 | 12000 | **62.33** |

### 1.1 Normal load — 20 VUs, 30 s

| Endpoint | Requests | Avg (ms) | Median (ms) | p95 (ms) | Throughput (rps) | Errors (%) |
|---|---:|---:|---:|---:|---:|---:|
| GET /api/notifications | 20 | 1035 | 1000 | 1400 | 0.73 | 0.00 |
| GET /api/tickets | 48 | 5136 | 4200 | 8800 | 1.76 | 0.00 |
| POST /api/auth/login | 20 | 1027 | 990 | 1500 | 0.73 | 0.00 |
| POST /api/tickets | 23 | 529 | 510 | 800 | 0.84 | 0.00 |
| Aggregated | 111 | 2702 | 1200 | 8300 | 4.06 | 0.00 |

### 1.2 Peak load — 100 VUs, 60 s

| Endpoint | Requests | Avg (ms) | Median (ms) | p95 (ms) | Throughput (rps) | Errors (%) |
|---|---:|---:|---:|---:|---:|---:|
| GET /api/notifications | 229 | 1056 | 1000 | 1700 | 3.77 | 1.75 |
| GET /api/tickets | 596 | 4724 | 3900 | 11000 | 9.82 | 3.69 |
| POST /api/auth/login | 100 | 640 | 510 | 1700 | 1.65 | 0.00 |
| POST /api/tickets | 214 | 589 | 520 | 1100 | 3.53 | 1.40 |
| Aggregated | 1139 | 2851 | 1300 | 10000 | 18.77 | 2.55 |

### 1.3 Spike load — 200 VUs, 30 s

| Endpoint | Requests | Avg (ms) | Median (ms) | p95 (ms) | Throughput (rps) | Errors (%) |
|---|---:|---:|---:|---:|---:|---:|
| GET /api/notifications | 75 | 2770 | 2 | 8300 | 2.67 | 66.67 |
| GET /api/tickets | 250 | 3571 | 2 | 12000 | 8.90 | 80.40 |
| POST /api/auth/login | 110 | 7871 | 6800 | 21000 | 3.92 | 9.09 |
| POST /api/tickets | 80 | 2459 | 3 | 7500 | 2.85 | 75.00 |
| Aggregated | 515 | 4200 | 4300 | 12000 | 18.33 | 62.33 |

## 2. Mutation Testing

**Tool:** Custom deterministic runner (full app restart per mutant). 15 hand-picked mutants from the risk model.

**Overall mutation score: 66.7%** (10/15 killed, 5 survived).

### Per-module breakdown

| Module | Created | Killed | Survived | Mutation score |
|---|---:|---:|---:|---:|
| Authentication | 5 | 4 | 1 | **80.0%** |
| Ticket Validation | 4 | 3 | 1 | **75.0%** |
| Ticket CRUD | 4 | 2 | 2 | **50.0%** |
| Notifications | 2 | 1 | 1 | **50.0%** |

### Surviving mutants (real coverage gaps)

| ID | Module | Mutation type | Description |
|---|---|---|---|
| `M-AUTH-03` | Authentication | Boolean short-circuit removal | Change OR to AND in credential check — weakens validation. |
| `M-VAL-02` | Ticket Validation | Tuple member removal | 'critical' priority no longer accepted — regression. |
| `M-CRUD-02` | Ticket CRUD | SQL WHERE clause removal | User filter removed from list query — privacy leak. |
| `M-CRUD-04` | Ticket CRUD | Default value change | Default priority changed — may affect downstream logic. |
| `M-NOTIF-02` | Notifications | Boolean field mutation | 'Mark as read' actually marks as unread. |

## 3. Chaos / Fault-Injection Testing

Total elapsed: 46.3 s. Target: `http://localhost:8080`.

### 3.1 DB Latency — exclusive-lock scenario

- Read availability: **100 %**
- Write availability: **0 %**
- Avg write latency under lock: 3003 ms
- MTTR: 0.01 s
- Error propagation: 100 %
- _Write operations stall; reads may still succeed (WAL mode)._

### 3.2 Network Latency — +500 ms, 10 % packet loss

- Baseline avg: 3.5 ms → degraded avg: **507 ms** (+504 ms)
- Baseline error: 0.0 % → degraded error: **8.7 %**
- Recovery avg: 3.5 ms
- MTTR: instant (proxy stop)
- _Client-visible slowdown; retries amplify load on upstream._

### 3.3 CPU Exhaustion — 1 burner, 10 s

- Baseline avg: 4.7 ms → degraded avg: **5.5 ms** (+18 %)
- Recovery avg: 4.6 ms
- MTTR: 0.32 s
- Errors during fault: 0.0 %
- _App still responds but slow; no graceful degradation observed._


## 4. Derived Insights (for Discussion)

### 4.1 Saturation point

- Throughput is roughly the same at peak (18.77 rps, 100 VUs) and spike (18.33 rps, 200 VUs) → **throughput plateau between 100 and 200 VUs**.
- Error rate jumps from 2.5 % → 62.3 % over the same range → **system saturates near 100 VUs**, then enters the "server queue overflow" regime.

### 4.2 Latency inflation

- Normal → peak avg latency: 2702 → 2851 ms (1.06×).
- Peak → spike avg latency: 2851 → 4200 ms (1.47×).
- Spike p95: 12000 ms — ≈ 2.9× the average; long tail dominates.

### 4.3 Mock-based vs real-backend numbers

| Metric | Estimate (Asgmt 2, mock) | Actual (Asgmt 3, real) | Gap |
|---|---:|---:|---:|
| Normal-load avg (ms) | 420 | 2702.0 | +543 % |
| Peak-load avg (ms) | 980 | 2851.0 | +191 % |
| Spike-load err (%) | 8 | 62.3 | +679 % |
