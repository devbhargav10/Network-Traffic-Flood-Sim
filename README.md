# Network Traffic Lab

Windows-first, safety-controlled WLAN traffic test controller.

**For the one-Windows-machine setup, follow [docs/WINDOWS_WLAN_AGENT.md](docs/WINDOWS_WLAN_AGENT.md).** The repository includes a FastAPI controller/dashboard, a native Windows traffic agent, and a small UDP receiver for a separate private test VLAN.

## One-host WLAN design

Windows Wi-Fi client (one real MAC/IP)
-> WLAN SSID and WLC forwarding path
-> separately authorized private test receiver (UDP/19055)
-> flow exporter in the WLAN data path
-> Cisco SNA Flow Collector (UDP/2055).

The controller runs in Docker on localhost. The Windows agent runs natively, polls the controller, and sends traffic through the normal Windows Wi-Fi interface. The receiver is a separate host on the test path.

**Important:** 50 workers are logical traffic streams, not 50 independently associated WLAN clients. The WLC will see one Windows client. This mode does not test 50-client association scale, per-client identity, roaming, or client-specific policy.

## Safety controls

- Hard cap: 50 logical workers, 1 packet/second per worker, 50 packets/second aggregate.
- Hard cap: 10 seconds and 500 packets per experiment.
- One active WLAN experiment at a time; explicit plan and start.
- Fixed UDP receiver port 19055; no arbitrary target entered in the dashboard.
- Windows agent requires a private IPv4 receiver in its local config and explicit authorization acknowledgement.
- Agent refuses the known lab WLC, SNA collector, and gateway IPs.
- Controller is published only on 127.0.0.1:8010; the Windows agent polls outbound.
- Stop, emergency stop, audit events, and no automatic job resumption after controller restart.
- UDP delivery is measured at the receiver; sender counters are not treated as proof of receipt.

## Quick start

1. Clone or update the repository.
2. Prepare a separate private test receiver and restrict UDP/19055 to the Windows client's source IP.
3. Keep your existing SIM_API_KEY in .env and set SIM_WLAN_AGENT_ENABLED=true.
4. Run docker compose up --build -d.
5. Configure windows-agent/agent-config.json with the receiver IP and run windows-agent/wlan_agent.py from PowerShell.
6. Open http://127.0.0.1:8010/, connect with the API key, and start with 1 worker for 5 seconds.

Full setup, commands, firewall notes, and troubleshooting: [Windows WLAN agent guide](docs/WINDOWS_WLAN_AGENT.md).

## Local self-test mode

The original loopback-only experiment mode remains available separately with SIM_LOCAL_TRAFFIC_ENABLED=true. It does not send traffic over Wi-Fi and is not a substitute for WLAN/SNA validation.

## Tests

From backend/:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

CI runs the backend test suite and builds the Docker image.
