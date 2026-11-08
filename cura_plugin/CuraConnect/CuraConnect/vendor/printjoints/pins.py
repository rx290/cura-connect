"""Alignment pins and holes."""
from __future__ import annotations

from .core import EPS, JointPair, cyl, measure_fit
from .materials import get_material
import manifold3d as m3d


def alignment_pins(diameter=3.0, length=6.0, positions=((0.0, 0.0),), tip_chamfer=0.5, material="PETG",
                   clearance=None, segments=48) -> JointPair:
    """Pins (male, on part A, rising along +z) and matching blind holes with a lead-in (female, in part B).
    positions: (x, y) list in the mating plane."""
    mat = get_material(material)
    c = mat.clearance if clearance is None else float(clearance)
    r = diameter / 2.0
    ch = min(tip_chamfer, r * 0.6)
    pin = (cyl(r, -0.5, length - ch, segments)
           + m3d.Manifold.cylinder(ch, r, r - ch, segments).translate([0, 0, length - ch]))
    hole = (cyl(r + c, -EPS, length + c, segments)
            + m3d.Manifold.cylinder(0.6, r + c + 0.6, r + c, segments).translate([0, 0, -0.01]))
    male = female = None
    for x, y in positions:
        pm, hm = pin.translate([x, y, 0]), hole.translate([x, y, 0])
        male = pm if male is None else male + pm
        female = hm if female is None else female + hm
    rep = measure_fit(male, female, joint="alignment-pins", material=mat, nominal=c, min_feature=diameter,
                      min_wall=mat.min_wall + 0.6,
                      orientation="Print the pin part with pins pointing up; the chamfered tip prints without support. "
                                  "Pin holes print with the opening up or sideways.",
                      notes=[f"{len(positions)} pin(s) d{diameter:g} x {length:g} mm, hole d{diameter + 2 * c:.2f} mm",
                             "use two pins at least, ideally far apart and not symmetric, so parts cannot go together wrong"],
                      fit_female=female, search=1.5)
    if len(positions) < 2:
        rep.notes.append("single pin: add a second to stop rotation")
    return JointPair("alignment-pins", male, female, rep, dict(diameter=diameter, length=length, clearance=c,
                                                                 positions=[tuple(p) for p in positions]),
                     fit_female=female)
