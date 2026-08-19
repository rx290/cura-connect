import sys
from pathlib import Path

import numpy as np
import pytest
import manifold3d as m3d

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cura_plugin" / "CuraConnect" / "CuraConnect"))
from core.geometry import CutPlane, split_solid, is_watertight
from core.connectors import (
    ConnectorParams, ConnectorResult,
    apply_plug, apply_dowel, apply_dovetail, apply_snap, apply_connector_instances,
    filter_offsets_on_solid_material, local_wall_thickness, _snap_offset_to_material,
)


@pytest.fixture
def split_cube():
    cube = m3d.Manifold.cube([40, 40, 40], True)
    plane = CutPlane.from_normal(point=[0, 0, 0], normal=[0, 0, 1])
    a, b = split_solid(cube, plane)
    return a, b, plane


@pytest.fixture
def params():
    return ConnectorParams(width=8, depth=6, tolerance=0.15)


# ---------- Plug ----------

def test_plug_pieces_are_watertight(split_cube, params):
    a, b, plane = split_cube
    result = apply_plug(a, b, plane, params)
    assert is_watertight(result.piece_a)
    assert is_watertight(result.piece_b)


def test_plug_fits_with_near_zero_overlap(split_cube, params):
    a, b, plane = split_cube
    result = apply_plug(a, b, plane, params)
    overlap = result.piece_a ^ result.piece_b
    assert overlap.volume() < 1e-6


def test_plug_boss_actually_bridges_into_the_other_half(split_cube, params):
    """Proves the boss protrudes across the seam (the exact bug caught and
    fixed during development -- a boss buried inside its own half would
    still pass the two tests above with zero overlap, since it wouldn't
    touch piece_b's space at all)."""
    a, b, plane = split_cube
    result = apply_plug(a, b, plane, params)
    grown_a_volume = result.piece_a.volume() - a.volume()
    assert grown_a_volume > 0.9 * (params.width ** 2 * params.depth)


def test_plug_without_tolerance_still_fits_but_oversized_boss_collides(split_cube):
    """Negative control: proves the collision test above would actually
    catch a broken build, not just always report zero by construction."""
    a, b, plane = split_cube
    tight = ConnectorParams(width=8, depth=6, tolerance=0.15)
    fitted = apply_plug(a, b, plane, tight)
    assert (fitted.piece_a ^ fitted.piece_b).volume() < 1e-6

    # Manually build an oversized boss the same way apply_plug does, but
    # sized to guarantee it doesn't fit the (unchanged) cavity -- this is
    # the deliberate "would this test have caught it" check.
    from core.connectors import _box_2d
    from core.geometry import place
    oversized_boss = m3d.Manifold.extrude(_box_2d(20, 20), tight.depth)
    oversized_world = place(oversized_boss, plane, protrude_toward_normal=False)
    broken_a = a + oversized_world
    overlap = broken_a ^ fitted.piece_b
    assert overlap.volume() > 100, (
        "an oversized boss should visibly collide with the cavity-bearing "
        "piece -- if this fails, the collision test itself is broken"
    )


# ---------- Dowel ----------

def test_dowel_pieces_and_pin_are_watertight(split_cube, params):
    a, b, plane = split_cube
    result = apply_dowel(a, b, plane, params)
    assert is_watertight(result.piece_a)
    assert is_watertight(result.piece_b)
    assert is_watertight(result.loose_piece)


def test_dowel_pin_fits_inside_both_holes(split_cube, params):
    """The pin, placed at the same location the holes were cut, must not
    protrude outside either hole's cross-section."""
    a, b, plane = split_cube
    result = apply_dowel(a, b, plane, params)
    from core.geometry import place
    pin_world = place(result.loose_piece, plane, local_origin=(0, 0, -params.depth + params.tolerance / 2),
                       protrude_toward_normal=False)
    # The pin should sit entirely within material removed from the original
    # solid (a + b), i.e. have ~zero overlap with what's left of (a union b).
    remaining_solid = result.piece_a + result.piece_b
    overlap = pin_world ^ remaining_solid
    assert overlap.volume() < 1.0, "the dowel pin should fit inside the holes, not collide with remaining material"


def test_dowel_hole_is_centered_on_the_seam(split_cube, params):
    """The hole must extend into BOTH pieces -- a hole only on one side
    would make this a plug in disguise, not a real two-piece dowel joint."""
    a, b, plane = split_cube
    result = apply_dowel(a, b, plane, params)
    assert (a.volume() - result.piece_a.volume()) > 1.0
    assert (b.volume() - result.piece_b.volume()) > 1.0


