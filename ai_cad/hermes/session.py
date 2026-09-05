"""HERMES session persistence and state management."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ai_cad.hermes.models import Message, Plan, Session
from ai_cad.hermes.planner import (
    approve_step,
    reject_step,
    advance_plan,
    build_plan,
    execute_plan_step,
)
from ai_cad.hermes.tools import HermesToolRegistry


class HermesSessionStore:
    """JSON sidecar store for HERMES sessions under designs/{id}/hermes_session.json."""

    def __init__(self, base_dir: Path = Path("designs")) -> None:
        self.base_dir = base_dir

    def path_for(self, session_id: str, design_id: str | None = None) -> Path:
        if design_id:
            return self.base_dir / design_id / "hermes_session.json"
        # Fallback: global sessions stored in a dedicated directory.
        global_dir = self.base_dir / "_hermes"
        global_dir.mkdir(parents=True, exist_ok=True)
        return global_dir / f"{session_id}.json"

    def save(self, session: Session) -> Path:
        session.updated_at = datetime.now(timezone.utc).isoformat()
        path = self.path_for(session.id, session.design_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(session.model_dump_json(indent=2), encoding="utf-8")
        return path

    def load(self, session_id: str, design_id: str | None = None) -> Session | None:
        path = self.path_for(session_id, design_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return Session(**data)
        except Exception:
            return None

    def delete(self, session_id: str, design_id: str | None = None) -> None:
        path = self.path_for(session_id, design_id)
        if path.exists():
            path.unlink()


class HermesSession:
    """High-level HERMES session wrapper with persistence."""

    def __init__(
        self,
        session: Session,
        store: HermesSessionStore,
        registry: HermesToolRegistry | None = None,
    ) -> None:
        self.session = session
        self.store = store
        self.registry = registry or HermesToolRegistry()

    @classmethod
    def create(
        cls,
        design_id: str | None = None,
        base_dir: Path = Path("designs"),
        registry: HermesToolRegistry | None = None,
    ) -> "HermesSession":
        session = Session(design_id=design_id)
        store = HermesSessionStore(base_dir=base_dir)
        wrapper = cls(session=session, store=store, registry=registry)
        wrapper.save()
        return wrapper

    @classmethod
    def load(
        cls,
        session_id: str,
        design_id: str | None = None,
        base_dir: Path = Path("designs"),
        registry: HermesToolRegistry | None = None,
    ) -> "HermesSession":
        store = HermesSessionStore(base_dir=base_dir)
        session = store.load(session_id, design_id)
        if session is None:
            raise FileNotFoundError(f"HERMES session {session_id!r} not found")
        return cls(session=session, store=store, registry=registry)

    def save(self) -> Path:
        return self.store.save(self.session)

    def add_message(self, role: str, content: str, **metadata: Any) -> Message:
        msg = Message(role=role, content=content, metadata=metadata)
        self.session.messages.append(msg)
        self.session.updated_at = datetime.now(timezone.utc).isoformat()
        self.save()
        return msg

    def set_context(self, key: str, value: Any) -> None:
        self.session.context[key] = value
        self.save()

    def create_plan(self, goal: str, steps_data: list[dict[str, Any]]) -> Plan:
        plan = build_plan(goal, steps_data)
        self.session.plans.append(plan)
        self.session.updated_at = datetime.now(timezone.utc).isoformat()
        self.save()
        return plan

    def advance(self, context: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        plan = self.session.active_plan()
        if plan is None:
            self._update_session_status()
            self.save()
            return []
        results = advance_plan(plan, self.registry, context=context)
        self._update_session_status()
        self.save()
        return [r.model_dump() for r in results]

    def approve(self, step_id: str, parameter_overrides: dict[str, Any] | None = None) -> dict[str, Any]:
        plan = self.session.active_plan()
        if plan is None:
            raise ValueError("No active plan")
        step = approve_step(plan, step_id, parameter_overrides)
        self._update_session_status()
        self.save()
        return step.model_dump()

    def reject(self, step_id: str, reason: str = "") -> dict[str, Any]:
        plan = self.session.active_plan()
        if plan is None:
            raise ValueError("No active plan")
        step = reject_step(plan, step_id, reason)
        self._update_session_status()
        self.save()
        return step.model_dump()

    def execute_step(self, step_id: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        plan = self.session.active_plan()
        if plan is None:
            raise ValueError("No active plan")
        step = plan.step_by_id(step_id)
        if step is None:
            raise KeyError(f"Step {step_id!r} not found")
        result = execute_plan_step(plan, step, self.registry, context=context)
        self._update_session_status()
        self.save()
        return result.model_dump()

    def _update_session_status(self) -> None:
        plan = self.session.active_plan()
        if plan is None:
            # No active plan: if there are completed plans, we are done; otherwise idle.
            if self.session.plans and all(p.status.value == "completed" for p in self.session.plans):
                self.session.status = "done"
            else:
                self.session.status = "idle"
            return
        if plan.status.value == "awaiting_approval":
            self.session.status = "awaiting_approval"
        elif plan.status.value == "running":
            self.session.status = "running"
        elif plan.status.value == "failed":
            self.session.status = "error"
        elif plan.status.value == "completed":
            self.session.status = "done"
        else:
            self.session.status = "idle"
