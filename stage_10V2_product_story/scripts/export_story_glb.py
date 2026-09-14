"""Export the Task 10-V2 animated scene to GLB for the web viewer.

The glTF animation carries every keyed transform (per-shot arrivals,
settle, idle float, camera drift). Visibility toggles are NOT exported —
glTF 2.0 has no visibility channel — so the viewer applies the isolate
policy itself from story_manifest.json.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from stage_10V2_product_story.scripts.story_v2_data import SCENE_OUTPUT

try:  # pragma: no cover - Blender-only implementation.
    import bpy  # type: ignore
except ImportError:  # pragma: no cover
    bpy = None  # type: ignore

GLB_OUTPUT = "stage_10V2_product_story/web/product_story_v2.glb"


def export_story_glb(project_root: Path) -> dict[str, object]:
    if bpy is None:
        raise RuntimeError("Blender bpy is required to export the story GLB")
    root = Path(project_root).expanduser().resolve()
    bpy.ops.wm.open_mainfile(filepath=str(root / SCENE_OUTPUT))
    output = root / GLB_OUTPUT
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(
        filepath=str(output),
        export_format="GLB",
        export_animations=True,
        export_extras=True,
        export_cameras=True,
        export_apply=False,
        export_yup=True,
    )
    return {
        "output": str(output),
        "size_mb": round(output.stat().st_size / 1e6, 1),
    }


def _script_arguments() -> list[str]:
    arguments = list(sys.argv[1:])
    return arguments[arguments.index("--") + 1 :] if "--" in arguments else arguments


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args(argv if argv is not None else _script_arguments())
    print(json.dumps(export_story_glb(args.project_root), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
