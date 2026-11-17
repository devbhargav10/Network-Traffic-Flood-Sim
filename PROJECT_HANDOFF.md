# Project Handoff

## Source of truth
Repository: `devbhargav10/Network-Traffic-Flood-Sim`
Branch: `main`

## Reference repository
`devbhargav10/Network-Traffic-Sim-Prototype` was inspected on 2026-11-17 and is empty (GitHub repository size 0). No reference code is available.

## User environment
- Windows + Docker Desktop; no extra Linux VM.
- Cisco SNA Manager, Flow Collector, and Flow Sensor VMs.
- Hypervisor reported as "other"; exact product is unknown.
- Goal: manage multiple Docker lab hosts and validate Cisco SNA visibility and detections.

## Current implementation
- FastAPI control plane, SQLite persistence, Dockerfile, Compose file.
- Experiment plans can be created, listed, and marked stopped.
- Explicit private IP/CIDR allowlist via `SIM_ALLOWED_TARGETS`; empty configuration denies all.
- Caps: 50 workers, 60 seconds, 100 events/second, 3,000 aggregate packet-equivalent events.
- Tests added but not executed in this environment.
- **No traffic is generated. No Docker worker containers are orchestrated. No frontend exists. No SNA integration exists.**

## Critical networking constraint
Docker Desktop containers run behind a managed Linux networking layer. Distinct internal Docker IPs do not prove that Cisco SNA sees those addresses as separate sources. Record separate evidence for generated traffic, sensor observation, exporter sends, collector receipt, and SNA display.

## Safety contract
Do not add unrestricted Internet flooding, spoofed source addresses, reflection/amplification, or unbounded packet rates. Enforce allowlist and limits server-side. Any future worker must be cancellable, auditable, duration-bounded, and constrained to the configured lab target.

## Exact next actions
1. Clone repo and run `python -m pip install -r backend/requirements.txt`.
2. Add pytest to dev dependencies and run policy tests.
3. Build with `docker compose build`; start only the API and verify `/health`.
4. Add a worker manager that provisions idle containers only, with resource limits and ownership labels.
5. Add an authenticated UI for host inventory and experiment plans.
6. Only then add bounded lab traffic profiles and real cancellation.
7. Identify the actual hypervisor before specifying Flow Sensor port mirroring.
8. Implement telemetry evidence collection and verify end-to-end in SNA.

Update this file, `PROJECT_STATUS.md`, and `IMPLEMENTATION_LOG.md` after each meaningful task. Report test results exactly; do not mark unexecuted tests as passed.