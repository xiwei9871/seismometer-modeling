"""Run the focused static hierarchical presentation v4 pipeline."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.presentation_explosion_v4 import (
    IMPORTANT_PART_IDS,
    REVIEW_QUESTION,
    V4_VIEW_NAMES,
    build_presentation_layout_v4,
    write_presentation_outputs_v4,
)
from scripts.task08_data import write_json
from scripts.task09_data import validate_task09_baseline


RUN_RESULT_PATH = "data/presentation_v4_run_result.json"
REPORT_PATH = "output/reports/presentation_explosion_v4.md"
LOG_PATH = "logs/presentation_v4.log"
BLEND_PATH = "output/stage03_presentation_exploded_v4.blend"
RENDER_DIR = "output/explosion_validation_v4"


def build_presentation_report_v4(
    layout: Mapping[str, Any],
    *,
    scene_result: Mapping[str, Any] | None,
    render_result: Mapping[str, Any] | None,
) -> str:
    """Build the v4 report around visibility, occlusion, and layout clarity."""
    parts = layout.get("parts") or {}
    visible_count = sum(
        record.get("presentation_visibility") == "VISIBLE"
        for record in parts.values()
    )
    hidden_count = sum(
        record.get("presentation_visibility") == "HIDDEN"
        for record in parts.values()
    )
    lines = [
        "# Focused Hierarchical Presentation Explosion v4",
        "",
        "## Scope",
        "",
        "- Mode: `STATIC_FOCUSED_HIERARCHICAL_PRESENTATION`",
        "- This is a static presentation layout, not a physical disassembly sequence.",
        "- No keyframes, animation data, materials, or geometry changes were created.",
        "",
        "## Source baseline",
        "",
        f"- Source SHA256: `{layout.get('source_sha256', '')}`",
        f"- Source PART meshes: {layout.get('source_baseline', {}).get('source_parts', 0)}",
        f"- Faces: {layout.get('source_baseline', {}).get('faces', 0)}",
        f"- Indexed vertices: {layout.get('source_baseline', {}).get('indexed_vertices', 0)}",
        "",
        "## Focused presentation coverage",
        "",
        f"- {visible_count} visible important parts",
        f"- {hidden_count} hidden source parts",
        f"- Anchor: `{layout.get('animation_anchor', '')}`",
        "- The visible set is the confirmed important-part set `PART_001` through `PART_022`.",
        "- Unknown medium geometry and SMALL/FRAGMENT geometry remain source objects but are hidden from presentation.",
        "",
        "## Functional assemblies and fixed zones",
        "",
        "| Assembly | Zone | Parts | Expansion policy |",
        "|---|---|---:|---|",
    ]
    for assembly_id, assembly in (layout.get("assemblies") or {}).items():
        lines.append(
            f"| `{assembly_id}` | `{assembly.get('zone', '')}` | "
            f"{len(assembly.get('part_ids') or [])} | {assembly.get('expansion_policy', '')} |"
        )
    lines.extend(["", "## Required inspection renders", ""])
    for view_name in V4_VIEW_NAMES:
        lines.append(f"- `{RENDER_DIR}/{view_name}.png`")
    lines.extend(
        [
            "",
            "## Human review focus",
            "",
            f"- {REVIEW_QUESTION}",
            "- Confirm each important part is immediately visible.",
            "- Confirm no important part is occluded by another important part.",
            "- Confirm the zones and component spacing are easy to understand.",
            "- SMALL/FRAGMENT and unresolved medium parts have no collision, animation, or motion-review entries.",
            "",
            "## Run status",
            "",
            f"- Blender scene: {'generated' if scene_result else 'not run'}",
            f"- Validation renders: {'generated' if render_result else 'not run'}",
        ]
    )
    return "\n".join(lines) + "\n"


def blender_stage_succeeded(returncode: int, stderr: str) -> bool:
    """Treat an unhandled Blender Python traceback as a failed stage."""
    if int(returncode) != 0:
        return False
    return "Traceback (most recent call last):" not in (stderr or "")


def run_presentation_v4(
    project_root: Path,
    *,
    blender_path: str | None = None,
    skip_blender: bool = False,
) -> dict[str, Any]:
    """Plan, serialize, build, render, and record v4 results."""
    root = Path(project_root).expanduser().resolve()
    baseline = validate_task09_baseline(root)
    log_path = root / LOG_PATH
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_lines = [
        f"start_utc={datetime.now(timezone.utc).isoformat()}",
        f"project_root={root}",
        f"source_sha256={baseline['source_sha256']}",
        f"source_parts={baseline['source_parts']}",
        f"faces={baseline['faces']}",
        f"indexed_vertices={baseline['indexed_vertices']}",
    ]
    layout = build_presentation_layout_v4(root)
    paths = write_presentation_outputs_v4(root, layout)
    scene_result: dict[str, Any] | None = None
    render_result: dict[str, Any] | None = None
    failures: list[dict[str, Any]] = []
    if skip_blender:
        status = "SKIPPED"
        log_lines.append("blender_status=SKIPPED_BY_REQUEST")
    else:
        executable = blender_path or os.environ.get("BLENDER_PATH") or "/opt/homebrew/bin/blender"
        builder_command = [
            executable,
            "-b",
            "--python",
            str(root / "scripts/build_presentation_explosion_v4.py"),
            "--",
            "--project-root",
            str(root),
        ]
        builder = _run_stage("build_scene", builder_command, root, log_lines)
        if builder["returncode"] != 0:
            failures.append(builder)
            status = "FAIL"
        else:
            scene_result = {"output": str(root / BLEND_PATH), "returncode": 0}
            renderer_command = [
                executable,
                "-b",
                "--python",
                str(root / "scripts/generate_presentation_explosion_v4.py"),
                "--",
                "--project-root",
                str(root),
            ]
            renderer = _run_stage("render_views", renderer_command, root, log_lines)
            if renderer["returncode"] != 0:
                failures.append(renderer)
                status = "FAIL"
            else:
                expected_paths = [root / RENDER_DIR / f"{view}.png" for view in V4_VIEW_NAMES]
                missing = [
                    str(path)
                    for path in expected_paths
                    if not path.is_file() or path.stat().st_size == 0
                ]
                if missing:
                    failures.append(
                        {
                            "stage": "render_views",
                            "returncode": 1,
                            "error": f"missing or empty render outputs: {missing}",
                        }
                    )
                    status = "FAIL"
                else:
                    render_result = {
                        "views": [str(path) for path in expected_paths],
                        "returncode": 0,
                    }
                    status = "PASS"

    report = build_presentation_report_v4(
        layout,
        scene_result=scene_result,
        render_result=render_result,
    )
    report_path = root / REPORT_PATH
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    visible_count = sum(
        record.get("presentation_visibility") == "VISIBLE"
        for record in layout["parts"].values()
    )
    hidden_count = sum(
        record.get("presentation_visibility") == "HIDDEN"
        for record in layout["parts"].values()
    )
    log_lines.extend(
        [
            f"visible_part_count={visible_count}",
            f"hidden_part_count={hidden_count}",
            f"review_queue_count={len(layout['review_queue'])}",
            f"status={status}",
        ]
    )
    if failures:
        log_lines.append(f"failures={json.dumps(failures, ensure_ascii=False, sort_keys=True)}")
    log_path.write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    result = {
        "status": status,
        "source_baseline": layout["source_baseline"],
        "source_sha256": layout["source_sha256"],
        "visible_part_count": visible_count,
        "hidden_part_count": hidden_count,
        "review_queue_count": len(layout["review_queue"]),
        "important_part_ids": list(IMPORTANT_PART_IDS),
        "animation_created": False,
        "keyframe_count": 0,
        "source_geometry_modified": False,
        "scene": scene_result,
        "renders": render_result,
        "report": str(report_path),
        "log": str(log_path),
        "failures": failures,
    }
    write_json(root / RUN_RESULT_PATH, result)
    return result


def _run_stage(
    stage: str,
    command: Sequence[str],
    cwd: Path,
    log_lines: list[str],
) -> dict[str, Any]:
    completed = subprocess.run(
        list(command),
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    effective_returncode = completed.returncode if blender_stage_succeeded(completed.returncode, stderr) else 1
    log_lines.extend(
        [
            f"stage={stage}",
            f"command={json.dumps(list(command), ensure_ascii=False)}",
            f"process_returncode={completed.returncode}",
            f"returncode={effective_returncode}",
            f"stdout={stdout[-4000:]}",
            f"stderr={stderr[-4000:]}",
        ]
    )
    return {
        "stage": stage,
        "command": list(command),
        "returncode": effective_returncode,
        "process_returncode": completed.returncode,
        "stdout": stdout[-4000:],
        "stderr": stderr[-4000:],
        "error": stderr[-4000:] if completed.returncode != 0 else "",
    }


def _script_arguments() -> list[str]:
    arguments = list(sys.argv[1:])
    return arguments[arguments.index("--") + 1 :] if "--" in arguments else arguments


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--blender-path", default=None)
    parser.add_argument("--skip-blender", action="store_true")
    args = parser.parse_args(argv if argv is not None else _script_arguments())
    result = run_presentation_v4(
        args.project_root,
        blender_path=args.blender_path,
        skip_blender=args.skip_blender,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
