"""Safe control-plane API for an authorized network lab.

This first implementation records bounded experiment plans. It deliberately does
not launch packet generators or send network traffic.
"""
from __future__ import annotations

import ipaddress
import os
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator

APP_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("SIM_DB_PATH", APP_DIR.parent / "data" / "simulator.db"))
MAX_WORKERS = 50
MAX_DURATION_SECONDS = 60
MAX_RATE_PPS = 100
MAX_TOTAL_PACKETS = 3000

app = FastAPI(
    title="Network Traffic Lab Controller",
    version="0.1.0",
    description=(
        "Control-plane foundation for authorized lab experiments. "
        "This release stores plans only and does not generate traffic."
    ),
)


def db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def initialize() -> None:
    with closing(db()) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS experiments (
                id TEXT PRIMARY KEY,
                target_ip TEXT NOT NULL,
                protocol TEXT NOT NULL,
                workers INTEGER NOT NULL,
                duration_seconds INTEGER NOT NULL,
                rate_pps INTEGER NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                stopped_at TEXT
            )
            """
        )
        conn.commit()


@app.on_event("startup")
def startup() -> None:
    initialize()


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
            raise ValueError("target_ip must be a valid IPv4 or IPv6 address") from exc
        if not address.is_private or address.is_loopback or address.is_link_local:
            raise ValueError("Only private RFC1918/ULA lab targets are allowed")
        configured = [item.strip() for item in os.getenv("SIM_ALLOWED_TARGETS", "").split(",") if item.strip()]
        if not configured:
            raise ValueError("No lab targets are configured; set SIM_ALLOWED_TARGETS to explicit IPs/CIDRs")
        try:
            networks = [ipaddress.ip_network(item, strict=False) for item in configured]
        except ValueError as exc:
            raise ValueError("SIM_ALLOWED_TARGETS contains an invalid IP or CIDR") from exc
        if not any(address.version == network.version and address in network for network in networks):
            raise ValueError("Target is not inside SIM_ALLOWED_TARGETS")
        return str(address)

    def validate_budget(self) -> None:
        if self.workers * self.duration_seconds * self.rate_pps > MAX_TOTAL_PACKETS:
            raise ValueError(
                f"Requested budget exceeds {MAX_TOTAL_PACKETS} packet-equivalent events"
            )


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "network-traffic-lab-controller",
        "mode": "control-plane-only",
        "traffic_generation_enabled": False,
    }


@app.get("/api/v1/limits")
def limits() -> dict:
    return {
        "max_workers": MAX_WORKERS,
        "max_duration_seconds": MAX_DURATION_SECONDS,
        "max_rate_pps": MAX_RATE_PPS,
        "max_total_packet_equivalents": MAX_TOTAL_PACKETS,
        "allowed_targets": "explicit SIM_ALLOWED_TARGETS IP/CIDR allowlist; deny by default",
        "traffic_generation_enabled": False,
    }


@app.post("/api/v1/experiments", status_code=201)
def create_experiment(request: ExperimentRequest) -> dict:
    try:
        request.validate_budget()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    experiment_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    with closing(db()) as conn:
        conn.execute(
            """
            INSERT INTO experiments
            (id, target_ip, protocol, workers, duration_seconds, rate_pps,
             status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'PLANNED', ?)
            """,
            (
                experiment_id,
                request.target_ip,
                request.protocol,
                request.workers,
                request.duration_seconds,
                request.rate_pps,
                created_at,
            ),
        )
        conn.commit()

    return {
        "id": experiment_id,
        "status": "PLANNED",
        "created_at": created_at,
        "message": (
            "Plan stored only. No containers were started and no traffic was sent."
        ),
    }


@app.get("/api/v1/experiments")
def list_experiments() -> list[dict]:
    with closing(db()) as conn:
        rows = conn.execute(
            "SELECT * FROM experiments ORDER BY created_at DESC"
        ).fetchall()
    return [dict(row) for row in rows]


@app.post("/api/v1/experiments/{experiment_id}/stop")
def stop_experiment(experiment_id: str) -> dict:
    stopped_at = datetime.now(timezone.utc).isoformat()
    with closing(db()) as conn:
        cursor = conn.execute(
            """
            UPDATE experiments
            SET status = 'STOPPED', stopped_at = ?
            WHERE id = ? AND status IN ('PLANNED', 'RUNNING')
            """,
            (stopped_at, experiment_id),
        )
        conn.commit()
        if cursor.rowcount == 0:
            exists = conn.execute(
                "SELECT status FROM experiments WHERE id = ?", (experiment_id,)
            ).fetchone()
            if exists is None:
                raise HTTPException(status_code=404, detail="Experiment not found")
            return {"id": experiment_id, "status": exists["status"]}
    return {"id": experiment_id, "status": "STOPPED", "stopped_at": stopped_at}
