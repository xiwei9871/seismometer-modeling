"""Generate PART, duplicate-group, and semantic inspection preview renders."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
_IMAGE_PYTHON_OVERRIDE: Path | None = None
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.task08_data import load_json, load_manifest
from scripts.generate_reference_views import (
    inspection_light_energy,
    select_render_engine,
)

CONTACT_SHEET_PAGE_SIZE = 25
VIEW_NAMES = ("front", "side", "top", "iso")
CLASS_NAMES = ("major", "medium", "small")

try:  # Blender is optional for contract tests.
    import bpy  # type: ignore
    from mathutils import Vector  # type: ignore
except ImportError:  # pragma: no cover
    bpy = None  # type: ignore
    Vector = None  # type: ignore


def required_part_ids() -> list[str]:
    return [f"PART_{index:03d}" for index in range(1, 83)]


def required_part_highlight_names() -> list[str]:
    return [f"{part_id}_iso.png" for part_id in required_part_ids()]


def project_package_root(script_path: str | Path) -> Path:
    return Path(script_path).resolve().parent.parent


def build_contact_sheet_pages(
    part_ids: Sequence[str], page_size: int = CONTACT_SHEET_PAGE_SIZE
) -> list[list[str]]:
    if page_size <= 0:
        raise ValueError("contact sheet page size must be positive")
    return [
        list(part_ids[index:index + page_size])
        for index in range(0, len(part_ids), page_size)
    ]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--blend", type=Path)
    parser.add_argument("--resolution", type=int, default=480)
    parser.add_argument("--image-python", type=Path)
    args = parser.parse_args(_script_arguments(argv))
    if bpy is None:
        print("Blender bpy is required.", file=sys.stderr)
        return 2

    root = args.project_root.expanduser().resolve()
    global _IMAGE_PYTHON_OVERRIDE
    if args.image_python is not None:
        _IMAGE_PYTHON_OVERRIDE = args.image_python.expanduser().resolve()
    blend = (
        args.blend.expanduser().resolve()
        if args.blend is not None
        else root / "output/stage01_split.blend"
    )
    if not blend.is_file():
        raise FileNotFoundError(f"Stage 01 blend does not exist: {blend}")
    manifest = load_manifest(root)
    manifest_by_part = {record["part_id"]: record for record in manifest}
    bpy.ops.wm.open_mainfile(filepath=str(blend))
    objects = {
        str(obj.get("part_id")): obj
        for obj in bpy.data.objects
        if obj.type == "MESH" and obj.get("source") == "original_stl"
    }
    if sorted(objects) != required_part_ids():
        raise ValueError("frozen blend does not contain all 82 source PART IDs")
    if sum(len(obj.data.polygons) for obj in objects.values()) != 444296:
        raise ValueError("frozen blend polygon total changed")
    if sum(len(obj.data.vertices) for obj in objects.values()) != 221902:
        raise ValueError("frozen blend vertex total changed")

    output = root / "output"
    preview_dir = output / "part_previews"
    group_dir = output / "reports/duplicate_groups"
    highlight_dir = output / "part_id_renders"
    individual_highlight_dir = output / "part_highlights"
    for directory in (preview_dir, group_dir, highlight_dir, individual_highlight_dir):
        directory.mkdir(parents=True, exist_ok=True)
    _configure_render(args.resolution)
    camera = _new_camera()
    light = _new_light()
    for part_id in required_part_ids():
        record = manifest_by_part[part_id]
        dimensions = record.get("bbox_dimensions", record.get("bbox", {}))
        duplicate = record.get("duplicate_group") or "-"
        label = (
            f"{part_id}\n"
            f"BBox: {_format_dimensions(dimensions)}\n"
            f"Faces: {int(record.get('face_count', 0)):,}  DG: {duplicate}"
        )
        _render_isolated(
            objects[part_id],
            camera,
            light,
            preview_dir / f"{part_id}.png",
            label=label,
        )
    groups = load_json(root / "data/duplicate_groups.json").get("groups", [])
    for group in groups:
        group_id = str(group["group_id"])
        members = list(group["parts"])
        representative = objects[members[0]]
        record = manifest_by_part[members[0]]
        dimensions = record.get("bbox_dimensions", record.get("bbox", {}))
        member_label = ", ".join(members[:4])
        if len(members) > 4:
            member_label += ", ..."
        label = (
            f"{group_id}  Qty: {len(members)}\n"
            f"BBox: {_format_dimensions(dimensions)}\n"
            f"Faces: {int(record.get('face_count', 0)):,}\n"
            f"Parts: {member_label}"
        )
        _render_isolated(
            representative,
            camera,
            light,
            group_dir / f"{group_id}.png",
            label=label,
        )
        (group_dir / f"{group_id}.json").write_text(
            json.dumps(
                {
                    "group_id": group_id,
                    "quantity": len(members),
                    "parts": members,
                    "representative_part": members[0],
                    "image": str(group_dir / f"{group_id}.png"),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    _render_highlight_views(objects, camera, light, highlight_dir, manifest)
    _render_individual_highlights(objects, camera, light, individual_highlight_dir)
    _remove_temporary(camera)
    _remove_temporary(light)
    _write_contact_sheets(preview_dir, output / "reports", required_part_ids())
    print("Rendered 82 PART previews and duplicate-group previews.")
    return 0


def _render_isolated(
    obj: Any,
    camera: Any,
    light: Any,
    path: Path,
    *,
    label: str,
) -> None:
    for candidate in bpy.data.objects:
        if candidate.type == "MESH":
            _set_visibility(candidate, candidate == obj)
    minimum, maximum = _object_bounds(obj)
    _aim_camera(camera, minimum, maximum, view="iso")
    _aim_light(light, camera)
    bpy.context.scene.camera = camera
    raw_path = path.with_name(f"{path.stem}.raw{path.suffix}")
    bpy.context.scene.render.filepath = str(raw_path)
    bpy.ops.render.render(write_still=True)
    _annotate_image(raw_path, path, label)


def _render_highlight_views(
    objects: Mapping[str, Any],
    camera: Any,
    light: Any,
    output: Path,
    manifest: Sequence[Mapping[str, Any]],
) -> None:
    classes = {
        "major": {r["part_id"] for r in manifest if r.get("size_class") == "MAJOR"},
        "medium": {r["part_id"] for r in manifest if r.get("size_class") == "MEDIUM"},
        "small": {r["part_id"] for r in manifest if r.get("size_class") == "SMALL"},
    }
    for view in VIEW_NAMES:
        _render_all(
            objects,
            camera,
            light,
            output / f"part_id_{view}.png",
            view,
            label=f"PART ID inspection: {view}",
        )
    for class_name, selected in classes.items():
        _render_all(
            objects,
            camera,
            light,
            output / f"part_id_{class_name}_iso.png",
            "iso",
            selected=selected,
            label=f"PART ID inspection: {class_name.upper()}",
        )


def _render_individual_highlights(
    objects: Mapping[str, Any],
    camera: Any,
    light: Any,
    output: Path,
) -> None:
    """Render each PART in its original assembled position with one part highlighted."""
    for part_id in required_part_ids():
        _render_all(
            objects,
            camera,
            light,
            output / f"{part_id}_iso.png",
            "iso",
            selected={part_id},
            label=f"Highlight: {part_id}",
        )


def _render_all(
    objects: Mapping[str, Any],
    camera: Any,
    light: Any,
    path: Path,
    view: str,
    *,
    selected: set[str] | None = None,
    label: str,
) -> None:
    material = _material("Task08_Part_ID_Inspection", (0.24, 0.52, 0.85, 1.0))
    muted = _material("Task08_Muted_Inspection", (0.12, 0.12, 0.12, 1.0))
    for part_id, obj in objects.items():
        _set_visibility(obj, True)
        _assign_material(obj, material if selected is None or part_id in selected else muted)
    minimum, maximum = _objects_bounds(list(objects.values()))
    _aim_camera(camera, minimum, maximum, view=view)
    _aim_light(light, camera)
    bpy.context.scene.camera = camera
    raw_path = path.with_name(f"{path.stem}.raw{path.suffix}")
    bpy.context.scene.render.filepath = str(raw_path)
    bpy.ops.render.render(write_still=True)
    _annotate_image(raw_path, path, label)


def _set_visibility(obj: Any, visible: bool) -> None:
    obj.hide_render = not visible


def _object_bounds(obj: Any) -> tuple[Any, Any]:
    corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    return (
        Vector(min(c[index] for c in corners) for index in range(3)),
        Vector(max(c[index] for c in corners) for index in range(3)),
    )


def _objects_bounds(objects: Sequence[Any]) -> tuple[Any, Any]:
    bounds = [_object_bounds(obj) for obj in objects]
    return (
        Vector(min(pair[0][index] for pair in bounds) for index in range(3)),
        Vector(max(pair[1][index] for pair in bounds) for index in range(3)),
    )


def _aim_camera(camera: Any, minimum: Any, maximum: Any, view: str) -> None:
    directions = {
        "front": Vector((0, -1, 0)),
        "side": Vector((1, 0, 0)),
        "top": Vector((0, 0, 1)),
        "iso": Vector((1, -1, 1)),
    }
    center = (minimum + maximum) * 0.5
    extent = maximum - minimum
    direction = directions[view].normalized()
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = max(
        float(max(extent.x, extent.y, extent.z) * 1.35), 1.0
    )
    camera.location = center - direction * max(float(extent.length) * 1.8, 10.0)
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def _configure_render(resolution: int) -> None:
    scene = bpy.context.scene
    available = {
        item.identifier
        for item in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items
    }
    scene.render.engine = select_render_engine(available)
    scene.render.resolution_x = resolution
    scene.render.resolution_y = resolution
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.world.color = (0.92, 0.92, 0.92)


def _new_camera() -> Any:
    data = bpy.data.cameras.new("Task08_Preview_Camera")
    obj = bpy.data.objects.new("Task08_Preview_Camera", data)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def _new_light() -> Any:
    data = bpy.data.lights.new("Task08_Preview_Sun", type="SUN")
    data.energy = inspection_light_energy()
    data.angle = 0.35
    obj = bpy.data.objects.new("Task08_Preview_Area", data)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def _aim_light(light: Any, camera: Any) -> None:
    light.location = camera.location
    light.rotation_euler = camera.rotation_euler


def _material(name: str, color: tuple[float, float, float, float]) -> Any:
    material = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    material.diffuse_color = color
    material.use_nodes = True
    node = material.node_tree.nodes.get("Principled BSDF")
    if node:
        node.inputs["Base Color"].default_value = color
        node.inputs["Roughness"].default_value = 0.8
    return material


def _assign_material(obj: Any, material: Any) -> None:
    if obj.data.materials:
        obj.data.materials[0] = material
    else:
        obj.data.materials.append(material)


def _write_contact_sheets(preview_dir: Path, report_dir: Path, part_ids: Sequence[str]) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    for index, page in enumerate(build_contact_sheet_pages(part_ids), start=1):
        manifest_path = report_dir / f"part_contact_sheet_{index:02d}.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "page": index,
                    "parts": page,
                    "images": [str(preview_dir / f"{p}.png") for p in page],
                },
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )
        output = report_dir / f"part_contact_sheet_{index:02d}.png"
        _render_contact_sheet(page, preview_dir, output)


def _render_contact_sheet(
    part_ids: Sequence[str], preview_dir: Path, output: Path
) -> None:
    """Create a real tiled PNG from the already rendered thumbnails."""
    image_python = _image_python(output)
    compose = Path(__file__).with_name("compose_task08_images.py")
    command = [
        str(image_python),
        str(compose),
        "tile",
        "--output",
        str(output),
        "--columns",
        "5",
        "--rows",
        "5",
        *[str(preview_dir / f"{part_id}.png") for part_id in part_ids],
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0 or not output.is_file():
        raise RuntimeError(
            f"contact sheet failed: {completed.stderr.strip() or completed.returncode}"
        )


def _annotate_image(raw_path: Path, output: Path, label: str) -> None:
    command = [
        str(_image_python(raw_path)),
        str(Path(__file__).with_name("compose_task08_images.py")),
        "annotate",
        "--input",
        str(raw_path),
        "--output",
        str(output),
        "--label",
        label,
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    try:
        if completed.returncode != 0 or not output.is_file():
            raise RuntimeError(
                f"image annotation failed: {completed.stderr.strip() or completed.returncode}"
            )
    finally:
        if raw_path.exists():
            raw_path.unlink()


def _format_dimensions(dimensions: Any) -> str:
    if isinstance(dimensions, Mapping):
        values = [dimensions.get(axis, 0.0) for axis in ("x", "y", "z")]
    else:
        values = list(dimensions)
    return " × ".join(f"{float(value):.1f}" for value in values) + " mm"


def _image_python(_path: Path) -> Path:
    project_root = Path(__file__).resolve().parent.parent
    if _IMAGE_PYTHON_OVERRIDE is not None:
        if not _IMAGE_PYTHON_OVERRIDE.is_file():
            raise FileNotFoundError(
                f"configured image Python does not exist: {_IMAGE_PYTHON_OVERRIDE}"
            )
        return _IMAGE_PYTHON_OVERRIDE
    candidate = project_root / ".venv/bin/python"
    if candidate.is_file():
        return candidate
    environment = Path(
        __import__("os").environ.get("TASK08_IMAGE_PYTHON", sys.executable)
    )
    return environment


def _remove_temporary(obj: Any) -> None:
    bpy.data.objects.remove(obj, do_unlink=True)


def _script_arguments(argv: Sequence[str] | None) -> list[str]:
    if argv is not None:
        return list(argv)
    args = list(sys.argv[1:])
    return args[args.index("--") + 1:] if "--" in args else args


if __name__ == "__main__":
    raise SystemExit(main())
