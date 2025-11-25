import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.utils import configure_sqlite_env, reload_module


@pytest.fixture()
def notification_module(tmp_path: Path):
    configure_sqlite_env("NOTIFICATION_DB_URL", tmp_path / "notifications.db")
    module = reload_module("services.notification_service.app")
    with TestClient(module.app) as client:
        yield module, client


@pytest.mark.asyncio
async def test_event_handler_persists_notifications(notification_module):
    module, client = notification_module
    event = {
        "type": "loan.created",
        "payload": {"user_id": 7, "user_name": "eve", "book_title": "Some Book"},
    }
    await module.event_handler(event)

    response = client.get("/notifications/", params={"user_id": 7})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert "взял книгу" in data[0]["message"]


