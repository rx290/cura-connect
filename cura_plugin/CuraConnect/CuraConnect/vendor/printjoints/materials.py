"""Per-material fit defaults. All lengths in mm, per side unless noted.

The numbers start from the owner's own prints (PETG: 0.20 sliding, 0.18 snap-on) and typical published
snap-fit strain limits (Covestro/Bayer snap-fit design guide style short-term strain, FDM layer direction
making it lower than moulded plastic). They are starting points: the Lamp Studio calibration print should
overwrite them per printer via Material.replace(...).
"""
from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Material:
    name: str
    clearance: float          # sliding / loose fit, per side
    snap_clearance: float     # snap-on and click fits, per side
    thread_clearance: float   # radial, threads
    press_clearance: float    # magnet / insert pockets that grip, per side
    max_strain: float         # short-term allowable bending strain (fraction), one assembly
    modulus_mpa: float        # flexural modulus used for the force estimate
    min_wall: float           # smallest wall a joint may leave around itself (3 perimeters at 0.4)
    nozzle: float = 0.4
    snap_safety: float = 0.8  # share of max_strain a snap may use

    @property
    def strain_limit(self) -> float:
        return self.max_strain * self.snap_safety

    def replace(self, **kw) -> "Material":
        return replace(self, **kw)


PLA = Material("PLA", 0.15, 0.13, 0.20, 0.08, 0.020, 3500.0, 1.2)
PETG = Material("PETG", 0.20, 0.18, 0.25, 0.10, 0.040, 2100.0, 1.2)
TPU = Material("TPU", 0.25, 0.20, 0.30, 0.05, 0.120, 26.0, 1.6)

MATERIALS = {m.name: m for m in (PLA, PETG, TPU)}


def get_material(m) -> Material:
    if isinstance(m, Material):
        return m
    try:
        return MATERIALS[str(m).upper()]
    except KeyError:
        raise ValueError(f"unknown material {m!r}, use one of {sorted(MATERIALS)} or a Material") from None
