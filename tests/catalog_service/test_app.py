from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.utils import configure_sqlite_env, reload_module


@pytest.fixture()
def catalog_client(tmp_path: Path):
    configure_sqlite_env("CATALOG_DB_URL", tmp_path / "catalog.db")
    module = reload_module("services.catalog_service.app")
    with TestClient(module.app) as client:
        yield client


def test_catalog_crud_and_inventory(catalog_client: TestClient):
    payload = {
        "title": "Clean Architecture",
        "author": "Bob",
        "isbn": "1234567890123",
        "total_copies": 3,
        "available_copies": 3,
    }
    create_resp = catalog_client.post("/books/", json=payload)
    assert create_resp.status_code == 201
    book_id = create_resp.json()["id"]

    list_resp = catalog_client.get("/books/")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    reserve = catalog_client.post(f"/books/{book_id}/reserve", json={"count": 1})
    assert reserve.status_code == 200
    assert reserve.json()["book"]["available_copies"] == 2

    release = catalog_client.post(f"/books/{book_id}/release", json={"count": 1})
    assert release.status_code == 200
    assert release.json()["book"]["available_copies"] == 3

    update = catalog_client.put(
        f"/books/{book_id}",
        json={
            "title": "Clean Architecture 2",
            "author": "Bob",
            "isbn": "1234567890123",
            "total_copies": 4,
            "available_copies": 4,
        },
    )
    assert update.status_code == 200
    assert update.json()["title"] == "Clean Architecture 2"


