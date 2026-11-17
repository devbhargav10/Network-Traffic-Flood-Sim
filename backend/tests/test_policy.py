import os

import pytest
from pydantic import ValidationError

from app.main import ExperimentRequest


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
    request = ExperimentRequest(
        target_ip="192.168.100.20",
        protocol="tcp-connect",
        workers=2,
        duration_seconds=10,
        rate_pps=5,
    )
    request.validate_budget()


def test_public_target_is_rejected_even_if_configured(monkeypatch):
    monkeypatch.setenv("SIM_ALLOWED_TARGETS", "8.8.8.8/32")
    with pytest.raises(ValidationError):
        ExperimentRequest(target_ip="8.8.8.8", protocol="icmp")


def test_worker_and_duration_caps_are_enforced(monkeypatch):
    monkeypatch.setenv("SIM_ALLOWED_TARGETS", "192.168.100.0/24")
    with pytest.raises(ValidationError):
        ExperimentRequest(
            target_ip="192.168.100.20",
            protocol="udp-echo",
            workers=51,
        )


def test_packet_equivalent_budget_is_enforced(monkeypatch):
    monkeypatch.setenv("SIM_ALLOWED_TARGETS", "192.168.100.0/24")
    request = ExperimentRequest(
        target_ip="192.168.100.20",
        protocol="udp-echo",
        workers=50,
        duration_seconds=60,
        rate_pps=100,
    )
    with pytest.raises(ValueError):
        request.validate_budget()
