from __future__ import annotations
import os
from dataclasses import dataclass
from functools import lru_cache
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    app_base_url: str
    api_base_url: str
    ui_base_url: str
    username: str
    password: str
    invalid_password: str
    request_timeout: int
    ui_headless: bool
    ui_slow_mo: int
    ui_expect_timeout: int


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    base = os.getenv("APP_BASE_URL", "http://localhost:8080").rstrip("/")
    return Settings(
        app_base_url=base,
        api_base_url=os.getenv("API_BASE_URL", base).rstrip("/"),
        ui_base_url=os.getenv("UI_BASE_URL", base).rstrip("/"),
        username=os.getenv("TEST_USERNAME", "test.user"),
        password=os.getenv("TEST_PASSWORD", "ChangeMe123!"),
        invalid_password=os.getenv("INVALID_TEST_PASSWORD", "WrongPassword123!"),
        request_timeout=int(os.getenv("REQUEST_TIMEOUT", "30")),
        ui_headless=os.getenv("UI_HEADLESS", "true").lower() in ("1", "true", "yes"),
        ui_slow_mo=int(os.getenv("UI_SLOW_MO", "0")),
        ui_expect_timeout=int(os.getenv("UI_EXPECT_TIMEOUT", "10000")),
    )
