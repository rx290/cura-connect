import sys
from pathlib import Path

import manifold3d as m3d
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cura_plugin" / "CuraConnect" / "CuraConnect"))
from core.geometry import CutPlane, split_solid, is_watertight
from core.joints_bridge import apply_printjoint, JOINT_KINDS


@pytest.fixture
def split_cube():
    cube = m3d.Manifold.cube([60, 60, 60], True)
    plane = CutPlane.from_normal(point=[0, 0, 0], normal=[0, 0, 1])
    a, b = split_solid(cube, plane)
    return a, b, plane


@pytest.mark.parametrize("kind,params", [
    ("dovetail", dict(width=8, depth=5, length=20)),
    ("snap_ring", dict(radius=10, length=8)),
    ("bayonet", dict(radius=12, length=9)),
    ("alignment_pins", dict()),
    ("t_thread", dict(major_d=30, length=10)),
])
def test_bridge_joins_pieces_across_the_seam(split_cube, kind, params):
    a, b, plane = split_cube
    result, report = apply_printjoint(a, b, plane, kind, **params)
    assert is_watertight(result.piece_a) and is_watertight(result.piece_b)
    assert (result.piece_a ^ result.piece_b).volume() < 1e-3          # fits, nothing overlaps
    assert result.piece_a.volume() > a.volume()                        # a boss was added
    assert result.piece_b.volume() < b.volume()                        # a cavity was cut
    assert report.interference_mm3 == 0


def test_bridge_rejects_unknown_kind(split_cube):
    a, b, plane = split_cube
    with pytest.raises(ValueError):
        apply_printjoint(a, b, plane, "glue")
    assert "thread" in JOINT_KINDS
