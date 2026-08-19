# Copyright (c) 2026, cura-connect -- MIT licensed, see the repo's LICENSE file.
"""
The interactive Cura Tool (Phase 2). With this tool active, click (or
click-drag) on a selected model to position a preview cut plane, adjust its
position/size, then press Cut to split the model at that plane, with the
connector geometry from core/connectors.py applied automatically.

v1 scope, deliberately: the cut plane is always perpendicular to one of the
X/Y/Z world axes (chosen in the tool panel) -- not a freely-rotatable 3D
gizmo like PrusaSlicer/OrcaSlicer's own Cut Tool. That's a real, useful scope
(splitting a tall model horizontally, or a wide one vertically, covers the
common case), not the full feature set -- extending to a free-rotation gizmo
is real, separate follow-up work, not attempted here.

Axis convention, confirmed by reading Cura's own STL reader
(share/uranium/plugins/FileHandlers/STLReader/STLReader.py, which swaps
columns 1/2 on import) and cura/BuildVolume.py (which treats bounding-box
`.top`/`.bottom`, i.e. world Y, as the vertical/printable-height axis): Cura's
live scene graph is Y-up, not Z-up. So the default cut axis for "split a tall
model into a top and bottom half" is Y, not Z -- Z is the horizontal
front/back (depth) axis in world space. The original v1 shipped with a
default of "Z", which actually split front/back rather than top/bottom; that
default is corrected here to "Y" as part of adding the movable plane.

Follows the exact real pattern Cura's own bundled SupportEraser plugin uses
for creating new scene nodes at runtime (picking_selected render pass,
GroupedOperation of Add/Remove SceneNodeOperations, BuildPlateDecorator +
SliceableObjectDecorator on every new node) -- read directly from the
installed Cura 5.13 source before writing this, not guessed.
"""
import math
from typing import Optional

import numpy as np
from PyQt6.QtCore import Qt

from UM.Application import Application
from UM.Event import Event, MouseEvent
from UM.Logger import Logger
from UM.Math.Plane import Plane
from UM.Math.Vector import Vector
from UM.Mesh.MeshBuilder import MeshBuilder
from UM.Operations.AddSceneNodeOperation import AddSceneNodeOperation
from UM.Operations.GroupedOperation import GroupedOperation
from UM.Operations.RemoveSceneNodeOperation import RemoveSceneNodeOperation
from UM.Scene.Selection import Selection
from UM.Scene.ToolHandle import ToolHandle
from UM.Tool import Tool

from cura.CuraApplication import CuraApplication
from cura.Scene.CuraSceneNode import CuraSceneNode
from cura.Scene.SliceableObjectDecorator import SliceableObjectDecorator
from cura.Scene.BuildPlateDecorator import BuildPlateDecorator

from .core.geometry import (
    CutPlane, split_solid, suggest_cut_position, suggest_connector_layout, evenly_spaced_offsets,
    rotate_vector,
)
from .core.connectors import (
    ConnectorParams, apply_plug, apply_dowel, apply_dovetail, apply_snap, apply_connector_instances,
)
from .core.scene_bridge import cura_vertices_to_manifold, manifold_to_cura_vertices
from .CutPlaneIndicator import CutPlaneIndicator
from .CutAxisToolHandle import CutAxisToolHandle

_CONNECTOR_FUNCTIONS = {
    "plug": apply_plug,
    "dowel": apply_dowel,
    "snap": apply_snap,
    "dovetail": apply_dovetail,
}

_AXIS_NORMALS = {
    "X": np.array([1.0, 0.0, 0.0]),
    "Y": np.array([0.0, 1.0, 0.0]),
    "Z": np.array([0.0, 0.0, 1.0]),
}

_AXIS_INDEX = {"X": 0, "Y": 1, "Z": 2}

