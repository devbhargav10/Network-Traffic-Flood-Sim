# Network Traffic Lab

A Windows-first Docker application for exercising bounded worker concurrency against a **local-only UDP receiver**.

## Safety model

- The receiver and sender bind exclusively to `127.0.0.1` inside the API container.
- The app does not accept arbitrary target IPs, hostnames, URLs, packet payloads or source addresses.
- No traffic is sent to a WLC, another LAN device, or the Internet.
- 50 logical asyncio workers maximum; each sends at most 1 fixed UDP datagram/second.
- 10 seconds maximum; 50 messages/second aggregate maximum; 500 messages total maximum.
- Only one experiment may run at a time.
- API-key authentication, SQLite audit trail, per-experiment stop, global emergency stop and restart recovery are included.
- Plan creation sends no messages. An explicit Start action is required.
- Worker tasks run inside the unprivileged API container; they are not 50 separate containers or distinct wireless endpoints.

## Windows quick start

From the repository root in PowerShell:

```powershell
# Pull the implementation
git pull origin main

# Keep your existing SIM_API_KEY. Add this setting to .env:
# SIM_LOCAL_TRAFFIC_ENABLED=true
notepad .env

# Validate and rebuild
docker compose config --quiet
docker compose up --build -d

# Verify
docker compose ps
Invoke-RestMethod http://127.0.0.1:8010/health
Invoke-RestMethod http://127.0.0.1:8010/ready

# Open dashboard
Start-Process http://127.0.0.1:8010/
```

Do not paste your API key into chat, source control or screenshots. Enter it into the dashboard's password field; the key is kept only in the current browser tab's JavaScript memory.

## Dashboard workflow

1. Open `http://127.0.0.1:8010/`.
2. Enter the `SIM_API_KEY` value from your local `.env` and select Connect.
3. Select up to 50 workers and up to 10 seconds.
4. Create plan. This sends no traffic.
5. Select Start selected plan.
6. Watch sent/received counters, loss and status.
7. Use Stop experiment or Emergency stop all when required.

## API

All `/api/v1/*` endpoints require `Authorization: Bearer <SIM_API_KEY>`.

- `GET /api/v1/limits`
- `POST /api/v1/local-experiments` JSON: `{"workers":50,"duration_seconds":10}`
- `POST /api/v1/local-experiments/{id}/start`
- `POST /api/v1/local-experiments/{id}/stop`
- `POST /api/v1/local-experiments/stop-all`
- `GET /api/v1/local-experiments`
- `GET /api/v1/local-experiments/{id}`
- `GET /api/v1/audit?limit=100`

## Tests

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

## Cisco SNA note

This local receiver validates worker concurrency and application lifecycle only. Since all packets terminate inside the API container's loopback interface, they are not WLAN client traffic and will not appear as WLC-originated or client-originated flows in SNA. To test SNA visibility, a separately authorized observation topology is required.
