"""Pure-Python camera-frustum and exploded-layout math for Task 10-V3.

Clean-room reimplementation of the algorithmic approach described in
docs/superpowers/research/2026-09-14-exploded-view-landscape.md (the
blender-exploded-assembly-studio addon's method). No bpy/mathutils: vectors
are plain 3-tuples so this module runs identically under pytest and inside
Blender's interpreter.

Conventions (match Blender):
- A camera looks down its local -Z with local +Y up.
- Camera-space points in front of the lens have z < 0.
- The perspective frustum is four side planes through the origin.
"""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

Vec3 = tuple[float, float, float]

EPSILON = 1e-9
SENSOR_WIDTH_MM = 36.0
RENDER_ASPECT = 1920.0 / 1080.0

# A side vector is "camera facing" when it points at the lens more than this.
CAMERA_FACING_LIMIT = 0.55

SIDE_ORDER = ("+X", "-X", "+Y", "-Y", "+Z", "-Z")
SIDE_VECTORS: dict[str, Vec3] = {
    "+X": (1.0, 0.0, 0.0),
    "-X": (-1.0, 0.0, 0.0),
    "+Y": (0.0, 1.0, 0.0),
    "-Y": (0.0, -1.0, 0.0),
    "+Z": (0.0, 0.0, 1.0),
    "-Z": (0.0, 0.0, -1.0),
}


# ---------------------------------------------------------------------------
# vector helpers
# ---------------------------------------------------------------------------

def v_add(a: Sequence[float], b: Sequence[float]) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def v_sub(a: Sequence[float], b: Sequence[float]) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def v_scale(a: Sequence[float], s: float) -> Vec3:
    return (a[0] * s, a[1] * s, a[2] * s)


