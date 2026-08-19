"""
The four connector types confirmed against PrusaSlicer/OrcaSlicer's real
built-in Cut Tool (Plug, Dowel, Snap, Dovetail -- see the repo README for the
source citation). Each function takes a solid already split into two halves
by core.geometry.split_solid, and returns the two halves with connector
geometry applied (plus, for Dowel, a third loose printable piece).

All local shapes are built with local +Z as the protrusion axis (across the
seam, away from the solid they're attached to) and placed into world space
via core.geometry.place -- see that module's docstring for why the
protrude_toward_normal flag exists and what happens if you get it backwards.
"""
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

import numpy as np
import manifold3d as m3d

from .geometry import CutPlane, place


@dataclass
class ConnectorParams:
    width: float       # mm, cross-section size of the connector
    depth: float       # mm, how far it protrudes / how deep the socket is
    tolerance: float = 0.15  # mm, per-side clearance for a friction fit


@dataclass
class ConnectorResult:
    piece_a: m3d.Manifold   # the +normal-side piece (from split_solid's first result)
    piece_b: m3d.Manifold   # the -normal-side piece
    loose_piece: Optional[m3d.Manifold] = None  # only set for Dowel


def _box_2d(width, length):
    hw, hl = width / 2, length / 2
    return m3d.CrossSection([[(-hw, -hl), (hw, -hl), (hw, hl), (-hw, hl)]])


def apply_plug(piece_a, piece_b, plane: CutPlane, params: ConnectorParams) -> ConnectorResult:
    """A boss on piece_a, a matching (slightly oversized) cavity in piece_b."""
    boss = m3d.Manifold.extrude(_box_2d(params.width, params.width), params.depth)
    boss_world = place(boss, plane, protrude_toward_normal=False)
    new_a = piece_a + boss_world

    cavity_w = params.width + 2 * params.tolerance
    # extend the cavity slightly past `depth` so its floor isn't exactly
    # coincident with the boss's tip -- a zero-clearance coincident face is
    # the kind of degenerate geometry that produces flaky, not-really-fitting
    # boolean results.
    cavity = m3d.Manifold.extrude(_box_2d(cavity_w, cavity_w), params.depth + params.tolerance)
    cavity_world = place(cavity, plane, protrude_toward_normal=False)
    new_b = piece_b - cavity_world

    return ConnectorResult(piece_a=new_a, piece_b=new_b)


def apply_dowel(piece_a, piece_b, plane: CutPlane, params: ConnectorParams) -> ConnectorResult:
    """A cylindrical hole in BOTH pieces, centered on the seam, plus a
    separate loose printable pin the user prints once and glues/friction-fits
    into both holes after printing -- this is how PrusaSlicer/Orca's Dowel
    mode works, distinct from Plug's one-piece boss+cavity."""
    hole_radius = (params.width + 2 * params.tolerance) / 2
    hole = m3d.Manifold.cylinder(2 * params.depth, hole_radius, hole_radius, circular_segments=32)
    hole_world = place(hole, plane, local_origin=(0, 0, -params.depth), protrude_toward_normal=False)

    new_a = piece_a - hole_world
    new_b = piece_b - hole_world

    pin_radius = params.width / 2
    pin_length = 2 * params.depth - params.tolerance
    pin = m3d.Manifold.cylinder(pin_length, pin_radius, pin_radius, circular_segments=32)

    return ConnectorResult(piece_a=new_a, piece_b=new_b, loose_piece=pin)


def apply_dovetail(piece_a, piece_b, plane: CutPlane, params: ConnectorParams,
                    tail_length: Optional[float] = None, flare: float = 1.6) -> ConnectorResult:
    """A trapezoidal tail on piece_a that flares wider toward its tip (along
    the slide axis `plane.u`'s perpendicular width, i.e. it flares in the
    `plane.v`-ish width as depth increases -- see below), and a matching
    socket in piece_b. This locks against being pulled straight apart along
    the plane normal; it can only be assembled/disassembled by sliding along
    `plane.u` (the joint's length direction).

    `flare` > 1.0 sets how much wider the tail is at its tip vs. its base
    (PrusaSlicer/Orca don't expose this as a named ratio, but the shape is
    the same idea). `tail_length` defaults to 3x width if not given.
    """
    if tail_length is None:
        tail_length = params.width * 3.0

    # Cross-section is (width along U) x (tail_length along... this becomes
    # the joint's sliding direction once placed): the box's own local X is
    # width (which manifold3d's extrude scale_top will flare), local Y is
    # tail_length (held constant by scale_top's second component staying 1.0).
    tail = m3d.Manifold.extrude(
        _box_2d(params.width, tail_length), params.depth,
        scale_top=(flare, 1.0),
    )
    tail_world = place(tail, plane, protrude_toward_normal=False)
    new_a = piece_a + tail_world

    socket_w = params.width + 2 * params.tolerance
    socket_l = tail_length + 2 * params.tolerance
    socket = m3d.Manifold.extrude(
        _box_2d(socket_w, socket_l), params.depth + params.tolerance,
        scale_top=(flare, 1.0),
    )
    socket_world = place(socket, plane, protrude_toward_normal=False)
    new_b = piece_b - socket_world

    return ConnectorResult(piece_a=new_a, piece_b=new_b)


