"""TC-TICK-*: Ticket API tests — CRUD, validation, edge cases, concurrency."""
from __future__ import annotations
import concurrent.futures
import pytest
from utils.api_client import APIClient


def _ticket(title="Test Ticket", desc="A test ticket", priority="medium"):
    return {"title": title, "description": desc, "priority": priority, "category": "general"}


@pytest.mark.api
class TestTicketAPI:
    # ── TC-TICK-01: Create valid ticket ──
    def test_create_ticket(self, api_client, auth_token):
        resp = api_client.create_ticket(auth_token, _ticket())
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"]
        assert data["title"] == "Test Ticket"
        assert data["status"] == "open"

    # ── TC-TICK-02: Get ticket by ID ──
    def test_get_ticket(self, api_client, auth_token):
        created = api_client.create_ticket(auth_token, _ticket("Get Me")).json()
        resp = api_client.get_ticket(auth_token, created["id"])
        assert resp.status_code == 200
        assert resp.json()["title"] == "Get Me"

    # ── TC-TICK-03: List tickets ──
    def test_list_tickets(self, api_client, auth_token):
        api_client.create_ticket(auth_token, _ticket("List Test"))
        resp = api_client.list_tickets(auth_token)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
        assert len(resp.json()) >= 1

    # ── TC-TICK-04: Update ticket ──
    def test_update_ticket(self, api_client, auth_token):
        created = api_client.create_ticket(auth_token, _ticket("Before Update")).json()
        resp = api_client.update_ticket(auth_token, created["id"], {"title": "After Update", "status": "closed"})
        assert resp.status_code == 200
        assert resp.json()["title"] == "After Update"
        assert resp.json()["status"] == "closed"

    # ── TC-TICK-05: Delete ticket ──
    def test_delete_ticket(self, api_client, auth_token):
        created = api_client.create_ticket(auth_token, _ticket("Delete Me")).json()
        resp = api_client.delete_ticket(auth_token, created["id"])
        assert resp.status_code == 200
        get_resp = api_client.get_ticket(auth_token, created["id"])
        assert get_resp.status_code == 404

    # ── TC-TICK-06: Get non-existent ticket → 404 ──
    def test_get_nonexistent_ticket(self, api_client, auth_token):
        resp = api_client.get_ticket(auth_token, "nonexistent-id")
        assert resp.status_code == 404

    # ── TC-TICK-07: Empty title → 422 ──
    def test_create_ticket_empty_title(self, api_client, auth_token):
        resp = api_client.create_ticket(auth_token, _ticket(title=""))
        assert resp.status_code == 422
        assert "title" in resp.json().get("errors", {})

    # ── TC-TICK-08: Empty description → 422 ──
    def test_create_ticket_empty_description(self, api_client, auth_token):
        resp = api_client.create_ticket(auth_token, _ticket(desc=""))
        assert resp.status_code == 422
        assert "description" in resp.json().get("errors", {})

    # ── TC-TICK-09: Invalid priority → 422 ──
    def test_create_ticket_invalid_priority(self, api_client, auth_token):
        resp = api_client.create_ticket(auth_token, _ticket(priority="ultra"))
        assert resp.status_code == 422
        assert "priority" in resp.json().get("errors", {})

    # ── TC-TICK-10: Title exceeds 200 chars → 422 ──
    def test_create_ticket_title_too_long(self, api_client, auth_token):
        resp = api_client.create_ticket(auth_token, _ticket(title="A" * 201))
        assert resp.status_code == 422

    # ── TC-TICK-EDGE-01: Large payload ──
    def test_create_ticket_large_description(self, api_client, auth_token):
        resp = api_client.create_ticket(auth_token, _ticket(desc="x" * 10000))
        assert resp.status_code == 201

    # ── TC-TICK-EDGE-02: Special characters / XSS ──
    def test_create_ticket_special_chars(self, api_client, auth_token):
        resp = api_client.create_ticket(auth_token, _ticket(title="<script>alert('xss')</script>", desc="Test & 'quotes' \"double\""))
        assert resp.status_code == 201
        data = resp.json()
        assert "<script>" in data["title"]  # stored as-is, escaped at render

    # ── TC-TICK-CONC-01: Concurrent ticket creation ──
    def test_concurrent_ticket_creation(self, api_client, auth_token, settings):
        """Simulate 5 simultaneous ticket creation requests."""
        import requests

        def create_one(i):
            s = requests.Session()
            return s.post(
                f"{settings.api_base_url}/api/tickets",
                headers={"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"},
                json=_ticket(title=f"Concurrent-{i}", desc=f"Concurrent test {i}"),
                timeout=10,
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(create_one, i) for i in range(5)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        statuses = [r.status_code for r in results]
        assert all(s == 201 for s in statuses), f"Expected all 201, got {statuses}"

    # ── TC-TICK-EDGE-03: Create ticket without auth ──
    def test_create_ticket_no_auth(self, api_client, settings):
        resp = api_client.session.post(
            f"{settings.api_base_url}/api/tickets",
            json=_ticket(),
            timeout=10,
        )
        assert resp.status_code == 401
