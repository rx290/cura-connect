"""Bayonet twist lock: a post with diamond pins into a bore with entry channels and an arc slot."""
from __future__ import annotations

import math

import manifold3d as m3d
import numpy as np

from .core import EPS, JointPair, cs_poly, cyl, measure_fit, prism
from .materials import get_material


def _radial_diamond(r0, r1, half, zc, offset=0.0):
    """Diamond (square on its corner, so no overhang) in the tangent/z plane, extruded along +x from r0 to r1."""
    h = half + offset
    d = prism([(-h, zc), (0, zc - h), (h, zc), (0, zc + h)], r1 - r0)    # (u=tangent, v=z) extruded along w
    # (u, v, w) -> (x=w, y=u, z=v)
    M = np.array([[0, 0, 1, r0], [1, 0, 0, 0], [0, 1, 0, 0]], float)
    return d.transform(M)


def bayonet(radius=15.0, length=10.0, pins=3, pin_size=2.6, pin_len=1.6, twist_deg=40.0, pin_z=None,
            material="PETG", clearance=None, segments=96) -> JointPair:
    """radius: post radius. length: post length (bore depth). pins: evenly spaced. pin_size: pin height/width.
    pin_len: how far a pin sticks out past the post. twist_deg: quarter-turn-ish lock angle (25 to 60)."""
    mat = get_material(material)
    c = mat.clearance if clearance is None else float(clearance)
    zp = length * 0.5 if pin_z is None else float(pin_z)
    half = pin_size / 2.0
    if zp - half - c < 0.4 or zp + half + c > length - 0.4:
        raise ValueError("pin does not fit between the post ends, shorten pin_size or move pin_z")
    post = cyl(radius, -0.5, length, segments)
    male = post
    female = cyl(radius + c, -EPS, length + c, segments)
    ext = math.degrees((half + c) / (radius + pin_len / 2))
    for k in range(pins):
        a = 360.0 * k / pins
        male = male + _radial_diamond(radius - 0.4, radius + pin_len, half, zp).rotate([0, 0, a + twist_deg])
        # axial entry channel: sweep of the offset diamond from the face up to the pin height
        lo = _radial_diamond(radius - 0.05, radius + pin_len + c, half, -half - c - EPS, c)
        hi = _radial_diamond(radius - 0.05, radius + pin_len + c, half, zp, c)
        chan = m3d.Manifold.batch_hull([lo, hi])
        # arc slot at the pin height (rectangle in r,z revolved)
        zlo, zhi = zp - half - c, zp + half + c
        arc = cs_poly([(radius - 0.05, zlo), (radius + pin_len + c, zlo), (radius + pin_len + c, zhi),
                       (radius - 0.05, zhi)]).revolve(segments, twist_deg + 2 * ext)
        female = female + chan.rotate([0, 0, a]) + arc.rotate([0, 0, a - ext])
    rep = measure_fit(male, female, joint="bayonet", material=mat, nominal=c,
                      min_feature=pin_size, min_wall=mat.min_wall + pin_len,
                      orientation="Print both parts with the axis vertical. Pins are diamonds so they print without support; "
                                  "the arc slot ceiling bridges only the pin size.",
                      notes=[f"{pins} pins, push in along the channels then twist {twist_deg:g} deg to lock",
                             "pure friction lock: add a drop of silicone grease or a thin O-ring if it must resist vibration"],
                      fit_male=post, fit_female=cyl(radius + c, -EPS, length + c, segments), search=1.5)
    # whole-pair interference (pins in their slots) as well
    full = (male.trim_by_plane([0, 0, 1], 0) - female).volume()
    rep.interference_mm3 = max(rep.interference_mm3, full)
    return JointPair("bayonet", male, female, rep, dict(radius=radius, length=length, pins=pins, pin_size=pin_size,
                                                          pin_len=pin_len, twist_deg=twist_deg, clearance=c),
                     fit_male=post, fit_female=cyl(radius + c, -EPS, length + c, segments))
