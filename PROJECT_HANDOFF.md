# Project Handoff

## Current source of truth
Repository: `devbhargav10/Network-Traffic-Flood-Sim`
Branch: `main`

## Reference repository
`devbhargav10/Network-Traffic-Sim-Prototype` was inspected on 2026-11-17 and is empty (repository size 0). Do not assume it contains a working prototype.

## User environment
- Windows + Docker Desktop; no extra Linux VM.
- Cisco SNA Manager, Flow Collector, Flow Sensor VMs.
- Hypervisor reported as "other"; exact product is unknown.
- Goal: create multiple independent Docker hosts and validate Cisco SNA visibility and DDoS detections in an authorized lab.

## Critical design constraint
Docker Desktop container IPs are internal addresses. They do not guarantee that Cisco SNA sees those IPs as distinct sources. Do not claim source identity is preserved through NAT. Implement explicit telemetry checkpoints: container generated, observation point seen, flow exporter sent, collector accepted, SNA displayed.

## Safety contract
Only bounded experiments to explicitly allowlisted lab endpoints. Never implement unrestricted Internet flooding, spoofed source addresses, reflection/amplification, or unbounded packet rates. Hard duration/rate/byte/worker caps, authentication, audit log, and emergency stop are release blockers.

## Next engineering sequence
1. Inspect current branch and these handoff docs.
2. Implement backend skeleton and tests without replacing the safety contract.
3. Implement Docker host lifecycle using Docker Engine API / Docker CLI safely.
4. Implement allowlist + experiment policy enforcement server-side (not only in UI).
5. Implement bounded traffic profiles against local/private lab services only.
6. Implement dashboard and WebSocket status updates.
7. Implement SNA telemetry adapter only after confirming supported observation/export path for this hypervisor.
8. Add Windows PowerShell setup/start/stop scripts and compose configuration.
9. Run automated tests, document actual results, and update this handoff after each meaningful task.

## Required checkpoint format
Update `PROJECT_STATUS.md`, `IMPLEMENTATION_LOG.md`, and this file with:
- files changed
- commands run
- test results (include failures)
- known limitations
- exact next action
Do not report a feature as complete until code and tests demonstrate it.