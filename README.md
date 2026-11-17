# Network Traffic Flood Sim

A Windows-first, Docker-based network behavior and telemetry validation platform for authorized Cisco Secure Network Analytics (SNA) lab environments.

> **Safety boundary:** This project is designed for isolated, explicitly authorized lab targets. It does not provide unrestricted public-IP flooding, source-IP spoofing, or unbounded traffic generation. Experiments must be destination-allowlisted, rate-limited, time-limited, auditable, and stoppable.

## Project goals

- Manage independent Docker host containers on Docker Desktop.
- Assign and track distinct private container IP addresses.
- Configure bounded network-behavior profiles for lab validation.
- Track generated traffic separately from traffic observed by a sensor and flows ingested by SNA.
- Provide a Windows-friendly dashboard and API.
- Preserve implementation state in repository handoff files so another session can continue.

## Environment

- Host: Windows with Docker Desktop (Linux containers).
- Monitoring: Cisco SNA Manager, Flow Collector, and Flow Sensor VMs.
- Hypervisor: not yet identified; monitoring integration must remain hypervisor-agnostic until the virtual-switch capabilities are discovered.
- Initial scale target: 50 hosts, subject to host resource limits.

## Important networking limitation

Docker Desktop runs Linux containers inside a managed Linux VM. Container bridge addresses are not automatically routable or visible as distinct source addresses outside that environment. The application must never report a container as SNA-visible merely because it has a private Docker IP.

The SNA integration must distinguish:
1. Container-assigned identity and address.
2. Traffic measured at the container/worker.
3. Traffic observed by the Flow Sensor.
4. Flow records received and processed by the Flow Collector.

Only evidence from the relevant monitoring point may mark a host as observed by SNA.

## Repository map

- `backend/` — API and orchestration services.
- `frontend/` — dashboard (to be added after stack discovery).
- `docs/ARCHITECTURE.md` — system and network design.
- `docs/OPERATIONS.md` — Windows/Docker setup and operations.
- `docs/TESTING.md` — verification plan and test evidence.
- `PROJECT_STATUS.md` — current implementation state.
- `PROJECT_HANDOFF.md` — exact continuation instructions.
- `IMPLEMENTATION_LOG.md` — chronological work log.

## Initial status

This repository was empty when implementation began. The first commits establish the project contract and persistent handoff system. Application implementation and verification must be recorded as they are completed; do not infer completion from documentation alone.

## Safety defaults

- No arbitrary Internet destinations.
- No source-address spoofing.
- No unbounded packet generation or concurrency.
- No traffic starts automatically on application startup.
- A target must be explicitly allowlisted as a lab endpoint.
- Every experiment has a strict maximum duration and rate/volume budget.
- An emergency stop must cancel jobs and stop associated containers/processes.