# The indicator quad's own in-plane axes, chosen per cut axis purely so the
# rendered plane looks axis-aligned rather than arbitrarily rotated -- kept
# independent of CutPlane's own u/v (which drive real connector orientation
# in core/connectors.py and must not change). Also used to get u/v AXIS
# INDICES for the cross-section analysis below -- only the index (via
# argmax) matters there, not the sign, so the two conventions not matching
# exactly (see module docstring in core/geometry.py) is harmless.
_INDICATOR_AXES = {
    "X": (np.array([0.0, 1.0, 0.0]), np.array([0.0, 0.0, 1.0])),
    "Y": (np.array([1.0, 0.0, 0.0]), np.array([0.0, 0.0, 1.0])),
    "Z": (np.array([1.0, 0.0, 0.0]), np.array([0.0, 1.0, 0.0])),
}

# Cura's own STL-import axis swap (see module docstring) also means the
# machine's user-facing dimensions map onto world axes this way: width->X,
# height->Y (the real vertical axis), depth->Z.
_MACHINE_DIM_FOR_AXIS = {"X": "machine_width", "Y": "machine_height", "Z": "machine_depth"}

# UM.Scene.ToolHandle's axis IDs, returned by the "selection" render pass
# when the user clicks one of CutAxisToolHandle's three colored cubes.
_HANDLE_AXIS_TO_STRING = {
    ToolHandle.XAxis: "X",
    ToolHandle.YAxis: "Y",
    ToolHandle.ZAxis: "Z",
}


