"""Pockets for hardware: magnets, heat-set inserts, self-tapping screw pilot holes.

Insert and pilot sizes are typical values consolidated from supplier guidance, NOT a single datasheet:
  * heat-set inserts: Ruthex RX-M series datasheet / CNC Kitchen insert hole guidance / McMaster-Carr 94180A
    (tapered brass inserts). M3: 4.0 mm hole for a 4.6 mm OD x 5.7 mm insert, M4: 5.6 mm hole.
  * pilot holes for thread-forming screws in FDM plastic: about 80-85% of the screw major diameter, the usual
    boss-design rule of thumb (e.g. Covestro/Bayer and Protolabs screw-boss guidance); boss outer diameter about
    2.2 x the screw diameter, engagement at least 2 x diameter.
Check the numbers against YOUR insert's sheet and your printer; override with hole_d / pilot_d.
"""
from __future__ import annotations

import math

import manifold3d as m3d

from .core import EPS, JointPair, cyl, measure_fit
from .materials import get_material

# size: (insert OD mm, insert length mm, hole diameter mm, extra hole depth mm, boss min wall mm)
HEAT_SET = {
    "M2": (3.6, 3.0, 3.2, 0.8, 1.6),
    "M2.5": (4.0, 4.0, 3.6, 0.8, 1.6),
    "M3": (4.6, 5.7, 4.0, 1.0, 1.8),
    "M4": (6.0, 8.1, 5.6, 1.2, 2.4),
}

# size: (screw major diameter, pilot diameter, clearance hole diameter)
SELF_TAP = {
    "M2": (2.0, 1.6, 2.4),
    "M2.5": (2.5, 2.0, 2.9),
    "M3": (3.0, 2.5, 3.4),
    "M4": (4.0, 3.3, 4.5),
    "M5": (5.0, 4.2, 5.5),
}


def magnet_pocket(diameter=6.0, thickness=3.0, mode="press", recess=0.0, lip_overlap=None, material="PETG",
                  clearance=None, segments=64) -> JointPair:
    """Pocket for a disc magnet. male = the magnet itself (reference body), female = pocket cutter, opening at z=0.
    mode 'press': bore d + 2*press_clearance, grips by friction, good for snug printers.
    mode 'lip': glue-free capture, bore d + 2*snap clearance with a thin lip at the mouth narrower than the magnet.
    The magnet is pushed past the lip once; the lip overlap is kept under the material strain limit
    (hoop strain about overlap / radius). recess: how far the magnet face sits below the mating face."""
    mat = get_material(material)
    r = diameter / 2.0
    if mode not in ("press", "lip"):
        raise ValueError("mode must be 'press' or 'lip'")
    c = (mat.press_clearance if mode == "press" else mat.snap_clearance) if clearance is None else float(clearance)
    depth = recess + thickness + 0.1
    magnet = cyl(r, recess, recess + thickness, segments)
    female = cyl(r + c, -EPS, depth, segments)
    notes, warn = [], []
    strain = None
    if mode == "lip":
        lip_t = 0.6
        ov = min(0.3, 0.85 * mat.strain_limit * r) if lip_overlap is None else float(lip_overlap)
        strain = ov / r
        # mouth opening is r - ov for lip_t, then the full bore; the magnet seats just behind the lip
        z0 = max(recess, lip_t)
        depth = z0 + thickness + 0.1
        magnet = cyl(r, z0, z0 + thickness, segments)
        female = cyl(r + c, z0, depth, segments) + cyl(r - ov, -EPS, z0 + 0.01, segments)
        notes.append(f"lip {lip_t} mm thick, {ov:.2f} mm overlap, magnet is pressed in once")
        notes.append("the lip holds the magnet while handling; the mating magnet's pull is what loads it, so keep the lip face the loaded side")
        if strain > mat.strain_limit * 1.0001:
            warn.append(f"lip strain {strain:.1%} exceeds {mat.strain_limit:.1%}")
    rep = measure_fit(magnet, female, joint=f"magnet-pocket-{mode}", material=mat, nominal=c,
                      min_feature=max(0.6, 0.0) if mode == "lip" else diameter, min_wall=mat.min_wall + 0.4,
                      orientation="Print with the pocket opening up so it needs no support; for a closed pocket pause at the "
                                  "magnet's top layer, insert (mind polarity, mark it) and let the next layer bridge it.",
                      notes=notes, fit_female=female, search=1.5)
    rep.warnings += warn
    rep.strain, rep.strain_limit = strain, (mat.strain_limit if strain is not None else None)
    rep.notes.append("check polarity: mirror the part and the magnet orientation, mark both with a dot")
    return JointPair(rep.joint, magnet, female, rep, dict(diameter=diameter, thickness=thickness, mode=mode,
                                                           recess=recess, clearance=c), fit_female=female)


