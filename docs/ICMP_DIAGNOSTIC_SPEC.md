# Bounded ICMP Diagnostic Experiment Specification

Status: **Design only — not implemented; no traffic has been sent.**  
Target profile: **10.6.1.55, 5 ICMP echo requests/second, 10 seconds.**

## 1. Objective and scope

Add an IP-driven ICMP diagnostic experiment to the existing Windows + Docker Desktop simulator. An authenticated operator supplies an explicitly allowlisted private destination IP, selects the ICMP diagnostic profile, reviews the calculated packet budget, and starts or stops a short reachability/response test.

This is a diagnostic workload, not a denial-of-service or flood feature. The initial profile is fixed at one worker, 5 packets per second, 10 seconds, and at most 50 echo requests. No traffic is sent by this specification or by the current application.

## 2. Known environment

- Simulator host: Windows, Wi-Fi address reported as 10.5.1.204.
- Candidate destination: 10.6.1.55. Operator describes this as the WLC IP; its exact interface/role is not independently confirmed.
- SNA Flow Collector: 10.6.1.94.
- Intended NetFlow destination: UDP/2055, but the Collector listener and WLC exporter configuration are not yet verified.
- ICMP reachability from the Windows host to 10.6.1.55 succeeded with 0% loss and 3–5 ms RTT in the operator's test.
- Current API is a plan-only FastAPI + SQLite control plane. `traffic_generation_enabled` is false. No worker runtime, real cancellation, or NetFlow exporter exists.

## 3. User workflow

1. Operator enters destination IP.
2. API validates the IP syntax, private-address policy, and exact membership in `SIM_ALLOWED_TARGETS`.
3. UI/API displays the resolved experiment profile and packet budget before start.
4. Operator explicitly confirms and starts the experiment.
5. Controller launches one isolated ICMP worker and records its worker identity/process/container ID.
6. UI/API reports running state, sent/reply counts, loss, RTT statistics, and timestamps.
7. Operator can stop the experiment immediately. Natural completion, manual stop, timeout, worker failure, and controller restart are distinct outcomes.
8. Audit history records requested settings, policy decision, lifecycle transitions, and aggregate results. Never log the API key.

## 4. Initial approved profile

| Setting | Initial value | Enforced ceiling |
|---|---:|---:|
| Protocol | ICMP echo request only | ICMP echo only |
| Destination | 10.6.1.55 | Exact allowlist match required |
| Workers | 1 | 1 |
| Rate | 5 packets/second | 5 packets/second |
| Duration | 10 seconds | 10 seconds |
| Total requests | 50 maximum | 50 |
| Payload | 32 bytes | Fixed; no user-controlled payload |
| Concurrency | 1 outstanding probe | 1 |
| Redirects / alternate targets | Disabled | Disabled |

The scheduler must use a monotonic clock and evenly space probes at 200 ms intervals. It must not catch up by sending bursts after a delayed interval. A late tick is skipped or the experiment is terminated according to the implementation's documented timing policy. The worker stops at the first of: 50 requests sent, 10 seconds elapsed, explicit cancellation, policy violation, or fatal worker error.

## 5. Authorization and target policy

- Require the existing bearer API key for all experiment and control endpoints.
- Keep `SIM_ALLOWED_TARGETS` deny-by-default. For this first authorized test, the operator may configure the single host as `10.6.1.55/32`.
- Validate the destination on the server immediately before launch, not only in the UI or request model.
- Reject public, multicast, broadcast, loopback, link-local, unspecified, IPv4-mapped IPv6, and non-allowlisted destinations.
- Do not accept a hostname, URL, arbitrary packet type, source-address override, raw packet bytes, or user-supplied payload for this profile.
- Do not spoof source addresses, use fragmentation, send ICMP redirects, or implement reflection/amplification.
- A destination being pingable does not prove it is a WLC management IP, client gateway, or valid traffic observation point. Display the destination as operator-supplied and unverified until confirmed.

## 6. Worker isolation and permissions

- Keep the API/controller container unprivileged and without raw-socket capability.
- Run the probe in a separate short-lived worker container/process with only the minimum raw ICMP capability required (Linux `CAP_NET_RAW`); never use privileged mode or host networking.
- Drop all other Linux capabilities, use a read-only root filesystem, non-root UID, memory/CPU/PID limits, and a bounded execution timeout.
- Worker must have egress only to the exact approved destination and ICMP echo protocol, enforced outside the worker as well as in application policy where feasible. Do not rely on an in-container allowlist alone.
- Do not expose the Docker socket to the worker. If the controller requires Docker orchestration, isolate that authority in a narrowly scoped launcher component; do not give the API container unrestricted Docker control.
- Docker Desktop networking/NAT may make the packet source appear as the Windows host or Docker VM. Do not claim the WLC sees a separate wireless client or distinct endpoint identity.

## 7. API and lifecycle contract

