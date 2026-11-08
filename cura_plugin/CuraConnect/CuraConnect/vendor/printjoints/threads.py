"""Printable helical threads made from a twisted extrusion (no helix maths): a cross-section whose radius follows the
thread profile once round per start, extruded with 360 deg of twist per lead.

  thread()    metric M8..M30 coarse pitch, 'iso' 60 deg flanks or 'print' 45 deg flanks (support-free vertical)
  t_thread()  the owner's coarse lamp thread (Lamp Studio T3: 4 mm pitch, 2 starts, 1.6 mm deep, 0.3 mm clearance)

Axis +z, right-handed. Male studs start at z=0 and run to z=length; the female cutter has the same phase so the pair
is seated with a uniform radial gap. Print with the axis vertical.
ISO metric coarse pitches: ISO 261 / ISO 262 (M8 1.25, M10 1.5, M12 1.75, M14 2, M16 2, M18 2.5, M20 2.5,
M22 2.5, M24 3, M27 3, M30 3.5).
"""
from __future__ import annotations

import math

import manifold3d as m3d
import numpy as np

from .core import EPS, JointPair, cyl, measure_fit
from .materials import get_material

COARSE_PITCH = {8: 1.25, 10: 1.5, 12: 1.75, 14: 2.0, 16: 2.0, 18: 2.5, 20: 2.5, 22: 2.5, 24: 3.0, 27: 3.0, 30: 3.5}

# profile name: (thread depth / pitch, crest flat / pitch, flank half-angle deg)
PROFILES = {"iso": (0.54, 0.125, 30.0), "print": (0.40, 0.15, 45.0)}


def _radius_fn(r_root, depth, pitch, crest, flank_deg):
    """Radius of the thread at axial position p (mod pitch): trapezoid, crest centred at pitch/2."""
    half_base = crest / 2 + depth * math.tan(math.radians(flank_deg))
    half_base = min(half_base, 0.49 * pitch)
    slope = depth / max(half_base - crest / 2, 1e-9)

    def r(p):
        d = abs(((p % pitch) + pitch) % pitch - pitch / 2)
        return r_root + float(np.clip((half_base - d) * slope, 0.0, depth))
    return r


def _section(r_fn, pitch, starts, steps_per_start=72):
    n = steps_per_start * starts
    t = np.arange(n) * (2 * math.pi / n)
    # angle theta covers lead*theta/2pi axially; fold into one pitch
    lead = pitch * starts
    p = (t / (2 * math.pi)) * lead
    r = np.array([r_fn(x) for x in p])
    return m3d.CrossSection([np.column_stack([r * np.cos(t), r * np.sin(t)])])


def _helix(cs, length, lead, z0=0.0):
    turns = length / lead
    return m3d.Manifold.extrude(cs, length, n_divisions=max(8, int(turns * 48)),
                                twist_degrees=360.0 * turns).translate([0, 0, z0])


def _build(major_d, pitch, starts, depth, crest, flank_deg, length, clearance, mat, joint, profile_name,
           chamfer=True, flank_gap=False) -> JointPair:
    r_major = major_d / 2.0
    r_root = r_major - depth
    lead = pitch * starts
    fn = _radius_fn(r_root, depth, pitch, crest, flank_deg)
    cs = _section(fn, pitch, starts)
    stud = _helix(cs, length, lead)
    if chamfer:   # 45 deg lead-in at the tip so it starts easily and the last layer is not a sharp flare
        ch = min(depth + 0.4, 0.3 * length)
        cone = m3d.Manifold.cylinder(length + 1, r_major + 0.1, r_major + 0.1, 96)
        tip = m3d.Manifold.cylinder(ch, r_major + 0.1, r_root - 0.2, 96).translate([0, 0, length - ch])
        keep = cyl(r_major + 0.1, -1, length - ch, 96) + tip
        stud = stud ^ keep
    male = stud + cyl(r_root + 0.05, -0.5, 0.01, 96)
    off = clearance / math.sin(math.radians(flank_deg)) if flank_gap else clearance
    hole_cs = cs.offset(off, m3d.JoinType.Round, 2.0, 48)
    cutter = _helix(hole_cs, length + off, lead) + cyl(r_major + off, -EPS, 0.01, 96)
    lead_in = m3d.Manifold.cylinder(0.8, r_major + off + 0.8, r_major + off, 96).translate([0, 0, -0.01])
    female = cutter + lead_in
    rep = measure_fit(male, female, joint=joint, material=mat, nominal=clearance,
                      min_feature=depth, min_wall=mat.min_wall + 1.0,
                      orientation="Print with the thread axis vertical. 45 deg flanks need no support; ISO 30 deg flanks "
                                  "(overhang 60 deg from vertical) want a fine layer height or the 'print' profile.",
                      notes=[f"{profile_name}: pitch {pitch:g}, {starts} start(s), depth {depth:.2f} mm, "
                             f"flank {flank_deg:g} deg, radial clearance {off:.2f} mm, right-handed",
                             f"lead {lead:g} mm per turn: about {length / lead:.1f} turns engaged"],
                      fit_female=female, search=0.6)
    if length < 1.5 * lead:
        rep.warnings.append(f"only {length / lead:.1f} turns of engagement, use at least 1.5 turns")
    return JointPair(joint, male, female, rep, dict(major_d=major_d, pitch=pitch, starts=starts, depth=depth,
                                                     length=length, clearance=clearance, profile=profile_name),
                     fit_female=female)


def thread(size=12, length=None, profile="print", pitch=None, material="PETG", clearance=None, flank_gap=False) -> JointPair:
    """Metric coarse thread M8..M30 (size is the major diameter in mm, or 'M12'). profile: 'iso' or 'print'.
    Printed-to-printed pair; clearance is radial and defaults to the material's thread clearance. The gap measured
    on the flanks is about clearance * sin(flank angle); pass flank_gap=True to make the FLANK gap equal clearance."""
    mat = get_material(material)
    d = int(str(size).upper().lstrip("M"))
    if d not in COARSE_PITCH:
        raise ValueError(f"metric size must be one of {['M%d' % k for k in COARSE_PITCH]}")
    p = COARSE_PITCH[d] if pitch is None else float(pitch)
    if profile not in PROFILES:
        raise ValueError(f"profile must be one of {sorted(PROFILES)}")
    dp, cr, fl = PROFILES[profile]
    L = max(2.5 * p, 8.0) if length is None else float(length)
    c = mat.thread_clearance if clearance is None else float(clearance)
    return _build(d, p, 1, dp * p, cr * p, fl, L, c, mat, f"thread-M{d}", f"M{d} {profile}", flank_gap=flank_gap)


def t_thread(major_d=50.0, length=14.0, pitch=4.0, starts=2, depth=1.6, flank_deg=45.0, material="PETG",
             clearance=0.3) -> JointPair:
    """Coarse trapezoid thread for lamp parts: defaults are the Lamp Studio T3 (4 mm pitch, 2 starts, 1.6 mm deep,
    0.3 mm radial clearance). 45 deg flanks so it prints upright without support."""
    mat = get_material(material)
    crest = max(0.2 * pitch, 0.8)
    return _build(major_d, pitch, starts, depth, crest, flank_deg, length, float(clearance), mat,
                  "t-thread", f"T{pitch:g}x{starts}")
