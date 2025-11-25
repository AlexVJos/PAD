from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.utils import configure_sqlite_env, reload_module


@pytest.fixture()
def loan_context(tmp_path: Path, monkeypatch):
    configure_sqlite_env("LOAN_DB_URL", tmp_path / "loan.db")
    module = reload_module("services.loan_service.app")

    async def fake_fetch_book(book_id: int):
        return {"id": book_id, "title": "Demo Book", "available_copies": 5}

    async def fake_adjust_inventory(book_id: int, action: str, count: int = 1):
        return None

    published: list[tuple[str, dict]] = []

    async def fake_publish_event(amqp_url: str, event_type: str, payload: dict, routing_key=None):
        published.append((event_type, payload))

    monkeypatch.setattr(module, "fetch_book", fake_fetch_book)
    monkeypatch.setattr(module, "adjust_inventory", fake_adjust_inventory)
    monkeypatch.setattr(module, "publish_event", fake_publish_event)

    with TestClient(module.app) as client:
        yield client, published


def test_create_and_return_loan_flow(loan_context):
    client, published = loan_context
    payload = {"user_id": 1, "user_name": "alice", "book_id": 42}

    create_resp = client.post("/loans/", json=payload)
    assert create_resp.status_code == 201
    loan = create_resp.json()
    assert loan["status"] == "active"
    assert published[0][0] == "loan.created"

    duplicate = client.post("/loans/", json=payload)
    assert duplicate.status_code == 400

    return_resp = client.post(f"/loans/{loan['id']}/return", json={"user_id": 1})
    assert return_resp.status_code == 200
    assert return_resp.json()["status"] == "returned"
    assert published[-1][0] == "loan.returned"