def apply_snap(piece_a, piece_b, plane: CutPlane, params: ConnectorParams,
               bulge: float = 1.35) -> ConnectorResult:
    """A peg on piece_a with a bulbous tip (radius = neck radius x bulge),
    into a two-stage socket in piece_b: a throat narrower than the bulb
    (forcing the peg tip to compress slightly on the way in) opening into a
    wider pocket sized for the bulb once past it.

    Honest limitation, matching this project's own standing rule about not
    faking flex-dependent joints: this is a rigid boolean-geometry model.
    It can prove the LOCKED state (bulb seated in the wide pocket) is
    collision-free, and that the throat is genuinely narrower than the bulb
    (so it isn't a snap in name only) -- it cannot simulate the actual
    material flex needed to get the bulb past the throat, which depends on
    your filament and wall thickness, not on this geometry alone.
    """
    neck_r = params.width / 2
    bulb_r = neck_r * bulge
    if bulb_r <= neck_r + params.tolerance:
        raise ValueError(
            "bulge must be large enough that the bulb radius exceeds the "
            "throat radius by more than `tolerance`, or this isn't a snap "
            "joint at all -- it's just a slightly lumpy plug"
        )

    neck_height = params.depth * 0.6
    bulb_height = params.depth * 0.4
    neck = m3d.Manifold.cylinder(neck_height, neck_r, neck_r, circular_segments=32)
    bulb = m3d.Manifold.sphere(bulb_r, circular_segments=32).translate([0, 0, neck_height])
    peg_local = neck + bulb
    peg_world = place(peg_local, plane, protrude_toward_normal=False)
    new_a = piece_a + peg_world

    throat_r = neck_r + params.tolerance
    pocket_r = bulb_r + params.tolerance
    throat = m3d.Manifold.cylinder(neck_height, throat_r, throat_r, circular_segments=32)
    pocket = m3d.Manifold.sphere(pocket_r, circular_segments=32).translate([0, 0, neck_height])
    socket_local = throat + pocket
    socket_world = place(socket_local, plane, protrude_toward_normal=False)
    new_b = piece_b - socket_world

    return ConnectorResult(piece_a=new_a, piece_b=new_b)


def _is_solidly_on_material(piece, center, probe_radius: float, min_fill_fraction: float = 0.3) -> bool:
    """Is `piece` genuinely solid in the neighborhood of `center`? Uses a
    SPHERE probe, not a cube -- a real bug, found live: a cube probe's flat
    faces under-reach a curved hollow boundary while its CORNERS (at
    radius*sqrt(3) from center, not radius) over-reach past one, so a cube
    centered dead in the hollow middle of a tube still caught real wall
    material at its corners and was wrongly called "solid." A sphere has
    neither problem.

    The threshold is 0.3, not close to 1.0: `center` sits exactly ON the
    cut plane by construction (it's the connector's own position), so the
    probe is always bisected by that plane -- measured directly on a solid
    cube and a real tube wall, a valid position reliably fills exactly
    half the probe (0.5) on each side, while a hollow or off-model position
    fills exactly 0.0. 0.3 sits with clear margin in between rather than
    guessing a number close to the wrong reference point (the full probe,
    which a valid position can never fill more than half of anyway)."""
    probe = m3d.Manifold.sphere(probe_radius, circular_segments=16).translate(list(center))
    probe_volume = probe.volume()
    return (probe ^ piece).volume() >= probe_volume * min_fill_fraction


