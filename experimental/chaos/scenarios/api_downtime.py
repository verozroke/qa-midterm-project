"""api_downtime.py — simulates the API being unavailable.

Injects: kills the Flask process (or blocks the port), then measures how
client code handles the outage and how fast the system recovers once the
process is restarted.

Measures:
  - availability %  (% of health checks that succeed during the window)
  - mean time to recover (MTTR)
  - error propagation (how many dependent calls fail)
"""
from __future__ import annotations

import signal
import subprocess
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))


def find_app_pids(port: int = 8080) -> list[int]:
    """Find PIDs bound to the given port. Portable-ish via `lsof`."""
    try:
        out = subprocess.check_output(
            ["lsof", "-iTCP:%d" % port, "-sTCP:LISTEN", "-t"],
            text=True, stderr=subprocess.DEVNULL,
        )
        return [int(p) for p in out.strip().splitlines() if p.strip()]
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []


def probe(url: str, timeout: float = 1.0) -> tuple[bool, float]:
    """Return (ok, elapsed_ms).  ok = 2xx."""
    t0 = time.time()
    try:
        r = requests.get(url, timeout=timeout)
        return (200 <= r.status_code < 300), (time.time() - t0) * 1000
    except requests.RequestException:
        return False, (time.time() - t0) * 1000


def run(base_url: str = "http://localhost:8080", outage_duration: int = 10):
    """Run the scenario.  Returns a metrics dict."""
    health_url = f"{base_url}/api/health"
    tickets_url = f"{base_url}/api/tickets"  # dependent endpoint

    print(f"[api_downtime] baseline check — {health_url}")
    ok, _ = probe(health_url)
    if not ok:
        return {"error": "App not reachable at baseline — start it first."}

    pids = find_app_pids(8080)
    if not pids:
        return {"error": "Could not find app PID on port 8080."}
    print(f"[api_downtime] found app PID(s): {pids}")

    # ── Kill the app ──
    t_killed = time.time()
    print(f"[api_downtime] SIGTERM at t=0 (outage for {outage_duration}s)")
    for pid in pids:
        try:
            subprocess.run(["kill", "-TERM", str(pid)], check=False)
        except Exception as e:
            print(f"  warning: kill {pid} failed: {e}")

    # ── Probe during outage ──
    probes = []  # list of (elapsed_s, ok, latency_ms, dep_ok)
    end_outage = t_killed + outage_duration
    while time.time() < end_outage:
        h_ok, h_ms = probe(health_url)
        d_ok, _ = probe(tickets_url)  # unauthenticated → expect 401 when up
        probes.append((time.time() - t_killed, h_ok, h_ms, d_ok))
        time.sleep(0.5)

    # ── Restart app ──
    print(f"[api_downtime] restarting app...")
    t_restart = time.time()
    # Start detached so this script keeps control
    subprocess.Popen(
        [sys.executable, "-m", "app.main"],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    # ── Wait for recovery ──
    t_recovered = None
    deadline = t_restart + 30
    while time.time() < deadline:
        ok, _ = probe(health_url)
        if ok:
            t_recovered = time.time()
            break
        time.sleep(0.5)

    recovery_time = (t_recovered - t_restart) if t_recovered else None
    total_probes = len(probes)
    successful_probes = sum(1 for _, ok, _, _ in probes if ok)
    availability = (successful_probes / total_probes * 100) if total_probes else 0.0
    # Error propagation: during outage, dependent endpoint should also fail.
    dep_failures = sum(1 for _, _, _, dep_ok in probes if not dep_ok)
    propagation = (dep_failures / total_probes * 100) if total_probes else 0.0

    print(f"[api_downtime] recovered in {recovery_time:.2f}s" if recovery_time
          else "[api_downtime] FAILED TO RECOVER within 30s")

    return {
        "scenario": "API Downtime",
        "outage_duration_s": outage_duration,
        "availability_pct": round(availability, 2),
        "mttr_s": round(recovery_time, 2) if recovery_time else None,
        "error_propagation_pct": round(propagation, 2),
        "probes_taken": total_probes,
        "probes_succeeded": successful_probes,
        "impact": "Full system block — dependent endpoints unreachable.",
    }


if __name__ == "__main__":
    import json
    print(json.dumps(run(), indent=2))
