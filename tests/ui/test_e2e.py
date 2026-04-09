"""UI E2E tests covering login, dashboard, ticket creation, logout."""
from __future__ import annotations
import re
import pytest
from playwright.sync_api import Page
from utils.ui_pages import LoginPage, DashboardPage, CreateTicketPage


@pytest.mark.ui
class TestLoginUI:
    def test_valid_login(self, page, settings, test_logger):
        lp = LoginPage(page, settings, test_logger)
        dp = DashboardPage(page, settings, test_logger)
        lp.open()
        lp.login(settings.username, settings.password)
        dp.assert_loaded()
        assert "/dashboard" in page.url

    def test_invalid_login(self, page, settings, test_logger):
        lp = LoginPage(page, settings, test_logger)
        lp.open()
        lp.login(settings.username, "WrongPass!")
        lp.assert_error_visible()
        assert "/login" in page.url

    def test_empty_login(self, page, settings, test_logger):
        """Submit empty form — browser validation or server error."""
        lp = LoginPage(page, settings, test_logger)
        lp.open()
        lp.login("", "")
        # Should stay on login page
        assert "/login" in page.url or "/dashboard" not in page.url


@pytest.mark.ui
class TestDashboardUI:
    def test_dashboard_shows_username(self, logged_in_page, settings, test_logger):
        dp = DashboardPage(logged_in_page, settings, test_logger)
        assert settings.username in dp.get_username_display()

    def test_dashboard_redirect_if_not_logged_in(self, page, settings, test_logger):
        page.goto(f"{settings.ui_base_url}/dashboard", wait_until="domcontentloaded")
        page.wait_for_url("**/login")
        assert "/login" in page.url

    def test_dashboard_has_new_ticket_link(self, logged_in_page, settings, test_logger):
        assert logged_in_page.locator("a[href='/tickets/new']").first.is_visible()

    def test_dashboard_shows_tickets_table_or_empty(self, logged_in_page, settings, test_logger):
        dp = DashboardPage(logged_in_page, settings, test_logger)
        has_table = logged_in_page.locator("[data-testid='tickets-table']").is_visible()
        has_empty = logged_in_page.locator("[data-testid='no-tickets']").is_visible()
        assert has_table or has_empty


@pytest.mark.ui
class TestCreateTicketUI:
    def test_create_ticket_flow(self, logged_in_page, settings, test_logger):
        cp = CreateTicketPage(logged_in_page, settings, test_logger)
        cp.open()
        cp.fill_and_submit("UI Test Ticket", "Created from Playwright", "high")
        cp.assert_success()

    def test_create_ticket_empty_fields(self, logged_in_page, settings, test_logger):
        cp = CreateTicketPage(logged_in_page, settings, test_logger)
        cp.open()
        cp.fill_and_submit("", "", "medium")
        cp.assert_error()

    def test_ticket_appears_on_dashboard(self, logged_in_page, settings, test_logger):
        cp = CreateTicketPage(logged_in_page, settings, test_logger)
        cp.open()
        cp.fill_and_submit("Dashboard Verify", "Should show up", "low")
        cp.assert_success()
        logged_in_page.goto(f"{settings.ui_base_url}/dashboard", wait_until="domcontentloaded")
        assert logged_in_page.locator("text=Dashboard Verify").first.is_visible()


@pytest.mark.ui
class TestLogoutUI:
    def test_logout_redirects_to_login(self, logged_in_page, settings, test_logger):
        dp = DashboardPage(logged_in_page, settings, test_logger)
        dp.logout()
        lp = LoginPage(logged_in_page, settings, test_logger)
        lp.assert_form_visible()
        assert "/login" in logged_in_page.url

    def test_cannot_access_dashboard_after_logout(self, logged_in_page, settings, test_logger):
        dp = DashboardPage(logged_in_page, settings, test_logger)
        dp.logout()
        logged_in_page.goto(f"{settings.ui_base_url}/dashboard", wait_until="domcontentloaded")
        assert "/login" in logged_in_page.url
