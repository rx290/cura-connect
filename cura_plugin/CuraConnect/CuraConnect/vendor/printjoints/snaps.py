"""Snap joints: split barbed tenon, cantilever snap hook, snap bead/groove ring."""
from __future__ import annotations

import math

import manifold3d as m3d

from .core import (EPS, JointPair, box, cantilever_strain, cs_poly, cyl, length_for_strain, measure_fit,
                   prism, revolve_rz)
from .materials import get_material


# ------------------------------------------------------------------ split barbed tenon
def barbed_tenon_profile(width=9.0, catch=5.8, tip=8.2, barb=0.45, slit=2.4, slit_in=-0.5, lead=0.6,
                         tip_chamfer=0.8, embed=1.0):
    """Outline of a split tenon as (d, x) pairs: d runs along the tenon from the part's face (d=0) to the tip,
    x is across. Two prongs split by a slit, each with a barb whose catch face sits at d=catch. This is exactly the
    outline the Fanoos lantern panels use, so lamp-print-packs and printjoints make the same tenon."""
    hw, bw = width / 2, width / 2 + barb
    return [(-embed, hw), (catch, hw), (catch, bw), (tip - lead, hw - 0.2), (tip, hw - tip_chamfer),
            (tip, slit / 2), (-slit_in, slit / 2), (-slit_in, -slit / 2), (tip, -slit / 2),
            (tip, -hw + tip_chamfer), (tip - lead, -hw + 0.2), (catch, -bw), (catch, -hw), (-embed, -hw)]


def barbed_snap_tenon(width=9.0, thickness=2.4, catch=5.8, tip=8.2, barb=0.45, slit=2.4, slit_in=-0.5,
                      throat_depth=5.4, slot_depth=8.8, material="PETG", clearance=None) -> JointPair:
    """Tenon (male, z = insertion, x = width, y = thickness centred) into a two-stage slot: a narrow throat the barbs
    squeeze through, then a wider chamber they spring open into. Defaults are the proven Fanoos panel tenon."""
    mat = get_material(material)
    c = mat.clearance if clearance is None else float(clearance)
    pts = barbed_tenon_profile(width, catch, tip, barb, slit, slit_in)
    # (d, x) -> polygon with x as X and d as Y, extruded over the thickness, then stood up so d is +z
    poly = prism([(x, d) for d, x in pts], thickness)
    male = poly.rotate([90, 0, 0]).translate([0, thickness / 2, 0])
    wn, ww, th = width + 2 * c, width + 2 * barb + 4 * c, thickness + 2 * c
    throat = box(-wn / 2, wn / 2, -th / 2, th / 2, -EPS, throat_depth)
    chamber = box(-ww / 2, ww / 2, -th / 2, th / 2, throat_depth - 0.01, slot_depth)
    female = throat + chamber
    prong = width / 2 - slit / 2
    squeeze = max(barb - c, 0.0)
    beam_len = catch + slit_in          # prong root sits at d = -slit_in
    eps = cantilever_strain(prong, squeeze, max(beam_len, 1e-6))
    rep = measure_fit(male, female, joint="barbed-snap-tenon", material=mat, nominal=c,
                      min_feature=min(prong, barb * 2, thickness), min_wall=mat.min_wall,
                      orientation="Print the tenon plate flat so the prongs flex within the layers (never across them).",
                      notes=[f"barb catch face sits {catch - throat_depth:.2f} mm behind the throat shoulder",
                             f"prong {prong:.2f} mm wide, flexes {squeeze:.2f} mm to pass the throat"],
                      fit_female=female, search=2.0)
    rep.strain, rep.strain_limit = eps, mat.strain_limit
    if eps > mat.strain_limit:
        rep.warnings.append(f"prong strain {eps:.1%} exceeds the {mat.strain_limit:.1%} {mat.name} limit: "
                            "lengthen the prong, shrink the barb or widen the slit")
    return JointPair("barbed-snap-tenon", male, female, rep,
                     dict(width=width, thickness=thickness, catch=catch, tip=tip, barb=barb, clearance=c),
                     fit_female=female, extra={"profile": pts})


