#!/usr/bin/env python3
"""
Exports real STL files for all four connector types, cutting a plain 40mm
test cube, so you can open them in OpenSCAD/Cura/any viewer and actually see
(and print, if you want) each connector fitted together -- not just trust
the automated collision tests.

Usage: .venv/bin/python demo.py [output_dir]
"""
import sys
from pathlib import Path

import manifold3d as m3d

sys.path.insert(0, str(Path(__file__).resolve().parent / "cura_plugin" / "CuraConnect" / "CuraConnect"))
from core.geometry import CutPlane, split_solid, write_stl
from core.connectors import ConnectorParams, apply_plug, apply_dowel, apply_dovetail, apply_snap

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "demo_output")
OUT.mkdir(exist_ok=True)

CUBE_SIZE = 40.0
params = ConnectorParams(width=8.0, depth=6.0, tolerance=0.15)


def make_split():
    cube = m3d.Manifold.cube([CUBE_SIZE] * 3, True)
    plane = CutPlane.from_normal(point=[0, 0, 0], normal=[0, 0, 1])
    return split_solid(cube, plane), plane


connectors = {
    "plug": apply_plug,
    "dowel": apply_dowel,
    "dovetail": apply_dovetail,
    "snap": apply_snap,
}

for name, fn in connectors.items():
    (a, b), plane = make_split()
    result = fn(a, b, plane, params)
    write_stl(result.piece_a, str(OUT / f"{name}_piece_a.stl"))
    write_stl(result.piece_b, str(OUT / f"{name}_piece_b.stl"))
    if result.loose_piece is not None:
        write_stl(result.loose_piece, str(OUT / f"{name}_loose_pin.stl"))
    print(f"{name}: wrote {OUT}/{name}_piece_a.stl, {name}_piece_b.stl"
          + (f", {name}_loose_pin.stl" if result.loose_piece is not None else ""))

print(f"\nAll files in {OUT.resolve()} -- open {name}_piece_a.stl and {name}_piece_b.stl "
      "together in the same viewer (they share world coordinates, so they'll appear "
      "already assembled) to see each connector fitted.")
