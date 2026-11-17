# Testing and Verification

## Unit tests
- Target allowlist rejects public/unapproved destinations.
- Duration, worker count, packet rate, and total-byte caps are enforced server-side.
- Stop requests cancel active workers and mark experiments stopped.
- Restart recovery terminates stale experiments safely.
- Audit events are created for create/start/stop/failure actions.

## Docker integration tests
- Worker container names are unique and deterministic.
- Container IP assignments are unique within the configured subnet.
- CPU, memory, PID, and restart policy limits are applied.
- Cleanup removes only resources owned by this application.
- Failure during partial provisioning rolls back created workers.

## SNA verification
For each test record:
- worker identity and Docker IP
- target IP/port/protocol
- generated packet/byte counters
- sensor observation evidence and timestamp
- flow exporter protocol/template and send counters
- collector receipt evidence
- SNA host/flow record evidence

A test is not an SNA pass unless the expected source/destination/protocol/volume is independently visible in SNA. Container IP assignment alone is never sufficient.

## Release gate
All automated tests pass, emergency stop is demonstrated, no experiment can exceed configured caps, and SNA visibility is reported honestly as PASS / FAIL / NOT VERIFIED.