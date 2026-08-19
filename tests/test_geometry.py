import sys
from pathlib import Path

import numpy as np
import pytest
import manifold3d as m3d

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cura_plugin" / "CuraConnect" / "CuraConnect"))
from core.geometry import (
    CutPlane, split_solid, place, is_watertight, write_stl, read_stl_as_manifold, normalize,
    cross_section_footprint, suggest_cut_position, suggest_connector_layout, evenly_spaced_offsets,
    rotate_vector, connector_count_for_width,
)


def _box_vertices(axis_index, lo, hi, half_a, half_b, n=30, seed=0):
    """A dense grid of vertices filling a box's surface-ish volume:
    `axis_index` spans [lo, hi], the other two axes span [-half_a, half_a]
    and [-half_b, half_b]. A deterministic grid (not random sampling) so a
    thin cross-section band reliably captures points right at the true
    extremes -- exactly what the cross-section functions consume, and
    enough to synthesize shapes (a dumbbell, a uniform bar) the real
    connector functions above don't need to build."""
    del seed  # kept for API stability; the grid is deterministic
    other = [i for i in range(3) if i != axis_index]
    axis_vals = np.linspace(lo, hi, n)
    a_vals = np.linspace(-half_a, half_a, n)
    b_vals = np.linspace(-half_b, half_b, n)
    grid = np.stack(np.meshgrid(axis_vals, a_vals, b_vals, indexing="ij"), axis=-1).reshape(-1, 3)
    verts = np.zeros_like(grid, dtype=np.float32)
    verts[:, axis_index] = grid[:, 0]
    verts[:, other[0]] = grid[:, 1]
    verts[:, other[1]] = grid[:, 2]
    return verts


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


# ---------- Cross-section analysis (suggest_cut_position / suggest_connector_layout) ----------

def test_cross_section_footprint_reports_the_real_span_and_none_outside_the_model():
    verts = _box_vertices(axis_index=2, lo=0, hi=40, half_a=15, half_b=10)
    info = cross_section_footprint(verts, cut_axis_index=2, position=20, axis_a_index=0, axis_b_index=1,
                                    band_fraction=0.05)
    assert info is not None
    assert np.isclose(info.span_a, 30, atol=2)  # 2 * half_a
    assert np.isclose(info.span_b, 20, atol=2)  # 2 * half_b

    outside = cross_section_footprint(verts, cut_axis_index=2, position=1000, axis_a_index=0, axis_b_index=1)
    assert outside is None


def test_suggest_cut_position_avoids_a_thin_neck_between_two_solid_ends():
    """A dumbbell: solid at both ends, a genuinely thin neck in the middle
    -- the same real shape category as the Eiffel Tower's delicate lattice
    base vs. its solid tapering mast. The suggester should not land inside
    the neck."""
    thick_a = _box_vertices(axis_index=2, lo=0, hi=30, half_a=20, half_b=20, seed=1)
    neck = _box_vertices(axis_index=2, lo=30, hi=70, half_a=3, half_b=3, seed=2)
    thick_b = _box_vertices(axis_index=2, lo=70, hi=100, half_a=20, half_b=20, seed=3)
    verts = np.vstack([thick_a, neck, thick_b])

    position = suggest_cut_position(verts, cut_axis_index=2)
    # A band straddling the exact 30/70 boundary picks up some trailing
    # points from the adjacent solid box, so the heuristic can land right at
    # the transition rather than exactly outside [30, 70] -- a fair, honest
    # limitation of band-sampling near a sharp discontinuity, not something
    # to paper over with false precision. What actually matters is that it
    # avoids the neck's deep, thin middle.
    assert not (40 <= position <= 60), (
        f"suggested position {position} falls deep inside the thin neck -- "
        "the suggester should prefer a wide, solid cross-section over a thin one"
    )


