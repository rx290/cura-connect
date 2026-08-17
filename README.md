# cura-connect

A Cura plugin that splits a 3D model into printable pieces joined by real mechanical connectors — Plug, Dowel, Snap, or Dovetail — so the pieces reassemble precisely. The same four connector modes as OrcaSlicer/PrusaSlicer's built-in Cut Tool, built from scratch for Cura, which has no native equivalent.

## Why this exists

OrcaSlicer and PrusaSlicer have no public plugin API for adding custom UI or tools — confirmed directly from an OrcaSlicer maintainer discussion ([#9960](https://github.com/OrcaSlicer/OrcaSlicer/discussions/9960)), not assumed. Their Cut Tool's four connector modes (Plug, Dowel, Snap, Dovetail — confirmed against [Prusa's own Cut Tool documentation](https://help.prusa3d.com/article/cut-tool_1779)) are built into the app itself, not a plugin. Cura has a real plugin SDK but no built-in cut/connector tool at all — this project builds that missing piece.

Two existing Cura plugins do mesh splitting ([banana-split](https://github.com/jarrrgh/banana-split), a pseudo-split via duplicate-and-mirror, and [Cura-MeshTools](https://github.com/fieldOfView/Cura-MeshTools), which separates already-disconnected bodies) — neither generates connector geometry. This is genuinely new ground, not a reimplementation.

## Status: both phases built and verified against a real Cura install

Followed the same phased approach as [PolyForge](https://github.com/rx290/polyforge) and Lumeforge: build and fully verify the core engine standalone first, then wire it into the actual interactive Cura tool.

**Phase 1 — headless geometry engine:**
- `cura_plugin/CuraConnect/CuraConnect/core/geometry.py` — plane-split and shape-placement math on top of [manifold3d](https://github.com/elalish/manifold), which guarantees watertight boolean results (its `.status()` reports a real error code rather than silently producing broken geometry).
- `core/connectors.py` — all four connector types: Plug, Dowel, Snap, Dovetail.
- `core/scene_bridge.py` — converts between Cura's raw (unindexed, flat) mesh vertex arrays and manifold3d's indexed representation, including auto-correcting inverted winding order from a mirrored model.
- 29 tests, including differential proofs, not just isolated checks: a dedicated test shows the Dovetail piece genuinely resists being pulled straight apart along the cut normal (real interference), while the Plug piece — checked the same way — slides free with zero interference. Numerically confirmed the dovetail tail is 8.00mm wide at the seam and flares to 12.80mm at depth (exactly matching the configured flare), not just eyeballed from a render.
- `demo.py` exports real STL files for all four connector types from a plain test cube, for opening in any viewer.

**Phase 2 — the real interactive Cura Tool:** `CuraConnectTool.py` (a Uranium `Tool` subclass) plus `CuraConnectPanel.qml` (connector type, cut axis, width/depth/tolerance). Click on a selected model with the tool active to split it at that point, along a chosen world axis, with the connector geometry applied automatically — replacing the one selected node with two new ones (three for Dowel, including the loose pin), using `AddSceneNodeOperation`/`RemoveSceneNodeOperation` in a single undoable `GroupedOperation`, the same real pattern Cura's own bundled `SupportEraser` plugin uses.

v1 scope, deliberately: the cut plane is always perpendicular to a world X/Y/Z axis, not a freely-rotatable 3D gizmo like PrusaSlicer/OrcaSlicer's own Cut Tool. That covers the common case (splitting a tall model horizontally, or a wide one vertically) without the much larger undertaking of a custom 3D interaction gizmo — a real, separate follow-up, not attempted here.

**A real deployment wrinkle, solved, not glossed over:** Cura ships its own frozen Python (3.12 as of Cura 5.13), isolated from any system Python — `manifold3d` isn't among Cura's bundled packages, and there's no clean way to install into an AppImage-style bundle without root, nor does its AppRun launcher reliably pass through an external `PYTHONPATH`. Solved by vendoring the one compiled dependency (`manifold3d`) plus its pure-Python chain (`numpy-stl`, `python-utils`, `typing-extensions`) directly inside `cura_plugin/CuraConnect/CuraConnect/vendor/` — which Cura's own `PluginRegistry` already puts on `sys.path` when it loads the plugin, so no system files were touched and no environment variable had to survive the AppImage wrapper.

**Verified end-to-end in a real Cura 5.13 install, not just unit-tested:** confirmed the plugin loads with zero import errors, confirmed the tool panel renders and its exposed properties (`ConnectorType`, `CutAxis`, `Width`, `Depth`, `Tolerance`) bind correctly, and actually performed a live dovetail cut on a real loaded model — the single `cura_test_cube.stl` object was replaced with `cura_test_cube.stl_A` and `cura_test_cube.stl_B`, both visually showing distinct connector geometry at the seam, with zero tracebacks referencing any of this project's files in Cura's own log.

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

## Installing the real Cura plugin

Copy `cura_plugin/CuraConnect/CuraConnect/` into your Cura plugins folder (Help → Show Configuration Folder → `plugins/CuraConnect/CuraConnect/`), restart Cura, and look for the tool at the bottom of the left toolbar (a chain-link icon, shortcut `J`). Select a model, activate the tool, pick your connector settings, and click on the model to cut it.

## Trying the headless engine directly (no Cura install needed)

```
.venv/bin/python demo.py
```

Exports `plug_piece_a.stl`/`plug_piece_b.stl` (and equivalents for the other three types, plus `dowel_loose_pin.stl`) into `demo_output/`. Each pair shares world coordinates, so opening both files together in the same viewer shows them already assembled.