def filter_offsets_on_solid_material(piece_a, piece_b, plane: CutPlane, offsets: List[float],
                                      probe_size: float) -> List[float]:
    """Keep only the offsets where a probe centered there is genuinely
    surrounded by real material in BOTH pieces. Evenly spacing connectors
    across the seam's bounding-box span (core.geometry.suggest_connector_
    layout) is a cheap vertex-based estimate -- fine for a solid
    cross-section, but a hollow or thin-walled model (a vase, a pipe, a
    lampshade) has empty space in the middle of that span, and a connector
    placed there has nothing to attach to. This checks the real split
    geometry with an actual boolean intersection (manifold3d's `^`
    operator), not a guess. Real, found via live testing on an actual
    hollow model, not assumed."""
    probe_radius = probe_size / 2
    return [
        offset for offset in offsets
        if _is_solidly_on_material(piece_a, plane.point + plane.u * offset, probe_radius)
        and _is_solidly_on_material(piece_b, plane.point + plane.u * offset, probe_radius)
    ]


def local_wall_thickness(piece_a, piece_b, plane: CutPlane, offset: float,
                          probe_extent: float, min_width: float = 3.0) -> Optional[float]:
    """The real local material thickness at `offset` along the seam, read
    directly from the actual split geometry -- clip a probe box to each
    piece with a real boolean intersection and read the RESULT's own
    bounding box (manifold3d's Manifold.bounding_box(), not a heuristic
    guess from vertex positions). Returns None if either piece isn't
    genuinely solid there (see _is_solidly_on_material) -- the hollow,
    edge, or too-close-to-empty-space case.

    This is what actually catches "chunky" connectors on a thin-walled
    model: sizing a connector from the seam's overall bounding-box span
    (a vase's ~150mm diameter) has nothing to do with how thick the wall
    is at one specific spot (often just a few mm) -- found via a live test
    on an actual wavy vase model where an 18mm-wide boss dwarfed an 8mm
    wall, not assumed.

    Two different probe sizes are used deliberately: a small, tight one
    (min_width) to decide IS there material here at all, and a bigger one
    (probe_extent, sized to the connector) to measure HOW FAR it extends.
    Using only the big probe for both would break on a thin wall: the big
    probe is SUPPOSED to spill into empty space at a thin wall's edges
    (that's what reveals the thickness), so requiring it to be "mostly
    full" would wrongly reject the very walls this function exists to
    measure."""
    center = plane.point + plane.u * offset
    if not _is_solidly_on_material(piece_a, center, min_width / 2) \
            or not _is_solidly_on_material(piece_b, center, min_width / 2):
        return None

    probe = m3d.Manifold.cube([probe_extent, probe_extent, probe_extent], True).translate(list(center))
    clipped_a = probe ^ piece_a
    clipped_b = probe ^ piece_b

    def span(clipped, axis_vec):
        lo_x, lo_y, lo_z, hi_x, hi_y, hi_z = clipped.bounding_box()
        lo, hi = np.array([lo_x, lo_y, lo_z]), np.array([hi_x, hi_y, hi_z])
        idx = int(np.argmax(np.abs(axis_vec)))
        return hi[idx] - lo[idx]

    return min(span(clipped_a, plane.u), span(clipped_a, plane.v),
               span(clipped_b, plane.u), span(clipped_b, plane.v))


def _snap_offset_to_material(piece_a, piece_b, plane: CutPlane, target_offset: float,
                              probe_radius: float, search_extent: float,
                              step: float) -> Optional[float]:
    """Find the nearest real offset to `target_offset` (searching outward
    along plane.u in alternating +/- steps, closest first, out to
    `search_extent`) where a probe reads genuinely solid in BOTH pieces.
    Returns `target_offset` itself if it already qualifies, or None if
    nothing solid turns up within range.

    Needed because a straight, evenly-spaced offset guess -- computed from
    the seam's vertex-bounding-box span, see core.geometry.suggest_
    connector_layout -- assumes the wall sits exactly there. A real, organic
    model doesn't: found live on wave_shade_v1.stl, an actual spiral-fluted
    vase, where vase mode's guessed offset sat under 1mm short of the wall
    (which only existed in a ~3mm-wide radial band at that angle, confirmed
    by directly scanning fill fraction radius-by-radius at the same height/
    angle). A tiny miss like that is invisible to a straight bounding-box
    guess and fatal to a probe with zero tolerance for it -- vase mode's
    probe is already necessarily small (scaled to the wall itself), so
    without this search EVERY offset silently came back empty, not just an
    edge case."""
    center = plane.point + plane.u * target_offset
    if _is_solidly_on_material(piece_a, center, probe_radius) \
            and _is_solidly_on_material(piece_b, center, probe_radius):
        return target_offset

    n_steps = max(1, int(search_extent / step))
    for i in range(1, n_steps + 1):
        for delta in (i * step, -i * step):
            candidate = target_offset + delta
            center = plane.point + plane.u * candidate
            if _is_solidly_on_material(piece_a, center, probe_radius) \
                    and _is_solidly_on_material(piece_b, center, probe_radius):
                return candidate
    return None


