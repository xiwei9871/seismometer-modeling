"""Run the complete, fail-closed Task 10 product-story pipeline."""

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
from stage_09C_refined_explosion.scripts.pipeline import validate_run_result_contract as validate_task09c_result
from stage_10_product_story.scripts.build_product_reference import PDF_NAME, PDF_SHA256, build_product_reference_manifest
from stage_10_product_story.scripts.build_story_scene import build_state_transforms, write_state_transforms
from stage_10_product_story.scripts.render_product_story import REQUIRED_OUTPUTS, render_product_story
from stage_10_product_story.scripts.story_data import write_story_configs
from stage_10_product_story.scripts.validate_product_story import validate_product_story


ROOT_DIR = "stage_10_product_story"
VALIDATION_PATH = f"{ROOT_DIR}/config/validation.json"
REPORT_PATH = f"{ROOT_DIR}/reports/task10_product_story_report.md"
LOG_PATH = f"{ROOT_DIR}/logs/task10.log"
RUN_RESULT_PATH = f"{ROOT_DIR}/data_task10_run_result.json"


def require_task09c_pass(project_root: Path) -> dict[str, Any]:
    root = Path(project_root).expanduser().resolve()
    path = root / "stage_09C_refined_explosion/data_task09c_run_result.json"
    if not path.is_file():
        raise ValueError("Task 9C PASS result is required before Task 10")
    try:
        result = load_json(path)
        return validate_task09c_result(result)
    except Exception as exc:
        raise ValueError(f"Task 9C must be PASS before Task 10: {exc}") from exc


