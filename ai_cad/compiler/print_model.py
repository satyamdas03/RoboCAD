"""A printed part is not a solid, and a servo is not plastic.

The B-rep gives a closed solid and the kernel integrates it exactly. What that answers is the mass
of the part *as if it were cast at 100 percent fill*. On a desktop robot almost nothing is: a printed
link is a shell of a few perimeters over a sparse infill, and roughly a third of the mass of a
servo-driven arm is bought-in servos that the CAD models as homogenous blocks.

Two numbers therefore live behind every link mass, and this module keeps them apart instead of
folding one into the other:

1. ``solid`` -- the kernel's volume at the material density. An upper bound, exactly the figure the
   compiler has always reported, and never wrong: nothing can weigh more than its solid.
2. ``printed`` -- a shell of ``wall_thickness_m`` over the surface, plus ``infill_fraction`` of the
   interior. This is a model, not a measurement, and it is labelled as one.

The effective-volume rule::

    shell = min(V, A * w)
    effective = shell + f * max(0, V - shell)

``min(V, A*w)`` matters. A part thinner than two wall thicknesses has no interior at all, so a shell
model that ignored the cap would inflate it above its own solid volume, which is impossible.

What this model does **not** claim. The centre of mass is held at the solid's centre of mass and the
inertia tensor is scaled by the mass ratio. Both are approximations. Hollowing a part moves its
centre of mass toward the shell, which on a link with a large printed boss at one end is a real
millimetre-scale shift, and a hollow part's inertia is not its solid inertia times a scalar. The
scale factor is the least-wrong cheap answer and the report says so rather than presenting the tensor
as measured.

Bought-in parts are a separate mechanism and deliberately not modelled here: a servo's mass comes
from a datasheet with a citation, not from its envelope volume, and mixing the two would make a
datasheet number indistinguishable from a guess.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

# Three perimeters at a 0.4 mm nozzle. A common desktop default, stated so it can be disputed.
DEFAULT_WALL_THICKNESS_M = 0.0012
# A common "20 percent infill" slicer setting.
DEFAULT_INFILL_FRACTION = 0.20
# The range the report sweeps, so a reader sees how much of the answer is this choice.
INFILL_SENSITIVITY = (0.15, 0.20, 0.30)


class PrintModel(BaseModel):
    """Shell-plus-infill volume model for a printed part."""

    model_config = ConfigDict(frozen=True)

    wall_thickness_m: float = Field(default=DEFAULT_WALL_THICKNESS_M, gt=0.0, allow_inf_nan=False)
    infill_fraction: float = Field(default=DEFAULT_INFILL_FRACTION, ge=0.0, le=1.0, allow_inf_nan=False)

    def shell_volume_m3(self, solid_volume_m3: float, surface_area_m2: float) -> float:
        """The outer wall. Capped at the part's own volume."""
        return min(solid_volume_m3, surface_area_m2 * self.wall_thickness_m)

    def effective_volume_m3(self, solid_volume_m3: float, surface_area_m2: float) -> float:
        """Wall plus infilled interior. Never greater than the solid, never less than the wall."""
        if solid_volume_m3 <= 0.0:
            return 0.0
        shell = self.shell_volume_m3(solid_volume_m3, surface_area_m2)
        return shell + self.infill_fraction * max(0.0, solid_volume_m3 - shell)

    def mass_factor(self, solid_volume_m3: float, surface_area_m2: float) -> float:
        """Effective over solid, in (0, 1]. The factor applied to mass and inertia."""
        if solid_volume_m3 <= 0.0:
            return 0.0
        return self.effective_volume_m3(solid_volume_m3, surface_area_m2) / solid_volume_m3

    def describe(self) -> str:
        return (
            f"{self.wall_thickness_m * 1e3:.2f} mm wall over {self.infill_fraction * 100:.0f}% "
            "infill"
        )

    def sensitivity(self) -> list["PrintModel"]:
        """The same wall at each candidate infill fraction, for the report's sensitivity rows."""
        return [
            PrintModel(wall_thickness_m=self.wall_thickness_m, infill_fraction=f)
            for f in INFILL_SENSITIVITY
        ]


#: A thin plate: surface area dominates volume, so the model must cap the shell at the volume.
def is_solid_at_this_wall(solid_volume_m3: float, surface_area_m2: float, model: PrintModel) -> bool:
    """True when the part is thinner than its own wall, so it prints solid and no infill applies."""
    if solid_volume_m3 <= 0.0 or surface_area_m2 <= 0.0:
        return True
    return surface_area_m2 * model.wall_thickness_m >= solid_volume_m3
