# Project Status

Last updated: 2026-11-17

## Repository baseline
- Development repository was empty at start.
- Reference repository `devbhargav10/Network-Traffic-Sim-Prototype` was also empty (GitHub reports size 0).
- No prior source implementation could be migrated or audited.

## Environment constraints
- Windows host with Docker Desktop Linux containers.
- Cisco SNA Manager, Flow Collector, and Flow Sensor VMs.
- Hypervisor product and virtual-switch/mirroring capabilities remain unknown.
- No additional Linux VM is available.

## Implemented in GitHub
- [x] Project scope, safety contract, architecture, operations, test plan, and handoff docs.
- [x] FastAPI control-plane foundation with SQLite persistence.
- [x] Health and hard-limit endpoints.
- [x] Experiment-plan creation/list/stop-state endpoints.
- [x] Explicit private target IP/CIDR allowlist; empty allowlist denies all.
- [x] Worker, duration, rate, and aggregate packet-equivalent budget validation.
- [x] Dockerfile and localhost-bound Docker Compose API service.
- [x] Initial policy unit tests.

## Not implemented / not verified
- [ ] Docker worker lifecycle and 50-host orchestration.
- [ ] Any real traffic generation (current API stores plans only).
- [ ] Frontend dashboard.
- [ ] Authentication and user/role management.
- [ ] Runtime execution of tests; GitHub writes do not execute code.
- [ ] Windows Docker deployment validation.
- [ ] Flow export, sensor observation, collector ingestion, and SNA UI verification.
- [ ] Hypervisor-specific mirror/virtual-switch setup.

## Current API limits
- 50 workers maximum (plan validation only).
- 60 seconds maximum duration.
- 100 events/second maximum per plan.
- 3,000 aggregate packet-equivalent events per plan.
- Only private targets explicitly covered by `SIM_ALLOWED_TARGETS`.
- Traffic generation is disabled.

## Acceptance criteria
1. Docker workers have unique private addresses, with no claim that Docker IP equals externally visible source IP.
2. A bounded experiment can only target an explicitly allowlisted lab endpoint.
3. Hard caps are enforced server-side.
4. Emergency stop terminates actual running work, not just metadata.
5. Generated, sensor-observed, exported, collector-accepted, and SNA-visible states have independent evidence.
6. Tests and Windows deployment pass before release.