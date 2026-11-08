"""Flush sliding dovetail, straight or tapered.

Frame: tail width along X, slide axis along Y (y = 0 is the entry end, y = length the far end), tail rises along
+z from the mating face. The groove is cut into part B and runs straight through (straight) or stops at the far end
(tapered, wedge seat). Perpendicular clearance is exactly `clearance` on every face, made with a 2D offset.
"""
from __future__ import annotations

import math

import manifold3d as m3d
import numpy as np

from .core import EPS, JointPair, box, cs_poly, measure_fit
from .materials import get_material

ORIENT = ("Stand each part with the slide axis (Y) vertical so the trapezoid lies flat on the bed: the flared tip "
          "is then a layer shape, not an overhang, and needs no support.")


def _section(neck_half, depth, angle_deg):
    """Convex trapezoid in (x, z): narrow neck on the face z=0, flaring to the tip at z=depth."""
    tip_half = neck_half + depth * math.tan(math.radians(angle_deg))
    return [(-neck_half, 0.0), (neck_half, 0.0), (tip_half, depth), (-tip_half, depth)]


def _sweep(sec_a, sec_b, y_a, y_b):
    """Convex hull of two (x, z) sections placed at y_a and y_b."""
    pts = [(x, y_a, z) for x, z in sec_a] + [(x, y_b, z) for x, z in sec_b]
    return m3d.Manifold.hull_points(np.array(pts, float))


def dovetail(width=10.0, depth=6.0, length=30.0, angle_deg=15.0, taper_deg=0.0, material="PETG",
             clearance=None, seat_ratio=0.35, embed=0.5) -> JointPair:
    """width: neck width at the face. depth: tail height. length: slide length.
    taper_deg: per-side wedge angle along the slide (0 = straight, through groove). Tapered tails are widest at
    the entry end, and the groove clearance shrinks from `clearance` at entry to clearance*seat_ratio at the far end
    so the last millimetres wedge tight. All other faces keep `clearance`."""
    mat = get_material(material)
    c = mat.clearance if clearance is None else float(clearance)
    if width <= 0 or depth <= 0 or length <= 0:
        raise ValueError("width, depth and length must be positive")
    k = math.tan(math.radians(taper_deg))
    nh0 = width / 2.0

    def neck_half(y):          # male half neck width at slide position y (wide at y=0)
        return nh0 + (length - y) * k

    def male_sec(y):
        return _section(neck_half(y), depth, angle_deg)

    def female_sec(y, off):
        return cs_poly(male_sec(y)).offset(off, m3d.JoinType.Miter, 4.0)

    def male_solid():
        tail = _sweep(male_sec(0), male_sec(length), 0.0, length)
        stub = _sweep([(-neck_half(0), -embed), (neck_half(0), -embed), (neck_half(0), 0.0), (-neck_half(0), 0.0)],
                      [(-neck_half(length), -embed), (neck_half(length), -embed), (neck_half(length), 0.0),
                       (-neck_half(length), 0.0)], 0.0, length)
        return tail + stub

    def cs_pts(cs):
        poly = cs.to_polygons()[0]
        return [(float(p[0]), float(p[1])) for p in poly]

    if taper_deg == 0:
        male = male_solid()
        sec = cs_pts(female_sec(0, c))
        f = _sweep(sec, sec, -EPS, length + EPS)
        fit_f = f ^ box(-1e3, 1e3, 0.0, length, -1e3, 1e3)
        wedge_note = "straight through groove, slides in from either end"
    else:
        male = male_solid()
        c_far = c * seat_ratio
        # female: gap c at the entry, c_far at the far end, closed there by a small end clearance
        f = _sweep(cs_pts(female_sec(0, c)), cs_pts(female_sec(length, c_far)), -EPS, length + c_far)
        # extend the entry end flat so the cutter breaks the face cleanly
        fit_f = f ^ box(-1e3, 1e3, 0.0, length, -1e3, 1e3)
        wedge_note = (f"tapered {taper_deg:g} deg per side, gap closes from {c:.2f} to {c_far:.2f} mm; "
                      "slide in from the wide end and it wedges at the stop")
    lip = depth * math.tan(math.radians(angle_deg))
    rep = measure_fit(male, f, joint="dovetail" + ("-tapered" if taper_deg else ""), material=mat, nominal=c,
                      min_feature=min(width, 2 * lip), min_wall=mat.min_wall, orientation=ORIENT,
                      notes=[wedge_note, "flush: the tail sits inside the groove, faces meet at z=0",
                             f"dovetail lip {lip:.2f} mm per side"], fit_female=fit_f, search=max(2.0, 4 * c))
    if lip < 2 * mat.nozzle:
        rep.warnings.append(f"dovetail lip {lip:.2f} mm per side is under two perimeters ({2 * mat.nozzle:.1f} mm)")
    return JointPair(rep.joint, male, f, rep, dict(width=width, depth=depth, length=length, angle_deg=angle_deg,
                                                    taper_deg=taper_deg, clearance=c), fit_female=fit_f)