def heat_set_insert(size="M3", hole_d=None, depth=None, material="PETG", segments=64) -> JointPair:
    """Hole for a brass heat-set insert. male = the insert body (reference, intentionally overlapping the host),
    female = hole with a lead-in chamfer and a little extra depth for melted plastic to pool."""
    mat = get_material(material)
    if size not in HEAT_SET:
        raise ValueError(f"size must be one of {sorted(HEAT_SET)}")
    od, ln, hd, extra, wall = HEAT_SET[size]
    hd = hd if hole_d is None else float(hole_d)
    dp = ln + extra if depth is None else float(depth)
    insert = cyl(od / 2, 0.0, ln, segments)
    female = (cyl(hd / 2, -EPS, dp, segments)
              + m3d.Manifold.cylinder(0.5, hd / 2 + 0.4, hd / 2, segments).translate([0, 0, -0.01]))
    rep = measure_fit(insert, female, joint=f"heat-set-{size}", material=mat, fit_type="interference", nominal=0.0,
                      min_feature=hd, min_wall=wall,
                      orientation="Print with the hole opening up (or sideways); press the hot insert in along the hole axis.",
                      notes=[f"insert {od} mm OD x {ln} mm, hole {hd} mm x {dp:.1f} mm deep",
                             f"interference {(od - hd) / 2:.2f} mm per side is intentional, the plastic melts around the knurls",
                             "typical values (Ruthex, CNC Kitchen, McMaster): verify against your insert's datasheet"],
                      fit_female=female, search=1.0)
    return JointPair(rep.joint, insert, female, rep, dict(size=size, hole_d=hd, depth=dp, insert_od=od,
                                                           insert_len=ln), fit_female=female)


def pilot_hole(screw="M3", engagement=None, pilot_d=None, material="PETG", segments=48) -> JointPair:
    """Pilot hole for a self-tapping (thread-forming) screw. male = the screw's major-diameter body (reference,
    overlaps host by design), female = pilot hole with lead-in. extra['clearance_hole'] is the through hole for the
    part being clamped, and extra['clearance_hole'] sits in the same frame (cut it from the other part)."""
    mat = get_material(material)
    if screw not in SELF_TAP:
        raise ValueError(f"screw must be one of {sorted(SELF_TAP)}")
    d, pd, cd = SELF_TAP[screw]
    pd = pd if pilot_d is None else float(pilot_d)
    eng = 2.0 * d if engagement is None else float(engagement)
    boss_od = 2.2 * d
    body = cyl(d / 2, 0.0, eng, segments)
    female = (cyl(pd / 2, -EPS, eng + 1.0, segments)
              + m3d.Manifold.cylinder(0.4, pd / 2 + 0.3, pd / 2, segments).translate([0, 0, -0.01]))
    clr = cyl(cd / 2, -eng - 10.0, EPS, segments)
    rep = measure_fit(body, female, joint=f"pilot-hole-{screw}", material=mat, fit_type="interference",
                      min_feature=pd, min_wall=0.5 * (boss_od - pd),
                      orientation="Print with the hole axis vertical (round) or horizontal with the hole opening sideways; avoid a "
                                  "hole axis lying in the layer plane under load.",
                      notes=[f"pilot {pd} mm for {screw} (about {pd / d:.0%} of major), engagement {eng:.1f} mm (2 x d)",
                             f"boss OD at least {boss_od:.1f} mm; clearance hole {cd} mm in the clamped part"],
                      fit_female=female, search=1.0)
    return JointPair(rep.joint, body, female, rep, dict(screw=screw, pilot_d=pd, engagement=eng, boss_od=boss_od),
                     fit_female=female, extra={"clearance_hole": clr})
