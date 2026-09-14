"""Render the six V1.1 lookdev reference stills from the presentation master.

Frames reuse the inherited V4 timeline so isolate visibility, explosion poses
and fitted cameras match the product story exactly:

  01 overview      frame   1  CAM_STORY_HERO
  02 architecture  frame 120  CAM_STORY_HERO      (PRIMARY_ARCHITECTURE mid)
  03 sensor        frame 232  CAM_STORY_SENSOR    (SENSOR_FOCUS mid)
  04 pcb           frame 360  CAM_STORY_PCB       (PCB_FOCUS mid)
  05 power         frame 562  CAM_STORY_POWER     (POWER_FOCUS mid)
  06 pcb closeup   frame 360  CAM_LOOKDEV_PCB_CLOSEUP

Output: web_presentation_v11/renders/0X_*.png @1920x1080 EEVEE.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:  # pragma: no cover - Blender-only
    import bpy  # type: ignore
    from mathutils import Vector  # type: ignore
except ImportError:  # pragma: no cover
    bpy = None  # type: ignore

MASTER = "web_presentation_v11/web_presentation_master.blend"
RENDER_DIR = "web_presentation_v11/renders"

# Last column: subject bbox fill fraction of the frame (width and height).
SHOTS = [
    ("01_overview_hero", 1, "CAM_STORY_HERO",
     ("PART_001", "PART_002", "PART_005"), 0.62),
    ("02_architecture", 120, "CAM_STORY_HERO",
     ("PART_001", "PART_004", "PART_019", "PART_020"), 0.75),
    ("03_sensor_inspection", 232, "CAM_STORY_SENSOR",
     ("PART_003", "PART_012", "PART_013", "PART_014"), 0.62),
    ("04_pcb_inspection", 360, "CAM_STORY_PCB",
     ("PART_019",), 0.60),
    ("05_power_inspection", 562, "CAM_STORY_POWER",
     ("PART_008", "PART_009", "PART_010", "PART_011", "PART_015", "PART_016"), 0.62),
    ("06_pcb_closeup", 360, "CAM_LOOKDEV_PCB_CLOSEUP",
     ("PART_019",), 0.85),
]


import math


def _subject_corners(part_ids: tuple[str, ...]) -> list["Vector"]:
    """World-space corners of every named part's local bbox (tight — no
    intermediate world AABB, which would inflate a rotated part's extent)."""
    out: list["Vector"] = []
    for obj in bpy.data.objects:
        if str(obj.get("part_id")) in part_ids and obj.type == "MESH":
            for corner in obj.bound_box:
                out.append(obj.matrix_world @ Vector(corner))
    return out


def _lookdev_camera(name: str, src_cam: object, corners: list["Vector"],
                    fill: float) -> object:
    """Temporary camera that frames the subject to `fill` of the frame.

    Distance is solved from the subject's true projected half-extents on the
    camera's right/up axes — corners are projected directly, so a rotated
    board's silhouette is measured exactly instead of via a fattened
    world-space AABB.
    """
    cam_data = bpy.data.cameras.new(name)
    cam_data.lens = src_cam.data.lens
    cam_data.sensor_width = src_cam.data.sensor_width
    cam_data.sensor_fit = src_cam.data.sensor_fit
    # mm-scale scene needs the story cameras' deep clip range — the 1000mm
    # default clips subjects beyond ~1m and renders them invisible
    cam_data.clip_start = src_cam.data.clip_start
    cam_data.clip_end = src_cam.data.clip_end
    cam = bpy.data.objects.new(name, cam_data)
    bpy.context.scene.collection.objects.link(cam)

    center = Vector((0.0, 0.0, 0.0))
    for p in corners:
        center += p
    center /= max(len(corners), 1)
    src_pos = src_cam.matrix_world.translation
    view_dir = (src_pos - center).normalized()
    rot = view_dir.to_track_quat("Z", "Y").to_euler().to_matrix()
    right, up = rot.col[0], rot.col[1]

    x_half = max(abs(right.dot(p - center)) for p in corners)
    y_half = max(abs(up.dot(p - center)) for p in corners)
    aspect = 1920.0 / 1080.0
    tan_h = math.tan(math.atan(cam_data.sensor_width / (2.0 * cam_data.lens)))
    tan_v = tan_h / aspect
    dist = max(x_half / (tan_h * fill), y_half / (tan_v * fill))

    cam.location = center + view_dir * dist
    look = center - cam.location
    cam.rotation_euler = look.to_track_quat("-Z", "Y").to_euler()
    cam_data.dof.use_dof = True
    cam_data.dof.focus_distance = look.length
    cam_data.dof.aperture_fstop = 6.3
    return cam, center, view_dir


