import sys
from pathlib import Path

import numpy as np
import pytest
import manifold3d as m3d

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cura_plugin" / "CuraConnect" / "CuraConnect"))
from core.geometry import CutPlane, split_solid, place, is_watertight, write_stl, read_stl_as_manifold, normalize


def test_normalize_rejects_near_zero_vector():
    with pytest.raises(ValueError):
        normalize([0, 0, 1e-12])


def test_normalize_returns_unit_length():
    v = normalize([3, 4, 0])
    assert np.isclose(np.linalg.norm(v), 1.0)


def test_cut_plane_axes_are_orthonormal_for_arbitrary_normal():
    for normal in ([0, 0, 1], [1, 1, 1], [0.3, -0.7, 0.2]):
        plane = CutPlane.from_normal(point=[0, 0, 0], normal=normal)
        assert np.isclose(np.dot(plane.u, plane.v), 0, atol=1e-9)
        assert np.isclose(np.dot(plane.u, plane.normal), 0, atol=1e-9)
        assert np.isclose(np.dot(plane.v, plane.normal), 0, atol=1e-9)
        assert np.isclose(np.linalg.norm(plane.u), 1.0)
        assert np.isclose(np.linalg.norm(plane.v), 1.0)


def test_split_solid_at_center_gives_equal_halves():
    cube = m3d.Manifold.cube([20, 20, 20], True)
    plane = CutPlane.from_normal(point=[0, 0, 0], normal=[0, 0, 1])
    a, b = split_solid(cube, plane)
    assert np.isclose(a.volume(), b.volume(), rtol=1e-6)
    assert np.isclose(a.volume() + b.volume(), cube.volume(), rtol=1e-6)


def test_split_solid_off_center_gives_unequal_halves_in_the_right_ratio():
    cube = m3d.Manifold.cube([20, 20, 20], True)  # spans -10..10 on each axis
    plane = CutPlane.from_normal(point=[0, 0, 5], normal=[0, 0, 1])
    a, b = split_solid(cube, plane)
    # a is the +normal side: z in [5, 10] -> a fifth of the 20mm height = 5mm
    # of a 20x20 cross-section = 2000; b is the rest = 6000
    assert np.isclose(a.volume(), 2000.0, rtol=1e-3)
    assert np.isclose(b.volume(), 6000.0, rtol=1e-3)


def test_split_solid_works_for_an_arbitrary_non_axis_aligned_plane():
    cube = m3d.Manifold.cube([20, 20, 20], True)
    plane = CutPlane.from_normal(point=[0, 0, 0], normal=[1, 1, 1])
    a, b = split_solid(cube, plane)
    assert np.isclose(a.volume() + b.volume(), cube.volume(), rtol=1e-6)
    assert is_watertight(a)
    assert is_watertight(b)


def test_place_protrude_toward_normal_false_bridges_into_the_opposite_half():
    """Regression test for the exact placement-direction bug caught during
    development: a boss meant to protrude from the +normal piece across the
    seam must end up occupying space on the -normal side."""
    cube = m3d.Manifold.cube([20, 20, 20], True)
    plane = CutPlane.from_normal(point=[0, 0, 0], normal=[0, 0, 1])
    a, b = split_solid(cube, plane)

    boss_local = m3d.Manifold.cube([5, 5, 5], True).translate([0, 0, 2.5])
    boss_world = place(boss_local, plane, protrude_toward_normal=False)

    combined = a + boss_world
    assert np.isclose(combined.volume() - a.volume(), 125.0, atol=0.5)
    overlap_with_b_region = combined ^ b
    assert np.isclose(overlap_with_b_region.volume(), 125.0, atol=0.5), (
        "the boss should poke into the space piece b occupies, proving it "
        "actually bridges the seam rather than sitting inside its own piece"
    )


def test_place_protrude_toward_normal_true_stays_on_the_normal_side():
    """The opposite flag value should keep the boss on the +normal side
    instead -- confirms the flag genuinely controls direction both ways,
    not just that False happens to work."""
    cube = m3d.Manifold.cube([20, 20, 20], True)
    plane = CutPlane.from_normal(point=[0, 0, 0], normal=[0, 0, 1])
    a, b = split_solid(cube, plane)

    boss_local = m3d.Manifold.cube([5, 5, 5], True).translate([0, 0, 2.5])
    boss_world = place(boss_local, plane, protrude_toward_normal=True)

    overlap_with_b_region = boss_world ^ b
    assert overlap_with_b_region.volume() < 1e-6, (
        "protrude_toward_normal=True should keep the boss entirely on the "
        "+normal side, with no overlap into b's region at all"
    )


def test_stl_roundtrip_preserves_volume(tmp_path):
    original = m3d.Manifold.cube([10, 10, 10])
    stl_path = str(tmp_path / "cube.stl")
    write_stl(original, stl_path)
    reloaded = read_stl_as_manifold(stl_path)
    assert np.isclose(reloaded.volume(), original.volume(), rtol=1e-4)
    assert is_watertight(reloaded)
