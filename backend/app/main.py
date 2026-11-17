"""Authenticated local-only traffic lab with bounded asyncio workers.

Workers send fixed-format UDP diagnostics only to the receiver bound to 127.0.0.1.
No raw sockets, Docker socket, host networking, arbitrary target or external egress.
"""
from __future__ import annotations

import asyncio
import hmac
import json
import os
import sqlite3
import uuid
from contextlib import asynccontextmanager, closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

APP_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("SIM_DB_PATH", str(APP_DIR.parent / "data" / "simulator.db")))
WEB_DIR = APP_DIR / "static"
API_KEY_MIN_LENGTH = 32
MAX_WORKERS = 50
MAX_DURATION_SECONDS = 10
MAX_PER_WORKER_PPS = 1
MAX_AGGREGATE_PPS = 50
MAX_TOTAL_EVENTS = 500
RECEIVER_HOST = "127.0.0.1"
RECEIVER_PORT = 9999
bearer = HTTPBearer(auto_error=False)

ACTIVE: dict[str, dict[str, Any]] = {}
receiver_transport: asyncio.DatagramTransport | None = None
sender_transport: asyncio.DatagramTransport | None = None
receiver_protocol: "LocalReceiver | None" = None
runtime_lock: asyncio.Lock | None = None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