def _measure_fill(img_path: Path) -> float:
    """Subject pixel coverage against a pure-black probe background.

    Probes render with world strength 0, so any pixel above noise floor is
    subject. Returns the larger of the row/column occupancy fractions.
    """
    img = bpy.data.images.load(str(img_path))
    w, h = img.size
    px = img.pixels[:]
    bpy.data.images.remove(img)

    def lum(x: int, y: int) -> float:
        i = (y * w + x) * 4
        return px[i] * 0.3 + px[i + 1] * 0.59 + px[i + 2] * 0.11

    thr = 0.03
    rows = [y for y in range(0, h, 2)
            if any(lum(x, y) > thr for x in range(2, w - 2, 4))]
    cols = [x for x in range(0, w, 2)
            if any(lum(x, y) > thr for y in range(2, h - 2, 4))]
    if not rows or not cols:
        return 0.0
    return max((max(rows) - min(rows)) / h, (max(cols) - min(cols)) / w)


def _frame_subject(scene: object, cam: object, center: "Vector",
                   view_dir: "Vector", fill: float, out_path: Path) -> None:
    """Render against black world, measure coverage, re-solve, repeat.

    Projected-bbox math disagrees with what EEVEE actually draws for rotated
    parts; empirical convergence is robust. World/floor state is restored
    afterwards so the final render keeps its gradient + contact shadow.
    """
    bg = None
    if scene.world and scene.world.node_tree:
        bg = scene.world.node_tree.nodes.get("Background")
    saved_strength = bg.inputs["Strength"].default_value if bg else None
    floor = bpy.data.objects.get("LOOKDEV_FLOOR")
    floor_saved = floor.hide_render if floor else None
    if bg:
        bg.inputs["Strength"].default_value = 0.0
    if floor:
        floor.hide_render = True
    try:
        dist = (cam.location - center).length
        for _ in range(4):
            scene.render.filepath = str(out_path)
            bpy.ops.render.render(write_still=True)
            actual = _measure_fill(out_path)
            if actual <= 0.0 or abs(actual - fill) < 0.05:
                break
            dist *= actual / fill
            cam.location = center + view_dir * dist
            cam.data.dof.focus_distance = (center - cam.location).length
    finally:
        if bg and saved_strength is not None:
            bg.inputs["Strength"].default_value = saved_strength
        if floor and floor_saved is not None:
            floor.hide_render = floor_saved


def render_all(project_root: Path) -> dict[str, object]:
    if bpy is None:
        raise RuntimeError("Blender bpy required")
    root = Path(project_root).expanduser().resolve()
    bpy.ops.wm.open_mainfile(filepath=str(root / MASTER))
    scene = bpy.context.scene
    # engine stays whatever the master was saved with (EEVEE in V2)
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    # lookdev stills read brighter than the motion cut — product CGI needs
    # luminous mid-tones, not a murky render
    scene.view_settings.exposure = 2.3
    # timeline camera markers would re-bind scene.camera during render —
    # detach them for this session so the temp lookdev cameras are used
    for marker in scene.timeline_markers:
        marker.camera = None

    out_dir = root / RENDER_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, frame, cam_name, subject_parts, fill in SHOTS:
        src_cam = bpy.data.objects.get(cam_name)
        if src_cam is None:
            raise RuntimeError(f"camera {cam_name} missing from master")
        scene.frame_set(frame)
        # hide annotation text AFTER frame_set — f-curves re-evaluate on set
        for obj in bpy.data.objects:
            if obj.type == "FONT":
                obj.hide_render = True
                obj.hide_viewport = True
        corners = _subject_corners(subject_parts)
        cam, center, view_dir = _lookdev_camera(f"LOOKDEV_{name}", src_cam,
                                               corners, fill)
        print(f"[lookdev] {name}: dist={round((cam.location - center).length)} "
              f"cam={[round(v) for v in cam.location]}")
        scene.camera = cam
        # converge framing on a low-res probe, then render final at full res
        scene.render.resolution_percentage = 30
        probe = out_dir / f"_{name}_probe.png"
        _frame_subject(scene, cam, center, view_dir, fill, probe)
        scene.render.resolution_percentage = 100
        path = out_dir / f"{name}.png"
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        probe.unlink(missing_ok=True)
        cam_data_ref = cam.data
        bpy.data.objects.remove(cam)
        bpy.data.cameras.remove(cam_data_ref)
        written.append(str(path))
    return {"renders": written, "count": len(written)}


def _argv() -> list[str]:
    a = sys.argv[1:]
    return a[a.index("--") + 1 :] if "--" in a else a


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args(argv if argv is not None else _argv())
    print(json.dumps(render_all(args.project_root), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
