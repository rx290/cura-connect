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
from typing import Optional

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