Proposed endpoints (names may be adjusted to match the implementation):

- `POST /api/v1/experiments`: validate and create a plan; preserve current plan-only behavior until the worker feature is enabled.
- `POST /api/v1/experiments/{id}/start`: explicit operator action to launch an approved plan.
- `POST /api/v1/experiments/{id}/stop`: signal cancellation and wait for worker termination within a short bounded grace period; force-terminate the worker if graceful cancellation fails.
- `GET /api/v1/experiments/{id}`: return lifecycle state and aggregate metrics.
- `GET /api/v1/experiments`: list recent experiments.
- `GET /api/v1/audit`: retrieve audit history.

Suggested lifecycle states: `PLANNED`, `STARTING`, `RUNNING`, `STOPPING`, `COMPLETED`, `STOPPED`, `FAILED`. State transitions must be transactional and validated. Repeated stop calls must be idempotent. Stop on a missing ID returns 404. A stop response must not claim success until the worker is confirmed stopped.

On API/container restart, reconcile persisted RUNNING/STARTING experiments against worker identity. Terminate orphaned workers owned by this application and mark interrupted experiments `FAILED` or `STOPPED` with a recovery audit event. Never automatically restart an ICMP experiment after a controller restart.

## 8. Emergency stop

Provide both per-experiment stop and a global stop-all control. The global control must:
- Require authentication and an explicit operator action.
- Signal all active workers, wait for confirmation, then force-terminate any remaining owned workers.
- Persist stop reason and timestamps and write audit events.
- Be idempotent and safe to invoke repeatedly.
- Be available independently of the dashboard UI (authenticated API/CLI path).
- Fail closed: if worker state cannot be determined, block new experiments and surface an unhealthy controller state.

The worker itself must enforce the hard 10-second deadline even if the API/controller becomes unavailable.

## 9. Telemetry and audit

Record only bounded aggregate evidence:
- Experiment ID, target IP, protocol/profile, requested and effective rate/duration/budget.
- Request count, reply count, timeout count, packet loss percentage.
- RTT min/mean/max when replies exist.
- Start/end/stop timestamps, final state, stop reason, worker ID.
- Policy decision and lifecycle audit events.

Do not store packet payloads or credentials. Avoid logging secrets or full authorization headers.

## 10. SNA/WLC interpretation

The ICMP test targets 10.6.1.55 directly. If this is the WLC management interface, packets may be processed by the controller's management/control plane. This does not prove that client traffic traversed the WLAN or that the WLC exported a flow record.

ICMP may not be represented in NetFlow in the same way as TCP/UDP conversations, depending on WLC export support and configuration. UDP/2055 is the intended flow-export transport destination, not the destination port for this ICMP test.

Validation must distinguish:
1. Worker reports ICMP requests sent.
2. Destination replies are received.
3. WLC/AP observation evidence exists (if applicable).
4. WLC exports a supported flow record.
5. Collector confirms receipt.
6. SNA displays the expected host/flow.

Never infer a later stage from an earlier one. Do not send arbitrary UDP payloads to port 2055 as a substitute for valid NetFlow records.

## 11. Acceptance criteria

- Invalid, public, or non-allowlisted destinations are rejected before worker creation.
- A request exceeding 1 worker, 5 pps, 10 seconds, or 50 requests is rejected server-side.
- Initial configured profile for 10.6.1.55 calculates exactly 50 maximum echo requests.
- No packet is sent when an experiment is merely created or previewed.
- Only an explicit authenticated start action launches the worker.
- Worker stops automatically at 10 seconds/50 requests.
- Manual per-experiment stop and global stop-all terminate the worker and are confirmed by process/container state.
- API/controller restart does not leave orphaned workers or restart old experiments.
- Audit records plan, authorization decision, start, stop/completion, and final metrics.
- Tests verify scheduler spacing, hard ceilings, allowlist enforcement, idempotent stop, forced termination, restart recovery, and absence of traffic on plan creation.
- End-to-end test confirms the actual WLC/Collector/SNA observation path before any claim of SNA visibility.

## 12. Implementation sequence

1. Extend schema and API lifecycle with plan-only tests; keep traffic generation disabled.
2. Implement isolated worker runner and cancellation/recovery contract.
3. Implement the fixed ICMP profile and unit/integration tests using a local controlled test target.
4. Add UI controls for preview, explicit start, live status, stop, and stop-all.
5. Test from the Windows/Docker Desktop environment against the single approved target during an authorized maintenance/test window.
6. Separately validate WLC flow export and SNA visibility; do not conflate ICMP reachability with NetFlow ingestion.

## 13. Current release status

This document is a specification only. The repository currently has no traffic worker or true emergency stop. Do not enable `traffic_generation_enabled` until implementation, tests, runtime isolation, and stop/recovery behavior pass their release gates. No traffic was generated while preparing this document.
