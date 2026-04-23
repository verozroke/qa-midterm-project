"""db_failure.py — simulates database unavailability and latency.

Two sub-scenarios:
  1. DB unavailable: rename the SQLite file mid-run; requests hit a broken DB.
  2. DB latency: open an exclusive write-lock from another connection so
     reads have to queue — simulates a slow DB under load.

Measures:
  - availability during DB degradation
  - response-time drift
  - error propagation to dependent endpoints (tickets, notifications)
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import sys
import threading
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))


def probe_endpoint(url: str, headers: dict | None = None, timeout: float = 5.0):
    t0 = time.time()
    try:
        r = requests.get(url, headers=headers or {}, timeout=timeout)
        return r.status_code, (time.time() - t0) * 1000
    except requests.RequestException:
        return None, (time.time() - t0) * 1000


def _get_token(base_url: str) -> str | None:
    try:
        r = requests.post(
            f"{base_url}/api/auth/login",
            json={"username": "test.user", "password": "ChangeMe123!"},
            timeout=5,
        )
        if r.status_code == 200:
            return r.json().get("token")
    except requests.RequestException:
        pass
    return None


# ── Scenario A: DB file unavailable ─────────────────────────────────────
def run_db_unavailable(base_url: str = "http://localhost:8080",
                      db_path: str = "tickets.db",
                      outage_duration: int = 8):
    """Rename the SQLite file so DB-backed endpoints break."""
    db = ROOT / db_path
    if not db.exists():
        return {"error": f"DB file not found: {db}"}

    backup = db.with_suffix(".db.chaos-bak")
    token = _get_token(base_url)

    print(f"[db_unavailable] moving {db.name} → {backup.name} for {outage_duration}s")
    shutil.move(str(db), str(backup))
    t_start = time.time()

    probes = []
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    while time.time() - t_start < outage_duration:
        status, ms = probe_endpoint(f"{base_url}/api/tickets", headers=headers)
        h_status, _ = probe_endpoint(f"{base_url}/api/health")
        probes.append({
            "t_s": round(time.time() - t_start, 2),
            "tickets_status": status,
            "tickets_latency_ms": round(ms, 1),
            "health_status": h_status,
        })
        time.sleep(0.5)

    # Restore
    print(f"[db_unavailable] restoring DB file...")
    t_restore = time.time()
    shutil.move(str(backup), str(db))

    # Wait for app to recover (next DB op will reconnect)
    t_recovered = None
    deadline = t_restore + 15
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    while time.time() < deadline:
        status, _ = probe_endpoint(f"{base_url}/api/tickets", headers=headers)
        if status == 200:
            t_recovered = time.time()
            break
        time.sleep(0.5)

    # Compute metrics. We count a probe "available" if tickets endpoint works.
    total = len(probes)
    succeeded = sum(1 for p in probes if p["tickets_status"] == 200)
    availability = (succeeded / total * 100) if total else 0.0
    health_ok = sum(1 for p in probes if p["health_status"] == 200)
    # Health does NOT hit the DB → should remain up even with DB down. That's
    # itself a useful finding: is the app honestly reporting health?
    propagation = ((total - succeeded) / total * 100) if total else 0.0
    mttr = (t_recovered - t_restore) if t_recovered else None

    return {
        "scenario": "DB Unavailable",
        "availability_pct": round(availability, 2),
        "health_check_availability_pct": round((health_ok / total * 100) if total else 0.0, 2),
        "mttr_s": round(mttr, 2) if mttr else None,
        "error_propagation_pct": round(propagation, 2),
        "probes_taken": total,
        "impact": "All DB-backed endpoints (auth, tickets, notifications) fail.",
        "probes": probes,
    }


# ── Scenario B: DB latency via exclusive lock ───────────────────────────
def run_db_latency(base_url: str = "http://localhost:8080",
                  db_path: str = "tickets.db",
                  lock_duration: int = 10):
    """Grab an EXCLUSIVE lock so app writes have to queue."""
    db = ROOT / db_path
    if not db.exists():
        return {"error": f"DB file not found: {db}"}

    stop = threading.Event()

    def hold_lock():
        # A separate connection that BEGINs EXCLUSIVE and sits on it.
        conn = sqlite3.connect(str(db), timeout=0.1)
        try:
            conn.isolation_level = None
            conn.execute("BEGIN EXCLUSIVE")
            while not stop.is_set():
                time.sleep(0.1)
            conn.execute("ROLLBACK")
        finally:
            conn.close()

    token = _get_token(base_url)
    if not token:
        return {"error": "Could not authenticate — skipping."}

    print(f"[db_latency] acquiring exclusive lock for {lock_duration}s")
    t = threading.Thread(target=hold_lock, daemon=True)
    t.start()
    time.sleep(0.3)  # let lock settle

    t_start = time.time()
    probes = []
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    while time.time() - t_start < lock_duration:
        # Reads might succeed (WAL mode allows concurrent reads even with writer).
        r_status, r_ms = probe_endpoint(f"{base_url}/api/tickets", headers=headers)
        # Writes should block or fail.
        t0 = time.time()
        try:
            resp = requests.post(
                f"{base_url}/api/tickets",
                headers=headers,
                json={"title": "chaos-latency", "description": "d", "priority": "low"},
                timeout=3,
            )
            w_status, w_ms = resp.status_code, (time.time() - t0) * 1000
        except requests.RequestException:
            w_status, w_ms = None, (time.time() - t0) * 1000
        probes.append({
            "t_s": round(time.time() - t_start, 2),
            "read_status": r_status,
            "read_latency_ms": round(r_ms, 1),
            "write_status": w_status,
            "write_latency_ms": round(w_ms, 1),
        })
        time.sleep(0.5)

    stop.set()
    t.join(timeout=2)
    print(f"[db_latency] lock released")

    # MTTR: time to first successful write after release.
    t_release = time.time()
    t_recovered = None
    deadline = t_release + 10
    while time.time() < deadline:
        try:
            r = requests.post(
                f"{base_url}/api/tickets", headers=headers,
                json={"title": "recovery-check", "description": "d", "priority": "low"},
                timeout=3,
            )
            if r.status_code == 201:
                t_recovered = time.time()
                break
        except requests.RequestException:
            pass
        time.sleep(0.3)

    reads_ok = sum(1 for p in probes if p["read_status"] == 200)
    writes_ok = sum(1 for p in probes if p["write_status"] == 201)
    total = len(probes)
    avg_write_ms = (sum(p["write_latency_ms"] for p in probes) / total) if total else 0.0
    read_availability = (reads_ok / total * 100) if total else 0.0
    write_availability = (writes_ok / total * 100) if total else 0.0
    mttr = (t_recovered - t_release) if t_recovered else None

    return {
        "scenario": "DB Latency (exclusive lock)",
        "read_availability_pct": round(read_availability, 2),
        "write_availability_pct": round(write_availability, 2),
        "avg_write_latency_ms": round(avg_write_ms, 1),
        "mttr_s": round(mttr, 2) if mttr else None,
        "error_propagation_pct": round(((total - writes_ok) / total * 100) if total else 0, 2),
        "probes_taken": total,
        "impact": "Write operations stall; reads may still succeed (WAL mode).",
    }


if __name__ == "__main__":
    import json, argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["unavailable", "latency", "both"], default="both")
    args = parser.parse_args()

    results = {}
    if args.mode in ("unavailable", "both"):
        results["db_unavailable"] = run_db_unavailable()
    if args.mode in ("latency", "both"):
        results["db_latency"] = run_db_latency()
    print(json.dumps(results, indent=2))
