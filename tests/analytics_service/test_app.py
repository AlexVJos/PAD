import pytest
from fastapi.testclient import TestClient
from pathlib import Path

from tests.utils import configure_sqlite_env, reload_module


@pytest.fixture()
def analytics_module(tmp_path: Path):
    configure_sqlite_env("ANALYTICS_DB_URL", tmp_path / "analytics.db")
    module = reload_module("services.analytics_service.app")
    with TestClient(module.app) as client:
        yield module, client


@pytest.mark.asyncio
async def test_metrics_updated_from_events(analytics_module):
    module, client = analytics_module
    event_base = {"payload": {"user_id": 3}}
    await module.event_handler({"type": "loan.created", **event_base})
    await module.event_handler({"type": "loan.returned", **event_base})

    summary = client.get("/metrics/summary")
    assert summary.status_code == 200
    assert summary.json()["total_loans"] == 1
    assert summary.json()["total_returns"] == 1

    user_metrics = client.get("/metrics/users/3")
    assert user_metrics.status_code == 200
    body = user_metrics.json()
    assert body["loans_taken"] == 1
    assert body["loans_returned"] == 1


