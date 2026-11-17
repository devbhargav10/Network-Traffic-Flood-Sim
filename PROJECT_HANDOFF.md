# Project Handoff

## Source of truth
Repository: `devbhargav10/Network-Traffic-Flood-Sim`
Branch: `main`

## Environment confirmed by operator
- Windows + Docker Desktop Linux containers.
- Windows IP `10.5.1.204`; PowerShell ping to Collector `10.6.1.94` succeeds (4 ms).
- Cisco SNA Collector/Data Store `10.6.1.94`, Data Node `10.6.1.92`, Manager `10.6.1.93`; all reported Connected.
- Operator says their network devices export NetFlow; no dedicated Flow Sensor.
- Actual Collector listen port/configuration and exporters have not been confirmed.
- Hypervisor remains unidentified.

## Current code state
- FastAPI + SQLite control plane.
- API-key bearer authentication (minimum 32-character `SIM_API_KEY`) for all `/api/v1/*` endpoints.
- `/health` and `/ready` are intentionally unauthenticated for local health checks.
- Explicit private IP/CIDR target allowlist; empty means deny all.
- Caps: 50 workers, 60 seconds, 100 events/second, 3,000 aggregate events.
- Plan creation, listing, cancellation, and audit event endpoints.
- Docker Compose binds to 127.0.0.1:8010 and requires root `.env` with `SIM_API_KEY`.
- No Docker workers, no traffic generation, no exporter, no frontend, no SNA integration.
- Tests authored; not executed.

## Run locally
1. Copy root `.env.example` to `.env`.
2. Generate a unique key with PowerShell:
   `[guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')`
3. Set `SIM_API_KEY` in `.env`. Leave `SIM_ALLOWED_TARGETS` empty until an authorized lab endpoint is confirmed.
4. `docker compose up --build -d`
5. Check `http://127.0.0.1:8010/health` and `/ready`.
6. Authenticated API requests use `Authorization: Bearer <SIM_API_KEY>`.

## Next engineering work
1. Run pytest and Docker build in Windows/Docker Desktop; fix any failures.
2. Design and implement isolated worker lifecycle with ownership labels, resource caps, rollback, and true cancellation.
3. Implement safe traffic profiles only after target and observation path are confirmed.
4. Add NetFlow/IPFIX exporter only after confirming Collector protocol/version/listen port and network reachability.
5. Add dashboard after API lifecycle stabilizes.
6. Verify each stage separately: generated -> exported -> Collector received -> SNA visible.

## Safety contract
No unrestricted Internet flooding, spoofed source IPs, reflection/amplification, or unbounded rates. Do not claim SNA sees container addresses merely because Docker assigned them. Any future worker must be destination-allowlisted, time/rate/volume-bounded, audited, resource-limited, and actually stoppable.
