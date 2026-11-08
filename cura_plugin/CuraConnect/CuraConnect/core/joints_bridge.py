# Copyright (c) 2026, cura-connect -- MIT licensed, see the repo's LICENSE file.
"""
Thin bridge from the shared `printjoints` library (vendored in ../vendor/printjoints, same code Lamp Studio and
lamp-print-packs use) to this plugin's CutPlane / ConnectorResult world. The existing connectors in connectors.py
are untouched; this only adds more joint types: tapered dovetail, barbed snap tenon, snap hook, bayonet, snap ring,
magnet pocket, heat-set insert, pilot hole, metric thread, T3 lamp thread, alignment pins.

The pair is built with insertion along +z. piece_a is the +normal side piece (split_solid's first result), so the
male protrudes from it in the -normal direction: place(..., protrude_toward_normal=False), same rule as
connectors.py.
"""
from .geometry import CutPlane, place
from .connectors import ConnectorResult

JOINT_KINDS = ("dovetail", "barbed_snap_tenon", "cantilever_snap_hook", "bayonet", "snap_ring", "magnet_pocket",
               "heat_set_insert", "pilot_hole", "thread", "t_thread", "alignment_pins")


def _printjoints():
    import printjoints   # on sys.path via core/__init__.py's vendor dir, or an installed copy
    return printjoints


def apply_printjoint(piece_a, piece_b, plane: CutPlane, kind: str, offset=(0.0, 0.0), **params):
    """Add joint `kind` across the seam at in-plane `offset` (along plane.u, plane.v from plane.point).
    Returns (ConnectorResult, FitReport). `params` go straight to the printjoints function (material='PETG', ...)."""
    if kind not in JOINT_KINDS:
        raise ValueError(f"unknown joint {kind!r}, use one of {JOINT_KINDS}")
    pair = getattr(_printjoints(), kind)(**params)
    origin = (float(offset[0]), float(offset[1]), 0.0)
    male = place(pair.male, plane, origin, protrude_toward_normal=False)
    female = place(pair.female, plane, origin, protrude_toward_normal=False)
    return ConnectorResult(piece_a=piece_a + male, piece_b=piece_b - female), pair.report
