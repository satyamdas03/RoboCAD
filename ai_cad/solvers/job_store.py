"""SQLite job queue for deep verification analysis.

The job store is thread-safe and persists verification job metadata, inputs,
solver type, status, progress, and result JSON to a local SQLite database.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ai_cad.verification_models import LoadCase, VerificationRequest


class JobStatus(str, Enum):
    """Finite states for a verification job."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


_TERMINAL_STATUSES = {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}


class VerificationJob(BaseModel):
    """Serialized view of a deep verification job."""

    job_id: str
    design_id: str
    load_case: LoadCase
    solver_type: str
    status: JobStatus
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    inputs: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: float
    updated_at: float

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()


class JobStore:
    """Thread-safe SQLite-backed store for verification jobs."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path or "verification_jobs.db").resolve()
        self._lock = threading.RLock()
        self._init_db()

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS verification_jobs (
                    job_id TEXT PRIMARY KEY,
                    design_id TEXT NOT NULL,
                    load_case TEXT NOT NULL,
                    solver_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    progress REAL DEFAULT 0,
                    inputs TEXT,
                    result TEXT,
                    error TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_verification_jobs_design_id "
                "ON verification_jobs(design_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_verification_jobs_status "
                "ON verification_jobs(status)"
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _now(self) -> float:
        return time.time()

    def submit(
        self,
        request: VerificationRequest,
        solver_type: str,
        inputs: dict[str, Any] | None = None,
    ) -> str:
        """Submit a new job and return its id."""
        job_id = uuid.uuid4().hex
        now = self._now()
        job = VerificationJob(
            job_id=job_id,
            design_id=request.design_id,
            load_case=request.load_case,
            solver_type=solver_type,
            status=JobStatus.PENDING,
            progress=0.0,
            inputs=inputs or request.model_dump(),
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO verification_jobs (
                        job_id, design_id, load_case, solver_type, status,
                        progress, inputs, result, error, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        job.job_id,
                        job.design_id,
                        job.load_case.value,
                        job.solver_type,
                        job.status.value,
                        job.progress,
                        json.dumps(job.inputs),
                        None,
                        None,
                        job.created_at,
                        job.updated_at,
                    ),
                )
        return job_id

    def get(self, job_id: str) -> VerificationJob | None:
        """Fetch a single job by id."""
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT * FROM verification_jobs WHERE job_id = ?", (job_id,)
                ).fetchone()
        return self._row_to_job(row) if row else None

    def update(
        self,
        job_id: str,
        status: JobStatus | None = None,
        progress: float | None = None,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> bool:
        """Update mutable job fields. Returns True if the job exists."""
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT status FROM verification_jobs WHERE job_id = ?", (job_id,)
                ).fetchone()
                if row is None:
                    return False
                current_status = JobStatus(row["status"])
                if current_status in _TERMINAL_STATUSES and status not in _TERMINAL_STATUSES:
                    return False

                updates: dict[str, Any] = {"updated_at": self._now()}
                if status is not None:
                    updates["status"] = status.value
                if progress is not None:
                    updates["progress"] = max(0.0, min(1.0, float(progress)))
                if result is not None:
                    updates["result"] = json.dumps(result)
                if error is not None:
                    updates["error"] = error

                set_clause = ", ".join(f"{key} = ?" for key in updates)
                values = list(updates.values()) + [job_id]
                conn.execute(
                    f"UPDATE verification_jobs SET {set_clause} WHERE job_id = ?",
                    values,
                )
        return True

    def cancel(self, job_id: str) -> bool:
        """Cancel a pending or running job."""
        job = self.get(job_id)
        if job is None:
            return False
        if job.status in _TERMINAL_STATUSES:
            return False
        return self.update(job_id, status=JobStatus.CANCELLED, progress=1.0)

    def list_jobs(
        self,
        design_id: str | None = None,
        status: JobStatus | None = None,
        limit: int = 100,
    ) -> list[VerificationJob]:
        """List jobs, optionally filtered by design and/or status."""
        query = "SELECT * FROM verification_jobs WHERE 1=1"
        params: list[Any] = []
        if design_id:
            query += " AND design_id = ?"
            params.append(design_id)
        if status:
            query += " AND status = ?"
            params.append(status.value)
        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(max(1, int(limit)))

        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(query, params).fetchall()
        return [self._row_to_job(row) for row in rows]

    def _row_to_job(self, row: sqlite3.Row) -> VerificationJob:
        return VerificationJob(
            job_id=row["job_id"],
            design_id=row["design_id"],
            load_case=LoadCase(row["load_case"]),
            solver_type=row["solver_type"],
            status=JobStatus(row["status"]),
            progress=float(row["progress"]),
            inputs=json.loads(row["inputs"]) if row["inputs"] else {},
            result=json.loads(row["result"]) if row["result"] else None,
            error=row["error"],
            created_at=float(row["created_at"]),
            updated_at=float(row["updated_at"]),
        )