def _rotated_frame(plane: CutPlane, angle_degrees: float) -> CutPlane:
    """A frame sharing `plane`'s point and normal, but with u/v rotated by
    `angle_degrees` within the plane. Lets vase mode search and place a
    connector along the ACTUAL local radial/tangential directions at any
    angle around the seam, not just along the single straight line
    `plane.u` itself defines -- a real, roughly round vase's wall runs all
    the way around its circumference, not along one diameter."""
    rad = np.radians(angle_degrees)
    u = plane.u * np.cos(rad) + plane.v * np.sin(rad)
    v = -plane.u * np.sin(rad) + plane.v * np.cos(rad)
    return CutPlane(point=plane.point, normal=plane.normal, u=u, v=v)


def _angular_distance(a: float, b: float) -> float:
    d = abs(a - b) % 360.0
    return min(d, 360.0 - d)


def _find_vase_connector_frames(piece_a, piece_b, plane: CutPlane, count: int,
                                 max_radius: float, probe_radius: float, half_length: float,
                                 angle_step: float = 8.0,
                                 radius_step: Optional[float] = None) -> List[CutPlane]:
    """Search a full circle of angles around `plane.point` (not just the one
    straight line `evenly_spaced_offsets` produces along `plane.u`) for
    positions genuinely solid in both pieces, then greedily pick up to
    `count` of them as angularly spread apart as possible.

    Found live, on the real wave_shade_v1.stl (an actual spiral-fluted
    vase): every offset `evenly_spaced_offsets` produces sits on the same
    straight line through the model's center, i.e. only ever at angle 0 deg
    or 180 deg -- so of 4 "evenly spaced" connectors, at most 2 could ever
    land on real wall material no matter how good the positional search
    along that line got, and the other 2 were always going to be either
    deep in the hollow interior or off the model entirely. "More
    connectors" only means anything if they're actually distributed around
    the wall, which requires searching in more than one direction from the
    center.

    A center passing `_is_solidly_on_material` alone isn't enough: a real
    wavy wall's material can run out tangentially well before its radial
    thickness does -- found live, a connector centered dead-on the wall's
    radial band still ran off the edge of that specific wave lobe and
    poked into open air past the wall's tangential end. So each candidate
    also gets checked `half_length` out to either side ALONG THE ARC (not a
    straight-line offset in `frame.v`): a straight tangent line diverges
    from any curved wall, even a perfectly uniform circular one, so testing
    a literal straight offset would reject good positions on a plain round
    vase too, not just a wavy one -- found live via a failing test on an
    ordinary uniform-thickness cylindrical shell fixture, not just the
    organic model. Converting `half_length` to an equivalent angular reach
    (arc_length = radius * angle_in_radians) and re-checking at the SAME
    radius but a nearby angle follows the actual curve instead. (Radial
    bulge -- the connector's width being wider than the wall's own thin
    cross-section -- is a separate, expected thing: any connector thick
    enough to print reliably on a sub-1mm wall inherently straddles past
    both of the wall's faces a little, the way a boss or rivet head does on
    a thin sheet; only the tangential run is actually variable per-lobe and
    worth rejecting on.)

    `radius_step` scales with `probe_radius`, not a fixed mm value: a
    vase-mode wall is routinely under 1mm thick, so a step coarser than the
    wall itself can step clean over it at every single angle -- a fixed
    step tuned for an ordinary 8mm+ connector would silently find nothing
    on a real 0.4mm single wall."""
    radius_step = radius_step or max(probe_radius * 0.5, 0.1)
    hits = []
    for angle in np.arange(0.0, 360.0, angle_step):
        frame = _rotated_frame(plane, float(angle))
        r = radius_step
        while r <= max_radius:
            center = frame.point + frame.u * r
            if _is_solidly_on_material(piece_a, center, probe_radius) \
                    and _is_solidly_on_material(piece_b, center, probe_radius):
                reach_degrees = np.degrees(half_length / r) if r > 1e-6 else 0.0
                side_ok = True
                for side in (reach_degrees, -reach_degrees):
                    side_frame = _rotated_frame(plane, float(angle) + side)
                    side_center = side_frame.point + side_frame.u * r
                    if not (_is_solidly_on_material(piece_a, side_center, probe_radius)
                            and _is_solidly_on_material(piece_b, side_center, probe_radius)):
                        side_ok = False
                        break
                if side_ok:
                    hits.append((float(angle), float(r)))
                    break
            r += radius_step
    if not hits:
        return []

    chosen = [hits[0]]
    remaining = hits[1:]
    while len(chosen) < count and remaining:
        best = max(remaining, key=lambda h: min(_angular_distance(h[0], c[0]) for c in chosen))
        chosen.append(best)
        remaining.remove(best)

    frames = []
    for angle, radius in chosen:
        frame = _rotated_frame(plane, angle)
        frames.append(CutPlane(point=frame.point + frame.u * radius, normal=frame.normal,
                                u=frame.u, v=frame.v))
    return frames


