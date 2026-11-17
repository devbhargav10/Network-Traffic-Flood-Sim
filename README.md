# Network Traffic Flood Sim

A Windows-first Docker lab controller for authorized network-behavior and Cisco Secure Network Analytics (SNA) telemetry validation.

> **Current release is control-plane only.** It stores bounded experiment plans; it does not launch worker containers or generate packets. Do not treat a planned experiment as generated traffic or SNA evidence.

## Confirmed lab environment
- Windows host with Docker Desktop (Linux containers).
- Windows address reported by PowerShell: `10.5.1.204`.
- Cisco SNA Flow Collector / Data Store: `10.6.1.94` (Connected).
- Cisco SNA Data Node: `10.6.1.92` (Connected).
- Cisco SNA Manager: `10.6.1.93` (Connected).
- Windows ping to the Flow Collector succeeds.
- Operator reports existing network devices export NetFlow; no dedicated Flow Sensor is deployed.
- Collector listen protocol/port and the exporting devices are not yet verified.

## Safety and networking
- Explicit private IP/CIDR allowlist; empty configuration denies every target.
- Hard server-side limits: 50 workers, 60 seconds, 100 events/second, 3,000 aggregate event budget.
- No unrestricted Internet flooding, source spoofing, reflection/amplification, or unbounded generation.
- API is bound to Windows localhost by Compose.
- Docker Desktop container IPs are internal addresses. They are not automatically visible as distinct source addresses outside Docker's managed Linux VM.
- SNA visibility must be confirmed from actual received flow records. A Docker IP or locally generated counter is not proof of Collector ingestion.

## Start on Windows
1. Install Docker Desktop and switch to Linux containers.
2. Copy `.env.example` to `.env`.
3. Generate a key in PowerShell:
   ```powershell
   [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
   ```
4. Put the generated value in `SIM_API_KEY` in `.env`. Keep `SIM_ALLOWED_TARGETS` empty until a specifically authorized lab target has been confirmed.
5. Start the API:
   ```powershell
   docker compose up --build -d
   docker compose ps
   docker compose logs -f api
   ```
6. Check health:
   ```powershell
   Invoke-RestMethod http://127.0.0.1:8010/health
   Invoke-RestMethod http://127.0.0.1:8010/ready
   ```

## Authenticated API example
Set the same secret in the current PowerShell session (do not paste it into tickets or commit it):
```powershell
$headers = @{ Authorization = "Bearer $env:SIM_API_KEY" }
Invoke-RestMethod -Uri http://127.0.0.1:8010/api/v1/limits -Headers $headers
```

API endpoints:
- `GET /health` — liveness, no credentials.
- `GET /ready` — database readiness, no credentials.
- `GET /api/v1/limits` — policy limits, bearer key required.
- `POST /api/v1/experiments` — create a validated plan, bearer key required.
- `GET /api/v1/experiments` — list plans, bearer key required.
- `POST /api/v1/experiments/{id}/stop` — cancel an unstarted plan, bearer key required.
- `GET /api/v1/audit?limit=100` — audit records, bearer key required.
- `/docs` — interactive OpenAPI docs (API operations still enforce authentication).

## Development tests
```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m pytest
```

## Roadmap / release gate
1. Run unit/API tests and Docker build on the actual Windows host.
2. Add isolated worker lifecycle with resource caps, ownership labels, rollback and real cancellation.
3. Add narrowly scoped, rate- and duration-bounded traffic profiles.
4. Confirm Collector NetFlow/IPFIX configuration and actual exporter network path before implementing exporter support.
5. Add a dashboard for hosts, experiments, audit and telemetry evidence.
6. Prove the chain: worker-generated -> exporter-sent -> Collector-received -> SNA-visible.

See [PROJECT_STATUS.md](PROJECT_STATUS.md), [PROJECT_HANDOFF.md](PROJECT_HANDOFF.md), and [docs/TESTING.md](docs/TESTING.md).