def initialize() -> None:
    with closing(db()) as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS experiments (
                id TEXT PRIMARY KEY,
                target_ip TEXT NOT NULL,
                protocol TEXT NOT NULL,
                workers INTEGER NOT NULL,
                duration_seconds INTEGER NOT NULL,
                rate_pps INTEGER NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('PLANNED', 'CANCELLED')),
                created_at TEXT NOT NULL,
                stopped_at TEXT
            );
            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                resource_id TEXT,
                details TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS local_experiments (
                id TEXT PRIMARY KEY,
                profile TEXT NOT NULL,
                workers INTEGER NOT NULL,
                duration_seconds INTEGER NOT NULL,
                per_worker_pps INTEGER NOT NULL,
                aggregate_pps INTEGER NOT NULL,
                max_events INTEGER NOT NULL,
                sent INTEGER NOT NULL DEFAULT 0,
                received INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                stop_reason TEXT
            );
            CREATE TABLE IF NOT EXISTS wlan_experiments (
                id TEXT PRIMARY KEY,
                workers INTEGER NOT NULL,
                duration_seconds INTEGER NOT NULL,
                per_worker_pps INTEGER NOT NULL,
                aggregate_pps INTEGER NOT NULL,
                max_events INTEGER NOT NULL,
                sent INTEGER NOT NULL DEFAULT 0,
                received INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                queued_at TEXT,
                started_at TEXT,
                finished_at TEXT,
                stop_reason TEXT,
                agent_id TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_wlan_created ON wlan_experiments(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_wlan_status ON wlan_experiments(status);
            CREATE INDEX IF NOT EXISTS idx_experiments_created
                ON experiments(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_audit_created
                ON audit_events(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_local_created
                ON local_experiments(created_at DESC);
            """
        )
        # Never resume traffic after a process/container restart.
        conn.execute(
            """UPDATE local_experiments
               SET status='INTERRUPTED', finished_at=?, stop_reason='controller_restart'
               WHERE status IN ('STARTING','RUNNING','STOPPING')""",
            (utc_now(),),
        )
        conn.execute(
            """UPDATE wlan_experiments
               SET status='INTERRUPTED', finished_at=?, stop_reason='controller_restart'
               WHERE status IN ('QUEUED','RUNNING','STOP_REQUESTED')""",
            (utc_now(),),
        )
        conn.commit()


def audit(conn: sqlite3.Connection, event_type: str, resource_id: str | None, details: str) -> None:
    conn.execute(
        "INSERT INTO audit_events(event_type, resource_id, details, created_at) VALUES (?, ?, ?, ?)",
        (event_type, resource_id, details, utc_now()),
    )


def local_enabled() -> bool:
    return os.getenv("SIM_LOCAL_TRAFFIC_ENABLED", "false").strip().lower() == "true"


def update_local(experiment_id: str, **fields: Any) -> None:
    allowed = {"status", "sent", "received", "started_at", "finished_at", "stop_reason"}
    if not fields or not set(fields).issubset(allowed):
        raise ValueError("Invalid local experiment update")
    assignments = ", ".join(f"{key}=?" for key in fields)
    values = list(fields.values()) + [experiment_id]
    with closing(db()) as conn:
        conn.execute(f"UPDATE local_experiments SET {assignments} WHERE id=?", values)
        conn.commit()


class LocalReceiver(asyncio.DatagramProtocol):
    """A loopback-only sink. It accepts only this application's small test frames."""

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        if addr[0] != "127.0.0.1" or len(data) > 256:
            return
        try:
            frame = json.loads(data.decode("utf-8"))
            experiment_id = str(frame["experiment_id"])
            worker_id = int(frame["worker_id"])
            sequence = int(frame["sequence"])
        except (ValueError, KeyError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
            return
        runtime = ACTIVE.get(experiment_id)
        if runtime is None or not (1 <= worker_id <= runtime["workers"]):
            return
        if not (1 <= sequence <= MAX_DURATION_SECONDS):
            return
        runtime["received"] += 1
        try:
            update_local(experiment_id, received=runtime["received"])
        except sqlite3.Error:
            runtime["receiver_errors"] += 1


async def wait_or_stop(event: asyncio.Event, delay: float) -> bool:
    try:
        await asyncio.wait_for(event.wait(), timeout=max(0.0, delay))
        return True
    except asyncio.TimeoutError:
        return False


async def run_worker(experiment_id: str, worker_id: int, runtime: dict[str, Any]) -> None:
    loop = asyncio.get_running_loop()
    start = runtime["start_monotonic"]
    deadline = runtime["deadline"]
    for sequence in range(1, MAX_DURATION_SECONDS + 1):
        due = start + (sequence - 1) + ((worker_id - 1) / MAX_WORKERS)
        if loop.time() >= deadline or runtime["stop_event"].is_set():
            return
        if await wait_or_stop(runtime["stop_event"], due - loop.time()):
            return
        if loop.time() >= deadline or runtime["stop_event"].is_set():
            return
        frame = json.dumps(
            {"experiment_id": experiment_id, "worker_id": worker_id, "sequence": sequence},
            separators=(",", ":"),
        ).encode("utf-8")
        # The sender and receiver are both loopback-bound inside this process/container.
        sender_transport.sendto(frame, (RECEIVER_HOST, RECEIVER_PORT))
        runtime["sent"] += 1
        update_local(experiment_id, sent=runtime["sent"])


async def run_experiment(experiment_id: str, runtime: dict[str, Any]) -> None:
    try:
        await asyncio.gather(
            *(run_worker(experiment_id, worker_id, runtime)
              for worker_id in range(1, runtime["workers"] + 1))
        )
        final_status = "STOPPED" if runtime["stop_event"].is_set() else "COMPLETED"
        reason = runtime.get("stop_reason") or ("operator_stop" if final_status == "STOPPED" else "duration_elapsed")
        update_local(
            experiment_id,
            status=final_status,
            finished_at=utc_now(),
            stop_reason=reason,
            sent=runtime["sent"],
            received=runtime["received"],
        )
        with closing(db()) as conn:
            audit(conn, f"LOCAL_EXPERIMENT_{final_status}", experiment_id,
                  f"sent={runtime['sent']}; received={runtime['received']}; reason={reason}")
            conn.commit()
    except asyncio.CancelledError:
        update_local(experiment_id, status="STOPPED", finished_at=utc_now(),
                     stop_reason="controller_shutdown", sent=runtime["sent"],
                     received=runtime["received"])
        raise
    except Exception as exc:
        update_local(experiment_id, status="FAILED", finished_at=utc_now(),
                     stop_reason=type(exc).__name__, sent=runtime["sent"],
                     received=runtime["received"])
        with closing(db()) as conn:
            audit(conn, "LOCAL_EXPERIMENT_FAILED", experiment_id, type(exc).__name__)
            conn.commit()
    finally:
        ACTIVE.pop(experiment_id, None)


async def stop_one(experiment_id: str, reason: str) -> dict:
    runtime = ACTIVE.get(experiment_id)
    if runtime is None:
        with closing(db()) as conn:
            row = conn.execute("SELECT status FROM local_experiments WHERE id=?", (experiment_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Local experiment not found")
        return {"id": experiment_id, "status": row["status"]}
    runtime["stop_reason"] = reason
    runtime["stop_event"].set()
    update_local(experiment_id, status="STOPPING")
    runner = runtime.get("runner")
    if runner is not None:
        try:
            await asyncio.wait_for(asyncio.shield(runner), timeout=2.0)
        except asyncio.TimeoutError:
            runner.cancel()
            await asyncio.gather(runner, return_exceptions=True)
    with closing(db()) as conn:
        row = conn.execute("SELECT status FROM local_experiments WHERE id=?", (experiment_id,)).fetchone()
        audit(conn, "LOCAL_EXPERIMENT_STOP_REQUESTED", experiment_id, reason)
        conn.commit()
    return {"id": experiment_id, "status": row["status"] if row else "STOPPED"}


@asynccontextmanager
async def lifespan(_: FastAPI):
    global receiver_transport, sender_transport, receiver_protocol, runtime_lock
    initialize()
    runtime_lock = asyncio.Lock()
    loop = asyncio.get_running_loop()
    receiver_transport, receiver_protocol = await loop.create_datagram_endpoint(
        LocalReceiver, local_addr=(RECEIVER_HOST, RECEIVER_PORT)
    )
    sender_transport, _ = await loop.create_datagram_endpoint(
        asyncio.DatagramProtocol, local_addr=(RECEIVER_HOST, 0)
    )
    yield
    for experiment_id in list(ACTIVE):
        runtime = ACTIVE.get(experiment_id)
        if runtime:
            runtime["stop_reason"] = "controller_shutdown"
            runtime["stop_event"].set()
            if runtime.get("runner"):
                runtime["runner"].cancel()
    if ACTIVE:
        await asyncio.gather(
            *(r["runner"] for r in list(ACTIVE.values()) if r.get("runner")),
            return_exceptions=True,
        )
    if sender_transport:
        sender_transport.close()
    if receiver_transport:
        receiver_transport.close()


app = FastAPI(
    title="Network Traffic Lab Controller",
    version="1.0.0",
    description="Authenticated local-only traffic lab with 50 bounded asyncio workers.",
    lifespan=lifespan,
)


def require_api_key(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> str:
    configured = os.getenv("SIM_API_KEY", "")
    if len(configured) < API_KEY_MIN_LENGTH:
        raise HTTPException(status_code=503, detail="API authentication is not configured")
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Bearer API key required",
                            headers={"WWW-Authenticate": "Bearer"})
    if not hmac.compare_digest(credentials.credentials, configured):
        raise HTTPException(status_code=401, detail="Invalid API key",
                            headers={"WWW-Authenticate": "Bearer"})
    return "api-key"

def require_agent_key(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> str:
    """Separate machine credential: never reuse the dashboard/operator API key."""
    configured = os.getenv("SIM_AGENT_API_KEY", "")
    if len(configured) < API_KEY_MIN_LENGTH:
        raise HTTPException(status_code=503, detail="Windows agent authentication is not configured")
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Agent bearer token required",
                            headers={"WWW-Authenticate": "Bearer"})
    if not hmac.compare_digest(credentials.credentials, configured):
        raise HTTPException(status_code=401, detail="Invalid agent credential",
                            headers={"WWW-Authenticate": "Bearer"})
    return "windows-agent"


class LocalExperimentRequest(BaseModel):
    workers: int = Field(default=50, ge=1, le=MAX_WORKERS)
    duration_seconds: int = Field(default=10, ge=1, le=MAX_DURATION_SECONDS)


@app.get("/", include_in_schema=False)
def dashboard() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "network-traffic-lab-controller",
        "mode": "local-receiver-only",
        "traffic_generation_enabled": local_enabled(),
        "wlan_agent_enabled": os.getenv("SIM_WLAN_AGENT_ENABLED", "false").lower() == "true",
        "active_local_experiments": len(ACTIVE),
    }


@app.get("/ready")
def readiness() -> dict:
    try:
        with closing(db()) as conn:
            conn.execute("SELECT 1").fetchone()
        receiver_ready = receiver_transport is not None and not receiver_transport.is_closing()
    except sqlite3.Error as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    if not receiver_ready:
        raise HTTPException(status_code=503, detail="Local receiver unavailable")
    return {"status": "ready", "database": "available", "local_receiver": "127.0.0.1:9999"}


def _wlan_active_statuses():
    with closing(db()) as conn:
        rows = conn.execute("SELECT status FROM wlan_experiments WHERE status IN ('QUEUED','RUNNING','STOP_REQUESTED')").fetchall()
    return [row["status"] for row in rows]


@app.get("/api/v1/limits", dependencies=[Depends(require_api_key)])
def limits() -> dict:
    return {
        "max_workers": MAX_WORKERS,
        "max_duration_seconds": MAX_DURATION_SECONDS,
        "per_worker_pps": MAX_PER_WORKER_PPS,
        "max_aggregate_pps": MAX_AGGREGATE_PPS,
        "max_total_events": MAX_TOTAL_EVENTS,
        "receiver": "Configured private test receiver on Windows agent",
        "target_scope": "One authorized private test receiver only; WLC management and NetFlow collector addresses are blocked",
        "wlan_agent_enabled": os.getenv("SIM_WLAN_AGENT_ENABLED", "false").lower() == "true",
        "traffic_generation_enabled": local_enabled(),
        "active_experiments": len(ACTIVE),
        "active_wlan_experiments": len(_wlan_active_statuses()),
    }


@app.post("/api/v1/local-experiments", status_code=201, dependencies=[Depends(require_api_key)])
def create_local_experiment(request: LocalExperimentRequest) -> dict:
    if not local_enabled():
        raise HTTPException(status_code=403, detail="Local traffic execution is disabled; set SIM_LOCAL_TRAFFIC_ENABLED=true")
    experiment_id = str(uuid.uuid4())
    created_at = utc_now()
    aggregate_pps = request.workers * MAX_PER_WORKER_PPS
    max_events = aggregate_pps * request.duration_seconds
    if max_events > MAX_TOTAL_EVENTS:
        raise HTTPException(status_code=422, detail="Experiment exceeds the 500-message budget")
    with closing(db()) as conn:
        if conn.execute("SELECT 1 FROM local_experiments WHERE status IN ('STARTING','RUNNING','STOPPING')").fetchone():
            raise HTTPException(status_code=409, detail="Another local experiment is active")
        conn.execute(
            """INSERT INTO local_experiments
               (id,profile,workers,duration_seconds,per_worker_pps,aggregate_pps,max_events,status,created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (experiment_id, "local-udp-loopback", request.workers, request.duration_seconds,
             MAX_PER_WORKER_PPS, aggregate_pps, max_events, "PLANNED", created_at),
        )
        audit(conn, "LOCAL_EXPERIMENT_PLANNED", experiment_id,
              f"workers={request.workers}; duration={request.duration_seconds}; receiver=loopback")
        conn.commit()
    return {"id": experiment_id, "status": "PLANNED", "workers": request.workers,
            "duration_seconds": request.duration_seconds, "aggregate_pps": aggregate_pps,
            "max_events": max_events, "receiver": f"{RECEIVER_HOST}:{RECEIVER_PORT}",
            "message": "Plan created only. No messages sent until explicit start."}


@app.post("/api/v1/local-experiments/stop-all", dependencies=[Depends(require_api_key)])
async def stop_all() -> dict:
    stopped = []
    for experiment_id in list(ACTIVE):
        stopped.append(await stop_one(experiment_id, "global_emergency_stop"))
    with closing(db()) as conn:
        audit(conn, "GLOBAL_EMERGENCY_STOP", None, f"active_experiments_stopped={len(stopped)}")
        conn.commit()
    return {"stopped": stopped, "count": len(stopped)}


@app.post("/api/v1/local-experiments/{experiment_id}/start", dependencies=[Depends(require_api_key)])
async def start_local_experiment(experiment_id: str) -> dict:
    if not local_enabled():
        raise HTTPException(status_code=403, detail="Local traffic execution is disabled")
    if sender_transport is None or sender_transport.is_closing():
        raise HTTPException(status_code=503, detail="Local sender unavailable")
    async with runtime_lock:
        with closing(db()) as conn:
            row = conn.execute("SELECT * FROM local_experiments WHERE id=?", (experiment_id,)).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="Local experiment not found")
            if row["status"] != "PLANNED":
                raise HTTPException(status_code=409, detail=f"Experiment is {row['status']}, not PLANNED")
            if conn.execute("SELECT 1 FROM local_experiments WHERE status IN ('STARTING','RUNNING','STOPPING')").fetchone():
                raise HTTPException(status_code=409, detail="Another local experiment is active")
            started_at = utc_now()
            conn.execute("UPDATE local_experiments SET status='RUNNING', started_at=? WHERE id=?",
                         (started_at, experiment_id))
            audit(conn, "LOCAL_EXPERIMENT_STARTED", experiment_id, "Local loopback worker tasks launched")
            conn.commit()
        loop = asyncio.get_running_loop()
        runtime = {
            "workers": row["workers"],
            "duration": row["duration_seconds"],
            "sent": 0,
            "received": 0,
            "receiver_errors": 0,
            "stop_event": asyncio.Event(),
            "start_monotonic": loop.time(),
            "deadline": loop.time() + row["duration_seconds"],
            "stop_reason": None,
        }
        ACTIVE[experiment_id] = runtime
        runtime["runner"] = asyncio.create_task(run_experiment(experiment_id, runtime))
    return {"id": experiment_id, "status": "RUNNING", "workers": row["workers"],
            "duration_seconds": row["duration_seconds"],
            "aggregate_pps": row["aggregate_pps"], "max_events": row["max_events"],
            "receiver": f"{RECEIVER_HOST}:{RECEIVER_PORT}"}


@app.post("/api/v1/local-experiments/{experiment_id}/stop", dependencies=[Depends(require_api_key)])
async def stop_local_experiment(experiment_id: str) -> dict:
    return await stop_one(experiment_id, "operator_stop")


@app.get("/api/v1/local-experiments", dependencies=[Depends(require_api_key)])
def list_local_experiments(limit: int = Query(default=100, ge=1, le=500)) -> list[dict]:
    with closing(db()) as conn:
        rows = conn.execute(
            "SELECT * FROM local_experiments ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(row) for row in rows]


@app.get("/api/v1/local-experiments/{experiment_id}", dependencies=[Depends(require_api_key)])
def get_local_experiment(experiment_id: str) -> dict:
    with closing(db()) as conn:
        row = conn.execute("SELECT * FROM local_experiments WHERE id=?", (experiment_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Local experiment not found")
    result = dict(row)
    runtime = ACTIVE.get(experiment_id)
    if runtime:
        result.update(sent=runtime["sent"], received=runtime["received"])
    return result


class WLANExperimentRequest(BaseModel):
    workers: int = Field(default=50, ge=1, le=MAX_WORKERS)
    duration_seconds: int = Field(default=10, ge=1, le=MAX_DURATION_SECONDS)


class AgentReport(BaseModel):
    sent: int = Field(ge=0, le=MAX_TOTAL_EVENTS)
    received: int = Field(ge=0, le=MAX_TOTAL_EVENTS)
    status: str = Field(pattern="^(COMPLETED|STOPPED|FAILED)$")
    stop_reason: str | None = Field(default=None, max_length=80)


@app.post("/api/v1/wlan-experiments", status_code=201, dependencies=[Depends(require_api_key)])
def create_wlan_experiment(request: WLANExperimentRequest) -> dict:
    if os.getenv("SIM_WLAN_AGENT_ENABLED", "false").lower() != "true":
        raise HTTPException(status_code=403, detail="Windows WLAN agent mode is disabled")
    experiment_id = str(uuid.uuid4())
    created = utc_now()
    rate = request.workers * MAX_PER_WORKER_PPS
    budget = rate * request.duration_seconds
    with closing(db()) as conn:
        active = conn.execute(
            "SELECT 1 FROM wlan_experiments WHERE status IN ('QUEUED','RUNNING','STOP_REQUESTED')"
        ).fetchone()
        if active:
            raise HTTPException(status_code=409, detail="A WLAN agent experiment is already active")
        conn.execute(
            """INSERT INTO wlan_experiments
               (id,workers,duration_seconds,per_worker_pps,aggregate_pps,max_events,status,created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (experiment_id, request.workers, request.duration_seconds, MAX_PER_WORKER_PPS,
             rate, budget, "PLANNED", created),
        )
        audit(conn, "WLAN_EXPERIMENT_PLANNED", experiment_id,
              f"workers={request.workers}; duration={request.duration_seconds}; aggregate_pps={rate}")
        conn.commit()
    return {"id": experiment_id, "status": "PLANNED", "workers": request.workers,
            "duration_seconds": request.duration_seconds, "aggregate_pps": rate,
            "max_events": budget,
            "message": "Plan only. Start queues the job for the authenticated Windows agent."}


@app.get("/api/v1/wlan-experiments", dependencies=[Depends(require_api_key)])
def list_wlan_experiments(limit: int = Query(default=100, ge=1, le=500)) -> list[dict]:
    with closing(db()) as conn:
        rows = conn.execute(
            "SELECT * FROM wlan_experiments ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(row) for row in rows]


@app.get("/api/v1/wlan-experiments/{experiment_id}", dependencies=[Depends(require_api_key)])
def get_wlan_experiment(experiment_id: str) -> dict:
    with closing(db()) as conn:
        row = conn.execute("SELECT * FROM wlan_experiments WHERE id=?", (experiment_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="WLAN experiment not found")
    return dict(row)


@app.post("/api/v1/wlan-experiments/{experiment_id}/start", dependencies=[Depends(require_api_key)])
def start_wlan_experiment(experiment_id: str) -> dict:
    if os.getenv("SIM_WLAN_AGENT_ENABLED", "false").lower() != "true":
        raise HTTPException(status_code=403, detail="Windows WLAN agent mode is disabled")
    with closing(db()) as conn:
        row = conn.execute("SELECT * FROM wlan_experiments WHERE id=?", (experiment_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="WLAN experiment not found")
        if row["status"] != "PLANNED":
            raise HTTPException(status_code=409, detail=f"Experiment is {row['status']}, not PLANNED")
        active = conn.execute(
            "SELECT 1 FROM wlan_experiments WHERE status IN ('QUEUED','RUNNING','STOP_REQUESTED')"
        ).fetchone()
        if active:
            raise HTTPException(status_code=409, detail="Another WLAN experiment is active")
        conn.execute("UPDATE wlan_experiments SET status='QUEUED', queued_at=? WHERE id=?",
                     (utc_now(), experiment_id))
        audit(conn, "WLAN_EXPERIMENT_QUEUED", experiment_id, "Queued for Windows host agent")
        conn.commit()
    return {"id": experiment_id, "status": "QUEUED",
            "message": "Waiting for the Windows agent. No traffic is sent by the API container."}


@app.post("/api/v1/wlan-experiments/{experiment_id}/stop", dependencies=[Depends(require_api_key)])
def stop_wlan_experiment(experiment_id: str) -> dict:
    with closing(db()) as conn:
        row = conn.execute("SELECT status FROM wlan_experiments WHERE id=?", (experiment_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="WLAN experiment not found")
        if row["status"] == "QUEUED":
            new_status = "CANCELLED"
            conn.execute("UPDATE wlan_experiments SET status=?, finished_at=?, stop_reason=? WHERE id=?",
                         (new_status, utc_now(), "cancelled_before_agent_start", experiment_id))
        elif row["status"] == "RUNNING":
            new_status = "STOP_REQUESTED"
            conn.execute("UPDATE wlan_experiments SET status=?, stop_reason=? WHERE id=?",
                         (new_status, "operator_stop", experiment_id))
        else:
            new_status = row["status"]
        audit(conn, "WLAN_EXPERIMENT_STOP_REQUESTED", experiment_id, "Operator stop")
        conn.commit()
    return {"id": experiment_id, "status": new_status}


@app.post("/api/v1/wlan-experiments/stop-all", dependencies=[Depends(require_api_key)])
def stop_all_wlan_experiments() -> dict:
    with closing(db()) as conn:
        queued = conn.execute(
            "UPDATE wlan_experiments SET status='CANCELLED', finished_at=?, stop_reason='global_emergency_stop' WHERE status='QUEUED'",
            (utc_now(),),
        ).rowcount
        running = conn.execute(
            "UPDATE wlan_experiments SET status='STOP_REQUESTED', stop_reason='global_emergency_stop' WHERE status='RUNNING'"
        ).rowcount
        audit(conn, "WLAN_GLOBAL_EMERGENCY_STOP", None, f"queued_cancelled={queued}; running_stop_requested={running}")
        conn.commit()
    return {"queued_cancelled": queued, "running_stop_requested": running}


# The Windows agent polls over the existing localhost-published API. It never accepts
# a destination from the controller; its receiver address is fixed in its local config.
@app.get("/api/v1/agent/next", dependencies=[Depends(require_agent_key)])
def agent_next_job(agent_id: str = Query(min_length=1, max_length=80)) -> dict:
    if os.getenv("SIM_WLAN_AGENT_ENABLED", "false").lower() != "true":
        raise HTTPException(status_code=403, detail="Windows WLAN agent mode is disabled")
    with closing(db()) as conn:
        # Serialize claims and make the state transition conditional. This prevents
        # two pollers from receiving the same queued experiment.
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT * FROM wlan_experiments WHERE status='QUEUED' ORDER BY queued_at LIMIT 1"
        ).fetchone()
        if row is None:
            conn.commit()
            return {"job": None}
        changed = conn.execute(
            "UPDATE wlan_experiments SET status='RUNNING', started_at=?, agent_id=? WHERE id=? AND status='QUEUED'",
            (utc_now(), agent_id, row["id"]),
        ).rowcount
        if changed != 1:
            conn.commit()
            return {"job": None}
        audit(conn, "WLAN_AGENT_CLAIMED_JOB", row["id"], f"agent_id={agent_id}")
        conn.commit()
    return {"job": {"id": row["id"], "workers": row["workers"],
                    "duration_seconds": row["duration_seconds"],
                    "per_worker_pps": row["per_worker_pps"],
                    "aggregate_pps": row["aggregate_pps"],
                    "max_events": row["max_events"]}}


@app.get("/api/v1/agent/jobs/{experiment_id}", dependencies=[Depends(require_agent_key)])
def agent_job_status(experiment_id: str) -> dict:
    if os.getenv("SIM_WLAN_AGENT_ENABLED", "false").lower() != "true":
        raise HTTPException(status_code=403, detail="Windows WLAN agent mode is disabled")
    with closing(db()) as conn:
        row = conn.execute("SELECT status FROM wlan_experiments WHERE id=?", (experiment_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="WLAN experiment not found")
    return {"id": experiment_id, "status": row["status"]}


@app.post("/api/v1/agent/jobs/{experiment_id}/report", dependencies=[Depends(require_agent_key)])
def agent_report(experiment_id: str, report: AgentReport) -> dict:
    if os.getenv("SIM_WLAN_AGENT_ENABLED", "false").lower() != "true":
        raise HTTPException(status_code=403, detail="Windows WLAN agent mode is disabled")
    with closing(db()) as conn:
        row = conn.execute("SELECT status,max_events FROM wlan_experiments WHERE id=?", (experiment_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="WLAN experiment not found")
        if row["status"] not in ("RUNNING", "STOP_REQUESTED"):
            raise HTTPException(status_code=409, detail=f"Cannot report for status {row['status']}")
        if report.sent > row["max_events"] or report.received > report.sent:
            raise HTTPException(status_code=422, detail="Reported counters exceed experiment budget")
        final_status = "STOPPED" if row["status"] == "STOP_REQUESTED" else report.status
        conn.execute(
            """UPDATE wlan_experiments SET status=?,sent=?,received=?,finished_at=?,stop_reason=?
               WHERE id=?""",
            (final_status, report.sent, report.received, utc_now(),
             report.stop_reason or ("controller_stop" if final_status == "STOPPED" else "duration_elapsed"),
             experiment_id),
        )
        audit(conn, "WLAN_AGENT_REPORT", experiment_id,
              f"status={final_status}; sent={report.sent}; received={report.received}")
        conn.commit()
    return {"id": experiment_id, "status": final_status}


@app.get("/api/v1/experiments", dependencies=[Depends(require_api_key)])
def list_legacy_experiments() -> list[dict]:
    with closing(db()) as conn:
        rows = conn.execute("SELECT * FROM experiments ORDER BY created_at DESC LIMIT 500").fetchall()
    return [dict(row) for row in rows]


@app.post("/api/v1/experiments/{experiment_id}/stop", dependencies=[Depends(require_api_key)])
def stop_legacy_experiment(experiment_id: str) -> dict:
    stopped_at = utc_now()
    with closing(db()) as conn:
        row = conn.execute("SELECT status FROM experiments WHERE id=?", (experiment_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Experiment not found")
        if row["status"] == "CANCELLED":
            return {"id": experiment_id, "status": "CANCELLED"}
        conn.execute("UPDATE experiments SET status='CANCELLED', stopped_at=? WHERE id=?",
                     (stopped_at, experiment_id))
        audit(conn, "EXPERIMENT_CANCELLED", experiment_id, "Unstarted legacy plan cancelled")
        conn.commit()
    return {"id": experiment_id, "status": "CANCELLED", "stopped_at": stopped_at}


@app.get("/api/v1/audit", dependencies=[Depends(require_api_key)])
def list_audit_events(limit: int = 100) -> list[dict]:
    if not 1 <= limit <= 500:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 500")
    with closing(db()) as conn:
        rows = conn.execute(
            "SELECT id,event_type,resource_id,details,created_at FROM audit_events ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]
