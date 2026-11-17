# One-host WLAN test mode

## What this mode does

The Windows host runs the traffic agent directly, outside Docker. The agent uses the normal Windows IP stack and active Wi-Fi route to send fixed-format UDP diagnostics to one separately administered private test receiver. The controller queues work; the Windows agent polls it over the existing localhost API.

The 50 workers are logical traffic streams, **not 50 WLAN associations**. The WLC will see one associated Windows client (one Wi-Fi MAC and the host's WLAN IP). This mode is useful for validating WLAN forwarding, throughput at a low bounded rate, flow visibility, and SNA ingestion. It cannot validate 50-client association scale, per-client policy, roaming, or per-device identity.

## Hard safety limits

- At most 50 logical workers, 1 datagram/second per worker, 50 datagrams/second aggregate.
- Maximum 10 seconds and 500 datagrams per experiment.
- One active WLAN experiment at a time.
- Fixed UDP destination port 19055; no user-supplied payload, source address, raw sockets, MAC spoofing, or arbitrary target fields.
- Agent accepts only a private IPv4 receiver and requires an explicit authorization string in its local config.
- Agent refuses the known lab WLC (10.6.1.55), SNA Flow Collector (10.6.1.94), and gateway (10.5.1.1) addresses. Verify the receiver is not any infrastructure address before enabling.
- Controller API is published only on 127.0.0.1:8010. The agent polls; no inbound listener is opened on the Windows host.
- Stop requests are polled every 250 ms. A disconnected agent cannot receive a remote stop; the hard 10-second local deadline still terminates its current job.
- UDP is unacknowledged. Receiver logs are authoritative for packets received; the controller does not claim a receiver measurement.

## Topology

Windows 11 Wi-Fi client -> WLAN/SSID -> WLC forwarding path -> private test VLAN receiver UDP/19055.

Configure NetFlow/IPFIX on the appropriate exporter in the WLAN data path to export to SNA Flow Collector 10.6.1.94:2055. UDP/2055 is the exporter destination, **not** the traffic-generator destination. Confirm whether your WLC or upstream gateway exports the client flow; do not assume the WLC management IP is a data-plane receiver.

## Setup

### 1. Prepare the receiver

Use a separate Linux or Windows host on an authorized test VLAN. Give it a stable private IPv4 address. On Linux, run:

```bash
python3 receiver/udp_receiver.py --bind <RECEIVER_PRIVATE_IP> --port 19055
```

Allow inbound UDP/19055 only from the Windows WLAN client's IP in the receiver host firewall and network ACL. Do not expose the receiver to the Internet or bind it to a public interface. Keep its console output for packet counts and source IP/port evidence.

### 2. Enable controller WLAN mode

Keep the existing SIM_API_KEY unchanged in the repository-root .env. Add:

```dotenv
SIM_WLAN_AGENT_ENABLED=true
SIM_LOCAL_TRAFFIC_ENABLED=false
SIM_AGENT_API_KEY=use-a-different-random-secret-at-least-32-characters
```

Then from PowerShell in the repository root:

```powershell
git pull origin main
docker compose config --quiet
docker compose up --build -d
Invoke-RestMethod http://127.0.0.1:8010/health
Invoke-RestMethod http://127.0.0.1:8010/ready
```

### 3. Configure and start the Windows agent

```powershell
Copy-Item .\windows-agent\agent-config.example.json .\windows-agent\agent-config.json
notepad .\windows-agent\agent-config.json
```

Set receiver_ip to the receiver host's private IPv4 address. Keep port 19055. Keep the authorization value only after confirming that this is your authorized test receiver and not the WLC, gateway, SNA collector, or another infrastructure host.

Open a second PowerShell window:

```powershell
$env:SIM_AGENT_API_KEY = Read-Host "Paste the SIM_AGENT_API_KEY machine secret"
$env:SIM_CONTROLLER_URL = "http://127.0.0.1:8010"
$env:SIM_AGENT_CONFIG = ".\windows-agent\agent-config.json"
py -3.12 .\windows-agent\wlan_agent.py
```

Do not reuse SIM_API_KEY for the agent. Do not save either secret in scripts or commit them. Keep the agent window running during the test.

### 4. Run a conservative first test

Open http://127.0.0.1:8010/, enter the same API key, connect, and start with **1 worker for 5 seconds**. Confirm receiver logs show the Windows WLAN IP and packets. Confirm the WLC shows only the Windows client and that the expected flow appears in SNA. Then increase to 5, 10, and only later 50 logical workers if the network owner approves.

The dashboard's received/loss fields are marked external because UDP delivery must be verified from the receiver logs. A successful sender socket call is not proof of receiver delivery.

## Stop and recovery

- Dashboard Stop sends a stop request to the agent.
- Emergency stop cancels queued jobs and requests stop for the running job.
- The agent has a fixed local 10-second deadline even if the controller becomes unreachable.
- To stop immediately at the host, press Ctrl+C in the agent console.
- On controller restart, queued/running jobs are not automatically resumed; inspect experiment status and re-create a test if needed.

## Troubleshooting

- No job starts: verify SIM_WLAN_AGENT_ENABLED=true and SIM_AGENT_API_KEY is set in .env, rebuild compose, and confirm agent is polling without authentication errors. The dashboard continues to use SIM_API_KEY; the Windows agent must use SIM_AGENT_API_KEY.
- No receiver packets: verify Windows route/interface, receiver IP, receiver UDP/19055 listener, firewall allow rule, and WLAN ACLs.
- SNA sees nothing: verify the exporter observes the WLAN client-to-receiver data path and exports to 10.6.1.94:2055. A failed TCP test to 2055 says nothing about UDP NetFlow export.
- WLC shows one client: expected for this single-Windows-host architecture.