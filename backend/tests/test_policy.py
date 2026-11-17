import pytest
from fastapi.testclient import TestClient

import app.main as main


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "policy-test.db")
    monkeypatch.setenv("SIM_API_KEY", "policy-test-key-" + "x" * 40)
    monkeypatch.setenv("SIM_WLAN_AGENT_ENABLED", "false")
    with TestClient(main.app) as test_client:
        yield test_client


def test_health_is_public_but_control_api_requires_auth(client):
    assert client.get("/health").status_code == 200
    assert client.get("/api/v1/limits").status_code == 401


def test_wlan_agent_mode_fails_closed_when_disabled(client):
    headers = {"Authorization": "Bearer policy-test-key-" + "x" * 40}
    response = client.post("/api/v1/wlan-experiments", headers=headers,
                           json={"workers": 1, "duration_seconds": 1})
    assert response.status_code == 403


def test_agent_cannot_claim_jobs_when_mode_is_disabled(client):
    headers = {"Authorization": "Bearer policy-test-key-" + "x" * 40}
    response = client.get("/api/v1/agent/next?agent_id=test-host", headers=headers)
    assert response.status_code == 403