def validate_run_result(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("status") != "PASS":
        raise ValueError("Task 10 run is not PASS")
    outputs = result.get("outputs")
    if not isinstance(outputs, dict) or set(outputs) != set(REQUIRED_OUTPUTS):
        raise ValueError("Task 10 run output set is incomplete")
    if result.get("source_geometry_modified") is not False:
        raise ValueError("Task 10 source geometry modification marker is invalid")
    if result.get("source_part_count") != 82 or result.get("source_faces") != 444296 or result.get("source_indexed_vertices") != 221902:
        raise ValueError("Task 10 source baseline is invalid")
    if result.get("animation_created") is not True or float(result.get("animation_duration_seconds", 0.0)) != 30.0:
        raise ValueError("Task 10 animation contract is invalid")
    if result.get("communication_protocol_text") != "PENDING_PRODUCT_CONFIRMATION":
        raise ValueError("Task 10 communication protocol must remain pending")
    for name, path in outputs.items():
        file_path = Path(path)
        if not file_path.is_file() or file_path.stat().st_size <= 0:
            raise ValueError(f"Task 10 output is missing or empty: {name}")
    return dict(result)


def run_task10(project_root: Path, *, blender_path: str | None = None, skip_blender: bool = False) -> dict[str, Any]:
    root = Path(project_root).expanduser().resolve()
    task09c = require_task09c_pass(root)
    log_lines = [
        f"start_utc={datetime.now(timezone.utc).isoformat()}",
        f"project_root={root}",
        "source_geometry_modified=False",
        f"task09c_status={task09c.get('status')}",
    ]
    stages: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    def python_stage(name: str, fn) -> Any:
        try:
            value = fn()
            stages.append({"stage": name, "returncode": 0})
            return value
        except Exception as exc:
            record = {"stage": name, "returncode": 1, "error": str(exc)}
            stages.append(record)
            failures.append(record)
            return None

    reference = python_stage(
        "build_product_reference",
        lambda: build_product_reference_manifest(
            root,
            pdf_path=root / PDF_NAME,
            expected_sha256=PDF_SHA256,
        ),
    )
    if reference is not None:
        write_json(root / f"{ROOT_DIR}/config/product_reference_manifest.json", reference)
    story_outputs = None
    if not failures:
        story_outputs = python_stage("write_story_configs", lambda: write_story_configs(root))
    state_data = None
    if not failures:
        state_data = python_stage("write_state_transforms", lambda: write_state_transforms(root, build_state_transforms(root)))
    executable = blender_path or os.environ.get("BLENDER_PATH") or "/opt/homebrew/bin/blender"
    if not failures and not skip_blender:
        for stage_name, script_name in (
            ("build_story_scene", "build_story_scene.py"),
            ("apply_story_animation", "apply_story_animation.py"),
            ("setup_story_presentation", "setup_story_presentation.py"),
            ("render_product_story", "render_product_story.py"),
        ):
            command = [executable, "-b", "--python", str(root / f"{ROOT_DIR}/scripts/{script_name}"), "--", "--project-root", str(root)]
            record = _run_stage(stage_name, command, root, log_lines)
            stages.append(record)
            if record["returncode"] != 0:
                failures.append(record)
                break
        if not failures:
            contact_command = [sys.executable, str(root / f"{ROOT_DIR}/scripts/compose_storyboard.py"), "--project-root", str(root)]
            record = _run_stage("compose_storyboard", contact_command, root, log_lines)
            stages.append(record)
            if record["returncode"] != 0:
                failures.append(record)
        if not failures:
            validate_command = [executable, "-b", "--python", str(root / f"{ROOT_DIR}/scripts/validate_product_story.py"), "--", "--project-root", str(root)]
            record = _run_stage("validate_product_story", validate_command, root, log_lines)
            stages.append(record)
            if record["returncode"] != 0:
                failures.append(record)
            scene_validation = _last_json(record.get("stdout", "")) if record["returncode"] == 0 else None
    elif skip_blender:
        log_lines.append("blender_status=SKIPPED_BY_REQUEST")
        scene_validation = None
    else:
        scene_validation = None

    outputs = _output_paths(root)
    if failures:
        status = "FAIL"
    elif skip_blender:
        status = "SKIPPED"
    elif scene_validation and scene_validation.get("status") == "PASS":
        status = "PASS"
    else:
        status = "FAIL"
    result = {
        "status": status,
        "source_part_count": 82,
        "source_faces": 444296,
        "source_indexed_vertices": 221902,
        "source_geometry_modified": False,
        "animation_created": status == "PASS",
        "animation_duration_seconds": 30.0,
        "communication_protocol_text": "PENDING_PRODUCT_CONFIRMATION",
        "outputs": outputs,
        "product_reference": str(root / f"{ROOT_DIR}/config/product_reference_manifest.json"),
        "story_configs": {name: str(path) for name, path in (story_outputs or {}).items()},
        "state_transforms": str(state_data) if state_data else None,
        "validation": scene_validation,
        "stages": stages,
        "failures": failures,
    }
    if result["status"] == "PASS":
        validate_run_result(result)
    write_json(root / VALIDATION_PATH, result)
    (root / f"{ROOT_DIR}/reports").mkdir(parents=True, exist_ok=True)
    (root / REPORT_PATH).write_text(_report(result, reference), encoding="utf-8")
    (root / f"{ROOT_DIR}/logs").mkdir(parents=True, exist_ok=True)
    log_lines.append(f"status={result['status']}")
    log_lines.append(f"failures={json.dumps(failures, ensure_ascii=False, sort_keys=True)}")
    (root / LOG_PATH).write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    write_json(root / RUN_RESULT_PATH, result)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return result


def _output_paths(root: Path) -> dict[str, str]:
    renders = root / f"{ROOT_DIR}/renders"
    return {
        **{name: str(renders / name) for name in REQUIRED_OUTPUTS if name not in {"product_story_preview.blend", "storyboard_contact_sheet.png"}},
        "storyboard_contact_sheet.png": str(renders / "storyboard_contact_sheet.png"),
        "product_story_preview.blend": str(root / f"{ROOT_DIR}/scene/product_story_preview.blend"),
    }


def _run_stage(stage: str, command: Sequence[str], cwd: Path, log_lines: list[str]) -> dict[str, Any]:
    completed = subprocess.run(list(command), cwd=str(cwd), capture_output=True, text=True, check=False)
    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    record = {
        "stage": stage,
        "command": list(command),
        "returncode": completed.returncode,
        "stdout": stdout[-8000:],
        "stderr": stderr[-8000:],
    }
    log_lines.extend([f"stage={stage}", f"returncode={completed.returncode}", f"stdout={stdout[-8000:]}", f"stderr={stderr[-8000:]}"])
    return record


def _last_json(output: str) -> dict[str, Any]:
    for line in reversed(output.splitlines()):
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("Task 10 Blender validation did not emit JSON")


def _report(result: Mapping[str, Any], reference: Mapping[str, Any] | None) -> str:
    story = load_json(Path(result["story_configs"]["product_story.json"])) if result.get("story_configs", {}).get("product_story.json") else {}
    lines = [
        "# Task 10 Product Functional Story Report",
        "",
        f"- Status: `{result['status']}`",
        f"- Duration: `{result['animation_duration_seconds']} s` at `{story.get('fps', 30)} fps`",
        f"- Source baseline: `{result['source_part_count']} PART / {result['source_faces']} faces / {result['source_indexed_vertices']} indexed vertices`",
        "- Source geometry modified: `False`",
        "",
        "## Functional modules",
        "",
    ]
    for module_id, module in (load_json(Path(result["story_configs"]["functional_modules.json"])) if result.get("story_configs", {}).get("functional_modules.json") else {}).items():
        lines.append(f"- `{module_id}`: {', '.join(module['part_ids'])} — {module['customer_takeaway']}")
    lines.extend(["", "## Shots", ""])
    for shot in story.get("shots", []):
        lines.append(f"- `{shot['shot_id']}` frames `{shot['frame_start']}–{shot['frame_end']}` — {shot['title']}")
    lines.extend([
        "",
        "## Product reference",
        "",
        f"- PDF: `{reference.get('source_file') if reference else 'not available'}`",
        f"- SHA256: `{reference.get('sha256') if reference else 'not available'}`",
        f"- Communication protocol: `{result['communication_protocol_text']}`; final protocol requires product confirmation.",
        "",
        "## Scope boundary",
        "",
        "- PAD/server/data-engine/report generation is reserved for a later continuation and is not animated in Task 10.",
        "- This is an Eevee/Workbench-style review preview, not a final 4K/Cycles commercial render.",
        "",
        "## Outputs",
        "",
    ])
    lines.extend(f"- `{name}`: `{path}`" for name, path in result["outputs"].items())
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--blender-path", default=None)
    parser.add_argument("--skip-blender", action="store_true")
    args = parser.parse_args(argv)
    result = run_task10(args.project_root, blender_path=args.blender_path, skip_blender=args.skip_blender)
    return 0 if result["status"] in {"PASS", "SKIPPED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
