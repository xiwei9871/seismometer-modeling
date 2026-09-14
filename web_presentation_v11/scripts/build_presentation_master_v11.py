"""Build web_presentation_master.blend — V1.1 Phase A (Blender Asset Pass).

Starts from product_story_v2.blend so the master inherits the full V4 motion,
isolate-visibility schedule and fitted cameras. This pass only adds the
presentation layer (spec §4: SOURCE stays untouched):

- unified MAT_* PBR library (§23) assigned by presentation priority
- bevel + smooth-by-angle normals on every HERO/PRIMARY part (§7–8)
- MAIN_PCB_PRESENTATION_V2: +34 Level-B detail components parented to the
  board, procedural solder-mask surface variation (§12–15)
- studio rig retune + LOOKDEV cameras (§25–35)

Nothing here edits source mesh data. Bevels are non-destructive modifiers.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import random
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:  # pragma: no cover - Blender-only
    import bpy  # type: ignore
    from mathutils import Vector  # type: ignore
except ImportError:  # pragma: no cover
    bpy = None  # type: ignore

SOURCE_SCENE = "stage_10V2_product_story/scene/product_story_v2.blend"
MASTER_OUTPUT = "web_presentation_v11/web_presentation_master.blend"

# ---------------------------------------------------------------------------
# Material library (spec §23). Values are linear-space RGBA.
# ---------------------------------------------------------------------------

MATERIALS: dict[str, dict[str, float | tuple[float, ...]]] = {
    "MAT_black_polymer":   {"base": (0.030, 0.032, 0.038, 1), "rough": 0.50, "metal": 0.0, "coat": 0.18},
    "MAT_orange_polymer":  {"base": (0.68, 0.19, 0.030, 1),  "rough": 0.36, "metal": 0.0, "coat": 0.28},
    "MAT_handle_polymer":  {"base": (0.038, 0.040, 0.046, 1), "rough": 0.58, "metal": 0.0, "coat": 0.10},
    "MAT_pcb_soldermask":  {"base": (0.024, 0.115, 0.052, 1), "rough": 0.40, "metal": 0.08},
    "MAT_ic_black":        {"base": (0.014, 0.015, 0.018, 1), "rough": 0.34, "metal": 0.18},
    "MAT_connector_dark":  {"base": (0.026, 0.028, 0.032, 1), "rough": 0.40, "metal": 0.30},
    "MAT_machined_metal":  {"base": (0.32, 0.34, 0.37, 1),   "rough": 0.30, "metal": 0.95},
    "MAT_structural_metal":{"base": (0.16, 0.17, 0.19, 1),   "rough": 0.42, "metal": 0.80},
    "MAT_battery_charcoal":{"base": (0.052, 0.055, 0.062, 1), "rough": 0.52, "metal": 0.05, "coat": 0.15},
    "MAT_sensor_fixture":  {"base": (0.15, 0.16, 0.18, 1),  "rough": 0.34, "metal": 0.55},
    "MAT_sensor_core":     {"base": (0.38, 0.40, 0.44, 1),   "rough": 0.26, "metal": 0.78},
    "MAT_pcb_shield":      {"base": (0.30, 0.32, 0.35, 1),   "rough": 0.26, "metal": 0.92},
    "MAT_cap_metal":       {"base": (0.14, 0.15, 0.17, 1),   "rough": 0.30, "metal": 0.85},
}

# part_id -> material name + bevel width mm (§7.1 scale-aware, not uniform)
PART_LOOK: dict[str, tuple[str, float]] = {
    "PART_001": ("MAT_orange_polymer", 1.4),
    "PART_002": ("MAT_black_polymer", 1.2),
    "PART_004": ("MAT_black_polymer", 0.9),
    "PART_005": ("MAT_handle_polymer", 1.1),
    "PART_017": ("MAT_connector_dark", 0.5),
    "PART_018": ("MAT_connector_dark", 0.5),
    "PART_003": ("MAT_sensor_fixture", 0.8),
    "PART_012": ("MAT_sensor_core", 0.6),
    "PART_013": ("MAT_sensor_core", 0.6),
    "PART_014": ("MAT_sensor_core", 0.6),
    "PART_019": ("MAT_pcb_soldermask", 0.15),
    "PART_006": ("MAT_structural_metal", 0.5),
    "PART_007": ("MAT_structural_metal", 0.3),
    "PART_008": ("MAT_battery_charcoal", 0.9),
    "PART_009": ("MAT_battery_charcoal", 0.9),
    "PART_010": ("MAT_battery_charcoal", 0.9),
    "PART_011": ("MAT_battery_charcoal", 0.9),
    "PART_015": ("MAT_battery_charcoal", 0.9),
    "PART_016": ("MAT_battery_charcoal", 0.9),
    "PART_020": ("MAT_machined_metal", 0.4),
    "PART_021": ("MAT_machined_metal", 0.4),
    "PART_022": ("MAT_machined_metal", 0.4),
}

COMP_MATERIAL = {
    "ic": "MAT_ic_black",
    "connector": "MAT_connector_dark",
    "shield": "MAT_pcb_shield",
    "cap": "MAT_cap_metal",
}


def _make_material(name: str, spec: dict) -> object:
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = spec["base"]
    bsdf.inputs["Roughness"].default_value = spec["rough"]
    bsdf.inputs["Metallic"].default_value = spec["metal"]
    coat = bsdf.inputs.get("Coat Weight") or bsdf.inputs.get("Clearcoat")
    if coat is not None:
        coat.default_value = spec.get("coat", 0.0)
    if name == "MAT_pcb_soldermask":
        # Level-C surface detail: procedural micro-variation, not flat green.
        noise = nt.nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = 65.0
        noise.inputs["Detail"].default_value = 3.0
        noise.inputs["Roughness"].default_value = 0.7
        bump = nt.nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = 0.18
        bump.inputs["Distance"].default_value = 0.05
        nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
        nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].color = (0.30, 0.34, 0.30, 1)
        ramp.color_ramp.elements[1].color = (0.52, 0.55, 0.52, 1)
        nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
        nt.links.new(ramp.outputs["Color"], bsdf.inputs["Roughness"])
    return mat


def _bevel_and_smooth(obj: object, width: float) -> None:
    """Non-destructive edge treatment: angle-limited bevel + smooth shading."""
    if obj.type != "MESH":
        return
    for poly in obj.data.polygons:
        poly.use_smooth = True
    bevel = obj.modifiers.get("v11_edge_bevel") or obj.modifiers.new("v11_edge_bevel", "BEVEL")
    bevel.width = width
    bevel.segments = 3
    bevel.limit_method = "ANGLE"
    bevel.angle_limit = 0.5
    if hasattr(bevel, "harden_normals"):
        bevel.harden_normals = True


def _assign(obj: object, mat_name: str) -> None:
    mat = bpy.data.materials[mat_name]
    obj.data.materials.clear()
    obj.data.materials.append(mat)


def _add_pcb_level_b(board: object, collection: object) -> int:
    """Level-B medium detail: deterministic seeded layout of medium ICs,
    capacitor clusters and small connectors on the board top surface."""
    rng = random.Random(20260914)
    board_z = float(board.location.z)
    top_z = board_z + 0.8  # board thickness 1.6 -> top face
    placed: list[tuple[float, float, float, float]] = []
    existing = [
        (0.0, -35.0, 44, 8), (-4.0, 33.0, 30, 12),  # big connectors
        (0.0, 0.0, 40, 34), (-30.0, 8.0, 22, 18),   # shields (approx)
        (30.0, -12.0, 18, 16), (-28.0, -25.0, 16, 14),
    ]
    placed.extend(existing)

    def free(x: float, y: float, w: float, d: float) -> bool:
        for (px, py, pw, pd) in placed:
            if abs(x - px) < (w + pw) / 2 + 2 and abs(y - py) < (d + pd) / 2 + 2:
                return False
        # board is an octagon ~102x102: keep components clear of the cut corners
        return abs(x) + w / 2 < 42 and abs(y) + d / 2 < 42

    specs = []
    for _ in range(14):  # medium ICs
        w, d = rng.choice([(8, 8), (10, 7), (6, 6), (12, 6)])
        specs.append(("ic", w, d, rng.uniform(1.6, 2.6)))
    for _ in range(10):  # caps / small blocks
        s = rng.uniform(2.5, 4.5)
        specs.append(("cap", s, s, rng.uniform(2.0, 5.0)))
    for _ in range(10):  # small connectors / modules
        w, d = rng.choice([(14, 5), (10, 5), (7, 9)])
        specs.append(("connector", w, d, rng.uniform(2.5, 4.0)))

    made = 0
    for role, w, d, h in specs:
        for _try in range(30):
            x = rng.uniform(-44, 44)
            y = rng.uniform(-44, 44)
            if free(x, y, w, d):
                placed.append((x, y, w, d))
                break
        else:
            continue
        if role == "cap" and rng.random() < 0.5:
            bpy.ops.mesh.primitive_cylinder_add(
                vertices=20, radius=w / 2, depth=h,
                location=(board.location.x + x, board.location.y + y, top_z + h / 2),
            )
        else:
            bpy.ops.mesh.primitive_cube_add(
                size=1.0, location=(board.location.x + x, board.location.y + y, top_z + h / 2),
            )
            obj = bpy.context.object
            obj.scale = (w, d, h)
            bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        obj = bpy.context.object
        obj.name = f"PCB_COMP_V2_{role.upper()}_{made:02d}"
        _bevel_and_smooth(obj, min(0.4, h * 0.15))
        obj.data.materials.append(bpy.data.materials[COMP_MATERIAL[role]])
        obj.parent = board
        obj.matrix_parent_inverse = board.matrix_world.inverted()
        obj["semanticId"] = f"GEO_{obj.name}"
        obj["type"] = "geometry"
        obj["systemId"] = "SYS_ACQUISITION"
        obj["logicalParent"] = "CMP_MAIN_PCB"
        obj["source"] = "presentation_detail_v11"
        obj["task10v2_presentation_component"] = True
        obj["materialRole"] = role
        # move into the presentation collection
        for c in list(obj.users_collection):
            c.objects.unlink(obj)
        collection.objects.link(obj)
        made += 1
    return made


def _inherit_hide_schedule(new_objs: list[object]) -> None:
    """New Level-B comps must follow the board's isolate-hide schedule.

    Slotted actions (Blender 4.4+) removed Action.fcurves, so we sample the
    donor's EVALUATED hide flags at shot boundaries and re-key via
    keyframe_insert — version-proof and honest about what actually ships.
    """
    donor = next(
        (o for o in bpy.data.objects
         if o.name.startswith("PCB_COMP_") and not o.name.startswith("PCB_COMP_V2_")),
        None,
    )
    if donor is None or not new_objs:
        return
    scene = bpy.context.scene
    # evaluate once at each shot boundary; the schedule only changes at edges
    samples: list[tuple[int, bool, bool]] = []
    probe_frames = [1, 74, 75, 76, 164, 165, 166, 299, 300, 301, 419, 420, 421,
                    509, 510, 511, 614, 615, 616, 704, 705, 706, 809, 810, 811, 900]
    for f in probe_frames:
        scene.frame_set(f)
        samples.append((f, bool(donor.hide_render), bool(donor.hide_viewport)))
    for obj in new_objs:
        for f, hr, hv in samples:
            obj.hide_render = hr
            obj.hide_viewport = hv
            obj.keyframe_insert("hide_render", frame=f)
            obj.keyframe_insert("hide_viewport", frame=f)
    scene.frame_set(1)


def build_master(project_root: Path) -> dict[str, object]:
    if bpy is None:
        raise RuntimeError("Blender bpy required")
    root = Path(project_root).expanduser().resolve()
    bpy.ops.wm.open_mainfile(filepath=str(root / SOURCE_SCENE))
    scene = bpy.context.scene
    scene.frame_set(1)

    for name, spec in MATERIALS.items():
        _make_material(name, spec)

    presentation = bpy.data.collections.get("PRESENTATION_V11") or bpy.data.collections.new("PRESENTATION_V11")
    if presentation.name not in [c.name for c in scene.collection.children]:
        scene.collection.children.link(presentation)

    objects = {str(o.get("part_id")): o for o in bpy.data.objects if str(o.get("part_id", "")).startswith("PART_")}
    for part_id, (mat_name, bevel_w) in PART_LOOK.items():
        obj = objects.get(part_id)
        if obj is None:
            continue
        _assign(obj, mat_name)
        _bevel_and_smooth(obj, bevel_w)
        obj["v11_material"] = mat_name
        obj["v11_bevel_mm"] = bevel_w

    # existing 15 presentation comps -> unified materials
    for obj in bpy.data.objects:
        if obj.get("task10v2_presentation_component") and obj.name.startswith("PCB_COMP_"):
            role = str(obj.get("task10v2_material_role", "ic"))
            _assign(obj, COMP_MATERIAL.get(role, "MAT_ic_black"))
            _bevel_and_smooth(obj, 0.3)

    board = objects["PART_019"]
    before = set(bpy.data.objects)
    made = _add_pcb_level_b(board, presentation)
    new_comps = [o for o in bpy.data.objects if o not in before]
    _inherit_hide_schedule(new_comps)

    # annotation fonts carry timed f-curves that re-evaluate during render —
    # move them into a view-layer-excluded collection instead (bulletproof)
    hidden_col = bpy.data.collections.get("LOOKDEV_HIDDEN") or bpy.data.collections.new("LOOKDEV_HIDDEN")
    if hidden_col.name not in [c.name for c in scene.collection.children]:
        scene.collection.children.link(hidden_col)
    for obj in bpy.data.objects:
        if obj.type == "FONT":
            for c in list(obj.users_collection):
                c.objects.unlink(obj)
            hidden_col.objects.link(obj)
    layer_col = scene.view_layers[0].layer_collection
    if hidden_col.name in layer_col.children:
        layer_col.children[hidden_col.name].exclude = True

    # lighting retune: raise all three + widen the areas for softer wrapping
    # mm-scale scene: area lights sit ~800-1500 units away, so inverse-square
    # falloff needs ~1e6-order energies for real directional shaping. Probed.
    LIGHT_BOOST = {"STORY_LIGHT_KEY": 4.5e5, "STORY_LIGHT_FILL": 2.4e5, "STORY_LIGHT_RIM": 3.0e5}
    for name, energy in LIGHT_BOOST.items():
        lamp = bpy.data.objects.get(name)
        if lamp is not None:
            lamp.data.energy = energy
            if lamp.data.type == "AREA":
                lamp.data.shape = "DISK"
                lamp.data.size = max(lamp.data.size, 240.0)

    # deep studio gradient (spec §32): dark backdrop, subject pops
    world = scene.world
    if world and world.node_tree:
        ramp = next(
            (n for n in world.node_tree.nodes if n.bl_idname == "ShaderNodeValToRGB"),
            None,
        )
        if ramp:
            # visible dark gradient — doubles as ambient fill in EEVEE, so it
            # must stay luminous enough to shape the subject (§32)
            ramp.color_ramp.elements[0].color = (0.045, 0.052, 0.065, 1.0)
            ramp.color_ramp.elements[1].color = (0.135, 0.150, 0.175, 1.0)
        bg = world.node_tree.nodes.get("Background")
        if bg:
            bg.inputs["Strength"].default_value = 0.65

    # subtle virtual floor for contact shadow + orientation (spec §33):
    # a dark plane that only reads through AO/shadow, enabled per-shot
    bpy.ops.mesh.primitive_plane_add(size=4000.0, location=(95.7, 84.5, 168.0))
    floor = bpy.context.object
    floor.name = "LOOKDEV_FLOOR"
    floor_mat = bpy.data.materials.new("MAT_lookdev_floor")
    floor_mat.use_nodes = True
    fbsdf = floor_mat.node_tree.nodes.get("Principled BSDF")
    fbsdf.inputs["Base Color"].default_value = (0.016, 0.018, 0.022, 1.0)
    fbsdf.inputs["Roughness"].default_value = 0.9
    floor.data.materials.append(floor_mat)
    floor.visible_shadow = True
    floor.hide_render = False
    floor["v11_role"] = "floor"

    # closeup camera on the board (frame 360 = PCB_FOCUS mid-shot)
    board_focus = Vector((95.7, 84.5, 274.7)) + Vector((50.0, 8.0, 14.0))
    cam_data = bpy.data.cameras.new("CAM_LOOKDEV_PCB_CLOSEUP")
    cam_data.lens = 62.0
    cam_data.sensor_width = 36.0
    cam = bpy.data.objects.new("CAM_LOOKDEV_PCB_CLOSEUP", cam_data)
    scene.collection.objects.link(cam)
    direction = Vector((0.85, -0.75, 0.55)).normalized()
    cam.location = board_focus + direction * 165.0
    look = board_focus - cam.location
    cam.rotation_euler = look.to_track_quat("-Z", "Y").to_euler()

    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    scene.render.resolution_percentage = 100

    output = root / MASTER_OUTPUT
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output))
    return {"output": str(output), "pcb_level_b_components": made, "materials": len(MATERIALS)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args(argv if argv is not None else _argv())
    print(json.dumps(build_master(args.project_root), ensure_ascii=False))
    return 0


def _argv() -> list[str]:
    a = sys.argv[1:]
    return a[a.index("--") + 1 :] if "--" in a else a


if __name__ == "__main__":
    raise SystemExit(main())
