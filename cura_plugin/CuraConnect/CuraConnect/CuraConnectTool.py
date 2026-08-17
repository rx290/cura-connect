# Copyright (c) 2026, cura-connect -- MIT licensed, see the repo's LICENSE file.
"""
The interactive Cura Tool (Phase 2). Click on a selected model with this
tool active to split it at the clicked point, along a chosen axis, with the
connector geometry from core/connectors.py applied automatically.

v1 scope, deliberately: the cut plane is always perpendicular to one of the
X/Y/Z world axes (chosen in the tool panel), positioned at the clicked
point's coordinate along that axis -- not a freely-rotatable 3D gizmo like
PrusaSlicer/OrcaSlicer's own Cut Tool. That's a real, useful scope (splitting
a tall model horizontally, or a wide one vertically, covers the common
case), not the full feature set -- extending to a free-rotation gizmo is
real, separate follow-up work, not attempted here.

Follows the exact real pattern Cura's own bundled SupportEraser plugin uses
for creating new scene nodes at runtime (picking_selected render pass,
GroupedOperation of Add/Remove SceneNodeOperations, BuildPlateDecorator +
SliceableObjectDecorator on every new node) -- read directly from the
installed Cura 5.13 source before writing this, not guessed.
"""
from typing import Optional

import numpy as np
from PyQt6.QtCore import Qt

from UM.Application import Application
from UM.Event import Event, MouseEvent
from UM.Logger import Logger
from UM.Mesh.MeshBuilder import MeshBuilder
from UM.Operations.AddSceneNodeOperation import AddSceneNodeOperation
from UM.Operations.GroupedOperation import GroupedOperation
from UM.Operations.RemoveSceneNodeOperation import RemoveSceneNodeOperation
from UM.Scene.Selection import Selection
from UM.Tool import Tool

from cura.CuraApplication import CuraApplication
from cura.Scene.CuraSceneNode import CuraSceneNode
from cura.Scene.SliceableObjectDecorator import SliceableObjectDecorator
from cura.Scene.BuildPlateDecorator import BuildPlateDecorator

from .core.geometry import CutPlane, split_solid
from .core.connectors import ConnectorParams, apply_plug, apply_dowel, apply_dovetail, apply_snap
from .core.scene_bridge import cura_vertices_to_manifold, manifold_to_cura_vertices

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
        self._cut_axis = "Z"

        self.setExposedProperties("ConnectorType", "Width", "Depth", "Tolerance", "CutAxis")

    def event(self, event):
        super().event(event)
        if event.type == Event.MousePressEvent and MouseEvent.LeftButton in event.buttons \
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

            self._performCut(selected_node, picked_position)
            return True

        return False

    def getRequiredExtraRenderingPasses(self) -> list:
        return ["picking_selected"]

    def _performCut(self, node: CuraSceneNode, picked_position):
        mesh_data = node.getMeshData()
        if mesh_data is None:
            Logger.log("w", "CuraConnectTool: selected node has no mesh data, nothing to cut")
            return

        world_matrix = node.getWorldTransformation(copy=True).getData()  # 4x4 numpy array
        local_verts = mesh_data.getVertices()
        homogeneous = np.hstack([local_verts, np.ones((local_verts.shape[0], 1))])
        world_verts = (homogeneous @ world_matrix.T)[:, :3].astype(np.float32)

        try:
            solid = cura_vertices_to_manifold(world_verts)
        except Exception as e:
            Logger.log("e", f"CuraConnectTool: could not convert mesh to a solid: {e}")
            return

        axis_normal = _AXIS_NORMALS[self._cut_axis]
        plane_point = np.array([picked_position.x, picked_position.y, picked_position.z])
        plane = CutPlane.from_normal(point=plane_point, normal=axis_normal)

        a, b = split_solid(solid, plane)
        if a.volume() < 1e-6 or b.volume() < 1e-6:
            Logger.log("w", "CuraConnectTool: the clicked point doesn't actually split the model into two "
                             "pieces (it's outside the model's extent along the chosen axis) -- nothing done")
            return

        connector_fn = _CONNECTOR_FUNCTIONS[self._connector_type]
        params = ConnectorParams(width=self._width, depth=self._depth, tolerance=self._tolerance)
        try:
            result = connector_fn(a, b, plane, params)
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
        return self._width

    def setWidth(self, value) -> None:
        value = float(value)
        if value > 0 and value != self._width:
            self._width = value
            self.propertyChanged.emit()

    def getDepth(self) -> float:
        return self._depth

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
            self.propertyChanged.emit()
