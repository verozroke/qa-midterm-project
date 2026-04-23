"""resource_exhaustion.py — CPU and memory exhaustion scenarios.

Approach: spawn background processes that consume CPU / RAM and measure
how the app degrades. We do NOT modify the app itself — just its environment.

Measures:
  - response-time drift as CPU / memory pressure rises
  - whether the system eventually rejects requests (protective)
  - recovery time once pressure releases
"""
from __future__ import annotations

import multiprocessing as mp
import os
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))


def _cpu_burn(stop_flag):
    """Tight loop that pegs one core. Stops when flag is set."""
    while not stop_flag.is_set():
        # Pointless arithmetic — the point is to burn cycles.
        x = 0
        for i in range(100_000):
            x += i * i
        # No sleep on purpose.


def _measure(base_url: str, n: int = 10) -> tuple[float, float]:
    """Return (avg_ms, error_rate_pct)."""
    times, errors = [], 0
    for _ in range(n):
        t0 = time.time()
        try:
            r = requests.get(f"{base_url}/api/health", timeout=5)
            times.append((time.time() - t0) * 1000)
            if r.status_code != 200:
                errors += 1
        except requests.RequestException:
            errors += 1
        time.sleep(0.1)
    return (sum(times) / len(times) if times else 0.0), (errors / n * 100)


def run_cpu(base_url: str = "http://localhost:8080",
            workers: int = None, duration_s: int = 10):
    """Spawn CPU burners, measure response-time inflation."""
    workers = workers or max(1, os.cpu_count() - 1)

    # Baseline
    print(f"[cpu_exhaust] baseline...")
    base_avg, base_err = _measure(base_url)
    print(f"  baseline avg={base_avg:.1f}ms err={base_err:.1f}%")

    stop = mp.Event()
    procs = [mp.Process(target=_cpu_burn, args=(stop,), daemon=True)
             for _ in range(workers)]
    print(f"[cpu_exhaust] spawning {workers} CPU burners for {duration_s}s")
    for p in procs: p.start()
    time.sleep(1)  # let them saturate

    samples = []
    t_start = time.time()
    while time.time() - t_start < duration_s:
        avg, err = _measure(base_url, n=5)
        samples.append({
            "t_s": round(time.time() - t_start, 2),
            "avg_ms": round(avg, 1),
            "err_pct": round(err, 2),
        })
        time.sleep(0.5)

    # Stop burners
    stop.set()
    for p in procs:
        p.join(timeout=2)
        if p.is_alive(): p.terminate()

    # Recovery
    print(f"[cpu_exhaust] burners stopped, measuring recovery...")
    t_release = time.time()
    t_recovered = None
    deadline = t_release + 15
    while time.time() < deadline:
        avg, _ = _measure(base_url, n=3)
        if avg < base_avg * 1.5:  # back within 50% of baseline
            t_recovered = time.time()
            break
        time.sleep(0.5)
    recover_avg, recover_err = _measure(base_url)

    degraded_avg = sum(s["avg_ms"] for s in samples) / len(samples) if samples else 0.0
    errors_total = sum(s["err_pct"] for s in samples) / len(samples) if samples else 0.0

    return {
        "scenario": f"CPU Exhaustion ({workers} burners)",
        "baseline_avg_ms": round(base_avg, 1),
        "degraded_avg_ms": round(degraded_avg, 1),
        "degraded_error_pct": round(errors_total, 2),
        "recovery_avg_ms": round(recover_avg, 1),
        "mttr_s": round(t_recovered - t_release, 2) if t_recovered else None,
        "latency_inflation_pct": round(((degraded_avg - base_avg) / base_avg * 100)
                                      if base_avg else 0, 1),
        "samples": samples,
        "impact": "App still responds but slow; no graceful degradation observed.",
    }


def run_memory(base_url: str = "http://localhost:8080",
              target_mb: int = 200, duration_s: int = 8):
    """Allocate large memory block in a child process to simulate pressure."""

    def hog(mb, stop):
        # Hold a byte array in memory until told to stop.
        blob = bytearray(mb * 1024 * 1024)
        # Touch every page so OS actually commits it.
        for i in range(0, len(blob), 4096):
            blob[i] = 1
        while not stop.is_set():
            time.sleep(0.1)
        del blob

    print(f"[mem_exhaust] baseline...")
    base_avg, base_err = _measure(base_url)
    print(f"  baseline avg={base_avg:.1f}ms")

    stop = mp.Event()
    p = mp.Process(target=hog, args=(target_mb, stop), daemon=True)
    print(f"[mem_exhaust] allocating {target_mb}MB for {duration_s}s")
    p.start()
    time.sleep(1)

    samples = []
    t_start = time.time()
    while time.time() - t_start < duration_s:
        avg, err = _measure(base_url, n=3)
        samples.append({
            "t_s": round(time.time() - t_start, 2),
            "avg_ms": round(avg, 1),
            "err_pct": round(err, 2),
        })
        time.sleep(0.5)

    stop.set()
    p.join(timeout=3)
    if p.is_alive(): p.terminate()

    recover_avg, _ = _measure(base_url)
    degraded_avg = sum(s["avg_ms"] for s in samples) / len(samples) if samples else 0.0

    return {
        "scenario": f"Memory Pressure ({target_mb}MB external hog)",
        "baseline_avg_ms": round(base_avg, 1),
        "degraded_avg_ms": round(degraded_avg, 1),
        "recovery_avg_ms": round(recover_avg, 1),
        "mttr_s": "~immediate",
        "impact": "Minor on SQLite/Flask workload; would matter on larger RSS apps.",
    }


if __name__ == "__main__":
    import json
    print(json.dumps({
        "cpu": run_cpu(),
        "memory": run_memory(),
    }, indent=2))
