# Project Status

Last updated: 2026-11-17

## Implemented in this release
- FastAPI dashboard served from the same origin as the API.
- Bearer API-key authentication on all control endpoints.
- SQLite persistence and audit history.
- Fixed local-only UDP sender and receiver, both bound to 127.0.0.1.
- Up to 50 concurrent asyncio worker tasks, one datagram/second each.
- Hard caps: 50 workers, 10 seconds, 50 aggregate messages/second, 500 messages/run.
- One active experiment at a time.
- Explicit plan then start workflow; plan creation sends nothing.
- Per-experiment stop, global emergency stop, no auto-resume after restart.
- Docker hardening: non-root, dropped capabilities, read-only root filesystem, resource limits, localhost-only published port.
- Automated API tests authored.

## Not yet independently verified
- Windows Docker Desktop build and runtime.
- Full pytest run in the user's environment.
- Dashboard browser interaction on the user's machine.
- Long-run reliability and abrupt process-kill recovery.
- Any SNA visibility. The local loopback traffic intentionally does not traverse WLAN or reach the WLC.

## Safety / architecture
These are 50 concurrent logical worker tasks in one API container, not 50 independent Docker containers or unique wireless clients. The receiver only listens on loopback. There is no external target mode in this release.