def v_dot(a: Sequence[float], b: Sequence[float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def v_cross(a: Sequence[float], b: Sequence[float]) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def v_len(a: Sequence[float]) -> float:
    return math.sqrt(v_dot(a, a))


def v_norm(a: Sequence[float]) -> Vec3:
    length = v_len(a)
    if length <= EPSILON:
        raise ValueError("cannot normalise a zero-length vector")
    return (a[0] / length, a[1] / length, a[2] / length)


# ---------------------------------------------------------------------------
# camera model
# ---------------------------------------------------------------------------

def camera_frame(
    location: Sequence[float],
    target: Sequence[float],
    up_hint: Vec3 = (0.0, 0.0, 1.0),
) -> tuple[Vec3, Vec3, Vec3]:
    """Camera-space basis vectors (right, up, back) in world coordinates.

    back = +Z of the camera (away from the view direction); right/up follow
    Blender's `-Z`-forward / `+Y`-up convention.
    """
    back = v_norm(v_sub(location, target))
    right_raw = v_cross(up_hint, back)
    if v_len(right_raw) <= EPSILON:
        # Degenerate view (looking straight down +Z): pick a stable right.
        right_raw = v_cross((0.0, 1.0, 0.0), back)
    right = v_norm(right_raw)
    cam_up = v_cross(back, right)
    return right, cam_up, back


def world_to_camera(
    point: Sequence[float],
    cam_location: Sequence[float],
    basis: tuple[Vec3, Vec3, Vec3],
) -> Vec3:
    rel = v_sub(point, cam_location)
    right, cam_up, back = basis
    return (v_dot(rel, right), v_dot(rel, cam_up), v_dot(rel, back))


def fov_xy(
    lens_mm: float,
    sensor_width: float = SENSOR_WIDTH_MM,
    aspect: float = RENDER_ASPECT,
) -> tuple[float, float]:
    """Horizontal/vertical field of view for a Blender PERSP camera.

    With sensor fit AUTO and a landscape frame the horizontal FOV is driven
    by the sensor width; the vertical FOV follows the render aspect.
    """
    fov_x = 2.0 * math.atan(sensor_width / (2.0 * max(float(lens_mm), EPSILON)))
    fov_y = 2.0 * math.atan(math.tan(fov_x * 0.5) / aspect)
    return fov_x, fov_y


def frustum_planes(fov_x: float, fov_y: float) -> tuple[Vec3, Vec3, Vec3, Vec3]:
    """Inward normals of the four side planes, camera space (looking -Z)."""
    hx, hy = fov_x * 0.5, fov_y * 0.5
    return (
        (-math.cos(hx), 0.0, -math.sin(hx)),  # right edge
        (math.cos(hx), 0.0, -math.sin(hx)),   # left edge
        (0.0, -math.cos(hy), -math.sin(hy)),  # top edge
        (0.0, math.cos(hy), -math.sin(hy)),   # bottom edge
    )


# ---------------------------------------------------------------------------
# screen-space queries
# ---------------------------------------------------------------------------

def screen_disc(
    point: Sequence[float],
    radius: float,
    cam_location: Sequence[float],
    basis: tuple[Vec3, Vec3, Vec3],
) -> dict[str, Any]:
    """Angular view of a bounding sphere.

    Returns a dict with:
    - ``direction``: unit vector from the camera to the sphere center
    - ``angular_radius``: the sphere's angular radius in radians
    - ``near_depth``: distance from the lens to the sphere's near surface
      (<= 0 when the sphere is behind the camera)
    - ``in_frustum``: whether the disc intersects the frustum cone
    """
    rel = v_sub(point, cam_location)
    distance = v_len(rel)
    direction = v_norm(rel) if distance > EPSILON else (0.0, 0.0, -1.0)
    forward = v_scale(basis[2], -1.0)
    center_angle = math.acos(max(-1.0, min(1.0, v_dot(direction, forward))))
    if distance <= max(radius, EPSILON):
        angular_radius = math.pi / 2.0  # camera inside the sphere
    else:
        angular_radius = math.asin(min(1.0, radius / distance))
    near_depth = v_dot(rel, forward) - radius
    return {
        "direction": direction,
        "angular_radius": angular_radius,
        "center_angle": center_angle,
        "near_depth": near_depth,
        "in_frustum": near_depth > 0.0
        and (center_angle - angular_radius) < math.pi / 2.0,
    }


def disc_separation(dir_a: Sequence[float], dir_b: Sequence[float]) -> float:
    """Angular separation between two disc centers, in radians."""
    return math.acos(max(-1.0, min(1.0, v_dot(dir_a, dir_b))))


def discs_overlap(
    disc_a: Mapping[str, Any],
    disc_b: Mapping[str, Any],
    margin_rad: float = 0.0,
) -> bool:
    """True when two screen-space discs intersect on the image plane."""
    separation = disc_separation(disc_a["direction"], disc_b["direction"])
    return separation < (
        disc_a["angular_radius"] + disc_b["angular_radius"] + margin_rad
    )


def offscreen_distance(
    point: Sequence[float],
    radius: float,
    direction: Sequence[float],
    cam_location: Sequence[float],
    basis: tuple[Vec3, Vec3, Vec3],
    fovs: tuple[float, float],
    margin: float = 1.0,
) -> float | None:
    """Travel along ``direction`` until the sphere leaves the frustum.

    Every frustum plane passes through the camera origin, so the crossing
    distance on one plane is a single linear solve; the answer is the first
    plane crossed. Returns None when no plane is crossed (the sphere moves
    parallel to, or back into, the frustum).
    """
    local = world_to_camera(point, cam_location, basis)
    local_dir = world_to_camera(direction, (0.0, 0.0, 0.0), basis)
    padded = radius * margin
    best: float | None = None
    for normal in frustum_planes(*fovs):
        offset = v_dot(normal, local)
        slope = v_dot(normal, local_dir)
        if offset < -padded:
            return 0.0  # already outside this plane
        if slope < -EPSILON:
            candidate = (-padded - offset) / slope
            if candidate >= 0.0 and (best is None or candidate < best):
                best = candidate
    return best


def clear_subject_distance(
    point: Sequence[float],
    radius: float,
    direction: Sequence[float],
    focus_center: Sequence[float],
    focus_radius: float,
    cam_location: Sequence[float],
    basis: tuple[Vec3, Vec3, Vec3],
    fovs: tuple[float, float],
    margin_rad: float = 0.01,
    t_max: float | None = None,
    grid_steps: int = 64,
    bisect_steps: int = 40,
) -> float | None:
    """Extra travel along ``direction`` so this sphere's screen disc no
    longer overlaps the focus subject's disc (or it leaves the frustum).

    Deterministic: uniform grid scan for the first feasible bracket, then
    bisection. Returns None when no travel up to ``t_max`` clears the disc.
    """
    unit = v_norm(direction)
    focus_disc = screen_disc(focus_center, focus_radius, cam_location, basis)

    def clears(travel: float) -> bool:
        moved = v_add(point, v_scale(unit, travel))
        disc = screen_disc(moved, radius, cam_location, basis)
        if disc["near_depth"] <= 0.0 or not disc["in_frustum"]:
            return True  # behind the lens or outside the frame
        return not discs_overlap(disc, focus_disc, margin_rad)

    if clears(0.0):
        return 0.0

    if t_max is None:
        t_off = offscreen_distance(
            point, radius, unit, cam_location, basis, fovs
        )
        t_max = (t_off if t_off is not None else 0.0) + radius * 8.0 + 1.0
    if t_max <= 0.0:
        return None

    bracket: tuple[float, float] | None = None
    for step in range(1, grid_steps + 1):
        t = t_max * step / grid_steps
        if clears(t):
            bracket = (t_max * (step - 1) / grid_steps, t)
            break
    if bracket is None:
        return None
    low, high = bracket
    for _ in range(bisect_steps):
        mid = (low + high) * 0.5
        if clears(mid):
            high = mid
        else:
            low = mid
    return high


def framing_distance(
    radius: float,
    fov_y: float,
    screen_fraction: float,
) -> float:
    """Camera distance putting a sphere at ``screen_fraction`` of frame height.

    ``screen_fraction`` is the subject's angular diameter divided by the
    vertical FOV (0.45 = subject fills ~45% of frame height).
    """
    sine = math.sin(fov_y * 0.5)
    if sine <= EPSILON or screen_fraction <= EPSILON:
        return max(radius * 3.0, 1.0)
    return radius / (sine * screen_fraction)


# ---------------------------------------------------------------------------
# explosion layout helpers
# ---------------------------------------------------------------------------

def assign_ranks(
    projections: Mapping[str, float],
    tolerance: float,
) -> dict[str, int]:
    """Cluster parts into explosion layers by axis projection.

    Parts whose projections differ by <= ``tolerance`` share a rank, so a row
    of same-depth components lifts as one sheet instead of a staircase.
    """
    ordered = sorted(projections.items(), key=lambda item: item[1])
    ranks: dict[str, int] = {}
    rank = 0
    previous: float | None = None
    for part_id, key in ordered:
        if previous is None or (key - previous) > max(tolerance, EPSILON):
            rank += 1
        ranks[part_id] = rank
        previous = key
    return ranks


def staggered_window(
    index: int,
    count: int,
    low: float,
    high: float,
    overlap: float,
) -> tuple[float, float]:
    """Frame window for member ``index`` of ``count`` staggered movers."""
    if count <= 1 or high <= low:
        return float(low), float(high)
    overlap = min(max(overlap, 0.0), 0.999)
    span = high - low
    segment = span / (count - (count - 1) * overlap)
    step = segment * (1.0 - overlap)
    start = low + index * step
    return start, min(start + segment, high)


def choose_entry_side(natural: str, to_camera: Sequence[float]) -> str:
    """Pick the side a context panel enters from, avoiding the camera's side.

    The natural side wins unless it sweeps across the lens; otherwise the
    acceptable side most aligned with the natural direction is used.
    """
    natural_vector = SIDE_VECTORS[natural]
    if v_dot(natural_vector, to_camera) <= CAMERA_FACING_LIMIT:
        return natural
    acceptable = [
        side
        for side in SIDE_ORDER
        if v_dot(SIDE_VECTORS[side], to_camera) <= CAMERA_FACING_LIMIT
    ]
    if not acceptable:
        return min(SIDE_ORDER, key=lambda s: v_dot(SIDE_VECTORS[s], to_camera))
    return max(acceptable, key=lambda s: v_dot(SIDE_VECTORS[s], natural_vector))


def bounding_sphere(
    center: Sequence[float],
    dimensions: Sequence[float],
) -> tuple[Vec3, float]:
    """Bounding-sphere (center, radius) for a bbox centered at ``center``."""
    half = v_scale(dimensions, 0.5)
    return (tuple(center), v_len(half))


# ---------------------------------------------------------------------------
# 2D projection + silhouette hulls (NDC space, y up, x right, range ~[-1, 1])
# ---------------------------------------------------------------------------

def project_ndc(
    point: Sequence[float],
    cam_location: Sequence[float],
    basis: tuple[Vec3, Vec3, Vec3],
    fovs: tuple[float, float],
) -> tuple[float, float] | None:
    """Project a world point to normalized device coords; None behind lens."""
    local = world_to_camera(point, cam_location, basis)
    if local[2] >= -EPSILON:
        return None
    tan_x = math.tan(fovs[0] * 0.5)
    tan_y = math.tan(fovs[1] * 0.5)
    return (
        (local[0] / -local[2]) / tan_x,
        (local[1] / -local[2]) / tan_y,
    )


def convex_hull_2d(points: Sequence[Sequence[float]]) -> list[tuple[float, float]]:
    """Andrew monotone-chain convex hull, CCW order, no repeated start point."""
    pts = sorted({(float(p[0]), float(p[1])) for p in points})
    if len(pts) <= 2:
        return list(pts)

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list[tuple[float, float]] = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def _hull_axes(hull: Sequence[Sequence[float]]) -> list[tuple[float, float]]:
    axes = []
    for i in range(len(hull)):
        a = hull[i]
        b = hull[(i + 1) % len(hull)]
        edge = (b[0] - a[0], b[1] - a[1])
        norm = math.hypot(edge[0], edge[1])
        if norm > EPSILON:
            axes.append((-edge[1] / norm, edge[0] / norm))
    return axes


def _project_hull(hull: Sequence[Sequence[float]], axis: Sequence[float]) -> tuple[float, float]:
    dots = [p[0] * axis[0] + p[1] * axis[1] for p in hull]
    return min(dots), max(dots)


def hulls_overlap(
    hull_a: Sequence[Sequence[float]],
    hull_b: Sequence[Sequence[float]],
) -> bool:
    """Separating-axis test for two convex 2D hulls."""
    if len(hull_a) < 3 or len(hull_b) < 3:
        return False
    for axis in _hull_axes(hull_a) + _hull_axes(hull_b):
        low_a, high_a = _project_hull(hull_a, axis)
        low_b, high_b = _project_hull(hull_b, axis)
        if high_a < low_b or high_b < low_a:
            return False
    return True


def hull_distance(
    hull_a: Sequence[Sequence[float]],
    hull_b: Sequence[Sequence[float]],
) -> float:
    """Minimum vertex/edge distance between convex hulls (0 when touching)."""
    if hulls_overlap(hull_a, hull_b):
        return 0.0

    def point_seg_dist(p, a, b) -> float:
        abx, aby = b[0] - a[0], b[1] - a[1]
        denom = abx * abx + aby * aby
        t = 0.0 if denom <= EPSILON else max(
            0.0, min(1.0, ((p[0] - a[0]) * abx + (p[1] - a[1]) * aby) / denom)
        )
        return math.hypot(p[0] - (a[0] + abx * t), p[1] - (a[1] + aby * t))

    def hull_pts_dist(h1, h2) -> float:
        best = float("inf")
        for p in h1:
            for i in range(len(h2)):
                best = min(best, point_seg_dist(p, h2[i], h2[(i + 1) % len(h2)]))
        return best

    return min(hull_pts_dist(hull_a, hull_b), hull_pts_dist(hull_b, hull_a))


def hulls_separated(
    hull_a: Sequence[Sequence[float]],
    hull_b: Sequence[Sequence[float]],
    margin_ndc: float = 0.0,
) -> bool:
    """True when the two convex hulls keep at least ``margin_ndc`` screen gap."""
    if hulls_overlap(hull_a, hull_b):
        return False
    return hull_distance(hull_a, hull_b) >= margin_ndc


def hull_extent(hull: Sequence[Sequence[float]]) -> tuple[float, float]:
    """(width, height) of a hull in NDC units."""
    if not hull:
        return 0.0, 0.0
    xs = [p[0] for p in hull]
    ys = [p[1] for p in hull]
    return max(xs) - min(xs), max(ys) - min(ys)


def hull_inside_frame(
    hull: Sequence[Sequence[float]],
    margin_ndc: float = 0.0,
) -> bool:
    """All hull vertices inside the frame edges (NDC ±1) minus margin."""
    limit = 1.0 - margin_ndc
    return all(abs(p[0]) <= limit and abs(p[1]) <= limit for p in hull)
