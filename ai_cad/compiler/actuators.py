"""One position servo per joint, with every number it did not measure said out loud.

A joint in a model is a hole without an actuator: MuJoCo will load it, gravity will move it, and
nothing in the file says what may command it or how hard it may push. This module carries the three
numbers that turn a joint into a drive -- what it is allowed to exert, how stiffly it holds a
position, and how much it is damped -- and keeps the provenance of each separate, because they do not
share one.

The torque figure is a datasheet number. It is read from the model at check time and compared
against the torque gravity actually demands, so a limit that is stated but too small shows up as
a failure rather than as a passing field.

``kp`` and ``kv`` are not datasheet numbers. A servo's control loop is closed inside the servo, and
its published specification says nothing about the stiffness a simulator should give it. They are
assumptions, and ``assumptions()`` returns the sentence that says so, so the report can carry it.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

# Not datasheet values. A position servo stiff enough to hold a small arm against gravity needs a
# few tens of N*m/rad with gear 1; 20 with a little damping is a starting point that runs stably at
# this model's masses and timestep. Anyone tuning a real machine replaces both.
DEFAULT_KP = 20.0
DEFAULT_KV = 1.0

TORQUE_KINDS = frozenset({"stall", "rated"})


class ActuatorSpec(BaseModel):
    """What one servo may be asked for, and where each part of that answer came from."""

    model_config = ConfigDict(frozen=True)

    # The hard ceiling written into forcerange. Stall is an upper bound the gearbox survives for
    # moments; rated is what it survives continuously. The kind is recorded because the two mean
    # different things to a reader deciding whether a design has margin.
    torque_nm: float | None = Field(default=None, gt=0.0, allow_inf_nan=False)
    torque_kind: str = "unstated"
    # The continuous figure, when the datasheet gives one. Used only to judge margin: a pose that
    # demands more than the continuous rating is a warning even when it is under stall.
    rated_torque_nm: float | None = Field(default=None, gt=0.0, allow_inf_nan=False)
    source: str | None = None
    kp: float = Field(default=DEFAULT_KP, gt=0.0, allow_inf_nan=False)
    kv: float = Field(default=DEFAULT_KV, ge=0.0, allow_inf_nan=False)
    gear: float = Field(default=1.0, gt=0.0, allow_inf_nan=False)

    def model_post_init(self, __context) -> None:  # noqa: D105 - pydantic hook
        if self.torque_nm is None:
            if self.torque_kind != "unstated":
                raise ValueError(
                    f"torque_kind is {self.torque_kind!r} but no torque is stated; the kind "
                    "describes a number and there is none to describe"
                )
            if self.source is not None:
                raise ValueError(
                    "a source is stated for an actuator with no torque; the citation would then "
                    "appear to cover an effort limit that was never written"
                )
            return
        if self.torque_kind not in TORQUE_KINDS:
            raise ValueError(
                f"torque_kind {self.torque_kind!r} is not one of {sorted(TORQUE_KINDS)}; a torque "
                "with no stated kind cannot be read as either a ceiling or a continuous rating"
            )
        if self.source is None or not self.source.strip():
            raise ValueError(
                "a torque without its source is indistinguishable from a guess, whatever its value"
            )
        if self.rated_torque_nm is not None and self.rated_torque_nm > self.torque_nm:
            raise ValueError(
                f"rated torque {self.rated_torque_nm} N*m exceeds the stated {self.torque_kind} "
                f"torque {self.torque_nm} N*m; a continuous rating above the ceiling is a "
                "misread datasheet, not a specification"
            )

    def is_stated(self) -> bool:
        return self.torque_nm is not None

    def describe(self) -> str:
        """One line for the report: the number, its kind, and the document it came from."""
        if self.torque_nm is None:
            return "no torque stated: the model carries no effort limit"
        kind = "stall" if self.torque_kind == "stall" else "rated"
        text = f"{self.torque_nm:g} N*m {kind}, from {str(self.source).rstrip('.')}"
        if self.rated_torque_nm is not None and self.torque_kind != "rated":
            text += f"; continuous rating {self.rated_torque_nm:g} N*m"
        return text

    def assumptions(self) -> list[str]:
        """Every claim in this specification that no datasheet supports."""
        return [
            f"kp = {self.kp:g} N*m/rad and kv = {self.kv:g} N*m*s/rad are ASSUMPTIONS, not "
            "datasheet values: the servo closes its own control loop and publishes no stiffness "
            "for a simulator to use. Every torque figure below was measured against these gains."
        ]


def actuators_for(joints: list[str], spec: ActuatorSpec) -> list[tuple[str, str]]:
    """(actuator name, joint name) for every joint, in the order the joints arrived."""
    return [(f"{joint}_servo", joint) for joint in joints]


__all__ = [
    "ActuatorSpec",
    "DEFAULT_KP",
    "DEFAULT_KV",
    "TORQUE_KINDS",
    "actuators_for",
]
