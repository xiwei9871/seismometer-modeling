"""Inspect one Stage 01 PART in an open Blender scene without saving changes."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

try:  # Blender is optional for the pure report formatter.
    import bpy  # type: ignore
except ImportError:  # pragma: no cover - exercised only outside Blender
    bpy = None  # type: ignore


def format_inspection_report(part_id: str, properties: Mapping[str, Any]) -> str:
    """Return a concise JSON inspection report from object properties."""
    bbox = properties.get("bbox")
    if not isinstance(bbox, Mapping):
        bbox = {
            "x": properties.get("bbox_x"),
            "y": properties.get("bbox_y"),
            "z": properties.get("bbox_z"),
        }
    payload = {
        "part_id": part_id,
        "bbox": dict(bbox),
        "face_count": properties.get("face_count"),
        "vertex_count": properties.get("vertex_count"),
        "duplicate_group": properties.get("duplicate_group", ""),
        "duplicate_confidence": properties.get("duplicate_confidence", ""),
        "suspected_fragment": properties.get("suspected_fragment", False),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--part", required=True, help="stable PART_XXX object ID")
    parser.add_argument("--isolate", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(_script_arguments(argv))
    if bpy is None:
        print("Error: Blender bpy is required for inspection.", file=sys.stderr)
        return 2

    object_name = str(args.part)
    obj = bpy.data.objects.get(object_name)
    if obj is None:
        print(f"Error: object {object_name} was not found.", file=sys.stderr)
        return 1
    if args.isolate:
        for other in bpy.context.scene.objects:
            other.hide_set(other != obj)
    for other in bpy.context.selected_objects:
        other.select_set(False)
    obj.hide_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    try:
        bpy.ops.view3d.view_selected(use_all_regions=False)
    except RuntimeError:
        # Headless Blender has no 3D View context; selection still succeeds.
        pass
    properties = {key: obj[key] for key in obj.keys()}
    report = format_inspection_report(object_name, properties)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(report, encoding="utf-8")
    print(report, end="")
    return 0


def _script_arguments(argv: Sequence[str] | None) -> list[str]:
    if argv is not None:
        return list(argv)
    arguments = list(sys.argv[1:])
    if "--" in arguments:
        arguments = arguments[arguments.index("--") + 1 :]
    return arguments


if __name__ == "__main__":
    raise SystemExit(main())
