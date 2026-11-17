# Architecture

## Logical components

1. **Dashboard** — host inventory, target allowlist, experiment configuration, live status, history, and telemetry verification.
2. **API/controller** — authentication, validation, policy enforcement, experiment lifecycle, audit events.
3. **Docker orchestrator** — creates and monitors worker containers on an isolated user-defined network.
4. **Worker** — performs bounded protocol/application behavior against a pre-approved lab target.
5. **Telemetry verifier** — records evidence from each observation stage; never equates Docker IP assignment with SNA visibility.
6. **Persistence** — durable experiment, host, configuration, and audit records.

## Windows-only deployment topology

```
Windows workstation
  ├─ Dashboard + API + database
  └─ Docker Desktop managed Linux VM
       └─ Isolated Docker bridge (private RFC1918 subnet)
            ├─ worker-001 (unique container IP)
            ├─ worker-002 (unique container IP)
            └─ worker-N (unique container IP)

Cisco SNA Flow Sensor VM
  └─ Must observe traffic through a supported virtual switch / mirror / routed observation point

Cisco SNA Flow Collector VM
  └─ Receives supported flow telemetry

Cisco SNA Manager VM
  └─ Displays hosts, conversations, and detection events
```

The sensor connection from Docker Desktop to the hypervisor is environment-dependent. No exact mirror/vSwitch configuration can be safely specified until the hypervisor product and network topology are identified.

## Network plan

Candidate isolated subnet: `172.30.50.0/24`
- Docker gateway: `172.30.50.1`
- worker addresses: `172.30.50.11`–`172.30.50.60` for a 50-worker test.

This is a proposal, not a final allocation. Before creating it, check for overlap with host routes, VPNs, Docker networks, and the SNA management/telemetry networks. Use Docker's internal network option for identity/lifecycle tests; this intentionally prevents external connectivity and is not an SNA traffic test.

## Telemetry state model

- `CONFIGURED`: container and IP exist.
- `GENERATED`: worker reports bounded traffic counters.
- `OBSERVED_AT_SENSOR`: sensor-side evidence confirms packets/flows.
- `EXPORTED`: exporter reports sending records.
- `COLLECTOR_ACCEPTED`: collector-side evidence confirms receipt.
- `VISIBLE_IN_SNA`: SNA UI/API confirms the expected host/flow.
- `NOT_VERIFIED` / `FAILED`: evidence missing or a stage failed.

Each state requires independent evidence and timestamp.

## Security controls

- Explicit target allowlist, private lab CIDRs only by default.
- Server-side policy enforcement.
- Fixed maximum workers, duration, packet/byte rate, and total volume.
- No spoofed source addresses or arbitrary destination selection.
- Authentication and audit log.
- Emergency stop and startup recovery that stops stale experiments.
- Docker CPU/memory/PID limits and least privilege.
- Secrets via environment/secret store; never commit credentials.