import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import app.main as main
from app.main import ExperimentRequest, app


@pytest.fixture
def isolated_db(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "test.db")


def test_target_is_denied_when_allowlist_is_empty(monkeypatch):
    monkeypatch.delenv("SIM_ALLOWED_TARGETS", raising=False)
    with pytest.raises(ValidationError):
        ExperimentRequest(target_ip="192.168.100.10", protocol="tcp-connect")


def test_target_must_match_explicit_allowlist(monkeypatch):
    monkeypatch.setenv("SIM_ALLOWED_TARGETS", "192.168.100.20/32")
    with pytest.raises(ValidationError):
        ExperimentRequest(target_ip="192.168.100.21", protocol="tcp-connect")


def test_allowlisted_private_target_is_accepted(monkeypatch):
    monkeypatch.setenv("SIM_ALLOWED_TARGETS", "192.168.100.0/24")
    request = ExperimentRequest(target_ip="192.168.100.20", protocol="tcp-connect", workers=2)
    request.validate_budget()


def test_public_target_is_rejected_even_if_configured(monkeypatch):
    monkeypatch.setenv("SIM_ALLOWED_TARGETS", "8.8.8.8/32")
    with pytest.raises(ValidationError):
        ExperimentRequest(target_ip="8.8.8.8", protocol="icmp")


def test_worker_and_duration_caps_are_enforced(monkeypatch):
    monkeypatch.setenv("SIM_ALLOWED_TARGETS", "192.168.100.0/24")
    with pytest.raises(ValidationError):
        ExperimentRequest(target_ip="192.168.100.20", protocol="udp-echo", workers=51)


def test_packet_equivalent_budget_is_enforced(monkeypatch):
    monkeypatch.setenv("SIM_ALLOWED_TARGETS", "192.168.100.0/24")
    request = ExperimentRequest(
        target_ip="192.168.100.20", protocol="udp-echo",
        workers=50, duration_seconds=60, rate_pps=100,
    )
    with pytest.raises(ValueError):
        request.validate_budget()


def test_api_requires_bearer_key(monkeypatch, isolated_db):
    monkeypatch.setenv("SIM_API_KEY", "x" * 40)
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/api/v1/limits").status_code == 401
        assert client.get("/api/v1/limits", headers={"Authorization": "Bearer " + "x" * 40}).status_code == 200


def test_create_cancel_and_audit(monkeypatch, isolated_db):
    monkeypatch.setenv("SIM_API_KEY", "k" * 40)
    monkeypatch.setenv("SIM_ALLOWED_TARGETS", "192.168.100.0/24")
    headers = {"Authorization": "Bearer " + "k" * 40}
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/experiments",
            headers=headers,
            json={"target_ip": "192.168.100.20", "protocol": "tcp-connect"},
        )
        assert created.status_code == 201
        experiment_id = created.json()["id"]
        cancelled = client.post(f"/api/v1/experiments/{experiment_id}/stop", headers=headers)
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "CANCELLED"
        events = client.get("/api/v1/audit", headers=headers).json()
        assert [event["event_type"] for event in events] == ["EXPERIMENT_CANCELLED", "EXPERIMENT_PLANNED"]
