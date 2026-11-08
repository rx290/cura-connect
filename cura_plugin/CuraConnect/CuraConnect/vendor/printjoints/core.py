"""Shared pieces: JointPair, FitReport, geometry helpers and the boolean fit measurement.

Frame convention for every joint, so they all behave the same:
  * the mating plane is z = 0, insertion runs along +z
  * part A (owns the male) lies at z <= 0, part B (gets the female cutter) lies at z >= 0
  * `male` is added to A, `female` is a cutter subtracted from B
  * both are returned in the SEATED pose, so male - female is the interference you can measure
Use JointPair.placed(origin, axis) to move a pair into a part's own frame.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import manifold3d as m3d

EPS = 0.5   # cutters poke this far past the mating face so booleans never leave a skin


# ------------------------------------------------------------------ geometry helpers
def ccw(points):
    p = np.asarray(points, float)
    area = 0.5 * np.sum(p[:, 0] * np.roll(p[:, 1], -1) - np.roll(p[:, 0], -1) * p[:, 1])
    return p if area > 0 else p[::-1]


def cs_poly(points) -> m3d.CrossSection:
    return m3d.CrossSection([ccw(points)])


def prism(points, height, z0=0.0) -> m3d.Manifold:
    """Polygon in XY extruded along +z from z0."""
    return cs_poly(points).extrude(height).translate([0, 0, z0])


def box(x0, x1, y0, y1, z0, z1) -> m3d.Manifold:
    return m3d.Manifold.cube([x1 - x0, y1 - y0, z1 - z0]).translate([x0, y0, z0])


def cyl(r, z0, z1, seg=96) -> m3d.Manifold:
    return m3d.Manifold.cylinder(z1 - z0, r, r, seg).translate([0, 0, z0])


def revolve_rz(points, seg=96) -> m3d.Manifold:
    """Polygon drawn in (r, z) revolved round the z axis."""
    return cs_poly(points).revolve(seg)


def rot_matrix(axis, up_hint=(0.0, 0.0, 1.0)) -> np.ndarray:
    """Rotation taking +z to `axis`, with the local +y kept as close to up_hint as possible."""
    z = np.asarray(axis, float)
    z = z / np.linalg.norm(z)
    h = np.asarray(up_hint, float)
    if abs(np.dot(h, z)) > 0.99:
        h = np.array([1.0, 0.0, 0.0])
    x = np.cross(h, z)
    x /= np.linalg.norm(x)
    y = np.cross(z, x)
    return np.column_stack([x, y, z])


def move(m: m3d.Manifold, origin=(0, 0, 0), axis=(0, 0, 1), up_hint=(0, 0, 1)) -> m3d.Manifold:
    R = rot_matrix(axis, up_hint)
    t = np.asarray(origin, float).reshape(3, 1)
    return m.transform(np.hstack([R, t]))


def is_watertight(m: m3d.Manifold) -> bool:
    return (not m.is_empty()) and m.status() == m3d.Error.NoError and m.volume() > 0


# ------------------------------------------------------------------ report + pair
@dataclass
class FitReport:
    joint: str
    material: str
    fit_type: str                       # "clearance" | "interference"
    nominal_clearance_mm: float         # what the geometry was built with (per side), 0 for interference fits
    min_gap_mm: Optional[float] = None  # measured by manifold min_gap, male vs a host block with the cutter removed
    interference_mm3: float = 0.0       # volume of the seated male that sits inside host material
    gap_volume_mm3: float = 0.0         # air left in the cutter around the male
    watertight: bool = True
    min_feature_mm: float = 0.0
    min_wall_mm: float = 0.0            # least material to leave around the cutter in the host part
    print_orientation: str = ""
    strain: Optional[float] = None      # peak bending strain of a flexing member, if any
    strain_limit: Optional[float] = None
    notes: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    def check_host_wall(self, wall_mm: float) -> bool:
        ok = wall_mm >= self.min_wall_mm
        if not ok:
            self.warnings.append(f"host wall {wall_mm:.2f} mm is under the {self.min_wall_mm:.2f} mm this joint needs")
        return ok

    @property
    def ok(self) -> bool:
        good = self.watertight and not self.warnings
        if self.fit_type == "clearance":
            good = good and self.interference_mm3 <= 1e-3
        return good

    def summary(self) -> str:
        gap = "n/a" if self.min_gap_mm is None else f"{self.min_gap_mm:.3f}"
        return (f"{self.joint} [{self.material}] {self.fit_type}: min gap {gap} mm, interference "
                f"{self.interference_mm3:.3f} mm3, {'OK' if self.ok else 'CHECK'}"
                + ("; " + "; ".join(self.warnings) if self.warnings else ""))


@dataclass
class JointPair:
    name: str
    male: m3d.Manifold
    female: m3d.Manifold
    report: FitReport
    params: dict = field(default_factory=dict)
    fit_male: Optional[m3d.Manifold] = None     # sub-shapes used for the fit measurement when the whole pair is
    fit_female: Optional[m3d.Manifold] = None   # not the right thing to compare (bayonet pins, open slots)
    extra: dict = field(default_factory=dict)   # extra cutters/solids, e.g. clearance_hole for a screw

    def placed(self, origin=(0, 0, 0), axis=(0, 0, 1), up_hint=(0, 0, 1)) -> "JointPair":
        f = lambda m: move(m, origin, axis, up_hint) if isinstance(m, m3d.Manifold) else m
        return JointPair(self.name, f(self.male), f(self.female), self.report, dict(self.params),
                         f(self.fit_male), f(self.fit_female), {k: f(v) for k, v in self.extra.items()})

    def apply(self, part_a: m3d.Manifold, part_b: m3d.Manifold):
        """(A + male, B - female), both already in the same frame as the pair."""
        return part_a + self.male, part_b - self.female


def measure_fit(male, female, *, joint, material, fit_type="clearance", nominal=0.0, min_feature=0.0,
                min_wall=0.0, orientation="", notes=(), fit_male=None, fit_female=None, margin=3.0,
                search=1.5) -> FitReport:
    """Boolean fit check in the seated pose. Only the part of the male on the +z side is counted.
    min_gap: distance between the seated male and a host block (cutter removed) from manifold's min_gap."""
    fm = fit_male if fit_male is not None else male
    ff = fit_female if fit_female is not None else female
    ins = fm.trim_by_plane([0, 0, 1], 0.0)
    cut = ff.trim_by_plane([0, 0, 1], 0.0)
    inside = (ins ^ cut).volume()
    interference = ins.volume() - inside
    gap_vol = cut.volume() - inside
    full = female.trim_by_plane([0, 0, 1], 0.0)
    bb = full.bounding_box()
    host = box(bb[0] - margin, bb[3] + margin, bb[1] - margin, bb[4] + margin, 0.0, bb[5] + margin) - full
    min_gap = ins.min_gap(host, search) if interference <= 1e-6 else 0.0
    rep = FitReport(joint=joint, material=material.name, fit_type=fit_type, nominal_clearance_mm=nominal,
                    min_gap_mm=float(min_gap), interference_mm3=float(max(interference, 0.0)),
                    gap_volume_mm3=float(max(gap_vol, 0.0)),
                    watertight=is_watertight(male) and is_watertight(female),
                    min_feature_mm=min_feature, min_wall_mm=min_wall, print_orientation=orientation,
                    notes=list(notes))
    if min_feature and min_feature < material.nozzle:
        rep.warnings.append(f"smallest feature {min_feature:.2f} mm is under the {material.nozzle} mm nozzle")
    return rep


def cantilever_strain(h, y, length) -> float:
    """Peak bending strain of a constant-section cantilever with tip deflection y: eps = 1.5 h y / L^2."""
    return 1.5 * h * y / (length ** 2)


def length_for_strain(h, y, strain) -> float:
    return math.sqrt(1.5 * h * y / strain)
