"""Deep verification solvers package for RoboCAD Phase 28C."""
from __future__ import annotations

from ai_cad.solvers.job_store import JobStatus, JobStore, VerificationJob
from ai_cad.solvers.nvidia_surrogate import NvidiaSurrogate
from ai_cad.solvers.verification_deep import (
    CalculiXAdapter,
    DeepVerificationDispatcher,
    ElmerAdapter,
    OpenFOAMAdapter,
    SurrogateAdapter,
    cancel_deep_verification,
    poll_deep_verification,
    run_deep_verification,
    solver_availability,
    submit_deep_verification,
)

__all__ = [
    "JobStatus",
    "JobStore",
    "VerificationJob",
    "NvidiaSurrogate",
    "CalculiXAdapter",
    "ElmerAdapter",
    "OpenFOAMAdapter",
    "SurrogateAdapter",
    "DeepVerificationDispatcher",
    "run_deep_verification",
    "submit_deep_verification",
    "poll_deep_verification",
    "cancel_deep_verification",
    "solver_availability",
]