_FIT_FRACTIONS = (1.0, 0.75, 0.55, 0.4, 0.3, 0.2)


def _fit_connector_size(piece_a, piece_b, plane: CutPlane, offset: float,
                         params: ConnectorParams, min_width: float) -> Optional[ConnectorParams]:
    """Find the largest size (as a fraction of `params`) that actually fits
    as solid material at `offset`, by directly testing candidate sizes
    against the real split geometry (the same proven sphere-probe,
    fraction-of-volume check as _is_solidly_on_material) rather than
    inferring a size from a bounding-box measurement -- see
    apply_connector_instances' docstring for why that measurement approach
    didn't hold up. Tries the full requested size first, shrinking through
    fixed steps; returns None if nothing down to `min_width` fits."""
    center = plane.point + plane.u * offset
    for fraction in _FIT_FRACTIONS:
        width = params.width * fraction
        if width < min_width:
            break
        test_radius = width * 0.7
        # A stricter fill fraction than _is_solidly_on_material's own 0.3
        # default: that default distinguishes "on material at all" from
        # "hollow" (0.5 vs 0.0, a wide gap). Here the question is "does
        # THIS SIZE actually fit," and measured directly against a real
        # thin wall, fill drops off smoothly as the tested size grows past
        # what fits (0.50 comfortably embedded, ~0.34 already spilling
        # past the wall) -- 0.3 would accept sizes visibly bigger than the
        # wall itself, which is the exact "chunky" bug this exists to fix.
        if _is_solidly_on_material(piece_a, center, test_radius, min_fill_fraction=0.45) \
                and _is_solidly_on_material(piece_b, center, test_radius, min_fill_fraction=0.45):
            return ConnectorParams(width=width, depth=params.depth * fraction, tolerance=params.tolerance)
    return None


