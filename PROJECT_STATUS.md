# Project Status

Last updated: 2026-11-17

## Repository baseline
- Development repository was empty at start.
- Reference repository `devbhargav10/Network-Traffic-Sim-Prototype` was also empty (GitHub reports size 0).
- No prior source implementation could be migrated or audited.

## Environment constraints
- Windows host with Docker Desktop Linux containers.
- Cisco SNA Manager, Flow Collector, and Flow Sensor are deployed as VMs.
- Hypervisor product and virtual-switch/mirroring capabilities are not yet known.
- No additional Linux VM is available.

## Implemented
- [x] Project README and safety contract.
- [x] Persistent status, handoff, architecture, operations, and test documentation.

## Not yet implemented / not verified
- [ ] Frontend dashboard.
- [ ] Backend API and durable experiment store.
- [ ] Docker host lifecycle/orchestration.
- [ ] Per-host traffic worker.
- [ ] Lab target allowlist and experiment guardrails.
- [ ] Emergency stop.
- [ ] SNA telemetry/flow ingestion verification.
- [ ] End-to-end tests on the user's Windows machine.

## Acceptance criteria
1. User can create/manage a bounded pool of independent containers.
2. Each container has a unique Docker-network IP; the UI labels this as container identity, not proof of external source-IP visibility.
3. User can define an allowlisted private lab target and a bounded experiment.
4. Every experiment is rate-, duration-, and resource-limited and can be stopped immediately.
5. UI reports generated, sensor-observed, and collector-ingested telemetry as separate states.
6. A failed or unverified SNA observation is shown honestly, never as success.
7. All operations are auditable and restart-safe.
8. Tests, docs, and Windows deployment scripts pass before release.