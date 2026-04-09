"""TC-AUTH-*: Authentication API tests — failure, edge, security scenarios."""
from __future__ import annotations
import pytest
from utils.api_client import APIClient


@pytest.mark.api
class TestAuthAPI:
    # ── TC-AUTH-01: Valid login ──
    def test_login_valid_credentials(self, api_client: APIClient, settings):
        resp = api_client.authenticate(settings.username, settings.password)
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert len(data["token"]) > 10

    # ── TC-AUTH-02: Invalid password ──
    def test_login_invalid_password(self, api_client: APIClient, settings):
        resp = api_client.authenticate(settings.username, "WrongPassword!")
        assert resp.status_code == 401
        assert "error" in resp.json()

    # ── TC-AUTH-03: Non-existent user ──
    def test_login_nonexistent_user(self, api_client: APIClient):
        resp = api_client.authenticate("no.such.user", "anything")
        assert resp.status_code == 401

    # ── TC-AUTH-04: Empty credentials ──
    def test_login_empty_credentials(self, api_client: APIClient):
        resp = api_client.authenticate("", "")
        assert resp.status_code == 400

    # ── TC-AUTH-05: Missing JSON body ──
    def test_login_no_body(self, api_client: APIClient, settings):
        resp = api_client.session.post(
            f"{settings.api_base_url}/api/auth/login",
            data="not json",
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        assert resp.status_code == 400

    # ── TC-AUTH-06: SQL injection attempt ──
    def test_login_sql_injection(self, api_client: APIClient):
        resp = api_client.authenticate("' OR 1=1 --", "password")
        assert resp.status_code == 401

    # ── TC-AUTH-07: Token required for protected endpoint ──
    def test_access_tickets_without_token(self, api_client: APIClient, settings):
        resp = api_client.session.get(
            f"{settings.api_base_url}/api/tickets",
            timeout=10,
        )
        assert resp.status_code == 401

    # ── TC-AUTH-08: Invalid token ──
    def test_access_with_invalid_token(self, api_client: APIClient, settings):
        resp = api_client.session.get(
            f"{settings.api_base_url}/api/tickets",
            headers={"Authorization": "Bearer fake-token-12345"},
            timeout=10,
        )
        assert resp.status_code == 401

    # ── TC-AUTH-09: Logout ──
    def test_logout(self, api_client: APIClient, settings):
        login_resp = api_client.authenticate(settings.username, settings.password)
        token = login_resp.json()["token"]
        logout_resp = api_client.logout(token)
        assert logout_resp.status_code == 200
