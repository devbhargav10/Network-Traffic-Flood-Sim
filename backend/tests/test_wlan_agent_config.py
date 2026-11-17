import importlib.util
import json
from pathlib import Path

import pytest


AGENT_PATH = Path(__file__).resolve().parents[2] / "windows-agent" / "wlan_agent.py"
SPEC = importlib.util.spec_from_file_location("wlan_agent", AGENT_PATH)
agent = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(agent)


def write_config(tmp_path, monkeypatch, **values):
    path = tmp_path / "agent-config.json"
    path.write_text(json.dumps(values), encoding="utf-8")
    monkeypatch.setenv("SIM_AGENT_CONFIG", str(path))


def test_receiver_config_accepts_private_test_host(tmp_path, monkeypatch):
    write_config(tmp_path, monkeypatch, receiver_ip="192.168.50.20", receiver_port=19055,
                 authorization="AUTHORIZED_TEST_RECEIVER_NOT_WLC")
    assert agent.load_receiver() == ("192.168.50.20", 19055)


@pytest.mark.parametrize("address", ["10.6.1.55", "10.6.1.94", "10.5.1.1"])
def test_receiver_config_blocks_known_infrastructure(address, tmp_path, monkeypatch):
    write_config(tmp_path, monkeypatch, receiver_ip=address, receiver_port=19055,
                 authorization="AUTHORIZED_TEST_RECEIVER_NOT_WLC")
    with pytest.raises(ValueError, match="Refusing known"):
        agent.load_receiver()


def test_receiver_config_rejects_non_private_address(tmp_path, monkeypatch):
    write_config(tmp_path, monkeypatch, receiver_ip="8.8.8.8", receiver_port=19055,
                 authorization="AUTHORIZED_TEST_RECEIVER_NOT_WLC")
    with pytest.raises(ValueError, match="private IPv4"):
        agent.load_receiver()


def test_receiver_config_requires_authorization_acknowledgement(tmp_path, monkeypatch):
    write_config(tmp_path, monkeypatch, receiver_ip="192.168.50.20", receiver_port=19055,
                 authorization="not-confirmed")
    with pytest.raises(ValueError, match="authorization"):
        agent.load_receiver()


def test_receiver_port_is_fixed(tmp_path, monkeypatch):
    write_config(tmp_path, monkeypatch, receiver_ip="192.168.50.20", receiver_port=2055,
                 authorization="AUTHORIZED_TEST_RECEIVER_NOT_WLC")
    with pytest.raises(ValueError, match="fixed at UDP 19055"):
        agent.load_receiver()
