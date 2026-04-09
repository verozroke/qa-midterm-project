from __future__ import annotations
import logging
from typing import Any
import requests
from requests import Response
from config.settings import Settings


class APIClient:
    def __init__(self, settings: Settings, logger: logging.Logger) -> None:
        self.settings = settings
        self.logger = logger
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json", "Content-Type": "application/json"})

    def _url(self, path: str) -> str:
        return f"{self.settings.api_base_url}{path}"

    def _auth(self, token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    def authenticate(self, username: str, password: str) -> Response:
        return self.session.post(self._url("/api/auth/login"), json={"username": username, "password": password}, timeout=self.settings.request_timeout)

    def logout(self, token: str) -> Response:
        return self.session.post(self._url("/api/auth/logout"), headers=self._auth(token), timeout=self.settings.request_timeout)

    def create_ticket(self, token: str, payload: dict[str, Any]) -> Response:
        return self.session.post(self._url("/api/tickets"), headers=self._auth(token), json=payload, timeout=self.settings.request_timeout)

    def get_ticket(self, token: str, ticket_id: str) -> Response:
        return self.session.get(self._url(f"/api/tickets/{ticket_id}"), headers=self._auth(token), timeout=self.settings.request_timeout)

    def list_tickets(self, token: str) -> Response:
        return self.session.get(self._url("/api/tickets"), headers=self._auth(token), timeout=self.settings.request_timeout)

    def update_ticket(self, token: str, ticket_id: str, payload: dict) -> Response:
        return self.session.put(self._url(f"/api/tickets/{ticket_id}"), headers=self._auth(token), json=payload, timeout=self.settings.request_timeout)

    def delete_ticket(self, token: str, ticket_id: str) -> Response:
        return self.session.delete(self._url(f"/api/tickets/{ticket_id}"), headers=self._auth(token), timeout=self.settings.request_timeout)

    def get_notifications(self, token: str) -> Response:
        return self.session.get(self._url("/api/notifications"), headers=self._auth(token), timeout=self.settings.request_timeout)

    def mark_notification_read(self, token: str, notif_id: str) -> Response:
        return self.session.put(self._url(f"/api/notifications/{notif_id}/read"), headers=self._auth(token), timeout=self.settings.request_timeout)

    def health(self) -> Response:
        return self.session.get(self._url("/api/health"), timeout=self.settings.request_timeout)

    def close(self) -> None:
        self.session.close()
