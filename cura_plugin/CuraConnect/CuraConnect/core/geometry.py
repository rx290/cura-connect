"""
Plane math and mesh I/O shared by every connector type in core/connectors.py.

Built on manifold3d (https://github.com/elalish/manifold), which guarantees
watertight boolean results (its own `.status()` reports a real error code
instead of silently producing a broken mesh) -- verified directly against
the real library before this module was written, not assumed.
"""
from dataclasses import dataclass
from typing import Optional

import numpy as np
import manifold3d as m3d
import stl as numpy_stl


def normalize(v):
    v = np.array(v, dtype=float)
    length = np.linalg.norm(v)
    if length < 1e-9:
        raise ValueError(f"Cannot normalize a near-zero vector: {v}")
    return v / length


def rotate_vector(v, axis, degrees):
    """Rotate `v` by `degrees` around `axis` (Rodrigues' rotation formula).
    Used to tilt a cut plane's normal away from a pure world axis by a
    user-chosen angle, on top of the axis-aligned position the suggestion
    heuristic picks -- the heuristic itself stays axis-aligned (tilting the
    search space too would be a much bigger, separate undertaking); tilt is
    a manual refinement applied on top of that base position."""
    axis = normalize(axis)
    v = np.array(v, dtype=float)
    theta = np.radians(degrees)
    return (
        v * np.cos(theta)
        + np.cross(axis, v) * np.sin(theta)
        + axis * np.dot(axis, v) * (1 - np.cos(theta))
    )


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


"""
Cheap, deliberately approximate cross-section analysis, shared by the
"suggest a cut position" and "size/count the connectors for this seam"
features. Neither one does real polygon slicing against the mesh -- both
sample raw vertices in a thin band around a candidate position, the same
by-hand technique used to pick a safe cut location on the Eiffel Tower demo
model (avoid the ornate lattice arches near its base, cut through the
solid tapering mast instead). That's a real, useful heuristic, not a
structural simulation -- it can be fooled by a model with genuinely thin
walls that happen to have few vertices, and it says nothing about material
strength. Documented here rather than oversold.
"""


@dataclass
class CrossSectionInfo:
    span_a: float       # footprint extent along axis_a_index, at this position
    span_b: float       # footprint extent along axis_b_index, at this position
    area: float         # span_a * span_b -- a bounding-box proxy, not a true polygon area
    vertex_count: int
    density: float       # vertex_count / area -- higher means more geometric detail per unit area


def cross_section_footprint(vertices: np.ndarray, cut_axis_index: int, position: float,
                             axis_a_index: int, axis_b_index: int,
                             band_fraction: float = 0.02) -> Optional[CrossSectionInfo]:
    """Sample vertices within a thin band around `position` along
    `cut_axis_index` and report the footprint along `axis_a_index`/
    `axis_b_index`. Returns None if too few vertices fall in the band (e.g.
    `position` sits between two disjoint sub-parts, or right at a tip)."""
    lo = float(vertices[:, cut_axis_index].min())
    hi = float(vertices[:, cut_axis_index].max())
    extent = hi - lo
    if extent < 1e-6:
        return None

    band = max(extent * band_fraction, 1e-3)
    mask = np.abs(vertices[:, cut_axis_index] - position) <= band
    band_verts = vertices[mask]
    if band_verts.shape[0] < 3:
        return None

    span_a = float(band_verts[:, axis_a_index].max() - band_verts[:, axis_a_index].min())
    span_b = float(band_verts[:, axis_b_index].max() - band_verts[:, axis_b_index].min())
    area = span_a * span_b
    vertex_count = int(band_verts.shape[0])
    density = vertex_count / max(area, 1e-6)
    return CrossSectionInfo(span_a=span_a, span_b=span_b, area=area,
                             vertex_count=vertex_count, density=density)


