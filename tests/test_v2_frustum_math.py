"""Contract tests for the pure-Python frustum/explosion math."""

from __future__ import annotations

import math
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from stage_10V2_product_story.scripts import frustum_math as fm


def make_camera(location, target, lens_mm=70.0):
    basis = fm.camera_frame(location, target)
    return basis, fm.fov_xy(lens_mm)


# ---------------------------------------------------------------------------
# camera frame + projection
# ---------------------------------------------------------------------------

def test_camera_frame_point_ahead_is_negative_z():
    basis = fm.camera_frame((0.0, -10.0, 0.0), (0.0, 0.0, 0.0))
    local = fm.world_to_camera((0.0, 0.0, 0.0), (0.0, -10.0, 0.0), basis)
    assert local[2] < 0.0  # in front of the lens
    assert abs(local[0]) < 1e-9 and abs(local[1]) < 1e-9


def test_camera_frame_is_orthonormal():
    right, up, back = fm.camera_frame((5.0, -7.0, 9.0), (1.0, 2.0, 3.0))
    for vec in (right, up, back):
        assert abs(fm.v_len(vec) - 1.0) < 1e-9
    assert abs(fm.v_dot(right, up)) < 1e-9
    assert abs(fm.v_dot(right, back)) < 1e-9
    assert abs(fm.v_dot(up, back)) < 1e-9


def test_fov_xy_matches_blender_70mm():
    fov_x, fov_y = fm.fov_xy(70.0)
    assert math.isclose(fov_x, 2.0 * math.atan(36.0 / 140.0), rel_tol=1e-9)
    assert fov_y < fov_x  # landscape frame narrows vertically


# ---------------------------------------------------------------------------
# screen discs
# ---------------------------------------------------------------------------

def test_screen_disc_centered_subject_has_zero_angle():
    basis, _fovs = make_camera((0.0, -100.0, 0.0), (0.0, 0.0, 0.0))
    disc = fm.screen_disc((0.0, 0.0, 0.0), 10.0, (0.0, -100.0, 0.0), basis)
    assert disc["center_angle"] < 1e-6
    assert math.isclose(disc["angular_radius"], math.asin(0.1), rel_tol=1e-9)
    assert disc["in_frustum"]


def test_discs_overlap_respects_direction_not_axis_angle():
    basis, _fovs = make_camera((0.0, -100.0, 0.0), (0.0, 0.0, 0.0))
    cam = (0.0, -100.0, 0.0)
    # Two points at the same polar angle from forward but opposite azimuths
    # must NOT be treated as overlapping.
    left = fm.screen_disc((-20.0, 0.0, 0.0), 2.0, cam, basis)
    right = fm.screen_disc((20.0, 0.0, 0.0), 2.0, cam, basis)
    assert not fm.discs_overlap(left, right)
    near = fm.screen_disc((-21.0, 0.0, 0.0), 2.0, cam, basis)
    assert fm.discs_overlap(left, near)


# ---------------------------------------------------------------------------
# offscreen distance
# ---------------------------------------------------------------------------

def test_offscreen_distance_leaves_through_nearest_plane():
    basis, fovs = make_camera((0.0, -100.0, 0.0), (0.0, 0.0, 0.0))
    cam = (0.0, -100.0, 0.0)
    point = (0.0, 0.0, 0.0)
    radius = 2.0
    # Moving left exits through the left plane; distance should be finite.
    d = fm.offscreen_distance(point, radius, (-1.0, 0.0, 0.0), cam, basis, fovs)
    assert d is not None and d > 0.0
    moved = fm.screen_disc(fm.v_add(point, (-d, 0.0, 0.0)), radius, cam, basis)
    assert not moved["in_frustum"] or not fm.discs_overlap(
        moved, fm.screen_disc(point, 1.0, cam, basis)
    )


def test_offscreen_distance_returns_none_when_moving_away():
    basis, fovs = make_camera((0.0, -100.0, 0.0), (0.0, 0.0, 0.0))
    # Moving straight away from the lens (receding down the view axis) never
    # leaves the side planes.
    d = fm.offscreen_distance(
        (0.0, 0.0, 0.0), 2.0, (0.0, 1.0, 0.0), (0.0, -100.0, 0.0), basis, fovs
    )
    assert d is None


def test_offscreen_distance_zero_when_already_outside():
    basis, fovs = make_camera((0.0, -100.0, 0.0), (0.0, 0.0, 0.0))
    d = fm.offscreen_distance(
        (-200.0, 0.0, 0.0), 2.0, (-1.0, 0.0, 0.0), (0.0, -100.0, 0.0), basis, fovs
    )
    assert d == 0.0


# ---------------------------------------------------------------------------
# clearance solver
# ---------------------------------------------------------------------------

def test_clear_subject_distance_zero_when_separated():
    basis, fovs = make_camera((0.0, -100.0, 0.0), (0.0, 0.0, 0.0))
    cam = (0.0, -100.0, 0.0)
    t = fm.clear_subject_distance(
        (-60.0, 0.0, 0.0), 2.0, (-1.0, 0.0, 0.0),
        (30.0, 0.0, 0.0), 5.0, cam, basis, fovs,
    )
    assert t == 0.0


