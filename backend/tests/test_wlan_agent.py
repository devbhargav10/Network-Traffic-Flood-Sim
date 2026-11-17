import pytest
from fastapi.testclient import TestClient
import app.main as main


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "wlan-test.db")
    monkeypatch.setenv("SIM_API_KEY", "operator-test-key-" + "x" * 40)
    monkeypatch.setenv("SIM_AGENT_API_KEY", "agent-test-key-" + "x" * 40)
    monkeypatch.setenv("SIM_WLAN_AGENT_ENABLED", "true")
    monkeypatch.setenv("SIM_LOCAL_TRAFFIC_ENABLED", "false")
    with TestClient(main.app) as test_client:
        yield test_client


@pytest.fixture
def headers():
    return {"Authorization": "Bearer operator-test-key-" + "x" * 40}


def test_wlan_agent_routes_require_separate_machine_credential(client, headers):
    assert client.get("/api/v1/agent/next?agent_id=test-windows", headers=headers).status_code == 401
    agent_headers = {"Authorization": "Bearer agent-test-key-" + "x" * 40}
    assert client.get("/api/v1/agent/next?agent_id=test-windows", headers=agent_headers).status_code == 200


def test_wlan_agent_mode_limits(client, headers):
    response = client.get("/api/v1/limits", headers=headers)
    assert response.status_code == 200
    assert response.json()["wlan_agent_enabled"] is True
    assert response.json()["active_wlan_experiments"] == 0


def test_wlan_job_is_queued_then_claimed_and_reported(client, headers):
    plan = client.post("/api/v1/wlan-experiments", headers=headers,
                       json={"workers": 5, "duration_seconds": 5})
    assert plan.status_code == 201
    experiment_id = plan.json()["id"]
    assert plan.json()["max_events"] == 25

    queued = client.post(f"/api/v1/wlan-experiments/{experiment_id}/start",
                         headers=headers)
    assert queued.status_code == 200
    assert queued.json()["status"] == "QUEUED"

    agent_headers = {"Authorization": "Bearer agent-test-key-" + "x" * 40}
    claimed = client.get("/api/v1/agent/next?agent_id=test-windows",
                         headers=agent_headers)
    assert claimed.status_code == 200
    assert claimed.json()["job"]["id"] == experiment_id

    state = client.get(f"/api/v1/agent/jobs/{experiment_id}", headers=agent_headers)
    assert state.json()["status"] == "RUNNING"

    stop = client.post(f"/api/v1/wlan-experiments/{experiment_id}/stop",
                       headers=headers)
    assert stop.json()["status"] == "STOP_REQUESTED"

    report = client.post(f"/api/v1/agent/jobs/{experiment_id}/report",
                         headers=agent_headers,
                         json={"sent": 5, "received": 0, "status": "STOPPED",
                               "stop_reason": "operator_stop"})
    assert report.status_code == 200
    assert report.json()["status"] == "STOPPED"


def test_wlan_job_hard_limits(client, headers):
    assert client.post("/api/v1/wlan-experiments", headers=headers,
                       json={"workers": 51, "duration_seconds": 10}).status_code == 422
    assert client.post("/api/v1/wlan-experiments", headers=headers,
                       json={"workers": 50, "duration_seconds": 11}).status_code == 422


def test_only_one_wlan_job_active(client, headers):
    first = client.post("/api/v1/wlan-experiments", headers=headers,
                        json={"workers": 1, "duration_seconds": 5}).json()
    assert client.post(f"/api/v1/wlan-experiments/{first['id']}/start",
                       headers=headers).status_code == 200
    second = client.post("/api/v1/wlan-experiments", headers=headers,
                         json={"workers": 1, "duration_seconds": 5})
    assert second.status_code == 409


def test_emergency_stop_cancels_queued_wlan_job(client, headers):
    plan = client.post("/api/v1/wlan-experiments", headers=headers,
                       json={"workers": 1, "duration_seconds": 1}).json()
    client.post(f"/api/v1/wlan-experiments/{plan['id']}/start", headers=headers)
    result = client.post("/api/v1/wlan-experiments/stop-all", headers=headers)
    assert result.status_code == 200
    state = client.get(f"/api/v1/wlan-experiments/{plan['id']}", headers=headers).json()
    assert state["status"] == "CANCELLED"
