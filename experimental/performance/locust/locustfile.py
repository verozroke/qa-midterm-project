"""Locust performance test — Python alternative to k6 scripts.

Use this if k6 isn't available on the host.  Produces comparable metrics
(response time percentiles, throughput, error rate) via Locust's built-in
CSV export.

Usage:
    # Normal load (20 users for 2 min)
    locust -f locustfile.py --headless -u 20 -r 5 -t 2m \
           --host http://localhost:8080 --csv=results/normal

    # Peak load
    locust -f locustfile.py --headless -u 100 -r 20 -t 5m \
           --host http://localhost:8080 --csv=results/peak

    # Spike
    locust -f locustfile.py --headless -u 200 -r 50 -t 2m \
           --host http://localhost:8080 --csv=results/spike
"""
from __future__ import annotations
import os
import random
from locust import HttpUser, task, between, events


USERNAME = os.getenv("TEST_USERNAME", "test.user")
PASSWORD = os.getenv("TEST_PASSWORD", "ChangeMe123!")


class TicketSystemUser(HttpUser):
    """Simulates a real user: login, browse tickets, create a ticket."""

    wait_time = between(1, 3)  # realistic think time

    def on_start(self):
        """Each simulated user logs in once at start."""
        self.token = None
        with self.client.post(
            "/api/auth/login",
            json={"username": USERNAME, "password": PASSWORD},
            name="POST /api/auth/login",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                self.token = resp.json().get("token")
                resp.success()
            else:
                resp.failure(f"Login failed: {resp.status_code}")

    @property
    def auth_headers(self):
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    @task(3)  # 3x weight — most common action
    def list_tickets(self):
        if not self.token:
            return
        self.client.get(
            "/api/tickets",
            headers=self.auth_headers,
            name="GET /api/tickets",
        )

    @task(1)
    def create_ticket(self):
        if not self.token:
            return
        self.client.post(
            "/api/tickets",
            json={
                "title": f"Locust Ticket {random.randint(1, 1_000_000)}",
                "description": "Load-test ticket from locust run.",
                "priority": random.choice(["low", "medium", "high"]),
                "category": "general",
            },
            headers={**self.auth_headers, "Content-Type": "application/json"},
            name="POST /api/tickets",
        )

    @task(1)
    def get_notifications(self):
        if not self.token:
            return
        self.client.get(
            "/api/notifications",
            headers=self.auth_headers,
            name="GET /api/notifications",
        )


# ─ Hooks: print a compact summary at the end for the report ─
@events.quitting.add_listener
def _(environment, **kwargs):
    stats = environment.stats.total
    print("\n" + "=" * 60)
    print("LOCUST RUN SUMMARY")
    print("=" * 60)
    print(f"  Total requests   : {stats.num_requests}")
    print(f"  Total failures   : {stats.num_failures}")
    print(f"  Failure rate     : {stats.fail_ratio * 100:.2f}%")
    print(f"  Avg response (ms): {stats.avg_response_time:.1f}")
    print(f"  Median (ms)      : {stats.median_response_time}")
    p95 = stats.get_response_time_percentile(0.95)
    print(f"  95th pct (ms)    : {p95:.1f}" if p95 else "  95th pct (ms)    : n/a")
    print(f"  RPS              : {stats.total_rps:.2f}")
    print("=" * 60)
