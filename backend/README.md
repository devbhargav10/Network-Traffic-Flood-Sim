# Backend API

## Run with Docker Compose (recommended)
From repository root, copy `.env.example` to `.env`, set a random `SIM_API_KEY` of at least 32 characters, then run:

```powershell
docker compose up --build -d
docker compose ps
Invoke-RestMethod http://127.0.0.1:8010/health
Invoke-RestMethod http://127.0.0.1:8010/ready
```

Keep `SIM_ALLOWED_TARGETS` empty until an authorized private lab endpoint is explicitly approved. Compose refuses to start if `SIM_API_KEY` is missing.

## Run locally (PowerShell)
```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:SIM_API_KEY = "replace-with-a-random-secret-of-at-least-32-characters"
$env:SIM_ALLOWED_TARGETS = ""
uvicorn app.main:app --host 127.0.0.1 --port 8010
```

## Authenticated API
Use `Authorization: Bearer <SIM_API_KEY>` for every `/api/v1/*` endpoint. Health and readiness are unauthenticated for local container health checks.

Endpoints: `GET /api/v1/limits`, `POST /api/v1/experiments`, `GET /api/v1/experiments`, `POST /api/v1/experiments/{id}/stop`, and `GET /api/v1/audit`.

## Tests
```powershell
python -m pip install -r requirements-dev.txt
python -m pytest
```

## Scope limitation
This version stores validated experiment plans and audit records only. It does not create Docker workers, generate packets, export NetFlow/IPFIX, or integrate with Cisco SNA. The cancellation endpoint cancels an unstarted plan; it is not yet an emergency stop for running processes. Do not describe this release as a traffic generator or SNA-integrated until those capabilities are implemented and verified.