def suggest_cut_position(vertices: np.ndarray, cut_axis_index: int, bed_limit: Optional[float] = None,
                          n_samples: int = 40, margin_fraction: float = 0.08,
                          lattice_density_multiple: float = 2.0) -> float:
    """Score candidate positions along `cut_axis_index` and return the best
    one. "Avoid a thin/lattice cross-section" is treated as a hard FILTER,
    not a soft tiebreaker against raw area -- a real, empirically necessary
    call: an early version scored area minus a density penalty, which let a
    model's single widest point (often right near one end, e.g. a tapering
    tower's base) dominate over everything else, defaulting to a barely-
    trimmed sliver off one end. Filtering out candidates whose density
    exceeds `lattice_density_multiple`x the median first, then ranking the
    survivors mainly by closeness to the middle (bed-fit still wins when it
    applies, area only breaks close ties), gives a far more useful default:
    a roughly balanced split that still steers clear of genuinely thin or
    highly-detailed regions."""
    other = [i for i in range(3) if i != cut_axis_index]
    lo = float(vertices[:, cut_axis_index].min())
    hi = float(vertices[:, cut_axis_index].max())
    extent = hi - lo
    if extent < 1e-6:
        raise ValueError("the model has no extent along the chosen cut axis")

    margin = extent * margin_fraction
    candidates = np.linspace(lo + margin, hi - margin, n_samples)
    infos = [cross_section_footprint(vertices, cut_axis_index, p, other[0], other[1]) for p in candidates]
    valid = [(p, info) for p, info in zip(candidates, infos) if info is not None]
    if not valid:
        return float(lo + extent / 2)

    median_density = float(np.median([info.density for _, info in valid]))
    threshold = median_density * lattice_density_multiple
    safe = [(p, info) for p, info in valid if info.density <= threshold or median_density <= 1e-9]
    if not safe:
        safe = valid  # every candidate looked "dense" (e.g. a uniformly lattice-like model) -- don't strand ourselves

    max_area = max(info.area for _, info in safe) or 1.0
    mid = lo + extent / 2

    best_p, best_score = float(safe[0][0]), -np.inf
    for p, info in safe:
        center_score = -abs(p - mid) / extent
        area_tiebreak = (info.area / max_area) * 0.1

        fit_score = 0.0
        if bed_limit is not None:
            piece_a_size = hi - p
            piece_b_size = p - lo
            if piece_a_size <= bed_limit and piece_b_size <= bed_limit:
                fit_score = 1.0
            else:
                overflow = max(piece_a_size - bed_limit, 0.0) + max(piece_b_size - bed_limit, 0.0)
                fit_score = -overflow / extent

        score = center_score + area_tiebreak + 2.0 * fit_score
        if score > best_score:
            best_score, best_p = score, float(p)

    return best_p


@dataclass
class ConnectorLayout:
    width: float
    depth: float
    count: int
    offsets: list  # positions along the plane's u axis, one per connector instance
    seam_size: float = 0.0  # the seam's extent along u -- kept so a manual count override can respace


def evenly_spaced_offsets(count: int, seam_size: float, usable_fraction: float = 0.7) -> list:
    """`count` positions along a seam of extent `seam_size`, spread across
    `usable_fraction` of it and centered on 0 -- shared by the automatic
    layout below and by a manual connector-count override."""
    if count <= 1:
        return [0.0]
    span = seam_size * usable_fraction
    return [float(x) for x in np.linspace(-span / 2, span / 2, count)]


def connector_count_for_width(width: float, seam_size: float, min_gap_factor: float = 2.5,
                               max_count: int = 4) -> int:
    """How many evenly-spaced connector instances of `width` fit along a
    seam of `seam_size` without crowding -- each needs roughly
    `width * min_gap_factor` of clear space to itself. Shared by the
    automatic layout below and by anything that computes its own width
    independently (e.g. a vase-mode wall thickness) and needs a matching
    count for that specific width, not the automatic one."""
    if width <= 0:
        return 1
    spacing_needed = width * min_gap_factor
    count = max(1, int(seam_size // spacing_needed)) if spacing_needed > 0 else 1
    return min(count, max_count)


def suggest_connector_layout(vertices: np.ndarray, cut_axis_index: int, position: float,
                              u_axis_index: int, v_axis_index: int,
                              base_width_fraction: float = 0.12, min_width: float = 4.0,
                              max_width: float = 20.0, min_gap_factor: float = 2.5,
                              max_count: int = 4) -> Optional[ConnectorLayout]:
    """Size the connector to the actual seam, and decide how many evenly
    spaced instances fit along it without crowding -- "bigger object, bigger
    (and more) connectors", grounded in the real cross-section at the cut
    rather than a fixed default. Returns None if the cross-section can't be
    sampled here (see cross_section_footprint)."""
    info = cross_section_footprint(vertices, cut_axis_index, position, u_axis_index, v_axis_index)
    if info is None:
        return None

    width = float(np.clip(min(info.span_a, info.span_b) * base_width_fraction, min_width, max_width))
    depth = width * 0.75
    seam_u = info.span_a  # span along axis_a_index, which the caller passes as u_axis_index

    count = connector_count_for_width(width, seam_u, min_gap_factor, max_count)

    return ConnectorLayout(width=width, depth=depth, count=count,
                            offsets=evenly_spaced_offsets(count, seam_u), seam_size=seam_u)
