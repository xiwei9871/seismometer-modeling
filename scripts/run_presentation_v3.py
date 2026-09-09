"""Run the complete static hierarchical presentation v3 pipeline."""

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

from scripts.generate_presentation_explosion_v3 import V3_VIEW_NAMES
from scripts.presentation_explosion_v3 import (
    build_presentation_layout,
    write_presentation_outputs,
)
from scripts.task08_data import write_json
from scripts.task09_data import validate_task09_baseline


RUN_RESULT_PATH = "data/presentation_v3_run_result.json"
REPORT_PATH = "output/reports/presentation_explosion_v3.md"
LOG_PATH = "logs/presentation_v3.log"
BLEND_PATH = "output/stage03_presentation_exploded_v3.blend"
RENDER_DIR = "output/explosion_validation_v3"
REVIEW_QUESTION = (
    "Is the important component visible, unobstructed, and clearly laid out?"
)


def build_presentation_report(
    layout: Mapping[str, Any],
    *,
    scene_result: Mapping[str, Any] | None,
    render_result: Mapping[str, Any] | None,
) -> str:
    """Build a concise human-review report for the static v3 layout."""
    parts = layout.get("parts") or {}
    visible = [
        record
        for record in parts.values()
        if record.get("presentation_visibility") == "VISIBLE"
    ]
    hidden = [
        record
        for record in parts.values()
        if record.get("presentation_visibility") == "HIDDEN"
    ]
    lines = [
        "# Hierarchical Presentation Explosion v3",
        "",
        "## Scope",
        "",
        f"- Mode: `{layout.get('mode', '')}`",
        "Static hierarchical presentation only. No realistic disassembly order,",
        "animation keyframes, materials, or geometry changes were created.",
        "",
        "## Source baseline",
        "",
        f"- Source SHA256: `{layout.get('source_sha256', '')}`",
        f"- Source PART meshes: {layout.get('source_baseline', {}).get('source_parts', 0)}",
        f"- Faces: {layout.get('source_baseline', {}).get('faces', 0)}",
        f"- Indexed vertices: {layout.get('source_baseline', {}).get('indexed_vertices', 0)}",
        "",
        "## Presentation coverage",
        "",
        f"- {len(visible)} visible MAJOR/MEDIUM parts",
        f"- {len(hidden)} hidden SMALL/FRAGMENT parts",
        f"- Animation anchor: `{layout.get('animation_anchor', '')}`",
        "- No keyframes or animation data were created.",
        "",
        "## Functional assemblies and zones",
        "",
        "| Assembly | Zone | Parts | Expansion policy |",
        "|---|---|---:|---|",
    ]
    for assembly_id, assembly in (layout.get("assemblies") or {}).items():
        lines.append(
            f"| `{assembly_id}` | `{assembly.get('zone', '')}` | "
            f"{len(assembly.get('part_ids') or [])} | {assembly.get('expansion_policy', '')} |"
        )
    lines.extend(
        [
            "",
            "## Required validation renders",
            "",
        ]
    )
    for view_name in V3_VIEW_NAMES:
        lines.append(f"- `{RENDER_DIR}/{view_name}.png`")
    lines.extend(
        [
            "",
            "## Human review focus",
            "",
            f"- {REVIEW_QUESTION}",
            "- Check only important-part visibility, occlusion, and layout clarity.",
            "- SMALL/FRAGMENT parts are not in collision, animation, or motion-review queues.",
            "",
            "## Run status",
            "",
            f"- Blender scene: {'generated' if scene_result else 'not run'}",
            f"- Validation renders: {'generated' if render_result else 'not run'}",
        ]
    )
    return "\n".join(lines) + "\n"


def run_presentation_v3(
    project_root: Path,
    *,
    blender_path: str | None = None,
    skip_blender: bool = False,
) -> dict[str, Any]:
    """Plan, serialize, build, render, and record the v3 pipeline result."""
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
    layout = build_presentation_layout(root)
    paths = write_presentation_outputs(root, layout)
    scene_result: dict[str, Any] | None = None
    render_result: dict[str, Any] | None = None
    failures: list[dict[str, Any]] = []

    if skip_blender:
        log_lines.append("blender_status=SKIPPED_BY_REQUEST")
        status = "SKIPPED"
    else:
        executable = blender_path or os.environ.get("BLENDER_PATH") or "/opt/homebrew/bin/blender"
        builder_command = [
            executable,
            "-b",
            "--python",
            str(root / "scripts/build_presentation_explosion_v3.py"),
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
                str(root / "scripts/generate_presentation_explosion_v3.py"),
                "--",
                "--project-root",
                str(root),
            ]
            renderer = _run_stage("render_views", renderer_command, root, log_lines)
            if renderer["returncode"] != 0:
                failures.append(renderer)
                status = "FAIL"
            else:
                expected_paths = [root / RENDER_DIR / f"{view}.png" for view in V3_VIEW_NAMES]
                missing = [str(path) for path in expected_paths if not path.is_file() or path.stat().st_size == 0]
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

    report = build_presentation_report(
        layout,
        scene_result=scene_result,
        render_result=render_result,
    )
    report_path = root / REPORT_PATH
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    log_lines.extend(
        [
            f"visible_part_count={sum(record.get('presentation_visibility') == 'VISIBLE' for record in layout['parts'].values())}",
            f"hidden_part_count={sum(record.get('presentation_visibility') == 'HIDDEN' for record in layout['parts'].values())}",
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
        "visible_part_count": sum(
            record.get("presentation_visibility") == "VISIBLE"
            for record in layout["parts"].values()
        ),
        "hidden_part_count": sum(
            record.get("presentation_visibility") == "HIDDEN"
            for record in layout["parts"].values()
        ),
        "review_queue_count": len(layout["review_queue"]),
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
    """Run one Blender stage and retain diagnostics for a non-zero result."""
    completed = subprocess.run(
        list(command),
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    log_lines.extend(
        [
            f"stage={stage}",
            f"command={json.dumps(list(command), ensure_ascii=False)}",
            f"returncode={completed.returncode}",
            f"stdout={stdout[-4000:]}",
            f"stderr={stderr[-4000:]}",
        ]
    )
    return {
        "stage": stage,
        "command": list(command),
        "returncode": completed.returncode,
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
    result = run_presentation_v3(
        args.project_root,
        blender_path=args.blender_path,
        skip_blender=args.skip_blender,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
