from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import httpx
from django.conf import settings


class ServiceClientError(Exception):
    """Raised when a downstream microservice call fails."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def _request(method: str, url: str, **kwargs):
    timeout = kwargs.pop("timeout", settings.SERVICE_CLIENT_TIMEOUT)
    try:
        response = httpx.request(method, url, timeout=timeout, **kwargs)
        response.raise_for_status()
        if response.content:
            return response.json()
        return None
    except httpx.HTTPStatusError as exc:
        detail = _extract_detail(exc.response)
        raise ServiceClientError(detail, status_code=exc.response.status_code) from exc
    except httpx.RequestError as exc:
        raise ServiceClientError("Service temporarily unavailable") from exc


def _extract_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
        if isinstance(payload, dict):
            return payload.get("detail") or payload.get("message") or str(payload)
        return str(payload)
    except ValueError:
        return response.text or "Unexpected server error"


@dataclass
class UserToken:
    access_token: str
    user_id: int
    username: str
    email: str


class UserServiceClient:
    def __init__(self):
        self.base_url = settings.USER_SERVICE_URL.rstrip("/")

    def register(self, payload: dict[str, Any]) -> dict[str, Any]:
        return _request("POST", f"{self.base_url}/users/", json=payload)

    def login(self, username: str, password: str) -> UserToken:
        data = _request(
            "POST",
            f"{self.base_url}/auth/login",
            json={"username": username, "password": password},
        )
        user = data["user"]
        return UserToken(
            access_token=data["access_token"],
            user_id=user["id"],
            username=user["username"],
            email=user["email"],
        )

    def get_user(self, user_id: int) -> dict[str, Any]:
        return _request("GET", f"{self.base_url}/users/{user_id}")


class CatalogServiceClient:
    def __init__(self):
        self.base_url = settings.CATALOG_SERVICE_URL.rstrip("/")

    def list_books(self, search: Optional[str] = None) -> list[dict[str, Any]]:
        params = {"search": search} if search else None
        return _request("GET", f"{self.base_url}/books/", params=params)

    def get_book(self, book_id: int) -> dict[str, Any]:
        return _request("GET", f"{self.base_url}/books/{book_id}")

    def create_book(self, payload: dict[str, Any]) -> dict[str, Any]:
        return _request("POST", f"{self.base_url}/books/", json=payload)

    def update_book(self, book_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return _request("PUT", f"{self.base_url}/books/{book_id}", json=payload)

    def delete_book(self, book_id: int) -> None:
        _request("DELETE", f"{self.base_url}/books/{book_id}")


class LoanServiceClient:
    def __init__(self):
        self.base_url = settings.LOAN_SERVICE_URL.rstrip("/")

    def list_loans(self, user_id: Optional[int] = None) -> list[dict[str, Any]]:
        params = {"user_id": user_id} if user_id else None
        return _request("GET", f"{self.base_url}/loans/", params=params)

    def create_loan(self, user_id: int, user_name: str, book_id: int) -> dict[str, Any]:
        return _request(
            "POST",
            f"{self.base_url}/loans/",
            json={"user_id": user_id, "user_name": user_name, "book_id": book_id},
        )

    def return_loan(self, loan_id: int, user_id: int) -> dict[str, Any]:
        return _request("POST", f"{self.base_url}/loans/{loan_id}/return", json={"user_id": user_id})


class NotificationServiceClient:
    def __init__(self):
        self.base_url = settings.NOTIFICATION_SERVICE_URL.rstrip("/")

    def list_notifications(self, user_id: Optional[int] = None) -> list[dict[str, Any]]:
        params = {"user_id": user_id} if user_id else None
        return _request("GET", f"{self.base_url}/notifications/", params=params)


class AnalyticsServiceClient:
    def __init__(self):
        self.base_url = settings.ANALYTICS_SERVICE_URL.rstrip("/")

    def summary(self) -> dict[str, Any]:
        return _request("GET", f"{self.base_url}/metrics/summary")


