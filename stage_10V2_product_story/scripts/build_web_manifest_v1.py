"""Emit the V1 interactive manifest consumed by the web runtime.

The V1 runtime never plays baked animation — it computes every transform as
baseTransform + stateTransform (spec §6/§12). This manifest therefore carries
positions, not keyframes:

- per-system explode vectors derived from the PRIMARY_ARCHITECTURE state
- per-component assembled + inspect positions for the three focus systems
- camera presets (context / inspect) per system
- the semantic map so the registry can be validated before a mesh is picked

All coordinates are converted Blender Z-up -> three.js Y-up.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.task08_data import load_json
from stage_10V2_product_story.scripts.camera_plan import build_camera_records
from stage_10V2_product_story.scripts.semantic_map import (
    COMPONENTS,
    SYSTEMS,
    validate_semantic_map,
)
from stage_10V2_product_story.scripts.story_v2_data import (
    build_story_v2_state_transforms,
)

MANIFEST_OUTPUT_V1 = "stage_10V2_product_story/web-v1/manifest_v1.json"
LAYOUT_PATH = "stage_09C_refined_explosion/config/refined_layout.json"

# Which focus state supplies each system's inspection layout.
INSPECT_STATE = {
    "SYS_SENSOR": "SENSOR_FOCUS",
    "SYS_ACQUISITION": "PCB_FOCUS",
    "SYS_POWER": "POWER_FOCUS",
}

INSPECT_CAMERA = {
    "SYS_SENSOR": "CAM_STORY_SENSOR",
    "SYS_ACQUISITION": "CAM_STORY_PCB",
    "SYS_POWER": "CAM_STORY_POWER",
}

# Fraction of the way from the hero camera to the inspect camera used for the
# context (x-ray locate) step — close enough to read location, wide enough to
# keep the whole device in frame.
CONTEXT_PULL = 0.45


def yup(coords: list[float]) -> list[float]:
    return [coords[0], coords[2], -coords[1]]


def _sub(a: list[float], b: list[float]) -> list[float]:
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def _lerp(a: list[float], b: list[float], t: float) -> list[float]:
    return [a[i] + (b[i] - a[i]) * t for i in range(3)]


def _centroid(points: list[list[float]]) -> list[float]:
    n = float(len(points))
    return [sum(p[i] for p in points) / n for i in range(3)]


def _length(v: list[float]) -> float:
    return (v[0] ** 2 + v[1] ** 2 + v[2] ** 2) ** 0.5


def _normalize(v: list[float]) -> list[float]:
    n = _length(v)
    return [c / n for c in v] if n else [0.0, 0.0, 0.0]


def build_web_manifest_v1(project_root: Path) -> dict[str, object]:
    validate_semantic_map()
    root = Path(project_root).expanduser().resolve()
    layout = load_json(root / LAYOUT_PATH)
    baseline = build_story_v2_state_transforms(root)
    cameras = build_camera_records(baseline, layout)["cameras"]
    states = baseline["states"]
    assembled = states["ASSEMBLED"]["parts"]
    primary = states["PRIMARY_ARCHITECTURE"]["parts"]

    # ---- components: assembled base + per-system inspect target ------------
    components: dict[str, dict[str, object]] = {}
    for part_id, spec in COMPONENTS.items():
        entry: dict[str, object] = {
            "semanticId": spec["semanticId"],
            "systemId": spec["systemId"],
            "displayName": spec["displayName"],
            "role": spec["role"],
            "inspectable": bool(spec.get("inspectable", True)),
            "assembled": yup(assembled[part_id]["location"]),
        }
        components[part_id] = entry

    for sys_id, state_id in INSPECT_STATE.items():
        inspect = states[state_id]["parts"]
        for part_id in SYSTEMS[sys_id]["parts"]:  # type: ignore[index]
            components[part_id]["inspect"] = yup(inspect[part_id]["location"])

    # ---- per-core extraction directions (sensor secondary explode) ---------
    sensor = INSPECT_STATE["SYS_SENSOR"]
    fixture_pos = yup(states[sensor]["parts"]["PART_003"]["location"])
    for part_id in ("PART_012", "PART_013", "PART_014"):
        inspect_pos = components[part_id]["inspect"]  # type: ignore[assignment]
        direction = _normalize(_sub(list(inspect_pos), fixture_pos))
        components[part_id]["extractDirection"] = direction

    # ---- systems: explode vector from PRIMARY_ARCHITECTURE -----------------
    systems: dict[str, dict[str, object]] = {}
    for sys_id, spec in SYSTEMS.items():
        part_ids = list(spec["parts"])  # type: ignore[index]
        delta = _centroid(
            [_sub(primary[p]["location"], assembled[p]["location"]) for p in part_ids]
        )
        systems[sys_id] = {
            "displayName": spec["displayName"],
            "oneLiner": spec["oneLiner"],
            "order": spec["order"],
            "parts": part_ids,
            "explodeVector": yup(delta),
        }

    # ---- camera presets -----------------------------------------------------
    def preset(name: str) -> dict[str, object]:
        record = cameras[name]
        return {
            "position": yup(record["location"]),
            "target": yup(record["target"]),
            "lens_mm": record["lens_mm"],
            "fstop": record.get("fstop"),
        }

    hero = preset("CAM_STORY_HERO")
    camera_presets: dict[str, dict[str, object]] = {
        "overviewHero": hero,
        "architectureHero": hero,
    }
    for sys_id, cam_name in INSPECT_CAMERA.items():
        inspect_cam = preset(cam_name)
        camera_presets[sys_id] = {
            "context": {
                "position": _lerp(hero["position"], inspect_cam["position"], CONTEXT_PULL),  # type: ignore[arg-type]
                "target": inspect_cam["target"],
                "lens_mm": inspect_cam["lens_mm"],
            },
            "inspect": inspect_cam,
        }

    manifest = {
        "version": 1,
        "glb": "product_v1.glb",
        "unit": "mm",
        "systems": systems,
        "components": components,
        "cameraPresets": camera_presets,
    }
    output = root / MANIFEST_OUTPUT_V1
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return {
        "output": str(output),
        "systems": len(systems),
        "components": len(components),
        "camera_presets": len(camera_presets),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args(argv)
    print(json.dumps(build_web_manifest_v1(args.project_root), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
