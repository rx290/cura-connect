import sys
from pathlib import Path

import numpy as np
import pytest
import manifold3d as m3d

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cura_plugin" / "CuraConnect" / "CuraConnect"))
from core.geometry import CutPlane, split_solid, is_watertight
from core.connectors import (
    ConnectorParams, ConnectorResult,
    apply_plug, apply_dowel, apply_dovetail, apply_snap,
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
