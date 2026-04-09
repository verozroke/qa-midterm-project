"""Unit tests — validate internal logic without network."""
from __future__ import annotations
import tempfile
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from app.main import create_app, _hash_pw, _create_token, _validate_token


@pytest.fixture
def app(tmp_path):
    db_path = str(tmp_path / "unit_test.db")
    os.environ["DATABASE_PATH"] = db_path
    application = create_app()
    application.config["TESTING"] = True
    yield application
    os.environ.pop("DATABASE_PATH", None)


@pytest.fixture
def client(app):
    return app.test_client()


class TestPasswordHashing:
    def test_hash_deterministic(self):
        assert _hash_pw("test") == _hash_pw("test")

    def test_hash_different_for_different_input(self):
        assert _hash_pw("a") != _hash_pw("b")


class TestTokenManagement:
    def test_create_and_validate_token(self):
        token = _create_token("user-001")
        assert _validate_token(f"Bearer {token}") == "user-001"

    def test_invalid_token_returns_none(self):
        assert _validate_token("Bearer fake-token") is None

    def test_none_token_returns_none(self):
        assert _validate_token(None) is None


class TestFlaskRoutes:
    def test_health(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200

    def test_login_page_renders(self, client):
        resp = client.get("/login")
        assert resp.status_code == 200
        assert b"Login" in resp.data

    def test_index_redirects(self, client):
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code == 302

    def test_api_login_valid(self, client):
        resp = client.post("/api/auth/login", json={"username": "test.user", "password": "ChangeMe123!"})
        assert resp.status_code == 200
        assert "token" in resp.get_json()

    def test_api_login_invalid(self, client):
        resp = client.post("/api/auth/login", json={"username": "test.user", "password": "wrong"})
        assert resp.status_code == 401
