# Project Status

Last updated: 2026-11-17

## Repository baseline
- Development repository was empty at start.
- Reference repository `devbhargav10/Network-Traffic-Sim-Prototype` was also empty.
- No prior source implementation could be migrated or audited.

## Environment facts supplied by operator
- Windows host with Docker Desktop Linux containers.
- Windows source IP reported by PowerShell: `10.5.1.204`.
- Cisco SNA Flow Collector / Data Store: `10.6.1.94`, Connected.
- Cisco SNA Data Node: `10.6.1.92`, Connected.
- Cisco SNA Manager: `10.6.1.93`, Connected.
- Windows ping to `10.6.1.94` succeeds (4 ms reported).
- Operator says existing network devices export NetFlow and there is no dedicated Flow Sensor.
- Collector's actual NetFlow/IPFIX listen configuration and sender device list have not yet been inspected.
- Hypervisor/virtual-switch details remain unknown.

## Implemented in GitHub
- [x] FastAPI control-plane foundation with SQLite persistence.
- [x] Health and readiness endpoints.
- [x] Bearer API-key authentication for control-plane endpoints.
- [x] Explicit private target IP/CIDR allowlist; empty allowlist denies all.
- [x] Worker, duration, rate, and aggregate event budget validation.
- [x] Experiment-plan creation/list/cancel endpoints.
- [x] Audit events for plan creation and cancellation.
- [x] SQLite WAL, busy timeout, parameterized SQL.
- [x] Dockerfile and localhost-bound Docker Compose API service.
- [x] Compose healthcheck, read-only filesystem, dropped Linux capabilities, resource limits.
- [x] Unit/API tests authored (not yet executed).

## Not implemented / not verified
- [ ] Docker worker lifecycle and multi-host orchestration.
- [ ] Traffic generation (API explicitly remains plan-only).
- [ ] NetFlow/IPFIX exporter implementation.
- [ ] Dashboard/frontend.
- [ ] Role-based users, key rotation and production secret management.
- [ ] Test execution, Docker build and Windows deployment validation.
- [ ] Collector ingest configuration, exporter source configuration and SNA flow visibility verification.
- [ ] Hypervisor-specific network integration.

## Current hard limits
- 50 workers maximum (plan validation only).
- 60 seconds maximum duration.
- 100 events/second maximum.
- 3,000 aggregate packet-equivalent events per plan.
- Only private targets explicitly covered by `SIM_ALLOWED_TARGETS`.
- Traffic generation is disabled.

## Release gate
Do not label production-ready until tests/build pass, runtime authentication and stop controls are verified, the worker runtime is bounded and cancellable, and SNA visibility is independently confirmed.