# ---------- Dovetail ----------

def test_dovetail_pieces_are_watertight(split_cube, params):
    a, b, plane = split_cube
    result = apply_dovetail(a, b, plane, params)
    assert is_watertight(result.piece_a)
    assert is_watertight(result.piece_b)


def test_dovetail_fits_with_near_zero_overlap_when_slid_into_place(split_cube, params):
    a, b, plane = split_cube
    result = apply_dovetail(a, b, plane, params)
    overlap = result.piece_a ^ result.piece_b
    assert overlap.volume() < 1e-6


def test_dovetail_resists_straight_pull_apart_along_the_normal(split_cube, params):
    """The whole point of a dovetail vs. a plug: translating piece_a a
    small amount along the plane normal (as if pulling the two halves
    straight apart, not sliding them) should immediately cause real
    interference with piece_b's socket, because the tail is wider at depth
    than at the opening. A plain plug would NOT show this (a straight boss
    slides cleanly out along the normal with zero interference)."""
    a, b, plane = split_cube
    result = apply_dovetail(a, b, plane, params)

    lift = 1.0  # mm, small pull-apart distance along the normal
    transform = np.column_stack([np.eye(3), plane.normal * lift])
    lifted_a = result.piece_a.transform(transform)

    overlap = lifted_a ^ result.piece_b
    assert overlap.volume() > 1.0, (
        "pulling the tail piece straight apart should interfere with the "
        "socket -- if it doesn't, the flare isn't actually locking anything "
        "and this is just a plug with extra steps"
    )


def test_plug_by_contrast_does_slide_apart_cleanly_along_the_normal(split_cube, params):
    """Contrast case proving the interference test above is measuring a
    real structural difference, not an artifact of the test itself."""
    a, b, plane = split_cube
    result = apply_plug(a, b, plane, params)

    lift = 1.0
    transform = np.column_stack([np.eye(3), plane.normal * lift])
    lifted_a = result.piece_a.transform(transform)

    overlap = lifted_a ^ result.piece_b
    assert overlap.volume() < 1e-6, (
        "a straight plug boss should slide cleanly along the normal with no "
        "interference -- if this fails, apply_plug's boss isn't actually "
        "a straight prism"
    )


# ---------- Snap ----------

def test_snap_pieces_are_watertight(split_cube, params):
    a, b, plane = split_cube
    result = apply_snap(a, b, plane, params)
    assert is_watertight(result.piece_a)
    assert is_watertight(result.piece_b)


def test_snap_locked_state_has_near_zero_overlap(split_cube, params):
    a, b, plane = split_cube
    result = apply_snap(a, b, plane, params)
    overlap = result.piece_a ^ result.piece_b
    assert overlap.volume() < 1e-6


def test_snap_bulb_is_genuinely_wider_than_throat(split_cube, params):
    """The geometric precondition for this to be a snap at all, not a plug
    that happens to be round."""
    neck_r = params.width / 2
    from core.connectors import apply_snap as _apply_snap
    # bulge default is 1.35; confirm it's rejected below its own stated floor
    with pytest.raises(ValueError):
        a, b, plane = split_cube
        _apply_snap(a, b, plane, params, bulge=1.01)


def test_snap_partial_insertion_before_the_throat_shows_real_interference(split_cube, params):
    """Proves the throat is genuinely narrower than the bulb by checking
    that a peg only partially advanced (bulb not yet past the throat) does
    collide -- otherwise 'snap' would be a socket with no constriction at
    all, and the test above would be trivially true for any loose hole."""
    a, b, plane = split_cube
    result = apply_snap(a, b, plane, params)

    # Push piece_a's peg back toward its own body by a couple mm (as if the
    # bulb hasn't reached the wide pocket yet) and check for interference
    # against the socket's narrower throat.
    pullback = -2.0
    transform = np.column_stack([np.eye(3), -plane.normal * abs(pullback)])
    retracted_a = result.piece_a.transform(transform)
    overlap = retracted_a ^ result.piece_b
    assert overlap.volume() > 0.5, (
        "a peg not yet through the throat should show real interference -- "
        "if it doesn't, the throat isn't actually constricting anything"
    )


# ---------- Multiple connector instances (apply_connector_instances) ----------

def test_multiple_connector_instances_stay_watertight(split_cube, params):
    a, b, plane = split_cube
    result = apply_connector_instances(a, b, plane, params, apply_plug, offsets=[-10.0, 0.0, 10.0])
    assert is_watertight(result.piece_a)
    assert is_watertight(result.piece_b)


