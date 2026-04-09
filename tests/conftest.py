from __future__ import annotations
import logging
import pytest
from config.settings import Settings, get_settings
from utils.api_client import APIClient
from utils.logger import get_logger


@pytest.fixture(scope="session")
def settings() -> Settings:
    return get_settings()


@pytest.fixture(scope="session")
def test_logger() -> logging.Logger:
    return get_logger("qa-automation")


@pytest.fixture(scope="session")
def api_client(settings, test_logger):
    client = APIClient(settings=settings, logger=test_logger)
    yield client
    client.close()


@pytest.fixture(scope="session")
def auth_token(api_client, settings) -> str:
    """Pre-authenticate and return a valid token for the session."""
    resp = api_client.authenticate(settings.username, settings.password)
    assert resp.status_code == 200
    return resp.json()["token"]
