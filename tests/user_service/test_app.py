from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.utils import configure_sqlite_env, reload_module


@pytest.fixture()
def user_client(tmp_path: Path):
    configure_sqlite_env("USER_DB_URL", tmp_path / "user.db")
    module = reload_module("services.user_service.app")
    with TestClient(module.app) as client:
        yield client


def test_register_and_login_flow(user_client: TestClient):
    register_payload = {"username": "alice", "email": "alice@example.com", "password": "secret"}
    resp = user_client.post("/users/", json=register_payload)
    assert resp.status_code == 201
    user_id = resp.json()["id"]

    duplicate = user_client.post("/users/", json=register_payload)
    assert duplicate.status_code == 400

    login_resp = user_client.post("/auth/login", json={"username": "alice", "password": "secret"})
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]

    me_resp = user_client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    assert me_resp.json()["id"] == user_id

    bad_login = user_client.post("/auth/login", json={"username": "alice", "password": "wrong"})
    assert bad_login.status_code == 401


def test_read_user_endpoint(user_client: TestClient):
    resp = user_client.post("/users/", json={"username": "bob", "email": "b@example.com", "password": "123456"})
    assert resp.status_code == 201
    user_id = resp.json()["id"]

    fetched = user_client.get(f"/users/{user_id}")
    assert fetched.status_code == 200
    assert fetched.json()["username"] == "bob"


