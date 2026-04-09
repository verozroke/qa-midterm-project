"""TC-NOTIF-*: Notification API tests. TC-HEALTH: Health endpoint."""
from __future__ import annotations
import pytest
from utils.api_client import APIClient


@pytest.mark.api
class TestNotificationAPI:
    # ── TC-NOTIF-01: Get notifications after login ──
    def test_get_notifications(self, api_client, auth_token):
        resp = api_client.get_notifications(auth_token)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    # ── TC-NOTIF-02: Notification created on ticket creation ──
    def test_notification_on_ticket_create(self, api_client, auth_token):
        api_client.create_ticket(auth_token, {"title": "Notif Test", "description": "desc", "priority": "low"})
        resp = api_client.get_notifications(auth_token)
        messages = [n["message"] for n in resp.json()]
        assert any("Notif Test" in m for m in messages)

    # ── TC-NOTIF-03: Mark notification as read ──
    def test_mark_notification_read(self, api_client, auth_token):
        notifs = api_client.get_notifications(auth_token).json()
        if notifs:
            resp = api_client.mark_notification_read(auth_token, notifs[0]["id"])
            assert resp.status_code == 200

    # ── TC-NOTIF-04: Notifications require auth ──
    def test_notifications_require_auth(self, api_client, settings):
        resp = api_client.session.get(f"{settings.api_base_url}/api/notifications", timeout=10)
        assert resp.status_code == 401


@pytest.mark.api
class TestHealthCheck:
    def test_health_endpoint(self, api_client):
        resp = api_client.health()
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
