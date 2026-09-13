"""Run the fail-closed Task 10-R-PCB-V1 presentation pipeline."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Mapping, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.task08_data import write_json
from stage_09C_refined_explosion.scripts.pipeline import validate_run_result_contract as validate_task09c_result
from stage_10R_pcb_presentation.scripts.build_presentation_plan import write_presentation_configs
from stage_10R_pcb_presentation.scripts.pcb_presentation_data import (
    CAMERAS_PATH,
    COMPARISON_RENDER,
    MANIFEST_PATH,
    MATERIALS_PATH,
    RENDER_ROOT,
    REQUIRED_RENDERS,
    ROOT_DIR,
    SCENE_OUTPUT,
    VALIDATION_PATH,
)

RUN_RESULT_PATH = f"{ROOT_DIR}/data_task10R_pcb_run_result.json"
REPORT_PATH = f"{ROOT_DIR}/reports/task10R_pcb_visual_review.md"
LOG_PATH = f"{ROOT_DIR}/logs/task10R_pcb.log"


def status_from_technical(technical_pass: bool) -> dict[str, str]:
    return {
        "technical_status": "PASS" if technical_pass else "FAIL",
        "visual_status": "PENDING_HUMAN_REVIEW",
        "overall_status": "REVIEW_REQUIRED" if technical_pass else "FAIL",
    }


def require_task09c_pass(project_root: Path) -> dict[str, Any]:
    root = Path(project_root).expanduser().resolve()
    path = root / "stage_09C_refined_explosion/data_task09c_run_result.json"
    if not path.is_file():
        raise ValueError("Task 9C PASS result is required before Task 10-R-PCB-V1")
    try:
        return validate_task09c_result(json.loads(path.read_text(encoding="utf-8")))
    except Exception as exc:
        raise ValueError(f"Task 9C must be PASS before Task 10-R-PCB-V1: {exc}") from exc


def run_task10r_pcb(project_root: Path, *, blender_path: str | None = None, skip_blender: bool = False) -> dict[str, Any]:
    root = Path(project_root).expanduser().resolve()
    task09c = require_task09c_pass(root)
    write_presentation_configs(root)

    log_lines = [
        f"start_utc={datetime.now(timezone.utc).isoformat()}",
        f"project_root={root}",
        "source_geometry_modified=False",
        f"task09c_status={task09c.get('status')}",
        "text_policy=NO_TEXT_OR_ANNOTATIONS",
        "animation_policy=NO_KEYFRAMES_OR_ANIMATION_DATA",
        "render_engine=BLENDER_EEVEE",
    ]
    stages: list[dict[str, Any]] = [
        {"stage": "build_presentation_plan", "returncode": 0},
        {"stage": "build_presentation_cameras", "returncode": 0},
    ]
    failures: list[dict[str, Any]] = []
    scene_validation: dict[str, Any] | None = None

    command = [sys.executable, str(root / f"{ROOT_DIR}/scripts/generate_surface_texture.py"), "--project-root", str(root)]
    record = _run_stage("generate_surface_texture", command, root, log_lines)
    stages.append(record)
    if record["returncode"] != 0:
        failures.append(record)

    if not failures and not skip_blender:
        executable = blender_path or os.environ.get("BLENDER_PATH") or "/opt/homebrew/bin/blender"
        for stage, script in (
            ("build_presentation_scene", "build_presentation_scene.py"),
            ("render_presentation", "render_presentation.py"),
        ):
            command = [executable, "-b", "--python", str(root / f"{ROOT_DIR}/scripts/{script}"), "--", "--project-root", str(root)]
            record = _run_stage(stage, command, root, log_lines)
            stages.append(record)
            if record["returncode"] != 0:
                failures.append(record)
                break
        if not failures:
            command = [sys.executable, str(root / f"{ROOT_DIR}/scripts/compose_reference_comparison.py"), "--project-root", str(root)]
            record = _run_stage("compose_reference_comparison", command, root, log_lines)
            stages.append(record)
            if record["returncode"] != 0:
                failures.append(record)
        if not failures:
            command = [executable, "-b", "--python", str(root / f"{ROOT_DIR}/scripts/validate_presentation.py"), "--", "--project-root", str(root)]
            record = _run_stage("validate_presentation", command, root, log_lines)
            stages.append(record)
            if record["returncode"] != 0:
                failures.append(record)
            else:
                scene_validation = record.pop("json_output", None)
                if scene_validation is None:
                    failures.append({"stage": "validate_presentation_parse", "returncode": 1, "error": "Blender validation emitted no JSON"})
    elif skip_blender:
        log_lines.append("blender_status=SKIPPED_BY_REQUEST")

    technical_pass = not failures and scene_validation is not None and scene_validation.get("technical_status") == "PASS"
    statuses = status_from_technical(technical_pass)
    result: dict[str, Any] = {
        **statuses,
        "source_part_count": 82,
        "source_faces": 444296,
        "source_indexed_vertices": 221902,
        "source_geometry_modified": False,
        "animation_created": False,
        "text_objects_created": False,
        "task09c_status": task09c.get("status"),
        "outputs": _output_paths(root),
        "manifest": str(root / MANIFEST_PATH),
        "camera_config": str(root / CAMERAS_PATH),
        "validation": scene_validation,
        "stages": stages,
        "failures": failures,
    }
    write_json(root / VALIDATION_PATH, scene_validation or {**statuses, "warnings": failures})
    (root / REPORT_PATH).parent.mkdir(parents=True, exist_ok=True)
    (root / REPORT_PATH).write_text(_report(result), encoding="utf-8")
    log_lines.append(f"technical_status={statuses['technical_status']}")
    log_lines.append(f"visual_status={statuses['visual_status']}")
    log_lines.append(f"failures={json.dumps(failures, ensure_ascii=False, sort_keys=True)}")
    (root / LOG_PATH).parent.mkdir(parents=True, exist_ok=True)
    (root / LOG_PATH).write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    result["outputs"]["task10R_pcb_visual_review.md"] = str(root / REPORT_PATH)
    write_json(root / RUN_RESULT_PATH, result)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return result


def _output_paths(root: Path) -> dict[str, str]:
    render_dir = root / RENDER_ROOT
    outputs = {name: str(render_dir / name) for name in REQUIRED_RENDERS}
    outputs[COMPARISON_RENDER] = str(render_dir / COMPARISON_RENDER)
    outputs["pcb_presentation_assembly.blend"] = str(root / SCENE_OUTPUT)
    outputs["pcb_presentation_manifest.json"] = str(root / MANIFEST_PATH)
    outputs["pcb_presentation_materials.json"] = str(root / MATERIALS_PATH)
    outputs["pcb_presentation_cameras.json"] = str(root / CAMERAS_PATH)
    outputs["pcb_presentation_validation.json"] = str(root / VALIDATION_PATH)
    outputs["pcb_surface_detail.png"] = str(root / f"{ROOT_DIR}/assets/pcb_surface_detail.png")
    return outputs


def _report(result: Mapping[str, Any]) -> str:
    validation = result.get("validation") or {}
    scene = validation.get("scene", {}) if isinstance(validation, Mapping) else {}
    lines = [
        "# Task 10-R-PCB-V1 Presentation PCB Review",
        "",
        f"- Technical status: `{result.get('technical_status')}`",
        f"- Visual status: `{result.get('visual_status')}`",
        f"- Overall status: `{result.get('overall_status')}`",
        "- Scope: static presentation-layer PCB assets only; no animation.",
        "",
        "## Frozen geometry check",
        "",
        f"- Source PART meshes: {result.get('source_part_count')}",
        f"- Faces: {result.get('source_faces')}",
        f"- Indexed vertices: {result.get('source_indexed_vertices')}",
        "- Source geometry modified: `False`",
        f"- Presentation components added: {scene.get('component_count', 'n/a')}",
        "",
        "## Visual review gate",
        "",
        "The clean render intentionally contains no title, metric, leader line, or annotation.",
        "Human review must answer:",
        "",
        "| Question | Status |",
        "|---|---|",
        "| Does MAIN_PCB_PRESENTATION read as a densely populated product PCB (connectors, shield cans, caps, ICs, traces)? | PENDING_HUMAN_REVIEW |",
        "| Is the presentation hierarchy 75/15/10 with the board as the sole hero? | PENDING_HUMAN_REVIEW |",
        "| Is PART_007 no longer a visual protagonist? | PENDING_HUMAN_REVIEW |",
        "| Is the generated board recognisably aligned with REF_PCB_002 in the comparison sheet? | PENDING_HUMAN_REVIEW |",
        "",
        "## Diagnostic data",
        "",
        f"- Validation warnings: {len(validation.get('warnings', [])) if isinstance(validation, dict) else 'n/a'}",
        "",
        "## Deliberate stop boundary",
        "",
        "Animation, communication state, rugged state, annotations, sales copy, timing, reassembly, and final commercial rendering were not started.",
    ]
    return "\n".join(lines) + "\n"


def _run_stage(stage: str, command: Sequence[str], cwd: Path, log_lines: list[str]) -> dict[str, Any]:
    completed = subprocess.run(list(command), cwd=str(cwd), capture_output=True, text=True, check=False)
    stdout, stderr = completed.stdout or "", completed.stderr or ""
    returncode = completed.returncode
    if "Traceback (most recent call last):" in stderr or "Error: Cannot" in stderr:
        returncode = 1
    record = {
        "stage": stage,
        "command": list(command),
        "returncode": returncode,
        "stdout": stdout[-8000:],
        "stderr": stderr[-8000:],
    }
    if stage == "validate_presentation" and returncode == 0:
        try:
            record["json_output"] = _last_json(stdout)
        except ValueError:
            record["json_output"] = None
    log_lines.extend([f"stage={stage}", f"returncode={completed.returncode}", f"stdout={stdout[-8000:]}", f"stderr={stderr[-8000:]}"])
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
    result = run_task10r_pcb(args.project_root, blender_path=args.blender_path, skip_blender=args.skip_blender)
    return 0 if result["technical_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
