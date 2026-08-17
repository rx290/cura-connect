"""
Plane math and mesh I/O shared by every connector type in core/connectors.py.

Built on manifold3d (https://github.com/elalish/manifold), which guarantees
watertight boolean results (its own `.status()` reports a real error code
instead of silently producing a broken mesh) -- verified directly against
the real library before this module was written, not assumed.
"""
from dataclasses import dataclass

import numpy as np
import manifold3d as m3d
import stl as numpy_stl


def normalize(v):
    v = np.array(v, dtype=float)
    length = np.linalg.norm(v)
    if length < 1e-9:
        raise ValueError(f"Cannot normalize a near-zero vector: {v}")
    return v / length


@dataclass
class CutPlane:
    """A plane defined by a point on it and a unit normal, plus the two
    in-plane axes used to orient connector geometry (u = the 'slide axis',
    meaningful for the dovetail's taper direction; v = the remaining
    in-plane axis, completing a right-handed frame with the normal)."""
    point: np.ndarray
    normal: np.ndarray
    u: np.ndarray
    v: np.ndarray

    @staticmethod
    def from_normal(point, normal, slide_axis=None):
        normal = normalize(normal)
        if slide_axis is not None:
            slide_axis = np.array(slide_axis, dtype=float)
            u = slide_axis - np.dot(slide_axis, normal) * normal
            if np.linalg.norm(u) < 1e-6:
                raise ValueError("slide_axis cannot be parallel to the plane normal")
            u = normalize(u)
        else:
            # Pick an arbitrary vector not parallel to normal, project out
            # the normal component, and normalize -- gives a deterministic
            # in-plane axis when the caller doesn't care which one.
            arbitrary = np.array([1.0, 0.0, 0.0])
            if abs(np.dot(arbitrary, normal)) > 0.9:
                arbitrary = np.array([0.0, 1.0, 0.0])
            u = normalize(arbitrary - np.dot(arbitrary, normal) * normal)
        v = np.cross(normal, u)
        return CutPlane(point=np.array(point, dtype=float), normal=normal, u=u, v=v)

    def origin_offset(self):
        """Distance of the plane from the world origin along its normal,
        as required by manifold3d's split_by_plane/trim_by_plane."""
        return float(np.dot(self.normal, self.point))

    def to_world_transform(self, local_origin=(0.0, 0.0, 0.0), protrude_toward_normal=True):
        """3x4 transform (matching manifold3d's Double3x4) mapping a shape
        built in its own local frame into world space at this plane, offset
        by `local_origin` in local coordinates first.

        Local +X = the slide axis u, local +Y = v, and local +Z = the
        direction the shape protrudes ACROSS THE SEAM into the other piece.
        `split_solid` puts the +normal-side piece first -- a boss meant to
        stick out of that piece and into the other one must protrude in the
        -normal world direction, i.e. protrude_toward_normal=False for that
        piece's boss (and True for the -normal-side piece's boss). Getting
        this backwards silently buries the boss inside its own piece instead
        of bridging the seam -- exactly the bug this parameter exists to
        make impossible to get wrong by accident.
        """
        z_axis = self.normal if protrude_toward_normal else -self.normal
        rotation = np.column_stack([self.u, self.v, z_axis])
        translation = self.point + rotation @ np.array(local_origin, dtype=float)
        # manifold3d wants a (3, 4) numpy array: 3x3 rotation, then a translation column
        return np.column_stack([rotation, translation])


def split_solid(solid: m3d.Manifold, plane: CutPlane):
    """Split a solid into the two halves either side of `plane`. The first
    result is on the side the normal points toward."""
    return solid.split_by_plane(tuple(plane.normal), plane.origin_offset())


def place(local_shape: m3d.Manifold, plane: CutPlane, local_origin=(0.0, 0.0, 0.0),
          protrude_toward_normal=True):
    """Transform a shape built in its own local frame into world space at
    `plane`, per CutPlane.to_world_transform."""
    return local_shape.transform(
        plane.to_world_transform(local_origin, protrude_toward_normal)
    )


def is_watertight(manifold: m3d.Manifold) -> bool:
    return manifold.status() == m3d.Error.NoError


def write_stl(manifold: m3d.Manifold, path: str):
    mesh = manifold.to_mesh()
    verts = np.array(mesh.vert_properties)[:, :3]
    tris = np.array(mesh.tri_verts)
    data = np.zeros(len(tris), dtype=numpy_stl.mesh.Mesh.dtype)
    for i, tri in enumerate(tris):
        data["vectors"][i] = verts[tri]
    numpy_stl.mesh.Mesh(data).save(path)


def read_stl_as_manifold(path: str) -> m3d.Manifold:
    source = numpy_stl.mesh.Mesh.from_file(path)
    # Deduplicate vertices so manifold3d gets a proper indexed mesh -- a raw
    # STL's vectors are unindexed triangle soup, and Manifold requires shared
    # vertex indices to determine watertightness at all.
    all_verts = source.vectors.reshape(-1, 3)
    unique_verts, inverse = np.unique(np.round(all_verts, 6), axis=0, return_inverse=True)
    tri_verts = inverse.reshape(-1, 3).astype(np.uint32)
    mesh = m3d.Mesh(vert_properties=unique_verts.astype(np.float64), tri_verts=tri_verts)
    return m3d.Manifold(mesh)
