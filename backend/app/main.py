"""Authenticated, policy-enforcing control plane for an authorized network lab.

This release stores experiment plans only. It does not create workers or send traffic.
"""
from __future__ import annotations

import hmac
import ipaddress
import os
import sqlite3
import uuid
from contextlib import asynccontextmanager, closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, field_validator

APP_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("SIM_DB_PATH", str(APP_DIR.parent / "data" / "simulator.db")))
MAX_WORKERS = 50
MAX_DURATION_SECONDS = 60
MAX_RATE_PPS = 100
MAX_TOTAL_EVENTS = 3000
API_KEY_MIN_LENGTH = 32
bearer = HTTPBearer(auto_error=False)


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
            CREATE INDEX IF NOT EXISTS idx_experiments_created
                ON experiments(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_audit_created
                ON audit_events(created_at DESC);
            """
        )
        conn.commit()


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize()
    yield


app = FastAPI(
    title="Network Traffic Lab Controller",
    version="0.2.0",
    description=(
        "Authenticated control-plane foundation for authorized lab experiments. "
        "This release stores plans only; it does not generate traffic."
    ),
    lifespan=lifespan,
)


def require_api_key(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> str:
    configured = os.getenv("SIM_API_KEY", "")
    if len(configured) < API_KEY_MIN_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API authentication is not configured; set a random SIM_API_KEY of at least 32 characters",
        )
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer API key required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not hmac.compare_digest(credentials.credentials, configured):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return "api-key"


def audit(conn: sqlite3.Connection, event_type: str, resource_id: str | None, details: str) -> None:
    conn.execute(
        "INSERT INTO audit_events(event_type, resource_id, details, created_at) VALUES (?, ?, ?, ?)",
        (event_type, resource_id, details, utc_now()),
    )


class ExperimentRequest(BaseModel):
    target_ip: str
    protocol: Literal["tcp-connect", "http-get", "udp-echo", "icmp"]
    workers: int = Field(default=1, ge=1, le=MAX_WORKERS)
    duration_seconds: int = Field(default=10, ge=1, le=MAX_DURATION_SECONDS)
    rate_pps: int = Field(default=5, ge=1, le=MAX_RATE_PPS)

    @field_validator("target_ip")
    @classmethod
    def validate_lab_target(cls, value: str) -> str:
        try:
            address = ipaddress.ip_address(value)
        except ValueError as exc:
            raise ValueError("target_ip must be a valid IP address") from exc
        if not address.is_private or address.is_loopback or address.is_link_local:
            raise ValueError("Only private lab IP addresses are allowed")
        configured = [
            item.strip()
            for item in os.getenv("SIM_ALLOWED_TARGETS", "").split(",")
            if item.strip()
        ]
        if not configured:
            raise ValueError("No lab targets configured; set SIM_ALLOWED_TARGETS to explicit IPs/CIDRs")
        try:
            networks = [ipaddress.ip_network(item, strict=False) for item in configured]
        except ValueError as exc:
            raise ValueError("SIM_ALLOWED_TARGETS contains an invalid IP or CIDR") from exc
        if not any(address.version == network.version and address in network for network in networks):
            raise ValueError("Target is not inside SIM_ALLOWED_TARGETS")
        return str(address)

    def validate_budget(self) -> None:
        total = self.workers * self.duration_seconds * self.rate_pps
        if total > MAX_TOTAL_EVENTS:
            raise ValueError(f"Requested budget ({total}) exceeds {MAX_TOTAL_EVENTS} events")


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "network-traffic-lab-controller",
        "mode": "control-plane-only",
        "traffic_generation_enabled": False,
    }


@app.get("/ready")
def readiness() -> dict:
    try:
        with closing(db()) as conn:
            conn.execute("SELECT 1").fetchone()
    except sqlite3.Error as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    return {"status": "ready", "database": "available"}


@app.get("/api/v1/limits", dependencies=[Depends(require_api_key)])
def limits() -> dict:
    return {
        "max_workers": MAX_WORKERS,
        "max_duration_seconds": MAX_DURATION_SECONDS,
        "max_rate_pps": MAX_RATE_PPS,
        "max_total_events": MAX_TOTAL_EVENTS,
        "allowed_targets": "explicit SIM_ALLOWED_TARGETS IP/CIDR allowlist; deny by default",
        "traffic_generation_enabled": False,
    }


@app.post("/api/v1/experiments", status_code=201, dependencies=[Depends(require_api_key)])
def create_experiment(request: ExperimentRequest) -> dict:
    request.validate_budget()
    experiment_id = str(uuid.uuid4())
    created_at = utc_now()
    with closing(db()) as conn:
        conn.execute(
            """
            INSERT INTO experiments
            (id, target_ip, protocol, workers, duration_seconds, rate_pps, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'PLANNED', ?)
            """,
            (
                experiment_id, request.target_ip, request.protocol, request.workers,
                request.duration_seconds, request.rate_pps, created_at,
            ),
        )
        audit(conn, "EXPERIMENT_PLANNED", experiment_id, "Validated plan stored; no traffic sent")
        conn.commit()
    return {
        "id": experiment_id,
        "status": "PLANNED",
        "created_at": created_at,
        "message": "Plan stored only. No containers were started and no traffic was sent.",
    }


@app.get("/api/v1/experiments", dependencies=[Depends(require_api_key)])
def list_experiments() -> list[dict]:
    with closing(db()) as conn:
        rows = conn.execute("SELECT * FROM experiments ORDER BY created_at DESC LIMIT 500").fetchall()
    return [dict(row) for row in rows]


@app.post("/api/v1/experiments/{experiment_id}/stop", dependencies=[Depends(require_api_key)])
def stop_experiment(experiment_id: str) -> dict:
    stopped_at = utc_now()
    with closing(db()) as conn:
        row = conn.execute("SELECT status FROM experiments WHERE id = ?", (experiment_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Experiment not found")
        if row["status"] == "CANCELLED":
            return {"id": experiment_id, "status": "CANCELLED"}
        # This release only creates plans. Do not pretend to stop a worker process.
        conn.execute(
            "UPDATE experiments SET status = 'CANCELLED', stopped_at = ? WHERE id = ?",
            (stopped_at, experiment_id),
        )
        audit(conn, "EXPERIMENT_CANCELLED", experiment_id, "Unstarted plan cancelled")
        conn.commit()
    return {"id": experiment_id, "status": "CANCELLED", "stopped_at": stopped_at}


@app.get("/api/v1/audit", dependencies=[Depends(require_api_key)])
def list_audit_events(limit: int = 100) -> list[dict]:
    if not 1 <= limit <= 500:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 500")
    with closing(db()) as conn:
        rows = conn.execute(
            "SELECT id, event_type, resource_id, details, created_at FROM audit_events ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]