def test_clear_subject_distance_finds_finite_travel():
    basis, fovs = make_camera((0.0, -100.0, 0.0), (0.0, 0.0, 0.0))
    cam = (0.0, -100.0, 0.0)
    focus = (5.0, 0.0, 0.0)
    t = fm.clear_subject_distance(
        (2.0, 0.0, 0.0), 8.0, (-1.0, 0.0, 0.0),
        focus, 10.0, cam, basis, fovs,
    )
    assert t is not None and t > 0.0
    moved = fm.screen_disc(
        fm.v_add((2.0, 0.0, 0.0), (-t, 0.0, 0.0)), 8.0, cam, basis
    )
    focus_disc = fm.screen_disc(focus, 10.0, cam, basis)
    assert not fm.discs_overlap(moved, focus_disc, 0.01)


def test_clear_subject_distance_is_deterministic():
    basis, fovs = make_camera((3.0, -100.0, 8.0), (1.0, 0.0, 2.0))
    cam = (3.0, -100.0, 8.0)
    args = dict(
        point=(2.0, 0.0, 0.0), radius=8.0, direction=(-1.0, -0.2, 0.1),
        focus_center=(5.0, 0.0, 0.0), focus_radius=10.0,
        cam_location=cam, basis=basis, fovs=fovs,
    )
    first = fm.clear_subject_distance(**args)
    second = fm.clear_subject_distance(**args)
    assert first == second


# ---------------------------------------------------------------------------
# framing + ranks + stagger + entry side
# ---------------------------------------------------------------------------

def test_framing_distance_fills_requested_fraction():
    _basis, fovs = make_camera((0.0, -100.0, 0.0), (0.0, 0.0, 0.0))
    distance = fm.framing_distance(50.0, fovs[1], screen_fraction=0.45)
    basis = fm.camera_frame((0.0, -distance, 0.0), (0.0, 0.0, 0.0))
    disc = fm.screen_disc((0.0, 0.0, 0.0), 50.0, (0.0, -distance, 0.0), basis)
    # Angular diameter should be ~45% of the vertical fov.
    assert math.isclose(disc["angular_radius"] * 2.0, fovs[1] * 0.45, rel_tol=0.02)


def test_assign_ranks_clusters_same_depth_parts():
    ranks = fm.assign_ranks({"A": 10.0, "B": 10.4, "C": 40.0, "D": 41.0}, tolerance=2.0)
    assert ranks["A"] == ranks["B"]
    assert ranks["C"] == ranks["D"]
    assert ranks["A"] != ranks["C"]


def test_staggered_window_partitions_and_orders():
    windows = [fm.staggered_window(i, 3, 0.0, 90.0, 0.25) for i in range(3)]
    assert windows[0][0] == 0.0
    assert windows[2][1] == 90.0
    assert windows[0][0] < windows[1][0] < windows[2][0]
    assert windows[0][1] > windows[1][0]  # overlap keeps motion continuous


def test_choose_entry_side_avoids_camera_side():
    to_camera = fm.v_norm((-1.0, 0.0, 0.0))  # camera sits on -X
    assert fm.choose_entry_side("-X", to_camera) != "-X"
    assert fm.choose_entry_side("+Y", to_camera) == "+Y"


def test_bounding_sphere_uses_half_diagonal():
    center, radius = fm.bounding_sphere((1.0, 2.0, 3.0), (10.0, 20.0, 30.0))
    assert center == (1.0, 2.0, 3.0)
    assert math.isclose(radius, math.sqrt(5**2 + 10**2 + 15**2), rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 2D hulls + NDC projection
# ---------------------------------------------------------------------------

def test_project_ndc_centers_target():
    basis = fm.camera_frame((0.0, -100.0, 0.0), (0.0, 0.0, 0.0))
    fovs = fm.fov_xy(70.0)
    assert fm.project_ndc((0.0, 0.0, 0.0), (0.0, -100.0, 0.0), basis, fovs) == (0.0, 0.0)
    assert fm.project_ndc((0.0, -150.0, 0.0), (0.0, -100.0, 0.0), basis, fovs) is None


def test_convex_hull_and_separation():
    square_a = fm.convex_hull_2d([(0, 0), (1, 0), (1, 1), (0, 1), (0.5, 0.5)])
    square_b = fm.convex_hull_2d([(2, 0), (3, 0), (3, 1), (2, 1)])
    overlap_c = fm.convex_hull_2d([(0.9, 0.1), (2, 0.1), (2, 0.9), (0.9, 0.9)])
    assert len(square_a) == 4  # interior point dropped
    assert fm.hulls_separated(square_a, square_b, margin_ndc=0.5)
    assert not fm.hulls_separated(square_a, square_b, margin_ndc=1.5)
    assert not fm.hulls_separated(square_a, overlap_c)


def test_hull_inside_frame_and_extent():
    hull = fm.convex_hull_2d([(-0.4, -0.4), (0.4, -0.4), (0.4, 0.4), (-0.4, 0.4)])
    assert fm.hull_inside_frame(hull, margin_ndc=0.5)
    assert not fm.hull_inside_frame(hull, margin_ndc=0.7)
    w, h = fm.hull_extent(hull)
    assert math.isclose(w, 0.8) and math.isclose(h, 0.8)
