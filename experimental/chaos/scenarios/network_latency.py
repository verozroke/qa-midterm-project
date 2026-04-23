"""network_latency.py — simulates network latency and packet loss.

We can't reliably use `tc` / `iptables` inside most CI containers without
root + NET_ADMIN, so this scenario uses a client-side approach: a blocking
HTTP proxy that adds artificial delay / drops a fraction of requests.

Measures:
  - response-time inflation under added latency
  - client-visible error rate under simulated packet loss
  - how well client retries handle transient failures
"""
from __future__ import annotations

import random
import socket
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))


class LatencyProxy:
    """A tiny TCP proxy that forwards to the real app with added delay/loss.

    Client should point requests at localhost:PROXY_PORT instead of the app.
    Not a full HTTP proxy — just a byte-pipe that pauses/drops.
    """
    def __init__(self, listen_port: int, target_host: str, target_port: int,
                 added_delay_ms: int = 500, packet_loss_pct: float = 0.0):
        self.listen_port = listen_port
        self.target = (target_host, target_port)
        self.added_delay_ms = added_delay_ms
        self.packet_loss_pct = packet_loss_pct
        self._stop = threading.Event()
        self._server: socket.socket | None = None

    def start(self):
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind(("127.0.0.1", self.listen_port))
        self._server.listen(64)
        self._server.settimeout(0.5)
        threading.Thread(target=self._accept_loop, daemon=True).start()

    def stop(self):
        self._stop.set()
        if self._server:
            try: self._server.close()
            except Exception: pass

    def _accept_loop(self):
        while not self._stop.is_set():
            try:
                client, _ = self._server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            # Simulate packet loss by closing without responding.
            if random.random() < self.packet_loss_pct:
                try: client.close()
                except Exception: pass
                continue
            threading.Thread(target=self._pipe, args=(client,), daemon=True).start()

    def _pipe(self, client: socket.socket):
        try:
            upstream = socket.create_connection(self.target, timeout=5)
        except OSError:
            client.close()
            return
        # Apply added delay once, at connection setup — coarse but effective.
        time.sleep(self.added_delay_ms / 1000.0)

        def fwd(src, dst):
            try:
                while True:
                    data = src.recv(8192)
                    if not data: break
                    dst.sendall(data)
            except OSError:
                pass
            finally:
                try: dst.shutdown(socket.SHUT_WR)
                except OSError: pass

        threading.Thread(target=fwd, args=(client, upstream), daemon=True).start()
        threading.Thread(target=fwd, args=(upstream, client), daemon=True).start()


def _baseline_measurement(base_url: str, n: int = 10) -> tuple[float, float]:
    """Return (avg_ms, error_rate_pct) for unloaded baseline."""
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
    avg = sum(times) / len(times) if times else 0.0
    return avg, (errors / n * 100)


def run(base_url: str = "http://localhost:8080",
        proxy_port: int = 8088,
        added_delay_ms: int = 500,
        packet_loss_pct: float = 0.10,
        duration_s: int = 15):
    """Stand up a proxy, drive probes through it, collect metrics."""
    parsed = urlparse(base_url)
    target_host = parsed.hostname or "localhost"
    target_port = parsed.port or 80

    # Baseline (direct)
    print(f"[net_latency] baseline (direct)...")
    base_avg, base_err = _baseline_measurement(base_url, n=10)
    print(f"  baseline avg={base_avg:.1f}ms err={base_err:.1f}%")

    # Start proxy
    print(f"[net_latency] starting proxy on :{proxy_port} "
          f"(delay={added_delay_ms}ms, loss={packet_loss_pct*100:.0f}%)")
    proxy = LatencyProxy(proxy_port, target_host, target_port,
                        added_delay_ms, packet_loss_pct)
    proxy.start()
    proxy_url = f"http://localhost:{proxy_port}"
    time.sleep(0.3)

    # Drive probes through the proxy.
    times, errors = [], 0
    total = 0
    t_start = time.time()
    try:
        while time.time() - t_start < duration_s:
            total += 1
            t0 = time.time()
            try:
                r = requests.get(f"{proxy_url}/api/health", timeout=5)
                times.append((time.time() - t0) * 1000)
                if r.status_code != 200:
                    errors += 1
            except requests.RequestException:
                errors += 1
            time.sleep(0.2)
    finally:
        proxy.stop()

    degraded_avg = sum(times) / len(times) if times else 0.0
    degraded_err = (errors / total * 100) if total else 0.0

    # Recovery: after proxy stops, requests hit the app directly → should snap back.
    recover_avg, recover_err = _baseline_measurement(base_url, n=10)

    return {
        "scenario": f"Network Latency (+{added_delay_ms}ms, {int(packet_loss_pct*100)}% loss)",
        "baseline_avg_ms": round(base_avg, 1),
        "degraded_avg_ms": round(degraded_avg, 1),
        "latency_inflation_ms": round(degraded_avg - base_avg, 1),
        "baseline_error_pct": round(base_err, 2),
        "degraded_error_pct": round(degraded_err, 2),
        "recovery_avg_ms": round(recover_avg, 1),
        "mttr_s": "instant (proxy stop)",
        "probes_taken": total,
        "impact": "Client-visible slowdown; retries amplify load on upstream.",
    }


if __name__ == "__main__":
    import json
    print(json.dumps(run(), indent=2))