# ------------------------------------------------------------------ cantilever snap hook
def cantilever_snap_hook(width=6.0, beam_thickness=1.4, undercut=0.8, length=None, ramp=1.6, lip=1.2,
                         wall=None, material="PETG", clearance=None) -> JointPair:
    """A beam rising from part A with a hook at the tip, and a channel plus catch window in part B.
    Beam runs along +z, flexes along X, width along Y. The beam length is chosen from the material strain
    limit (eps = 1.5 h y / L^2 for a constant-section cantilever, Bayer/Covestro snap-fit method) unless given."""
    mat = get_material(material)
    c = mat.snap_clearance if clearance is None else float(clearance)
    h, y = beam_thickness, undercut
    need = length_for_strain(h, y, mat.strain_limit)
    L = need if length is None else float(length)
    L = max(L, ramp + lip)
    eps = cantilever_strain(h, y, L)
    z_catch = L - ramp   # catch face height; hook tip at z = L
    beam = box(0, h, -width / 2, width / 2, -0.5, L)
    hook = prism([(h, z_catch), (h + y, z_catch), (h, L)], width).rotate([90, 0, 0]).translate([0, width / 2, 0])
    # prism([(x, z)...]) extruded along z then rotated: x stays, z-extrude -> -y, polygon y -> z
    male = beam + hook
    chan = box(-c, h + c, -width / 2 - c, width / 2 + c, -EPS, L + c)
    window = box(h + c - 0.01, h + y + c, -width / 2 - c, width / 2 + c, z_catch, L + c)
    female = chan + window
    ins_force = mat.modulus_mpa * (width * h * h / 6.0) * eps / L if L else 0.0   # N, tip force at full deflection
    rep = measure_fit(male, female, joint="cantilever-snap-hook", material=mat, nominal=c,
                      min_feature=min(h, y, width), min_wall=mat.min_wall,
                      orientation="Print the beam lying flat so it bends within the layers; standing it up makes it snap at a layer line.",
                      notes=[f"beam length {L:.1f} mm (minimum for strain {need:.1f} mm)",
                             f"approx. deflection force {ins_force:.1f} N", "retention face is square (permanent-ish); "
                             "chamfer it to 45 deg in your own hook for a releasable version"],
                      fit_female=female, search=2.0)
    rep.strain, rep.strain_limit = eps, mat.strain_limit
    if eps > mat.strain_limit * 1.0001:
        rep.warnings.append(f"hook strain {eps:.1%} exceeds {mat.strain_limit:.1%}: lengthen the beam")
    if wall is not None:
        rep.check_host_wall(wall)
    return JointPair("cantilever-snap-hook", male, female, rep,
                     dict(width=width, beam_thickness=h, undercut=y, length=L, clearance=c),
                     fit_female=female, extra={"force_n": ins_force})


# ------------------------------------------------------------------ snap bead / groove ring
def snap_ring(radius=20.0, length=8.0, bead_h=None, bead_w=1.6, bead_z=None, material="PETG",
              clearance=None, segments=128) -> JointPair:
    """Round spigot with one bead (male, axis +z) into a bore with a groove (female). The bead's tip-side face is a
    gentle lead-in, the back face is steep so it holds. Female hoop strain is about bead_h / radius, which sets the
    default bead height from the material limit (capped at 0.6 mm)."""
    mat = get_material(material)
    c = mat.snap_clearance if clearance is None else float(clearance)
    r = float(radius)
    bh = min(0.6, 0.85 * mat.strain_limit * r) if bead_h is None else float(bead_h)
    zb = length * 0.55 if bead_z is None else float(bead_z)
    bead = [(r - 0.3, zb), (r, zb), (r + bh, zb + 0.25 * bead_w), (r + bh, zb + 0.4 * bead_w), (r, zb + bead_w),
            (r - 0.3, zb + bead_w)]
    male = revolve_rz([(0, -0.5), (r, -0.5), (r, length), (0, length)], segments) + revolve_rz(bead, segments)
    groove = cs_poly(bead).offset(c, m3d.JoinType.Miter, 3.0)
    bore = cs_poly([(0, -EPS), (r + c, -EPS), (r + c, length + c), (0, length + c)])
    female = (bore + groove).revolve(segments)
    eps = bh / r
    rep = measure_fit(male, female, joint="snap-ring", material=mat, nominal=c, min_feature=min(bh, bead_w),
                      min_wall=mat.min_wall + bh,
                      orientation="Print with the axis vertical so the bead is a ring of layers (no overhang on the steep face is possible; keep it under 0.6 mm tall).",
                      notes=[f"bead {bh:.2f} mm high, {bead_w:.1f} mm wide, hoop strain about {eps:.1%}"],
                      fit_female=female, search=2.0)
    rep.strain, rep.strain_limit = eps, mat.strain_limit
    if eps > mat.strain_limit * 1.0001:
        rep.warnings.append(f"bead strain {eps:.1%} exceeds {mat.strain_limit:.1%}: lower the bead or use a bigger radius")
    return JointPair("snap-ring", male, female, rep, dict(radius=r, length=length, bead_h=bh, bead_w=bead_w, clearance=c),
                     fit_female=female)
