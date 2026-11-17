# Backend API

## Run locally (PowerShell)

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8010 --reload
```

Or run the API container from the repository root:

```powershell
docker compose up --build -d
docker compose logs -f api
```

API docs: http://127.0.0.1:8010/docs

## Current scope
This is a control-plane foundation: health, hard limits, private-target validation, durable experiment-plan storage, listing, and stop-state recording. It does not create Docker workers or generate network traffic. Do not describe it as a functioning traffic generator or as SNA-integrated until those features are implemented and tested.
