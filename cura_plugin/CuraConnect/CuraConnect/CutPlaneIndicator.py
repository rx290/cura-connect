"""
A visual-only preview of where CuraConnectTool will cut, shown while the
tool is active so the user can see and adjust the plane before committing.
Never added to the build volume / slice pipeline -- it's a SceneNode with
its own render(), same pattern Cura's own ConvexHullNode
(cura/Scene/ConvexHullNode.py) uses for the translucent buildplate-shadow
overlay, read directly from the installed Cura 5.13 source before writing
this rather than guessed.
"""
import numpy as np

from UM.Math.Color import Color
from UM.Mesh.MeshBuilder import MeshBuilder
from UM.Resources import Resources
from UM.Scene.SceneNode import SceneNode
from UM.View.GL.OpenGL import OpenGL

# Bright, translucent magenta -- deliberately far from any filament preview
# color (blues/oranges/greys) or Cura's own teal UI accents, so the plane is
# never mistaken for part of the model.
PLANE_COLOR = Color(0.95, 0.1, 0.85, 1.0)
PLANE_OPACITY = 0.55


class CutPlaneIndicator(SceneNode):
    _shader = None  # shared across instances, built once, same as ConvexHullNode

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCalculateBoundingBox(False)
        self.setSelectable(False)
        self._visible_override = False

    def show(self):
        self._visible_override = True

    def hide(self):
        self._visible_override = False

    def updatePlane(self, center: np.ndarray, u: np.ndarray, v: np.ndarray, size: float):
        """Rebuild the quad centered at `center`, spanning `size` mm along
        each of the given in-plane axes `u`/`v` (world-space vectors, need
        not match the CutPlane.u/v used for actual connector orientation --
        this quad exists purely to be seen, not to carry any cut math)."""
        half = size / 2.0
        c0 = center - u * half - v * half
        c1 = center + u * half - v * half
        c2 = center + u * half + v * half
        c3 = center - u * half + v * half

        builder = MeshBuilder()
        # Both winding orders, so the plane is visible from either side --
        # the camera can end up on either side of the cut depending on the
        # model's orientation and the user's current view angle.
        builder.addQuad(
            self._toVector(c0), self._toVector(c1), self._toVector(c2), self._toVector(c3),
        )
        builder.addQuad(
            self._toVector(c0), self._toVector(c3), self._toVector(c2), self._toVector(c1),
        )
        builder.calculateNormals()
        self.setMeshData(builder.build())
        self.show()

    @staticmethod
    def _toVector(arr: np.ndarray):
        from UM.Math.Vector import Vector
        return Vector(float(arr[0]), float(arr[1]), float(arr[2]))

    def render(self, renderer) -> bool:
        if not self._visible_override or self.getMeshData() is None:
            return True

        if not CutPlaneIndicator._shader:
            CutPlaneIndicator._shader = OpenGL.getInstance().createShaderProgram(
                Resources.getPath(Resources.Shaders, "transparent_object.shader")
            )
            CutPlaneIndicator._shader.setUniformValue("u_diffuseColor", PLANE_COLOR)
            CutPlaneIndicator._shader.setUniformValue("u_opacity", PLANE_OPACITY)

        batch = renderer.getNamedBatch("cura_connect_plane_indicator")
        if not batch:
            batch = renderer.createRenderBatch(
                transparent=True, shader=CutPlaneIndicator._shader, backface_cull=False, sort=-8
            )
            renderer.addRenderBatch(batch, name="cura_connect_plane_indicator")
        batch.addItem(self.getWorldTransformation(copy=False), self.getMeshData())
        return True
