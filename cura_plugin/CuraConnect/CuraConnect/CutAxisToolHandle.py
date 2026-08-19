"""
A visual X/Y/Z axis picker AND drag handle, replacing a text dropdown with
the same clicked-and-dragged handle convention Cura's own Move tool uses:
three arrows (a line plus a pyramid tip, exactly TranslateToolHandle.py's
own shape) near the selection, colored with the same theme colors as that
tool (x_axis/y_axis/z_axis) so it reads as the same visual language.
Clicking an arrow switches the cut axis; dragging it nudges the cut plane
along that axis -- the actual drag math (camera-facing drag plane, ray
intersection, per-axis delta) lives in CuraConnectTool.event(), reusing
UM.Tool's own getDragPlane/getDragVector exactly as TranslateTool.py does.
Read that file directly before writing this.

Also carries a single tilt ring -- a donut (MeshBuilder.addDonut, the same
primitive RotateToolHandle.py uses for its three rotation rings), sized to
sit clearly outside the cut-plane indicator so it's easy to grab, and
colored to match the CURRENT CUT AXIS (X/Y/Z, same red/blue/green as the
panel's legend) rather than the tilt's own geometric rotation axis -- that
axis is structurally always Z or Y (never X, see _RING_ORIENTATION), so
coloring by it would mean the ring could never show red at all. Only one
ring, not three: this plugin supports a single tilt DOF on top of the
axis-aligned suggested position, not free 3D rotation -- see
CuraConnectTool.py's module docstring for why that's the deliberate scope.
The drag-around-the-ring math (angle between drag_start and drag_end
relative to the ring's center, direction via cross-product sign) is read
directly from RotateTool.py's own event() before being adapted here.

Deliberately reuses UM.Scene.ToolHandle wholesale -- it already auto-scales
for consistent on-screen size, and (via the base UM.Tool class already
wiring self._handle) shows/hides itself on ToolActivateEvent/
ToolDeactivateEvent and highlights the hovered axis for free. Position is
NOT left to ToolHandle's own Selection-center auto-tracking, though --
CuraConnectTool repositions this handle to the cut plane's own center
every time the plane moves, since that (not the object's static center) is
what this gizmo actually manipulates. Only buildMesh() is new.
"""
import math
from enum import IntEnum

from UM.Math.Vector import Vector
from UM.Mesh.MeshBuilder import MeshBuilder
from UM.Scene.ToolHandle import ToolHandle

# cut_axis -> (letter of the tilt rotation axis v, donut build axis, donut build angle in degrees)
# -- the (axis, angle) pair rotates addDonut's default Y-normal ring to lie
# flat in the plane perpendicular to v; see core/geometry.py's _INDICATOR_AXES
# for why v is Z for an X or Y cut, and Y for a Z cut.
_RING_ORIENTATION = {
    "X": ("Z", Vector.Unit_X, 90.0),
    "Y": ("Z", Vector.Unit_X, 90.0),
    "Z": ("Y", Vector.Unit_Y, 0.0),
}