def apply_connector_instances(piece_a, piece_b, plane: CutPlane, params: ConnectorParams,
                               connector_fn: Callable[..., ConnectorResult],
                               offsets: List[float], min_width: float = 3.0,
                               vase_mode: bool = False) -> ConnectorResult:
    """Apply `connector_fn` once per offset along the seam's slide axis
    (`plane.u`), chaining the boolean results so multiple connector
    instances compound onto the same two pieces -- this is how "bigger
    object, more connectors" is actually placed, not a new connector shape,
    just the existing ones repeated at real, non-overlapping positions
    (see core.geometry.suggest_connector_layout for how offsets are chosen).
    Dowel's loose pins (one per instance) union into a single printable body
    since a slicer handles multiple disjoint solids in one export fine --
    each pin is translated by its own offset first, since apply_dowel builds
    the pin in a position-independent local frame (it's a standalone print,
    not attached to the seam); without that translation, two instances would
    produce two perfectly-overlapping pins whose union silently collapses to
    one pin's volume instead of two.

    Each offset gets its OWN width/depth, shrunk to fit the real local
    material there -- not `params` applied uniformly everywhere. Sized by
    directly TESTING candidate sizes against the actual split geometry
    (see _fit_connector_size), not by measuring an abstract "thickness"
    and calculating backward from it: an earlier version did that with
    local_wall_thickness's bounding-box reading, but a curved wall's
    material extends further at some points within a probe's footprint
    than directly at the connector's own center, inflating that reading
    well past the wall's real thickness -- found live (a measured 16.5mm
    on an actual 8mm-thick tube wall) after already having to fix the
    measurement once for a DIFFERENT reason (a large probe wrapping
    around to the opposite wall of a hollow shape entirely). Directly
    testing "does a connector of this size actually fit" sidesteps both
    failure modes instead of chasing a third fix to the measurement
    approach. An offset with no size that fits at all (or no material to
    begin with) is dropped entirely. If EVERY offset turns out unusable
    this way, the honest answer is no connector at all, not forcing one
    back onto a position already proven unfit.

    `vase_mode=True` skips that shrink-and-test search entirely and uses
    `params` exactly as given at every accepted position instead. It exists
    for a genuinely different situation: a model meant to print in Cura's
    "Spiralize Outer Contour" mode is a known, fixed-thickness single wall
    (typically under 1mm), not an unknown thickness to be discovered by
    shrinking a guess. The shrink-and-test search's own probe sizes are
    tuned around ordinary connector dimensions (3mm+) and would either
    reject a legitimately-sized vase-mode connector outright or waste many
    probe calls shrinking toward a size the caller already knows in
    advance. The caller (CuraConnectTool) is expected to have already sized
    `params` from Cura's real per-object wall_line_width_0/magic_spiralize
    settings before calling this -- not guessed here.

    Rather than reusing `offsets` as positions (see _find_vase_connector_
    frames' docstring for why a straight line through the center only ever
    reaches two opposite angles), vase mode searches a full circle around
    `plane.point` for real wall material and picks `len(offsets)` positions
    spread around it -- each also checked tangentially (does the wall
    keep going far enough sideways to fit the connector's actual length,
    not just at its own center point), since a real wavy wall's material
    can run out in that direction well before its radial thickness does."""
    if vase_mode:
        # min_width (an "ordinary connector" floor, 3mm by default) has no
        # business capping this probe from below -- a vase-mode wall is
        # routinely well under that, and maxing against it would swamp the
        # probe past the wall's own thickness, making even a position
        # genuinely on the wall read as "not solidly on material."
        probe_radius = params.depth / 2
        count = max(len(offsets), 1)

        # A generous outer bound for the radial search: prefer the existing
        # straight-line offsets' own magnitude (cheap, and already roughly
        # right) with headroom for a wall that turns out to sit a bit
        # further out than that guess -- but a single centered connector
        # request (evenly_spaced_offsets always returns [0.0] for count<=1)
        # gives a useless zero-radius bound, so fall back to the real
        # geometry's own extent in that case instead of searching nothing.
        offset_radius = max((abs(o) for o in offsets), default=0.0)
        if offset_radius > 1e-6:
            max_radius = offset_radius * 1.3
        else:
            lo_x, lo_y, lo_z, hi_x, hi_y, hi_z = (piece_a + piece_b).bounding_box()
            extent = np.array([hi_x - lo_x, hi_y - lo_y, hi_z - lo_z])
            max_radius = float(np.max(extent)) * 0.75

        # A generic proxy for "how far the connector's own footprint runs
        # tangentially": matches apply_dovetail's default tail_length
        # (width * 3) exactly, and is a reasonably conservative stand-in
        # for the square width x width footprint the other connector types
        # use (checking a bit further than their actual half-width is
        # needed).
        half_length = params.width * 1.5

        candidates = _find_vase_connector_frames(
            piece_a, piece_b, plane, count=max(count * 3, count + 4),
            max_radius=max_radius, probe_radius=probe_radius, half_length=half_length,
        )
        fitted: List[Tuple[CutPlane, ConnectorParams]] = [(frame, params) for frame in candidates[:count]]
    else:
        fitted = []
        for offset in offsets:
            local_params = _fit_connector_size(piece_a, piece_b, plane, offset, params, min_width)
            if local_params is not None:
                shifted_plane = CutPlane(
                    point=plane.point + plane.u * offset,
                    normal=plane.normal, u=plane.u, v=plane.v,
                )
                fitted.append((shifted_plane, local_params))

    if not fitted:
        return ConnectorResult(piece_a=piece_a, piece_b=piece_b, loose_piece=None)

    loose_pieces = []
    for frame, local_params in fitted:
        result = connector_fn(piece_a, piece_b, frame, local_params)
        piece_a, piece_b = result.piece_a, result.piece_b
        if result.loose_piece is not None:
            loose_pieces.append(result.loose_piece.translate(list(frame.point - plane.point)))

    loose = None
    if loose_pieces:
        loose = loose_pieces[0]
        for extra in loose_pieces[1:]:
            loose = loose + extra

    return ConnectorResult(piece_a=piece_a, piece_b=piece_b, loose_piece=loose)