def test_three_connector_instances_add_more_material_than_one(split_cube, params):
    a, b, plane = split_cube
    single = apply_connector_instances(a, b, plane, params, apply_plug, offsets=[0.0])
    triple = apply_connector_instances(a, b, plane, params, apply_plug, offsets=[-10.0, 0.0, 10.0])
    assert triple.piece_a.volume() > single.piece_a.volume(), (
        "three plug bosses should add noticeably more material than one -- "
        "this is the real mechanism behind 'bigger object, more connectors'"
    )


def test_multiple_dowel_pins_union_into_one_watertight_loose_body(split_cube, params):
    a, b, plane = split_cube
    single = apply_connector_instances(a, b, plane, params, apply_dowel, offsets=[0.0])
    double = apply_connector_instances(a, b, plane, params, apply_dowel, offsets=[-10.0, 10.0])
    assert double.loose_piece is not None
    assert is_watertight(double.loose_piece)
    assert double.loose_piece.volume() > single.loose_piece.volume() * 1.5, (
        "two disjoint pins unioned together should have roughly double the "
        "volume of one -- not one pin's worth, which would mean the second "
        "instance silently didn't get applied"
    )


# ---------- Hollow/thin-walled models (filter_offsets_on_solid_material) ----------
# A real bug found via live testing on an actual hollow vase/lampshade model:
# evenly spacing connectors across the seam's bounding-box span assumes a
# solid cross-section. A hollow tube's seam is a ring (wall material only
# near the outside), and a naive offset can land in the empty center where
# there's nothing to attach a connector to.

@pytest.fixture
def split_hollow_tube():
    """A tube, outer radius 20mm, inner radius 12mm (8mm wall), split flat
    at mid-height -- the same real shape category as a vase or lampshade."""
    outer = m3d.Manifold.cylinder(40, 20, 20, circular_segments=64)
    inner = m3d.Manifold.cylinder(40, 12, 12, circular_segments=64)
    tube = outer - inner
    plane = CutPlane.from_normal(point=[0, 0, 20], normal=[0, 0, 1])
    a, b = split_solid(tube, plane)
    return a, b, plane


def test_filter_offsets_removes_the_hollow_center_but_keeps_wall_positions(split_hollow_tube):
    a, b, plane = split_hollow_tube
    offsets = [0.0, 16.0, -16.0, 25.0]
    valid = filter_offsets_on_solid_material(a, b, plane, offsets, probe_size=4.0)

    assert 0.0 not in valid, "the hollow center has no wall to attach a connector to"
    assert 25.0 not in valid, "this position is entirely outside the tube"
    assert 16.0 in valid, "this position sits on the actual tube wall (12-20mm radius)"
    assert -16.0 in valid, "this position sits on the actual tube wall (12-20mm radius)"


def test_apply_connector_instances_skips_a_hollow_offset_instead_of_placing_it_in_empty_space(
        split_hollow_tube, params):
    a, b, plane = split_hollow_tube
    # 0.0 (dead center, hollow) and 16.0 (real wall material) -- the hollow
    # one should be silently dropped, not crash or produce a floating boss.
    result = apply_connector_instances(a, b, plane, params, apply_plug, offsets=[0.0, 16.0])
    assert is_watertight(result.piece_a)
    assert is_watertight(result.piece_b)

    center_only = apply_connector_instances(a, b, plane, params, apply_plug, offsets=[0.0])
    # If the hollow offset had actually been applied, piece_a would gain a
    # boss's worth of extra material; since it's dropped, this should be
    # unchanged from just cutting with no connector at all.
    assert np.isclose(center_only.piece_a.volume(), a.volume(), atol=1.0)


# ---------- Adaptive sizing to the real local wall ----------
# A second real bug found via the same live test on the hollow vase: even
# once a connector avoided the hollow center, it was still sized from the
# seam's overall bounding-box span (~150mm diameter) rather than the
# actual wall thickness at that one spot (a few mm) -- producing a boss far
# chunkier than the wall it was meant to attach to. apply_connector_
# instances fixes this by directly TESTING candidate sizes against the
# real geometry (_fit_connector_size), not by measuring an abstract
# "thickness" and calculating backward from it -- local_wall_thickness
# below is that earlier measurement approach, kept as a rough diagnostic,
# but its bounding-box reading is measurably inflated by wall curvature
# over the probe's footprint (a real, separate finding in its own right),
# so it's no longer what actually sizes a connector.