class CutAxisToolHandle(ToolHandle):
    class ExtraWidgets(IntEnum):
        TiltRing = ToolHandle.AllAxis + 1

    def __init__(self, parent=None):
        super().__init__(parent)
        self._name = "CutAxisToolHandle"
        self._line_width = 0.6
        self._handle_height = 8
        self._handle_width = 4
        self._handle_position = 30
        self._line_length = 30

        self._ring_color_letter = "Y"  # colored by the CUT axis (matches the panel's legend), not the tilt's rotation axis
        self._ring_axis = Vector.Unit_X
        self._ring_angle = 90.0
        self._ring_radius = 40.0
        self._ring_width = 0.8
        self._ring_selection_width = 6.0

    def setReach(self, model_half_extent: float) -> None:
        """Set how far the arrows extend from the selection center, given
        the model's own largest half-extent. A fixed reach (the original
        30mm) silently sat INSIDE a model bigger than ~60mm across -- the
        arrow was still positioned at the right 3D coordinate, but that
        coordinate was behind the model's own opaque surface from the
        camera's point of view, so the (correctly depth-tested) selection
        pass always favored the model over the handle. A click that visually
        looked like it hit the arrow silently picked the model instead --
        found by logging the real getIdAtPosition() result during live
        testing, not guessed. Reach now always clears the model with margin,
        so the arrows are unambiguously outside its silhouette."""
        position = max(model_half_extent * 1.4, 15.0)
        if position != self._handle_position:
            self._handle_position = position
            self._line_length = position
            self.buildMesh()

    def setRing(self, cut_axis: str, plane_half_size: float) -> None:
        """Configure the tilt ring for the current cut axis and size it to
        sit clearly outside the cut-plane indicator, per the explicit ask:
        wide enough that it's never confused with, or overlapped by, the
        plane itself. Colored by `cut_axis` itself (matching the bold
        letter + colored squares already shown in the panel) rather than
        the tilt's geometric rotation axis -- the rotation axis (see
        _RING_ORIENTATION) is structurally always Z or Y, never X, so
        coloring by IT would mean the ring could never actually show red;
        coloring by the active cut axis means red/blue/green are all real,
        reachable states, and the color directly answers "which axis is
        this rotating the cut plane on top of" the way the legend already
        does for position."""
        _letter, axis, angle = _RING_ORIENTATION[cut_axis]
        radius = max(plane_half_size * 1.3, self._handle_position * 1.1, 20.0)
        if cut_axis == self._ring_color_letter and axis is self._ring_axis \
                and angle == self._ring_angle and radius == self._ring_radius:
            return
        self._ring_color_letter = cut_axis
        self._ring_axis = axis
        self._ring_angle = angle
        self._ring_radius = radius
        self.buildMesh()

    def getRingRadius(self) -> float:
        return self._ring_radius

    def buildMesh(self) -> None:
        ring_color = {"X": self._x_axis_color, "Y": self._y_axis_color, "Z": self._z_axis_color}[
            self._ring_color_letter
        ]

        mb = MeshBuilder()
        mb.addCube(width=self._line_length, height=self._line_width, depth=self._line_width,
                   center=Vector(self._handle_position / 2, 0, 0), color=self._x_axis_color)
        mb.addCube(width=self._line_width, height=self._line_length, depth=self._line_width,
                   center=Vector(0, self._handle_position / 2, 0), color=self._y_axis_color)
        mb.addCube(width=self._line_width, height=self._line_width, depth=self._line_length,
                   center=Vector(0, 0, self._handle_position / 2), color=self._z_axis_color)

        mb.addPyramid(width=self._handle_width, height=self._handle_height, depth=self._handle_width,
                      center=Vector(self._handle_position, 0, 0),
                      color=self._x_axis_color, axis=Vector.Unit_Z, angle=90)
        mb.addPyramid(width=self._handle_width, height=self._handle_height, depth=self._handle_width,
                      center=Vector(0, self._handle_position, 0), color=self._y_axis_color)
        mb.addPyramid(width=self._handle_width, height=self._handle_height, depth=self._handle_width,
                      center=Vector(0, 0, self._handle_position),
                      color=self._z_axis_color, axis=Vector.Unit_X, angle=-90)

        mb.addDonut(inner_radius=self._ring_radius, outer_radius=self._ring_radius + self._ring_width,
                    width=self._ring_width, axis=self._ring_axis, angle=math.radians(self._ring_angle),
                    color=ring_color)
        self.setSolidMesh(mb.build())

        mb = MeshBuilder()
        mb.addCube(width=self._line_length, height=self._handle_width, depth=self._handle_width,
                   center=Vector(self._handle_position / 2, 0, 0), color=ToolHandle.XAxisSelectionColor)
        mb.addCube(width=self._handle_width, height=self._line_length, depth=self._handle_width,
                   center=Vector(0, self._handle_position / 2, 0), color=ToolHandle.YAxisSelectionColor)
        mb.addCube(width=self._handle_width, height=self._handle_width, depth=self._line_length,
                   center=Vector(0, 0, self._handle_position / 2), color=ToolHandle.ZAxisSelectionColor)

        mb.addDonut(inner_radius=self._ring_radius, outer_radius=self._ring_radius + self._ring_selection_width,
                    width=self._ring_selection_width, axis=self._ring_axis, angle=math.radians(self._ring_angle),
                    color=self._extra_widgets_color_map[self.ExtraWidgets.TiltRing.value])
        self.setSelectionMesh(mb.build())
