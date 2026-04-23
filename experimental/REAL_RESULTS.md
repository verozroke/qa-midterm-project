# Real Experimental Results — Assignment 3

All numbers below are from actual test runs in a sandboxed Linux container
against the midterm Flask app (dev server, SQLite WAL). No hand-picked
numbers — each comes from a JSON / CSV produced by the scripts in
`experimental/*/results/`.

The setup deliberately uses Flask's built-in dev server (same as the midterm
CI) so the findings describe the exact configuration students turned in, not
a hypothetical production deployment.

---

## 1. Performance Testing (Locust)

Tool: Locust 2.x.  k6 scripts are included in `experimental/performance/k6/`
for reviewers who have k6 installed; the numbers below are from the Python
runner because the sandbox lacked k6.

### Normal Load — 20 concurrent users, 30 s

| Endpoint                | Reqs | Avg (ms) | Median | p95 (ms) | Errors |
|-------------------------|------|----------|--------|----------|--------|
| POST /api/auth/login    | 20   | 1027     | 990    | 1500     | 0 %    |
| GET  /api/tickets       | 48   | 5136     | 4200   | 8800     | 0 %    |
| POST /api/tickets       | 23   | 529      | 510    | 800      | 0 %    |
| GET  /api/notifications | 20   | 1035     | 1000   | 1400     | 0 %    |
| **Aggregated**          | 112  | **2702** | 1200   | **8300** | **0 %** |
| Throughput              | —    | —        | —      | —        | 4.06 rps |

### Peak Load — 100 concurrent users, 60 s

| Endpoint                | Reqs | Avg (ms) | p95 (ms) | Errors |
|-------------------------|------|----------|----------|--------|
| POST /api/auth/login    | 100  | 640      | 1700     | 0 %    |
| GET  /api/tickets       | 596  | 4724     | 11 000   | 3.7 %  |
| POST /api/tickets       | 214  | 589      | 1100     | 1.4 %  |
| GET  /api/notifications | 229  | 1056     | 1700     | 1.7 %  |
| **Aggregated**          | 1139 | **2851** | **10 000** | **2.5 %** |
| Throughput              | —    | —        | —        | 18.77 rps |

### Spike Load — 200 concurrent users, 30 s

| Endpoint                | Reqs | Avg (ms) | p95 (ms) | Errors     |
|-------------------------|------|----------|----------|------------|
| POST /api/auth/login    | 110  | 7871     | 21 000   | 9.1 %      |
| GET  /api/tickets       | 250  | 3571     | 12 000   | **80.4 %** |
| POST /api/tickets       | 80   | 2459     | 7500     | **75.0 %** |
| GET  /api/notifications | 75   | 2770     | 8300     | **66.7 %** |
| **Aggregated**          | 515  | **4200** | **12 000** | **62.3 %** |
| Throughput              | —    | —        | —        | 18.33 rps  |

### Key Findings

1. **Ticket list endpoint is the bottleneck.** `GET /api/tickets` is 10×
   slower than `POST /api/tickets` under load because it returns the full
   list per user and the list grows as the test runs.  No pagination, no
   indexes beyond the primary key — a textbook N+1-ish behaviour in a
   simple app.
2. **Flask's dev server is the hard ceiling.** At 200 users the single-
   threaded server drops **62 % of requests** with `Connection refused`
   and `Remote end closed connection`. In production this app would need
   Gunicorn / uWSGI behind Nginx.
3. **Login latency inflates under load.** Normal ≈ 1 s, peak ≈ 0.6 s
   (variance), spike ≈ 7.9 s.  SHA-256 password hashing is fast; the
   latency comes from the server's request queue, not the hash step.

---

## 2. Mutation Testing (Custom Runner, 15 mutants)

Tool: custom deterministic mutation runner. Each mutant restarts the Flask
app fresh so the mutated bytes are actually loaded. Tests run against the
mutated app via `pytest tests/unit/ tests/api/`.

| Module              | Created | Killed | Survived | Score   |
|---------------------|---------|--------|----------|---------|
| Authentication      | 5       | 4      | 1        | **80 %** |
| Ticket Validation   | 4       | 3      | 1        | **75 %** |
| Ticket CRUD         | 4       | 2      | 2        | **50 %** |
| Notifications       | 2       | 1      | 1        | **50 %** |
| **Overall**         | **15**  | **10** | **5**    | **66.7 %** |

### Surviving Mutants (real coverage gaps)

| ID        | Module         | What the mutant does                                          |
|-----------|----------------|---------------------------------------------------------------|
| M-AUTH-03 | Auth           | `OR`→`AND` in the empty-field check (weaker, not caught)      |
| M-VAL-02  | Validation     | Removes `"critical"` from accepted priority list              |
| M-CRUD-02 | CRUD           | Removes user filter from ticket list — **privacy leak**       |
| M-CRUD-04 | CRUD           | Changes default priority from `medium` to `low`               |
| M-NOTIF-02| Notifications  | "Mark as read" actually unreads                               |

Elapsed: 40.1 s for all 15 mutants (app restarted 15 times).

---

## 3. Chaos / Fault Injection Testing

### Scenarios run

| Scenario                               | Availability                     | MTTR        | Notes                                                           |
|----------------------------------------|----------------------------------|-------------|-----------------------------------------------------------------|
| DB Latency (exclusive lock, 10 s)      | Reads 100 %, Writes 0 %          | 0.01 s      | SQLite WAL: reads survive even with writer locked               |
| Network Latency (+500 ms, 10 % loss)   | 91.3 % (8.7 % errors)            | "instant"   | Latency inflated 3.5 ms → 507 ms                                |
| CPU Exhaustion (1 burner, 10 s)        | 100 % (4.7 ms → 5.5 ms)          | 0.32 s      | Minimal — Flask/SQLite workload is I/O-bound                    |
| API Downtime                           | skipped in sandbox runs          | —           | Needs `lsof` + process management; covered by `api_downtime.py` |

### Key Findings

1. **WAL mode is doing its job.** Under an exclusive write lock, reads
   continued at 100 % availability — confirms the `PRAGMA journal_mode=WAL`
   setup from the midterm is correctly wired.
2. **No graceful degradation.** Under CPU pressure the app just slows
   down; there's no circuit breaker, no 429 responses, no shedding of
   low-priority traffic. Recovery is fast (0.3 s) but only because we're
   not actually overloading it.
3. **Client-side retries would amplify outages.** Under 10 % packet loss
   the client sees 8.7 % errors — a naive retry loop would turn a 10 %
   network blip into 2-3× load on the upstream.

---

## Comparison with teammate's theoretical numbers

| Scenario      | Teammate's report | Actual measurement           | Why the gap                                   |
|---------------|-------------------|------------------------------|-----------------------------------------------|
| Normal load   | 420 ms avg        | 2702 ms avg                  | Ticket list endpoint slower than estimated    |
| Peak load     | 980 ms, 3 % err   | 2851 ms, 2.5 % err           | Latency worse; error rate close to estimate   |
| Spike load    | 1500 ms, 8 % err  | 4200 ms, **62 % err**        | Dev server collapses far more aggressively    |
| Mutation score| 75 % overall      | 66.7 % overall               | Real gaps in CRUD & notification tests        |
| DB latency    | 92 %, 3 s recover | Writes 0 %, reads 100 %      | Writes block completely; reads unaffected     |
