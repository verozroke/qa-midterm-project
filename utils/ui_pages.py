from __future__ import annotations
import logging
import re
from playwright.sync_api import Page, expect
from config.settings import Settings


class LoginPage:
    def __init__(self, page: Page, settings: Settings, logger: logging.Logger) -> None:
        self.page = page
        self.s = settings
        self.log = logger

    def open(self):
        self.page.goto(f"{self.s.ui_base_url}/login", wait_until="domcontentloaded")

    def login(self, username: str, password: str):
        self.page.fill("input[name='username']", username)
        self.page.fill("input[name='password']", password)
        self.page.click("button[type='submit']")

    def assert_error_visible(self):
        expect(self.page.locator(".alert-danger")).to_be_visible(timeout=self.s.ui_expect_timeout)

    def assert_form_visible(self):
        expect(self.page.locator("input[name='username']")).to_be_visible(timeout=self.s.ui_expect_timeout)


class DashboardPage:
    def __init__(self, page: Page, settings: Settings, logger: logging.Logger) -> None:
        self.page = page
        self.s = settings
        self.log = logger

    def assert_loaded(self):
        expect(self.page).to_have_url(re.compile(r".*/dashboard"), timeout=self.s.ui_expect_timeout)

    def get_ticket_count(self) -> int:
        return self.page.locator("[data-testid='ticket-row']").count()

    def has_no_tickets_message(self) -> bool:
        return self.page.locator("[data-testid='no-tickets']").is_visible()

    def get_notification_count(self) -> int:
        badge = self.page.locator("[data-testid='notif-count']")
        if badge.is_visible():
            return int(badge.text_content() or "0")
        return 0

    def get_username_display(self) -> str:
        return self.page.locator("[data-testid='username-display']").text_content() or ""

    def click_new_ticket(self):
        self.page.click("a[href='/tickets/new']")

    def logout(self):
        self.page.click("[data-testid='logout-btn']")


class CreateTicketPage:
    def __init__(self, page: Page, settings: Settings, logger: logging.Logger) -> None:
        self.page = page
        self.s = settings
        self.log = logger

    def open(self):
        self.page.goto(f"{self.s.ui_base_url}/tickets/new", wait_until="domcontentloaded")

    def fill_and_submit(self, title: str, description: str, priority: str = "medium"):
        self.page.fill("input[name='title']", title)
        self.page.fill("textarea[name='description']", description)
        self.page.select_option("select[name='priority']", priority)
        self.page.click("button[type='submit']")

    def assert_success(self):
        expect(self.page.locator(".alert-success")).to_be_visible(timeout=self.s.ui_expect_timeout)

    def assert_error(self):
        expect(self.page.locator(".alert-danger")).to_be_visible(timeout=self.s.ui_expect_timeout)
