# Backend API

## Run locally (PowerShell)

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:SIM_ALLOWED_TARGETS = "192.168.100.20/32"
uvicorn app.main:app --host 127.0.0.1 --port 8010 --reload
```

Or run from repository root:

```powershell
$env:SIM_ALLOWED_TARGETS = "192.168.100.20/32"
docker compose up --build -d
docker compose logs -f api
```

API docs: http://127.0.0.1:8010/docs

## Tests

Install pytest in the development environment and run:

```powershell
python -m pip install pytest
python -m pytest
```

## Current scope
This is a control-plane foundation: health, hard limits, explicit private-target allowlist, durable experiment-plan storage, listing, and stop-state recording. It does not create Docker workers or generate network traffic. The stop endpoint updates plan state only; it is not yet an emergency stop for running processes. Do not describe this release as a functioning traffic generator or as SNA-integrated until those features are implemented and tested.
