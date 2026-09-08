"""Render reproducible orthographic and isometric views of the frozen scene."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

STANDARD_VIEWS = ("front", "rear", "left", "right", "top", "bottom")
ISO_VIEWS = (
    "iso_front_left",
    "iso_front_right",
    "iso_rear_left",
    "iso_rear_right",
)
INSPECTION_LIGHT_ENERGY = 4.0
VIEW_DIRECTIONS = {
    "front": (0.0, -1.0, 0.0),
    "rear": (0.0, 1.0, 0.0),
    "left": (-1.0, 0.0, 0.0),
    "right": (1.0, 0.0, 0.0),
    "top": (0.0, 0.0, 1.0),
    "bottom": (0.0, 0.0, -1.0),
    "iso_front_left": (-1.0, -1.0, 1.0),
    "iso_front_right": (1.0, -1.0, 1.0),
    "iso_rear_left": (-1.0, 1.0, 1.0),
    "iso_rear_right": (1.0, 1.0, 1.0),
}


def select_render_engine(available: set[str]) -> str:
    """Select a supported realtime engine across Blender 4/5 builds."""
    for preferred in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "BLENDER_WORKBENCH"):
        if preferred in available:
            return preferred
    if "CYCLES" in available:
        return "CYCLES"
    raise ValueError(f"no supported Blender render engine available: {sorted(available)}")


def inspection_light_energy() -> float:
    return INSPECTION_LIGHT_ENERGY

try:  # Blender is optional for the pure contract-test surface.
    import bpy  # type: ignore
    from mathutils import Vector  # type: ignore
except ImportError:  # pragma: no cover - only used outside Blender
    bpy = None  # type: ignore
    Vector = None  # type: ignore


def build_render_paths(project_root: Path) -> dict[str, Path]:
    """Return the complete standard/iso render allowlist."""
    directory = Path(project_root) / "output" / "reference_renders"
    names = (*STANDARD_VIEWS, *ISO_VIEWS)
    return {name: directory / f"{name}.png" for name in names}


def validate_source_object_facts(
    facts: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Validate source-only scene facts without changing the scene."""
    source = [
        fact
        for fact in facts
        if fact.get("type") == "MESH" and fact.get("source") == "original_stl"
    ]
    if len(source) != 82:
        raise ValueError(f"expected 82 source PART meshes, got {len(source)}")
    part_ids = sorted(str(fact.get("part_id")) for fact in source)
    expected = [f"PART_{index:03d}" for index in range(1, 83)]
    if part_ids != expected:
        raise ValueError("source PART ID coverage is not PART_001..PART_082")
    animated = sorted(
        str(fact.get("name"))
        for fact in source
        if fact.get("animation_data") is not None
    )
    transforms_changed = sorted(
        str(fact.get("name"))
        for fact in source
        if fact.get("transforms_changed") is True
    )
    return {
        "object_count": len(source),
        "geometry_counts": {
            "vertices": sum(int(fact.get("vertices", 0)) for fact in source),
            "polygons": sum(int(fact.get("polygons", 0)) for fact in source),
        },
        "animated_objects": animated,
        "transforms_changed": transforms_changed,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--blend", type=Path)
    parser.add_argument("--resolution", type=int, default=640)
    args = parser.parse_args(_script_arguments(argv))
    if bpy is None:
        print("Blender bpy is required.", file=sys.stderr)
        return 2

    root = args.project_root.expanduser().resolve()
    blend = (
        args.blend.expanduser().resolve()
        if args.blend is not None
        else root / "output/stage01_split.blend"
    )
    if not blend.is_file():
        raise FileNotFoundError(f"Stage 01 blend does not exist: {blend}")
    bpy.ops.wm.open_mainfile(filepath=str(blend))
    objects = _source_objects()
    facts = [_facts(obj) for obj in objects]
    validation = validate_source_object_facts(facts)
    if validation["geometry_counts"] != {"vertices": 221902, "polygons": 444296}:
        raise ValueError(f"frozen geometry totals changed: {validation}")
    _configure_render(args.resolution)
    paths = build_render_paths(root)
    paths[STANDARD_VIEWS[0]].parent.mkdir(parents=True, exist_ok=True)
    material = _material("Task08_Inspection_Gray", (0.42, 0.45, 0.5, 1.0))
    for obj in objects:
        _assign_material(obj, material)
    camera = _new_camera()
    light = _new_light()
    for name, path in paths.items():
        _aim_camera(camera, name, objects)
        _aim_light(light, camera)
        bpy.context.scene.camera = camera
        bpy.context.scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
    _remove_temporary(camera)
    _remove_temporary(light)
    print(f"Rendered {len(paths)} reference views.")
    return 0


def _source_objects() -> list[Any]:
    return sorted(
        [
            obj
            for obj in bpy.data.objects
            if obj.type == "MESH" and obj.get("source") == "original_stl"
        ],
        key=lambda obj: str(obj.get("part_id", obj.name)),
    )


def _facts(obj: Any) -> dict[str, Any]:
    return {
        "name": obj.name,
        "part_id": obj.get("part_id"),
        "type": obj.type,
        "source": obj.get("source"),
        "vertices": len(obj.data.vertices),
        "polygons": len(obj.data.polygons),
        "location": list(obj.location),
        "rotation_euler": list(obj.rotation_euler),
        "scale": list(obj.scale),
        "animation_data": obj.animation_data,
    }


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
    scene.render.film_transparent = False
    scene.world.color = (0.92, 0.92, 0.92)
    if scene.world is not None and scene.world.use_nodes:
        background = scene.world.node_tree.nodes.get("Background")
        if background is not None:
            background.inputs["Color"].default_value = (0.16, 0.16, 0.16, 1.0)
            background.inputs["Strength"].default_value = 0.35


def _new_camera() -> Any:
    camera_data = bpy.data.cameras.new("Task08_Inspection_Camera")
    camera_data.type = "ORTHO"
    camera = bpy.data.objects.new("Task08_Inspection_Camera", camera_data)
    bpy.context.scene.collection.objects.link(camera)
    return camera


def _new_light() -> Any:
    light_data = bpy.data.lights.new("Task08_Inspection_Sun", type="SUN")
    light_data.energy = INSPECTION_LIGHT_ENERGY
    light_data.angle = 0.35
    light = bpy.data.objects.new("Task08_Inspection_Sun", light_data)
    bpy.context.scene.collection.objects.link(light)
    return light


def _aim_light(light: Any, camera: Any) -> None:
    light.location = camera.location
    light.rotation_euler = camera.rotation_euler


def _aim_camera(camera: Any, view_name: str, objects: Sequence[Any]) -> None:
    minimum, maximum = _world_bounds(objects)
    center = (minimum + maximum) * 0.5
    direction = Vector(VIEW_DIRECTIONS[view_name]).normalized()
    extent = maximum - minimum
    projected = max(
        abs(direction.x) * extent.x + abs(direction.y) * extent.y,
        abs(direction.x) * extent.x + abs(direction.z) * extent.z,
        abs(direction.y) * extent.y + abs(direction.z) * extent.z,
    )
    camera.data.ortho_scale = max(float(projected) * 1.25, 1.0)
    camera.location = center - direction * max(float(extent.length) * 1.6, 10.0)
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def _world_bounds(objects: Sequence[Any]) -> tuple[Any, Any]:
    corners = [
        obj.matrix_world @ Vector(corner)
        for obj in objects
        for corner in obj.bound_box
    ]
    minimum = Vector(
        min(corner[index] for corner in corners) for index in range(3)
    )
    maximum = Vector(
        max(corner[index] for corner in corners) for index in range(3)
    )
    return minimum, maximum


def _material(name: str, color: tuple[float, float, float, float]) -> Any:
    material = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    material.diffuse_color = color
    material.use_nodes = True
    principled = material.node_tree.nodes.get("Principled BSDF")
    if principled:
        principled.inputs["Base Color"].default_value = color
        principled.inputs["Roughness"].default_value = 0.72
    return material


def _assign_material(obj: Any, material: Any) -> None:
    if obj.data.materials:
        obj.data.materials[0] = material
    else:
        obj.data.materials.append(material)


def _remove_temporary(obj: Any) -> None:
    bpy.data.objects.remove(obj, do_unlink=True)


def _script_arguments(argv: Sequence[str] | None) -> list[str]:
    if argv is not None:
        return list(argv)
    arguments = list(sys.argv[1:])
    if "--" in arguments:
        arguments = arguments[arguments.index("--") + 1:]
    return arguments


if __name__ == "__main__":
    raise SystemExit(main())
