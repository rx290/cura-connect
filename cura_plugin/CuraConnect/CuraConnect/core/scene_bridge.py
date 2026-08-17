"""
Converts between Cura's raw mesh representation (flat, unindexed vertex
arrays -- every triangle repeats its 3 corner vertices, per Uranium's
MeshData convention) and manifold3d's indexed representation (which needs
shared vertex indices to determine watertightness at all -- the same reason
core.geometry.read_stl_as_manifold has to deduplicate a raw STL's unindexed
triangle soup).

Kept independent of any real Cura import so it can be unit tested without a
Cura installation -- CuraConnectTool.py calls these with real
MeshData.getVertices()/getIndices() arrays, but this module itself only ever
sees plain numpy arrays.
"""
import numpy as np
import manifold3d as m3d


def cura_vertices_to_manifold(flat_vertices: np.ndarray) -> m3d.Manifold:
    """`flat_vertices` is an (N*3, 3) array, three rows per triangle, exactly
    as Uranium's MeshData.getVertices() returns when the mesh has no index
    buffer (the common case for an STL-derived model)."""
    if flat_vertices.shape[0] % 3 != 0:
        raise ValueError(
            f"expected a flat triangle-soup array (a multiple of 3 rows), "
            f"got {flat_vertices.shape[0]} rows"
        )
    unique_verts, inverse = np.unique(np.round(flat_vertices, 6), axis=0, return_inverse=True)
    tri_verts = inverse.reshape(-1, 3).astype(np.uint32)
    mesh = m3d.Mesh(vert_properties=unique_verts.astype(np.float64), tri_verts=tri_verts)
    manifold = m3d.Manifold(mesh)

    # A model that's been mirrored (Cura's own Mirror tool, or a mirrored
    # import) has every triangle's winding flipped relative to the standard
    # outward-normal convention -- manifold3d still reports it as watertight,
    # just with a negative volume. Caught by this module's own test suite
    # using a deliberately backward-wound fixture; correct for it here so a
    # mirrored model doesn't silently produce inside-out connector geometry.
    if manifold.volume() < 0:
        tri_verts_flipped = tri_verts[:, [0, 2, 1]]
        mesh_flipped = m3d.Mesh(vert_properties=unique_verts.astype(np.float64), tri_verts=tri_verts_flipped)
        manifold = m3d.Manifold(mesh_flipped)

    return manifold


def manifold_to_cura_vertices(manifold: m3d.Manifold) -> np.ndarray:
    """Inverse direction: expand manifold3d's indexed mesh back into a flat,
    unindexed (N*3, 3) triangle-soup array, which is what
    UM.Mesh.MeshBuilder.setVertices()/addFaceByPoints() expects when built
    without an explicit index buffer -- matching the same "no shared
    vertices" convention every other Cura-created mesh (e.g. SupportEraser's
    eraser cube) already uses."""
    mesh = manifold.to_mesh()
    verts = np.array(mesh.vert_properties)[:, :3]
    tris = np.array(mesh.tri_verts)
    return verts[tris].reshape(-1, 3).astype(np.float32)
