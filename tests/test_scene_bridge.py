import sys
from pathlib import Path

import numpy as np
import manifold3d as m3d

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cura_plugin" / "CuraConnect" / "CuraConnect"))
from core.geometry import is_watertight
from core.scene_bridge import cura_vertices_to_manifold, manifold_to_cura_vertices


def _hand_built_cube_flat_vertices(size=10.0):
    """A flat, unindexed triangle-soup array built by hand (not derived from
    manifold3d at all), matching exactly what Uranium's MeshData.getVertices()
    returns for a simple cube with no shared-vertex index buffer -- 12
    triangles x 3 corners = 36 rows, each triangle's 3 vertices listed in full
    even though adjacent triangles share corners."""
    s = size / 2
    corners = {
        "000": (-s, -s, -s), "100": (s, -s, -s), "110": (s, s, -s), "010": (-s, s, -s),
        "001": (-s, -s, s), "101": (s, -s, s), "111": (s, s, s), "011": (-s, s, s),
    }
    # Wound counter-clockwise as seen from outside each face (the standard
    # STL/right-hand-rule convention) -- an earlier version of this fixture
    # had every face wound backward, which manifold3d correctly caught as a
    # negative-volume (inside-out) manifold rather than silently accepting it.
    faces = [
        ("000", "010", "110"), ("000", "110", "100"),  # bottom (outward = -Z)
        ("001", "101", "111"), ("001", "111", "011"),  # top (outward = +Z)
        ("000", "100", "101"), ("000", "101", "001"),  # front (outward = -Y)
        ("010", "011", "111"), ("010", "111", "110"),  # back (outward = +Y)
        ("000", "001", "011"), ("000", "011", "010"),  # left (outward = -X)
        ("100", "110", "111"), ("100", "111", "101"),  # right (outward = +X)
    ]
    rows = []
    for tri in faces:
        for corner in tri:
            rows.append(corners[corner])
    return np.array(rows, dtype=np.float32)


def test_hand_built_flat_cube_converts_to_a_watertight_manifold_with_correct_volume():
    flat = _hand_built_cube_flat_vertices(size=10.0)
    assert flat.shape == (36, 3)

    manifold = cura_vertices_to_manifold(flat)
    assert is_watertight(manifold)
    assert np.isclose(manifold.volume(), 1000.0, rtol=1e-4)


def test_manifold_to_cura_vertices_roundtrips_through_cura_vertices_to_manifold():
    original = m3d.Manifold.cube([15, 15, 15], True)
    flat = manifold_to_cura_vertices(original)

    # Real Cura mesh: 12 triangles x 3 rows for a cube, no shared indices.
    assert flat.shape[0] % 3 == 0
    assert flat.shape[1] == 3

    reconstructed = cura_vertices_to_manifold(flat)
    assert is_watertight(reconstructed)
    assert np.isclose(reconstructed.volume(), original.volume(), rtol=1e-4)


def test_cura_vertices_to_manifold_corrects_inverted_winding_from_a_mirrored_model():
    """A model mirrored via Cura's own Mirror tool (or a mirrored import)
    has every triangle wound backward -- still watertight, but with a
    negative volume. This must self-correct rather than silently produce
    inside-out connector geometry against a mirrored model."""
    normal_flat = _hand_built_cube_flat_vertices(size=12.0)
    inverted_flat = normal_flat[:, :].copy()
    # reverse each triangle's winding (swap the 2nd and 3rd corner of every
    # 3-row group) without touching the coordinates themselves
    inverted_flat = inverted_flat.reshape(-1, 3, 3)[:, [0, 2, 1], :].reshape(-1, 3)

    manifold = cura_vertices_to_manifold(inverted_flat)
    assert is_watertight(manifold)
    assert manifold.volume() > 0, "should self-correct to a positive volume, not silently stay inside-out"
    assert np.isclose(manifold.volume(), 1728.0, rtol=1e-4)  # 12^3


def test_cura_vertices_to_manifold_rejects_a_non_multiple_of_3():
    import pytest
    bad = np.zeros((10, 3), dtype=np.float32)
    with pytest.raises(ValueError):
        cura_vertices_to_manifold(bad)


def test_full_roundtrip_through_a_real_connector_preserves_expected_geometry():
    """The actual pipeline CuraConnectTool.py will run: real-Cura-shaped flat
    vertices in -> manifold -> split+connector -> flat vertices back out."""
    from core.geometry import CutPlane, split_solid
    from core.connectors import ConnectorParams, apply_plug

    flat = _hand_built_cube_flat_vertices(size=40.0)
    solid = cura_vertices_to_manifold(flat)

    plane = CutPlane.from_normal(point=[0, 0, 0], normal=[0, 0, 1])
    a, b = split_solid(solid, plane)
    result = apply_plug(a, b, plane, ConnectorParams(width=8, depth=6, tolerance=0.15))

    out_a = manifold_to_cura_vertices(result.piece_a)
    out_b = manifold_to_cura_vertices(result.piece_b)
    assert out_a.shape[0] % 3 == 0
    assert out_b.shape[0] % 3 == 0

    # Re-import both outputs and confirm they still fit together as they did
    # before leaving the manifold representation -- proves nothing was lost
    # or corrupted crossing the Cura <-> manifold boundary twice.
    reimported_a = cura_vertices_to_manifold(out_a)
    reimported_b = cura_vertices_to_manifold(out_b)
    assert is_watertight(reimported_a)
    assert is_watertight(reimported_b)
    overlap = reimported_a ^ reimported_b
    assert overlap.volume() < 1e-3
