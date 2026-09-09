"""Run the complete Task 9C refined static and animation-preview pipeline."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.task08_data import load_json, write_json
from stage_09C_refined_explosion.scripts.build_animation_preview import (
    build_animation_plan,
    write_animation_plan,
)
from stage_09C_refined_explosion.scripts.build_refined_layout import (
    build_refined_layout,
    write_refined_layout,
)
from stage_09C_refined_explosion.scripts.compose_keyframes_contact_sheet import compose_keyframes_contact_sheet
from stage_09C_refined_explosion.scripts.render_refined_outputs import write_camera_config


ROOT_DIR = "stage_09C_refined_explosion"
VALIDATION_PATH = "stage_09C_refined_explosion/config/validation.json"
REPORT_PATH = "stage_09C_refined_explosion/reports/task09c_report.md"
LOG_PATH = "stage_09C_refined_explosion/logs/task09c.log"
REQUIRED_OUTPUTS = (
    "exploded_hero_refined.png",
    "exploded_engineering_refined.png",
    "pcb_detail_refined.png",
    "sensor_detail_refined.png",
    "exploded_animation_preview.blend",
    "exploded_preview.mp4",
    "exploded_keyframes_contact_sheet.png",
)


def validate_run_result_contract(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("status") != "PASS":
        raise ValueError("Task 9C run is not PASS")
    outputs = result.get("outputs")
    if not isinstance(outputs, dict) or set(outputs) != set(REQUIRED_OUTPUTS):
        raise ValueError("Task 9C run output set is incomplete")
    if result.get("source_geometry_modified") is not False:
        raise ValueError("Task 9C source geometry modification marker is invalid")
    if result.get("source_part_count") != 82 or result.get("source_faces") != 444296 or result.get("source_indexed_vertices") != 221902:
        raise ValueError("Task 9C source baseline is invalid")
    if result.get("animation_created") is not True or not 15.0 <= float(result.get("animation_duration_seconds", 0.0)) <= 22.0:
        raise ValueError("Task 9C animation contract is invalid")
    for name, path in outputs.items():
        file_path = Path(path)
        if not file_path.is_file() or file_path.stat().st_size <= 0:
            raise ValueError(f"Task 9C output is missing or empty: {name}")
    return dict(result)


def run_task09c(project_root: Path, *, blender_path: str | None = None, skip_blender: bool = False) -> dict[str, Any]:
    root = Path(project_root).expanduser().resolve()
    layout = build_refined_layout(root)
    refined_path = write_refined_layout(root, layout)
    plan = build_animation_plan(root)
    plan_path = write_animation_plan(root, plan)
    camera_path = write_camera_config(root, layout)
    executable = blender_path or os.environ.get("BLENDER_PATH") or "/opt/homebrew/bin/blender"
    log_lines = [
        f"start_utc={datetime.now(timezone.utc).isoformat()}",
        f"project_root={root}",
        "source_geometry_modified=False",
        f"refined_layout={refined_path}",
        f"animation_plan={plan_path}",
        f"camera_config={camera_path}",
    ]
    stages: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    if not skip_blender:
        for stage, script in (
            ("build_refined_scene", "build_refined_scene.py"),
            ("build_animation_preview", "build_animation_preview.py"),
            ("render_refined_outputs", "render_refined_outputs.py"),
        ):
            command = [executable, "-b", "--python", str(root / f"{ROOT_DIR}/scripts/{script}"), "--", "--project-root", str(root)]
            record = _run_stage(stage, command, root, log_lines)
            stages.append(record)
            if record["returncode"] != 0:
                failures.append(record)
                break
        if not failures:
            try:
                contact = compose_keyframes_contact_sheet(root)
                stages.append({"stage": "compose_keyframes_contact_sheet", "returncode": 0, "output": str(contact)})
            except Exception as exc:
                failures.append({"stage": "compose_keyframes_contact_sheet", "returncode": 1, "error": str(exc)})
        if not failures:
            command = [executable, "-b", "--python", str(root / f"{ROOT_DIR}/scripts/validate_refined_scene.py"), "--", "--project-root", str(root)]
            record = _run_stage("validate_refined_scene", command, root, log_lines)
            stages.append(record)
            if record["returncode"] != 0:
                failures.append(record)
            else:
                scene_validation = _last_json(record["stdout"])
        else:
            scene_validation = None
    else:
        scene_validation = None
        log_lines.append("blender_status=SKIPPED_BY_REQUEST")
    outputs = _output_paths(root)
    result = {
        "status": "PASS" if not failures and scene_validation and scene_validation.get("status") == "PASS" else ("SKIPPED" if skip_blender else "FAIL"),
        "source_part_count": 82,
        "source_faces": 444296,
        "source_indexed_vertices": 221902,
        "source_geometry_modified": False,
        "animation_created": not skip_blender and not failures,
        "animation_duration_seconds": 18.0,
        "outputs": outputs,
        "layout": str(refined_path),
        "animation_plan": str(plan_path),
        "camera_config": str(camera_path),
        "validation": scene_validation,
        "stages": stages,
        "failures": failures,
    }
    if result["status"] == "PASS":
        validate_run_result_contract(result)
    write_json(root / VALIDATION_PATH, result)
    (root / REPORT_PATH).parent.mkdir(parents=True, exist_ok=True)
    (root / REPORT_PATH).write_text(_report(result), encoding="utf-8")
    (root / LOG_PATH).parent.mkdir(parents=True, exist_ok=True)
    log_lines.append(f"status={result['status']}")
    log_lines.append(f"failures={json.dumps(failures, ensure_ascii=False, sort_keys=True)}")
    (root / LOG_PATH).write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    write_json(root / ROOT_DIR / "data_task09c_run_result.json", result)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return result


def _output_paths(root: Path) -> dict[str, str]:
    renders = root / f"{ROOT_DIR}/renders"
    return {
        "exploded_hero_refined.png": str(renders / "exploded_hero_refined.png"),
        "exploded_engineering_refined.png": str(renders / "exploded_engineering_refined.png"),
        "pcb_detail_refined.png": str(renders / "pcb_detail_refined.png"),
        "sensor_detail_refined.png": str(renders / "sensor_detail_refined.png"),
        "exploded_animation_preview.blend": str(root / f"{ROOT_DIR}/scene/exploded_animation_preview.blend"),
        "exploded_preview.mp4": str(renders / "exploded_preview.mp4"),
        "exploded_keyframes_contact_sheet.png": str(renders / "exploded_keyframes_contact_sheet.png"),
    }


def _report(result: dict[str, Any]) -> str:
    validation = result.get("validation") or {}
    lines = [
        "# Task 9C Refined Explosion Report",
        "",
        f"- Status: `{result['status']}`",
        "- Basis: incremental refinement of the validated R1 layout.",
        "- Primary axis: global Z.",
        "- Visible presentation parts: 22 (PART_001..PART_022).",
        "- SMALL / FRAGMENT: hidden or follow-parent metadata only; no animation tracks.",
        "",
        "## Animation preview",
        "",
        "- Duration: 18.0 seconds at 30 fps (frames 1–540).",
        "- Easing: Bezier ease-in/ease-out; overshoot disabled.",
        "- Static refined state is frame 540; assembled state is frame 1.",
        "",
        "## Actual Blender validation",
        "",
        f"- Source PART meshes: {validation.get('source_part_count')}",
        f"- Faces: {validation.get('source_faces')}",
        f"- Indexed vertices: {validation.get('source_indexed_vertices')}",
        f"- Animated parts: {validation.get('animated_part_count')}",
        f"- Hidden-part animation count: {validation.get('hidden_part_animation_count')}",
        f"- Frame 1 mismatches: {validation.get('frame1_assembled_mismatches')}",
        f"- Frame 540 mismatches: {validation.get('frame540_refined_mismatches')}",
        f"- Validation warnings: {validation.get('warnings')}",
        "",
        "## Review boundary",
        "",
        "This is a review preview, not a final commercial render. No material redesign, final lighting, or later task was started.",
    ]
    return "\n".join(lines) + "\n"


def _run_stage(stage: str, command: Sequence[str], cwd: Path, log_lines: list[str]) -> dict[str, Any]:
    completed = subprocess.run(list(command), cwd=str(cwd), capture_output=True, text=True, check=False)
    stdout, stderr = completed.stdout or "", completed.stderr or ""
    returncode = completed.returncode if "Traceback (most recent call last):" not in stderr else 1
    record = {"stage": stage, "command": list(command), "returncode": returncode, "process_returncode": completed.returncode, "stdout": stdout[-6000:], "stderr": stderr[-6000:]}
    log_lines.extend([f"stage={stage}", f"returncode={returncode}", f"stdout={stdout[-6000:]}", f"stderr={stderr[-6000:]}"])
    return record


def _last_json(output: str) -> dict[str, Any]:
    for line in reversed((output or "").splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise ValueError("Blender stage did not emit JSON")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--blender-path", default=None)
    parser.add_argument("--skip-blender", action="store_true")
    args = parser.parse_args(argv)
    result = run_task09c(args.project_root, blender_path=args.blender_path, skip_blender=args.skip_blender)
    return 0 if result["status"] in {"PASS", "SKIPPED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