def test_local_wall_thickness_measures_the_wall_not_the_overall_diameter(split_hollow_tube):
    a, b, plane = split_hollow_tube
    # the tube's overall diameter is 40mm, but the wall itself is only 8mm
    # thick (outer radius 20 - inner radius 12) -- the measurement should
    # reflect the wall, not the diameter. probe_extent=25 (not, say, 60):
    # too large a probe wraps clean across the 24mm hollow middle and picks
    # up the opposite wall too, which is a real, separate bug in its own
    # right. Even so, a curved wall's material within the probe's footprint
    # inflates the reading well past the true 8mm -- 20.0 is a loose bound
    # that still clearly distinguishes "thin wall" from "40mm diameter,"
    # not a claim that this reading is precise (see _fit_connector_size for
    # the approach that's actually robust enough to size a connector from).
    thickness = local_wall_thickness(a, b, plane, offset=16.0, probe_extent=25.0)
    assert thickness is not None
    assert thickness < 20.0, f"expected a reading well under the 40mm diameter, got {thickness}"
    assert thickness > 2.0


def test_local_wall_thickness_is_none_in_the_hollow_center(split_hollow_tube):
    a, b, plane = split_hollow_tube
    assert local_wall_thickness(a, b, plane, offset=0.0, probe_extent=25.0) is None


def test_apply_connector_instances_caps_an_oversized_width_to_fit_a_thin_wall(split_hollow_tube):
    a, b, plane = split_hollow_tube
    oversized = ConnectorParams(width=30.0, depth=20.0, tolerance=0.15)
    fitted_small = ConnectorParams(width=6.0, depth=4.0, tolerance=0.15)

    result = apply_connector_instances(a, b, plane, oversized, apply_plug, offsets=[16.0])
    small = apply_connector_instances(a, b, plane, fitted_small, apply_plug, offsets=[16.0])
    assert is_watertight(result.piece_a)
    assert is_watertight(result.piece_b)

    added_by_oversized = result.piece_a.volume() - a.volume()
    added_by_small = small.piece_a.volume() - a.volume()
    assert added_by_oversized < added_by_small * 3, (
        "requesting a 30mm-wide connector on an 8mm wall should be capped down "
        "close to what actually fits, not applied at the full requested (chunky) size"
    )


# ---------- Vase mode (apply_connector_instances(..., vase_mode=True)) ----------
# A genuinely thin single wall (Cura's "Spiralize Outer Contour"), not just a
# thicker hollow object -- the shrink-and-test search above is tuned around
# ordinary connector sizes and would either reject a real vase-mode-scale
# connector or waste effort shrinking toward a size already known in advance.

@pytest.fixture
def split_thin_shell():
    """A single-wall shell, outer radius 20mm, wall 0.4mm (a real single
    0.4mm-nozzle line width), split flat at mid-height."""
    outer = m3d.Manifold.cylinder(40, 20, 20, circular_segments=64)
    inner = m3d.Manifold.cylinder(40, 19.6, 19.6, circular_segments=64)
    shell = outer - inner
    plane = CutPlane.from_normal(point=[0, 0, 20], normal=[0, 0, 1])
    a, b = split_solid(shell, plane)
    return a, b, plane


def test_vase_mode_uses_the_requested_size_as_given_not_shrunk(split_thin_shell):
    a, b, plane = split_thin_shell
    # sized for the real 0.4mm wall, not an ordinary connector's 8mm default
    vase_params = ConnectorParams(width=4.0, depth=0.5, tolerance=0.1)
    on_wall = 19.8  # solid from radius 19.6 to 20 -- 0.0 would be the hollow core

    result = apply_connector_instances(a, b, plane, vase_params, apply_plug, offsets=[on_wall],
                                        vase_mode=True)
    assert is_watertight(result.piece_a)
    assert is_watertight(result.piece_b)

    # the ordinary (non-vase-mode) path would shrink this same request down
    # through _FIT_FRACTIONS on a wall this thin -- vase_mode should not.
    shrunk = apply_connector_instances(a, b, plane, vase_params, apply_plug, offsets=[on_wall],
                                        vase_mode=False)
    added_vase_mode = result.piece_a.volume() - a.volume()
    added_shrunk = shrunk.piece_a.volume() - a.volume()
    assert added_vase_mode > added_shrunk, (
        "vase_mode=True should apply the connector at its full requested size, "
        "not shrunk the way the ordinary fit-search would on a wall this thin"
    )


