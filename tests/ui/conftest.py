from __future__ import annotations
import pytest
from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright
from config.settings import Settings


@pytest.fixture(scope="session")
def playwright_instance():
    with sync_playwright() as pw:
        yield pw


@pytest.fixture(scope="session")
def browser(playwright_instance, settings):
    b = playwright_instance.chromium.launch(headless=settings.ui_headless, slow_mo=settings.ui_slow_mo)
    yield b
    b.close()


@pytest.fixture
def context(browser):
    ctx = browser.new_context(ignore_https_errors=True)
    yield ctx
    ctx.close()


@pytest.fixture
def page(context, settings):
    p = context.new_page()
    p.set_default_timeout(settings.ui_expect_timeout)
    yield p
    p.close()


def _ui_login(page, settings):
    """Helper to log in via UI."""
    page.goto(f"{settings.ui_base_url}/login", wait_until="domcontentloaded")
    page.fill("input[name='username']", settings.username)
    page.fill("input[name='password']", settings.password)
    page.click("button[type='submit']")
    page.wait_for_url("**/dashboard")


@pytest.fixture
def logged_in_page(page, settings):
    """Page already logged in."""
    _ui_login(page, settings)
    return page