class CuraConnectTool(Tool):
    def __init__(self):
        super().__init__()
        self._shortcut_key = Qt.Key.Key_J  # unused by any bundled tool (E/M/S/R/T are already taken)
        self._controller = self.getController()
        self._picking_pass = None

        self._connector_type = "dovetail"
        self._width = 8.0
        self._depth = 6.0
        self._tolerance = 0.15
        self._cut_axis = "Y"  # the real vertical axis in Cura's world space -- see module docstring
        self._tilt_degrees = 0.0  # manual tilt on top of the axis-aligned suggested position

        self._plane_position = 0.0  # world coordinate along _cut_axis
        self._plane_size = 80.0  # mm, the visible indicator's side length
        self._has_plane = False  # whether a plane has actually been placed for the current selection
        self._plane_indicator = CutPlaneIndicator()
        self._controller.getScene().getRoot().addChild(self._plane_indicator)

        self._connector_count = 1
        self._connector_offsets = [0.0]
        self._seam_size = 0.0  # last-computed seam extent along u, needed to respace a manual count override

        self.setHandle(CutAxisToolHandle())
        self._drag_mode = None  # "axis" (arrow) or "tilt" (ring) -- both share UM.Tool's single drag-plane slot

        Selection.selectionChanged.connect(self._onSelectionChanged)

        self.setExposedProperties(
            "ConnectorType", "Width", "Depth", "Tolerance", "CutAxis",
            "PlanePosition", "PlaneSize", "ConnectorCount", "TiltAngle",
        )

    def event(self, event):
        super().event(event)

        if event.type == Event.ToolActivateEvent:
            node = Selection.getSelectedObject(0)
            if node is not None:
                self._autoSuggestPlane(node)
            return False

        if event.type == Event.ToolDeactivateEvent:
            self._endHandleDrag()
            self._resetPlane()
            return False

        if event.type == Event.MousePressEvent and MouseEvent.LeftButton in event.buttons \
                and self._controller.getToolsEnabled():
            # Normally populated lazily by UM.Tool's own MouseMoveEvent
            # handling (a hover before any click) -- fetched directly here
            # too so a click works even without a preceding hover event.
            if self._selection_pass is None:
                self._selection_pass = Application.getInstance().getRenderer().getRenderPass("selection")
            if self._selection_pass is not None:
                handle_id = self._selection_pass.getIdAtPosition(event.x, event.y)
                if handle_id in _HANDLE_AXIS_TO_STRING:
                    self.setCutAxis(_HANDLE_AXIS_TO_STRING[handle_id])
                    self._beginHandleDrag(handle_id, event.x, event.y)
                    return True
                if handle_id == CutAxisToolHandle.ExtraWidgets.TiltRing.value:
                    self._beginTiltDrag(event.x, event.y)
                    return True

        if event.type == Event.MouseMoveEvent and self.getDragPlane() is not None:
            if self._drag_mode == "tilt":
                self._continueTiltDrag(event.x, event.y)
            else:
                self._continueHandleDrag(event.x, event.y)
            return True

        if event.type == Event.MouseReleaseEvent and self.getDragPlane() is not None:
            self._endHandleDrag()
            return True

        is_press_or_drag = event.type in (Event.MousePressEvent, Event.MouseMoveEvent)
        if is_press_or_drag and MouseEvent.LeftButton in event.buttons \
                and self._controller.getToolsEnabled():

            if self._picking_pass is None:
                self._picking_pass = Application.getInstance().getRenderer().getRenderPass("picking_selected")
                if not self._picking_pass:
                    return False

            selected_node = Selection.getSelectedObject(0)
            if selected_node is None:
                return False

            picked_position = self._picking_pass.getPickedPosition(event.x, event.y)
            if picked_position is None:
                return False

            self._placePlane(selected_node, picked_position)
            return True

        return False

    # ---- Dragging the axis handle's arrows to nudge the plane -- the same
    # camera-facing drag-plane + getDragVector mechanism Cura's own Move
    # tool (TranslateTool.py) uses, reusing UM.Tool's built-in helpers. ----

    def _beginHandleDrag(self, handle_id: int, x: float, y: float) -> None:
        self._drag_mode = "axis"
        self.setLockedAxis(handle_id)
        camera = self._controller.getScene().getActiveCamera()
        if camera is None:
            return
        camera_direction = camera.getPosition().normalized()
        if handle_id == ToolHandle.XAxis:
            plane_vector = Vector(0, camera_direction.y, camera_direction.z).normalized()
        elif handle_id == ToolHandle.YAxis:
            plane_vector = Vector(camera_direction.x, 0, camera_direction.z).normalized()
        else:
            plane_vector = Vector(camera_direction.x, camera_direction.y, 0).normalized()
        self.setDragPlane(Plane(plane_vector, 0))
        self.setDragStart(x, y)

    def _continueHandleDrag(self, x: float, y: float) -> None:
        if self.getDragStart() is None:
            self.setDragStart(x, y)
            return
        drag = self.getDragVector(x, y)
        self.setDragStart(x, y)
        if drag is None or not self._has_plane:
            return

        axis_index = _AXIS_INDEX[self._cut_axis]
        # float(...) matters here: Vector's components can come back as a
        # numpy scalar type, and once that contaminates _plane_position via
        # +=, later round()s on it produce a numpy scalar QML's text binding
        # can't display -- the drag itself was working the whole time
        # (confirmed via repeated mesh rebuilds in the log), only the
        # on-screen number silently stopped updating.
        delta = float([drag.x, drag.y, drag.z][axis_index])
        if delta == 0:
            return
        self._plane_position = float(self._plane_position) + delta

        node = Selection.getSelectedObject(0)
        if node is not None:
            mesh_data = node.getMeshData()
            if mesh_data is not None:
                self._updateConnectorLayout(self._worldVertices(node, mesh_data))
            self._renderPlane(node)
        self.propertyChanged.emit()

    def _endHandleDrag(self) -> None:
        if self.getDragPlane() is not None:
            self.setLockedAxis(ToolHandle.NoAxis)
            self.setDragPlane(None)
        self._drag_mode = None

    # ---- Dragging the tilt ring -- the same drag-plane-through-the-pivot
    # plus angle-between-drag_start-and-drag_end mechanism Cura's own
    # Rotate tool (RotateTool.py) uses, read from its event() before being
    # adapted to a single rotation axis (v) here. ----

    def _beginTiltDrag(self, x: float, y: float) -> None:
        self._drag_mode = "tilt"
        v = _INDICATOR_AXES[self._cut_axis][1]
        v_index = int(np.argmax(np.abs(v)))
        handle_position = self._handle.getWorldPosition()
        distance = [handle_position.x, handle_position.y, handle_position.z][v_index]
        plane_vector = Vector(float(v[0]), float(v[1]), float(v[2]))
        self.setDragPlane(Plane(plane_vector, distance))
        self.setDragStart(x, y)

    def _continueTiltDrag(self, x: float, y: float) -> None:
        drag_start_point = self.getDragStart()
        if drag_start_point is None:
            self.setDragStart(x, y)
            return
        drag_position = self.getDragPosition(x, y)
        if drag_position is None:
            return

        handle_position = self._handle.getWorldPosition()
        drag_start_vec = (drag_start_point - handle_position).normalized()
        drag_end_vec = (drag_position - handle_position).normalized()

        dot = max(-1.0, min(1.0, drag_start_vec.dot(drag_end_vec)))
        angle_degrees = math.degrees(math.acos(dot))
        if angle_degrees == 0:
            self.setDragStart(x, y)
            return

        v = _INDICATOR_AXES[self._cut_axis][1]
        rotation_axis = Vector(float(v[0]), float(v[1]), float(v[2]))
        direction = 1 if rotation_axis.dot(drag_start_vec.cross(drag_end_vec)) > 0 else -1

        self.setTiltAngle(self._tilt_degrees + direction * angle_degrees)
        self.setDragStart(x, y)

    def getRequiredExtraRenderingPasses(self) -> list:
        return ["picking_selected"]

    def _onSelectionChanged(self) -> None:
        self._resetPlane()
        if self._controller.getActiveTool() is self:
            node = Selection.getSelectedObject(0)
            if node is not None:
                self._autoSuggestPlane(node)

    def _resetPlane(self) -> None:
        self._has_plane = False
        self._plane_indicator.hide()

    @staticmethod
    def _worldVertices(node: CuraSceneNode, mesh_data) -> np.ndarray:
        world_matrix = node.getWorldTransformation(copy=True).getData()  # 4x4 numpy array
        local_verts = mesh_data.getVertices()
        homogeneous = np.hstack([local_verts, np.ones((local_verts.shape[0], 1))])
        return (homogeneous @ world_matrix.T)[:, :3].astype(np.float32)

    def _currentBedLimit(self) -> Optional[float]:
        stack = CuraApplication.getInstance().getGlobalContainerStack()
        if stack is None:
            return None
        value = stack.getProperty(_MACHINE_DIM_FOR_AXIS[self._cut_axis], "value")
        return float(value) if value is not None else None

    def _autoSuggestPlane(self, node: CuraSceneNode) -> None:
        """Called when the tool activates or the selection changes: places
        a smart default plane (avoiding thin/lattice cross-sections, and
        preferring a position where both resulting pieces fit the current
        machine's bed along this axis) instead of requiring a click first.
        The user can still click/drag to override it afterward."""
        mesh_data = node.getMeshData()
        if mesh_data is None:
            return
        world_verts = self._worldVertices(node, mesh_data)
        axis_index = _AXIS_INDEX[self._cut_axis]
        try:
            suggested = suggest_cut_position(world_verts, axis_index, bed_limit=self._currentBedLimit())
        except ValueError:
            return

        self._plane_position = suggested
        self._has_plane = True
        bbox = node.getBoundingBox()
        if bbox is not None:
            self._plane_size = max(bbox.width, bbox.height, bbox.depth) * 1.4
            self._handle.setReach(max(bbox.width, bbox.height, bbox.depth) / 2)

        self._updateConnectorLayout(world_verts)
        self._renderPlane(node)
        self.propertyChanged.emit()

    def _updateConnectorLayout(self, world_verts: np.ndarray) -> None:
        """Size and count the connectors to the actual seam at the current
        plane position -- "bigger object, bigger (and more) connectors"."""
        axis_index = _AXIS_INDEX[self._cut_axis]
        u, v = _INDICATOR_AXES[self._cut_axis]
        u_axis_index = int(np.argmax(np.abs(u)))
        v_axis_index = int(np.argmax(np.abs(v)))
        layout = suggest_connector_layout(
            world_verts, axis_index, self._plane_position, u_axis_index, v_axis_index
        )
        if layout is None:
            return
        self._width = layout.width
        self._depth = layout.depth
        self._connector_count = layout.count
        self._connector_offsets = layout.offsets
        self._seam_size = layout.seam_size

    def _placePlane(self, node: CuraSceneNode, picked_position) -> None:
        axis_index = _AXIS_INDEX[self._cut_axis]
        coord = [picked_position.x, picked_position.y, picked_position.z][axis_index]

        if not self._has_plane:
            bbox = node.getBoundingBox()
            if bbox is not None:
                self._plane_size = max(bbox.width, bbox.height, bbox.depth) * 1.4
            self._has_plane = True

        self._plane_position = float(coord)

        mesh_data = node.getMeshData()
        if mesh_data is not None:
            self._updateConnectorLayout(self._worldVertices(node, mesh_data))

        self._renderPlane(node)
        self.propertyChanged.emit()

    def _tiltedFrame(self):
        """The plane's (normal, u, v), tilted by `_tilt_degrees` around v on
        top of the base axis-aligned frame -- a manual refinement the user
        dials in on top of wherever the plane currently sits, not part of
        the auto-suggestion search (which stays axis-aligned)."""
        normal = _AXIS_NORMALS[self._cut_axis]
        u, v = _INDICATOR_AXES[self._cut_axis]
        if abs(self._tilt_degrees) < 1e-9:
            return normal, u, v
        return (
            rotate_vector(normal, v, self._tilt_degrees),
            rotate_vector(u, v, self._tilt_degrees),
            v,
        )

    def _renderPlane(self, node: CuraSceneNode) -> None:
        bbox = node.getBoundingBox()
        if bbox is None:
            return
        axis_index = _AXIS_INDEX[self._cut_axis]
        center = np.array([bbox.center.x, bbox.center.y, bbox.center.z])
        center[axis_index] = self._plane_position
        _normal, u, v = self._tiltedFrame()
        self._plane_indicator.updatePlane(center, u, v, self._plane_size)

        # The axis-arrows/tilt-ring gizmo tracks the PLANE's position, not
        # the object's static center -- what it manipulates is the plane,
        # and it should stay visually attached to it as it's dragged around.
        self._handle.setPosition(Vector(float(center[0]), float(center[1]), float(center[2])))
        self._handle.setRing(self._cut_axis, self._plane_size / 2)

    def performCut(self) -> None:
        node = Selection.getSelectedObject(0)
        if node is None or not self._has_plane:
            Logger.log("w", "CuraConnectTool: no cut plane placed yet -- click on the model first")
            return

        mesh_data = node.getMeshData()
        if mesh_data is None:
            Logger.log("w", "CuraConnectTool: selected node has no mesh data, nothing to cut")
            return

        world_verts = self._worldVertices(node, mesh_data)

        try:
            solid = cura_vertices_to_manifold(world_verts)
        except Exception as e:
            Logger.log("e", f"CuraConnectTool: could not convert mesh to a solid: {e}")
            return

        tilted_normal, _u, _v = self._tiltedFrame()
        axis_index = _AXIS_INDEX[self._cut_axis]
        bbox = node.getBoundingBox()
        plane_point = np.array([bbox.center.x, bbox.center.y, bbox.center.z])
        plane_point[axis_index] = self._plane_position
        plane = CutPlane.from_normal(point=plane_point, normal=tilted_normal)

        a, b = split_solid(solid, plane)
        if a.volume() < 1e-6 or b.volume() < 1e-6:
            Logger.log("w", "CuraConnectTool: the plane doesn't actually split the model into two "
                             "pieces (it's outside the model's extent along the chosen axis) -- nothing done")
            return

        connector_fn = _CONNECTOR_FUNCTIONS[self._connector_type]
        params = ConnectorParams(width=self._width, depth=self._depth, tolerance=self._tolerance)
        try:
            result = apply_connector_instances(a, b, plane, params, connector_fn, self._connector_offsets)
        except ValueError as e:
            Logger.log("e", f"CuraConnectTool: connector geometry rejected these parameters: {e}")
            return

        scene = self._controller.getScene()
        new_nodes = [
            self._buildSceneNode(result.piece_a, f"{node.getName()}_A"),
            self._buildSceneNode(result.piece_b, f"{node.getName()}_B"),
        ]
        if result.loose_piece is not None:
            new_nodes.append(self._buildSceneNode(result.loose_piece, f"{node.getName()}_pin"))

        op = GroupedOperation()
        for new_node in new_nodes:
            op.addOperation(AddSceneNodeOperation(new_node, scene.getRoot()))
        op.addOperation(RemoveSceneNodeOperation(node))
        op.push()

        for new_node in new_nodes:
            scene.sceneChanged.emit(new_node)

        self._resetPlane()

    def _buildSceneNode(self, manifold, name: str) -> CuraSceneNode:
        flat_verts = manifold_to_cura_vertices(manifold)

        mesh_builder = MeshBuilder()
        mesh_builder.setVertices(flat_verts)
        mesh_builder.calculateNormals()

        new_node = CuraSceneNode()
        new_node.setName(name)
        new_node.setSelectable(True)
        new_node.setCalculateBoundingBox(True)
        new_node.setMeshData(mesh_builder.build())
        new_node.calculateBoundingBoxMesh()

        active_build_plate = CuraApplication.getInstance().getMultiBuildPlateModel().activeBuildPlate
        new_node.addDecorator(BuildPlateDecorator(active_build_plate))
        new_node.addDecorator(SliceableObjectDecorator())

        return new_node

    # ---- Exposed properties (bound from CuraConnectPanel.qml via UM.Controller.properties) ----

    def getConnectorType(self) -> str:
        return self._connector_type

    def setConnectorType(self, value: str) -> None:
        if value != self._connector_type and value in _CONNECTOR_FUNCTIONS:
            self._connector_type = value
            self.propertyChanged.emit()

    def getWidth(self) -> float:
        return round(self._width, 2)

    def setWidth(self, value) -> None:
        value = float(value)
        if value > 0 and value != self._width:
            self._width = value
            self.propertyChanged.emit()

    def getDepth(self) -> float:
        return round(self._depth, 2)

    def setDepth(self, value) -> None:
        value = float(value)
        if value > 0 and value != self._depth:
            self._depth = value
            self.propertyChanged.emit()

    def getTolerance(self) -> float:
        return self._tolerance

    def setTolerance(self, value) -> None:
        value = float(value)
        if value >= 0 and value != self._tolerance:
            self._tolerance = value
            self.propertyChanged.emit()

    def getCutAxis(self) -> str:
        return self._cut_axis

    def setCutAxis(self, value: str) -> None:
        if value != self._cut_axis and value in _AXIS_NORMALS:
            self._cut_axis = value
            self._tilt_degrees = 0.0  # a tilt around the old axis's frame doesn't carry over meaningfully
            # a position along the old axis is meaningless on the new one --
            # re-suggest a fresh default for this axis instead of just
            # clearing it and waiting for a click.
            node = Selection.getSelectedObject(0)
            if node is not None:
                self._autoSuggestPlane(node)
            else:
                self._resetPlane()
            self.propertyChanged.emit()

    def getTiltAngle(self) -> float:
        return round(self._tilt_degrees, 1)

    def setTiltAngle(self, value) -> None:
        value = max(-85.0, min(85.0, float(value)))  # avoid the near-degenerate edge-on cases
        if value != self._tilt_degrees:
            self._tilt_degrees = value
            if self._has_plane:
                node = Selection.getSelectedObject(0)
                if node is not None:
                    self._renderPlane(node)
            self.propertyChanged.emit()

    def getPlanePosition(self) -> float:
        return round(self._plane_position, 2)

    def setPlanePosition(self, value) -> None:
        value = float(value)
        if self._has_plane and value != self._plane_position:
            self._plane_position = value
            node = Selection.getSelectedObject(0)
            if node is not None:
                mesh_data = node.getMeshData()
                if mesh_data is not None:
                    self._updateConnectorLayout(self._worldVertices(node, mesh_data))
                self._renderPlane(node)
            self.propertyChanged.emit()

    def getPlaneSize(self) -> float:
        return round(self._plane_size, 1)

    def setPlaneSize(self, value) -> None:
        value = float(value)
        if value > 0 and value != self._plane_size:
            self._plane_size = value
            if self._has_plane:
                node = Selection.getSelectedObject(0)
                if node is not None:
                    self._renderPlane(node)
            self.propertyChanged.emit()

    def getConnectorCount(self) -> int:
        return self._connector_count

    def setConnectorCount(self, value) -> None:
        value = max(1, int(value))
        if value != self._connector_count:
            self._connector_count = value
            self._connector_offsets = evenly_spaced_offsets(value, self._seam_size)
            self.propertyChanged.emit()
