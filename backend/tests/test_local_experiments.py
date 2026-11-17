import os
import pytest
from fastapi.testclient import TestClient

import app.main as main


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setenv("SIM_API_KEY", "test-key-" + "x" * 40)
    monkeypatch.setenv("SIM_LOCAL_TRAFFIC_ENABLED", "true")
    with TestClient(main.app) as test_client:
        yield test_client


@pytest.fixture
def headers():
    return {"Authorization": "Bearer test-key-" + "x" * 40}


def test_dashboard_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Traffic Experiment Console" in response.text


def test_auth_required(client):
    assert client.get("/api/v1/limits").status_code == 401


def test_plan_does_not_send_traffic(client, headers):
    response = client.post("/api/v1/local-experiments", headers=headers,
                           json={"workers": 50, "duration_seconds": 10})
    assert response.status_code == 201
    assert response.json()["max_events"] == 500
    assert response.json()["status"] == "PLANNED"
    detail = client.get("/api/v1/local-experiments/" + response.json()["id"],
                        headers=headers).json()
    assert detail["sent"] == 0
    assert detail["received"] == 0


@pytest.mark.parametrize("payload", [
    {"workers": 51, "duration_seconds": 10},
    {"workers": 50, "duration_seconds": 11},
    {"workers": 0, "duration_seconds": 10},
])
def test_hard_limits_reject_invalid_plan(client, headers, payload):
    assert client.post("/api/v1/local-experiments", headers=headers, json=payload).status_code == 422


def test_single_active_experiment_only(client, headers):
    first = client.post("/api/v1/local-experiments", headers=headers,
                        json={"workers": 2, "duration_seconds": 10}).json()
    started = client.post(f"/api/v1/local-experiments/{first['id']}/start", headers=headers)
    assert started.status_code == 200
    second = client.post("/api/v1/local-experiments", headers=headers,
                         json={"workers": 2, "duration_seconds": 10})
    assert second.status_code == 409
    stopped = client.post(f"/api/v1/local-experiments/{first['id']}/stop", headers=headers)
    assert stopped.status_code == 200
    assert stopped.json()["status"] == "STOPPED"


def test_local_execution_feature_flag_fails_closed(client, headers, monkeypatch):
    monkeypatch.setenv("SIM_LOCAL_TRAFFIC_ENABLED", "false")
    response = client.post("/api/v1/local-experiments", headers=headers,
                           json={"workers": 1, "duration_seconds": 1})
    assert response.status_code == 403


def test_run_completes_and_receiver_counts(client, headers):
    plan = client.post("/api/v1/local-experiments", headers=headers,
                       json={"workers": 3, "duration_seconds": 2}).json()
    started = client.post(f"/api/v1/local-experiments/{plan['id']}/start", headers=headers)
    assert started.status_code == 200
    import time
    deadline = time.time() + 4
    while time.time() < deadline:
        state = client.get(f"/api/v1/local-experiments/{plan['id']}", headers=headers).json()
        if state["status"] in ("COMPLETED", "FAILED", "STOPPED"):
            break
        time.sleep(0.05)
    assert state["status"] == "COMPLETED"
    assert state["sent"] == 6
    assert state["received"] == 6


def test_emergency_stop_endpoint(client, headers):
    plan = client.post("/api/v1/local-experiments", headers=headers,
                       json={"workers": 50, "duration_seconds": 10}).json()
    client.post(f"/api/v1/local-experiments/{plan['id']}/start", headers=headers)
    result = client.post("/api/v1/local-experiments/stop-all", headers=headers)
    assert result.status_code == 200
    state = client.get(f"/api/v1/local-experiments/{plan['id']}", headers=headers).json()
    assert state["status"] == "STOPPED"