def test_vase_mode_finds_the_wall_even_when_the_offset_hint_points_at_the_hollow_center(split_thin_shell):
    """`offsets` is only a count + rough-radius HINT for vase mode now (see
    _find_vase_connector_frames) -- real positions come from searching the
    whole seam, not from testing the literal offset value. So even a hint
    of 0.0 (this shell's hollow core, inner radius 19.6) should still find
    and use the real wall elsewhere on the seam, not give up because the
    hint itself missed."""
    a, b, plane = split_thin_shell
    vase_params = ConnectorParams(width=4.0, depth=0.5, tolerance=0.1)

    on_wall = apply_connector_instances(a, b, plane, vase_params, apply_plug, offsets=[19.8],
                                         vase_mode=True)
    assert is_watertight(on_wall.piece_a)
    assert is_watertight(on_wall.piece_b)
    assert on_wall.piece_a.volume() > a.volume(), (
        "offset 19.8 sits ON the thin wall (solid from radius 19.6 to 20) -- "
        "a real connector should have been applied"
    )

    hollow_hint = apply_connector_instances(a, b, plane, vase_params, apply_plug, offsets=[0.0],
                                             vase_mode=True)
    assert hollow_hint.piece_a.volume() > a.volume(), (
        "offset 0.0 is only a HINT (count=1, no useful radius) -- vase mode "
        "should still find the real wall by searching the seam, not fail "
        "just because the hint itself sat in the hollow core"
    )


def test_vase_mode_drops_everything_when_nothing_on_the_seam_fits_at_all(split_thin_shell):
    """A genuinely unusable request -- a probe far too big for this 0.4mm
    wall to ever pass `_is_solidly_on_material` for -- should still come
    back with no connector at all, not force one onto a position already
    proven unfit."""
    a, b, plane = split_thin_shell
    impossible_params = ConnectorParams(width=4.0, depth=40.0, tolerance=0.1)

    result = apply_connector_instances(a, b, plane, impossible_params, apply_plug, offsets=[19.8],
                                        vase_mode=True)
    assert np.isclose(result.piece_a.volume(), a.volume(), atol=1.0), (
        "a probe this large can't read 'solid' anywhere on a 0.4mm wall -- "
        "should be dropped, not applied anyway"
    )


# ---------- Snapping to the real wall on a near-miss offset ----------
# A real bug found live on the actual wave_shade_v1.stl model (a spiral-
# fluted vase): its wall isn't a clean, constant-radius ring -- evenly
# spacing offsets across the seam's vertex-bounding-box span put every
# single one of them under 1mm short of where the wall actually was at that
# angle (confirmed by scanning fill fraction radius-by-radius), so vase mode
# dropped every connector, not just a hollow-center edge case. Fixed by
# _snap_offset_to_material searching outward from each guessed offset for
# the nearest spot that's actually solid, instead of testing the guess at
# face value.

def test_snap_offset_to_material_returns_the_target_when_already_on_the_wall(split_thin_shell):
    a, b, plane = split_thin_shell
    snapped = _snap_offset_to_material(a, b, plane, target_offset=19.8, probe_radius=0.2,
                                        search_extent=5.0, step=0.1)
    assert snapped == 19.8


def test_snap_offset_to_material_finds_the_wall_when_the_guess_is_a_near_miss(split_thin_shell):
    """19.0 is a plausible bounding-box-derived guess that's actually just
    short of this shell's wall (solid only from radius 19.6 to 20) -- the
    exact shape of the real bug on wave_shade_v1.stl."""
    a, b, plane = split_thin_shell
    snapped = _snap_offset_to_material(a, b, plane, target_offset=19.0, probe_radius=0.2,
                                        search_extent=5.0, step=0.1)
    assert snapped is not None
    assert 19.5 <= snapped <= 20.0


def test_snap_offset_to_material_gives_up_past_search_extent(split_thin_shell):
    a, b, plane = split_thin_shell
    # 0.0 is the hollow core, over 19mm from the actual wall -- far outside
    # any reasonable search window, so this should stay unplaced rather than
    # wander off to the wall anyway.
    snapped = _snap_offset_to_material(a, b, plane, target_offset=0.0, probe_radius=0.2,
                                        search_extent=5.0, step=0.1)
    assert snapped is None


def test_vase_mode_snaps_a_near_miss_offset_onto_the_real_wall(split_thin_shell):
    a, b, plane = split_thin_shell
    vase_params = ConnectorParams(width=4.0, depth=0.5, tolerance=0.1)

    near_miss = apply_connector_instances(a, b, plane, vase_params, apply_plug, offsets=[19.0],
                                           vase_mode=True)
    assert is_watertight(near_miss.piece_a)
    assert is_watertight(near_miss.piece_b)
    assert near_miss.piece_a.volume() > a.volume(), (
        "offset 19.0 is a near-miss just short of the actual wall (19.6-20) -- "
        "vase mode should snap to the nearby real wall material, not drop it "
        "the way a plain positional check would"
    )