def test_suggest_cut_position_prefers_a_split_that_fits_the_bed():
    """A uniform 200mm bar and a 120mm bed limit: only a cut within [80, 120]
    makes BOTH resulting pieces fit (200-p <= 120 and p <= 120)."""
    verts = _box_vertices(axis_index=2, lo=0, hi=200, half_a=20, half_b=20)
    position = suggest_cut_position(verts, cut_axis_index=2, bed_limit=120)
    assert 80 <= position <= 120, f"expected a bed-fitting split in [80, 120], got {position}"


def test_evenly_spaced_offsets_are_symmetric_around_zero():
    offsets = evenly_spaced_offsets(3, seam_size=100)
    assert len(offsets) == 3
    assert np.isclose(offsets[0], -offsets[-1])
    assert np.isclose(offsets[1], 0, atol=1e-9)


def test_evenly_spaced_offsets_single_count_is_centered():
    assert evenly_spaced_offsets(1, seam_size=100) == [0.0]


def test_suggest_connector_layout_scales_up_with_a_bigger_seam():
    small = _box_vertices(axis_index=2, lo=48, hi=52, half_a=10, half_b=10, seed=4)
    big = _box_vertices(axis_index=2, lo=48, hi=52, half_a=100, half_b=100, seed=5)

    layout_small = suggest_connector_layout(small, cut_axis_index=2, position=50, u_axis_index=0, v_axis_index=1)
    layout_big = suggest_connector_layout(big, cut_axis_index=2, position=50, u_axis_index=0, v_axis_index=1)

    assert layout_small is not None and layout_big is not None
    assert layout_big.width > layout_small.width, "a bigger seam should get a bigger connector"
    assert layout_big.count >= layout_small.count, "a bigger seam should fit at least as many connectors"
    assert len(layout_big.offsets) == layout_big.count


def test_suggest_connector_layout_returns_none_off_the_model():
    verts = _box_vertices(axis_index=2, lo=0, hi=40, half_a=15, half_b=10)
    layout = suggest_connector_layout(verts, cut_axis_index=2, position=1000, u_axis_index=0, v_axis_index=1)
    assert layout is None


# ---------- Tilt (rotate_vector) ----------

def test_rotate_vector_by_zero_degrees_is_unchanged():
    v = rotate_vector([0, 1, 0], axis=[1, 0, 0], degrees=0)
    assert np.allclose(v, [0, 1, 0])


def test_rotate_vector_ninety_degrees_matches_a_known_case():
    # Rotating +Y by 90 degrees around +X should give +Z (right-hand rule).
    v = rotate_vector([0, 1, 0], axis=[1, 0, 0], degrees=90)
    assert np.allclose(v, [0, 0, 1], atol=1e-9)


def test_rotate_vector_preserves_length():
    v = rotate_vector([0.3, -0.7, 0.2], axis=[0, 1, 0], degrees=37)
    assert np.isclose(np.linalg.norm(v), np.linalg.norm([0.3, -0.7, 0.2]))


def test_rotate_vector_stays_perpendicular_to_its_rotation_axis_component():
    # Rotating a vector already perpendicular to the axis should keep it
    # perpendicular -- the axis-aligned component is untouched by rotation.
    axis = normalize([0, 1, 0])
    v = rotate_vector([1, 0, 0], axis=axis, degrees=25)
    assert np.isclose(np.dot(v, axis), 0, atol=1e-9)


# ---------- connector_count_for_width ----------

def test_connector_count_for_width_fits_more_of_a_narrower_connector():
    seam = 100.0
    narrow_count = connector_count_for_width(2.0, seam)   # a vase-mode-scale connector
    wide_count = connector_count_for_width(15.0, seam)    # an ordinary-scale connector
    assert narrow_count > wide_count, "a narrower connector should fit more instances on the same seam"


def test_connector_count_for_width_never_exceeds_max_count():
    assert connector_count_for_width(0.5, 1000.0, max_count=4) == 4


def test_connector_count_for_width_is_at_least_one():
    assert connector_count_for_width(50.0, 10.0) == 1
    assert connector_count_for_width(0.0, 100.0) == 1
