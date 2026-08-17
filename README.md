# cura-connect

A Cura plugin that splits a 3D model into printable pieces joined by real mechanical connectors — Plug, Dowel, Snap, or Dovetail — so the pieces reassemble precisely. The same four connector modes as OrcaSlicer/PrusaSlicer's built-in Cut Tool, built from scratch for Cura, which has no native equivalent.

## Why this exists

OrcaSlicer and PrusaSlicer have no public plugin API for adding custom UI or tools — confirmed directly from an OrcaSlicer maintainer discussion ([#9960](https://github.com/OrcaSlicer/OrcaSlicer/discussions/9960)), not assumed. Their Cut Tool's four connector modes (Plug, Dowel, Snap, Dovetail — confirmed against [Prusa's own Cut Tool documentation](https://help.prusa3d.com/article/cut-tool_1779)) are built into the app itself, not a plugin. Cura has a real plugin SDK but no built-in cut/connector tool at all — this project builds that missing piece.

Two existing Cura plugins do mesh splitting ([banana-split](https://github.com/jarrrgh/banana-split), a pseudo-split via duplicate-and-mirror, and [Cura-MeshTools](https://github.com/fieldOfView/Cura-MeshTools), which separates already-disconnected bodies) — neither generates connector geometry. This is genuinely new ground, not a reimplementation.

## Status: Phase 1 (headless geometry engine) complete, Phase 2 (Cura UI) not started

Following the same phased approach as [PolyForge](https://github.com/rx290/polyforge) and Lumeforge: build and fully verify the core engine standalone first, then wire it into the actual interactive Cura tool once the geometry is proven correct — a GUI's feel needs real eyes on it, but the underlying geometry can and should be proven with automated tests before that.

**What's built and tested (Phase 1):**
- `core/geometry.py` — plane-split and shape-placement math on top of [manifold3d](https://github.com/elalish/manifold), which guarantees watertight boolean results (its `.status()` reports a real error code rather than silently producing broken geometry).
- `core/connectors.py` — all four connector types: Plug, Dowel, Snap, Dovetail.
- 24 tests, including differential proofs, not just isolated checks: a dedicated test shows the Dovetail piece genuinely resists being pulled straight apart along the cut normal (real interference), while the Plug piece — checked the same way — slides free with zero interference. That contrast is the actual proof the dovetail's flare is mechanically doing something, not just cosmetically different.
- `demo.py` exports real STL files for all four connector types from a plain test cube, for opening in any viewer.

**What's not built yet (Phase 2):** the actual interactive Cura Tool — picking a cut plane on the real model in the 3D view, a settings panel for connector type/width/depth/tolerance, and wiring `core/connectors.py` into Cura's Uranium `Tool` plugin type and Scene/Operations system. Cura's own Tool plugin API exists and is documented (`TranslateTool`/`MirrorTool` are built on it) but the precise mesh-boolean integration points need to be worked out against Cura's real Scene graph, which is a GUI-facing job better done with the model owner watching, not guessed at.

## The four connectors

| Type | How it works | Assembly |
|---|---|---|
| **Plug** | A boss on one piece, a matching oversized cavity on the other | Press straight together |
| **Dowel** | A hole in both pieces plus a separate loose printable pin | Insert the pin, then press together |
| **Snap** | A peg with a bulbous tip into a socket with a narrower throat | Push past the throat (needs real material flex — see the honesty note below) |
| **Dovetail** | A trapezoidal tail, narrow at the seam and wider at depth | Slide along the joint's length — cannot be pulled straight apart |

**Honest limitation on Snap:** this project follows the same rule Lumeforge already established — don't fake a flex-dependent joint's real-world behavior. The Snap connector's automated tests can prove the *locked* state is collision-free and that the throat is genuinely narrower than the bulb (so it isn't a snap in name only), but they cannot simulate whether your actual filament/wall thickness will flex enough to assemble it. That depends on your printer and material, not on this geometry alone.

## Requirements

```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Running the tests

```
.venv/bin/python -m pytest tests/ -v
```

## Trying it now (before Phase 2's Cura UI exists)

```
.venv/bin/python demo.py
```

Exports `plug_piece_a.stl`/`plug_piece_b.stl` (and equivalents for the other three types, plus `dowel_loose_pin.stl`) into `demo_output/`. Each pair shares world coordinates, so opening both files together in the same viewer shows them already assembled.
