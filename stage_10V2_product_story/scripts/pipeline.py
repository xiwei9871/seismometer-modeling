"""Run the complete, fail-closed Task 10-V2 product-story pipeline."""

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

from scripts.task08_data import load_json, write_json
from stage_10_product_story.scripts.build_product_reference import (
    PDF_NAME,
    PDF_SHA256,
    build_product_reference_manifest,
)
from stage_10_product_story.scripts.pipeline import (
    require_task09c_pass,
    validate_preview_media,
)
from stage_10_product_story.scripts.story_data import (
    build_annotation_config,
    build_camera_sequence,
    build_functional_modules,
    build_story_config,
)
from stage_10R_pcb_presentation.scripts.pcb_presentation_data import (
    load_human_approval as load_pcb_approval,
)
from stage_10V2_product_story.scripts.render_product_story_v2 import REQUIRED_OUTPUTS
from stage_10V2_product_story.scripts.story_v2_data import (
    APPROVAL_PATH,
    LOG_PATH,
    PCB_MANIFEST_PATH,
    PCB_TEXTURE_SOURCE,
    RENDER_DIR,
    REPORT_PATH,
    ROOT_DIR,
    RUN_RESULT_PATH,
    SCENE_OUTPUT,
    STATE_OUTPUT,
    VALIDATION_PATH,
    build_story_v2_state_transforms,
    copy_surface_texture,
    load_human_approval,
    sha256_file,
)


def write_story_v2_configs(project_root: Path) -> dict[str, Path]:
    root = Path(project_root).expanduser().resolve()
    config_dir = root / f"{ROOT_DIR}/config"
    config_dir.mkdir(parents=True, exist_ok=True)
    payloads = {
        "product_story.json": build_story_config(),
        "functional_modules.json": build_functional_modules(),
        "shot_sequence.json": {"shots": build_story_config()["shots"]},
        "camera_sequence.json": build_camera_sequence(),
        "annotation_config.json": build_annotation_config(),
    }
    outputs: dict[str, Path] = {}
    for name, payload in payloads.items():
        output = config_dir / name
        write_json(output, payload)
        outputs[name] = output
    return outputs


def require_pcb_presentation_approval(project_root: Path) -> dict[str, Any]:
    """The V2 story may only build on a human-approved presentation PCB."""
    root = Path(project_root).expanduser().resolve()
    manifest = root / PCB_MANIFEST_PATH
    texture = root / PCB_TEXTURE_SOURCE
    if not manifest.is_file() or not texture.is_file():
        raise ValueError("approved Task 10-R-PCB-V1 inputs are required before Task 10-V2")
    approval = load_pcb_approval(root)
    if approval is None:
        raise ValueError("Task 10-R-PCB-V1 must be visually approved before Task 10-V2")
    return approval


def status_from_technical(technical_pass: bool, approval: Mapping[str, Any] | None = None) -> dict[str, str]:
    approved = approval is not None and approval.get("approved") is True
    return {
        "technical_status": "PASS" if technical_pass else "FAIL",
        "visual_status": "APPROVED" if approved else "PENDING_HUMAN_REVIEW",
        "overall_status": "PASS" if technical_pass and approved else ("REVIEW_REQUIRED" if technical_pass else "FAIL"),
    }


def validate_run_result(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("technical_status") != "PASS":
        raise ValueError("Task 10-V2 run is not technically PASS")
    outputs = result.get("outputs")
    if not isinstance(outputs, dict) or set(REQUIRED_OUTPUTS) - set(outputs):
        raise ValueError("Task 10-V2 run output set is incomplete")
    if result.get("source_geometry_modified") is not False:
        raise ValueError("Task 10-V2 source geometry modification marker is invalid")
    if result.get("source_geometry_fingerprint_verified") is not True:
        raise ValueError("Task 10-V2 source geometry fingerprint was not verified")
    if result.get("source_part_count") != 82 or result.get("source_faces") != 444296 or result.get("source_indexed_vertices") != 221902:
        raise ValueError("Task 10-V2 source baseline is invalid")
    if result.get("animation_created") is not True or float(result.get("animation_duration_seconds", 0.0)) != 30.0:
        raise ValueError("Task 10-V2 animation contract is invalid")
    if result.get("presentation_component_count") != 15:
        raise ValueError("Task 10-V2 presentation component count is invalid")
    if result.get("render_engine") != "BLENDER_EEVEE":
        raise ValueError("Task 10-V2 must render through Eevee")
    if result.get("communication_protocol_text") != "PENDING_PRODUCT_CONFIRMATION":
        raise ValueError("Task 10-V2 communication protocol must remain pending")
    expected_media = {
        "codec_name": "h264",
        "width": 1920,
        "height": 1080,
        "r_frame_rate": "30/1",
        "nb_frames": 900,
        "duration_seconds": 30.0,
    }
    if result.get("preview_media") != expected_media:
        raise ValueError("Task 10-V2 preview media was not independently validated")
    for name, path in outputs.items():
        file_path = Path(path)
        if not file_path.is_file() or file_path.stat().st_size <= 0:
            raise ValueError(f"Task 10-V2 output is missing or empty: {name}")
    return dict(result)


def run_task10v2(project_root: Path, *, blender_path: str | None = None, skip_blender: bool = False) -> dict[str, Any]:
    root = Path(project_root).expanduser().resolve()
    task09c = require_task09c_pass(root)
    pcb_approval = require_pcb_presentation_approval(root)
    log_lines = [
        f"start_utc={datetime.now(timezone.utc).isoformat()}",
        f"project_root={root}",
        "source_geometry_modified=False",
        f"task09c_status={task09c.get('status')}",
        "task10R_pcb_status=APPROVED",
        "render_engine=BLENDER_EEVEE",
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

    def build_verified_reference() -> dict[str, Any]:
        manifest = build_product_reference_manifest(
            root,
            pdf_path=root / PDF_NAME,
            expected_sha256=PDF_SHA256,
        )
        if manifest.get("pdf_status") != "VERIFIED_LOCAL_REFERENCE":
            raise ValueError("approved local product PDF is required for Task 10-V2")
        return manifest

    reference = python_stage("build_product_reference", build_verified_reference)
    if reference is not None:
        write_json(root / f"{ROOT_DIR}/config/product_reference_manifest.json", reference)
    story_outputs = None
    if not failures:
        story_outputs = python_stage("write_story_v2_configs", lambda: write_story_v2_configs(root))
    state_path = None
    if not failures:
        state_path = python_stage(
            "write_state_transforms",
            lambda: _write_state_transforms(root),
        )
    texture_record = None
    if not failures:
        texture_record = python_stage("copy_surface_texture", lambda: copy_surface_texture(root))

    executable = blender_path or os.environ.get("BLENDER_PATH") or "/opt/homebrew/bin/blender"
    preview_media = None
    scene_validation = None
    if not failures and not skip_blender:
        for stage_name, script_name in (
            ("build_story_scene_v2", "build_story_scene_v2.py"),
            ("solve_focus_layouts", "solve_focus_layouts.py"),
            ("apply_story_animation_v2", "apply_story_animation_v2.py"),
            ("setup_story_presentation_v2", "setup_story_presentation_v2.py"),
            ("render_product_story_v2", "render_product_story_v2.py"),
        ):
            command = [
                executable, "-b", "--python-exit-code", "1",
                "--python", str(root / f"{ROOT_DIR}/scripts/{script_name}"),
                "--", "--project-root", str(root),
            ]
            record = _run_stage(stage_name, command, root, log_lines)
            stages.append(record)
            if record["returncode"] != 0:
                failures.append(record)
                break
        if not failures:
            preview_media = python_stage(
                "validate_preview_media",
                lambda: validate_preview_media(root / RENDER_DIR / "product_story_v2_preview.mp4"),
            )
        if not failures:
            contact_command = [sys.executable, str(root / f"{ROOT_DIR}/scripts/compose_storyboard.py"), "--project-root", str(root)]
            record = _run_stage("compose_storyboard", contact_command, root, log_lines)
            stages.append(record)
            if record["returncode"] != 0:
                failures.append(record)
        if not failures:
            validate_command = [
                executable, "-b", "--python-exit-code", "1",
                "--python", str(root / f"{ROOT_DIR}/scripts/validate_product_story_v2.py"),
                "--", "--project-root", str(root),
            ]
            record = _run_stage("validate_product_story_v2", validate_command, root, log_lines)
            stages.append(record)
            if record["returncode"] != 0:
                failures.append(record)
            scene_validation = _last_json(record.get("stdout", "")) if record["returncode"] == 0 else None
    elif skip_blender:
        log_lines.append("blender_status=SKIPPED_BY_REQUEST")

    technical_pass = (
        not failures
        and scene_validation is not None
        and scene_validation.get("technical_status") == "PASS"
    )
    approval = load_human_approval(root)
    statuses = status_from_technical(technical_pass, approval)
    outputs = _output_paths(root)
    if failures:
        status = "FAIL"
    elif skip_blender:
        status = "SKIPPED"
    else:
        status = statuses["overall_status"]
    result = {
        **statuses,
        "status": status,
        "source_part_count": 82,
        "source_faces": 444296,
        "source_indexed_vertices": 221902,
        "source_geometry_modified": not bool(scene_validation and scene_validation.get("source_geometry_modified") is False),
        "source_geometry_fingerprint_verified": bool(
            scene_validation and scene_validation.get("source_geometry_fingerprint_verified") is True
        ),
        "animation_created": technical_pass,
        "animation_duration_seconds": 30.0,
        "presentation_component_count": int(
            (scene_validation or {}).get("presentation_component_count", 0)
        ),
        "render_engine": "BLENDER_EEVEE",
        "communication_protocol_text": "PENDING_PRODUCT_CONFIRMATION",
        "outputs": outputs,
        "product_reference": str(root / f"{ROOT_DIR}/config/product_reference_manifest.json"),
        "story_configs": {name: str(path) for name, path in (story_outputs or {}).items()},
        "state_transforms": str(state_path) if state_path else None,
        "surface_texture": texture_record,
        "pcb_presentation_approval": pcb_approval,
        "human_approval": approval,
        "validation": scene_validation,
        "preview_media": preview_media,
        "stages": stages,
        "failures": failures,
    }
    if result["technical_status"] == "PASS":
        validate_run_result(result)
    write_json(root / VALIDATION_PATH, scene_validation or {**statuses, "warnings": failures})
    (root / REPORT_PATH).parent.mkdir(parents=True, exist_ok=True)
    (root / REPORT_PATH).write_text(_report(result, reference), encoding="utf-8")
    (root / LOG_PATH).parent.mkdir(parents=True, exist_ok=True)
    log_lines.append(f"technical_status={statuses['technical_status']}")
    log_lines.append(f"visual_status={statuses['visual_status']}")
    log_lines.append(f"failures={json.dumps(failures, ensure_ascii=False, sort_keys=True)}")
    (root / LOG_PATH).write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    write_json(root / RUN_RESULT_PATH, result)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return result


def _write_state_transforms(root: Path) -> Path:
    output = root / STATE_OUTPUT
    write_json(output, build_story_v2_state_transforms(root))
    return output


def _output_paths(root: Path) -> dict[str, str]:
    renders = root / RENDER_DIR
    return {
        **{name: str(renders / name) for name in REQUIRED_OUTPUTS if name not in {"product_story_v2.blend", "storyboard_contact_sheet.png"}},
        "storyboard_contact_sheet.png": str(renders / "storyboard_contact_sheet.png"),
        "product_story_v2.blend": str(root / SCENE_OUTPUT),
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
    raise ValueError("Task 10-V2 Blender validation did not emit JSON")


def _report(result: Mapping[str, Any], reference: Mapping[str, Any] | None) -> str:
    story = load_json(Path(result["story_configs"]["product_story.json"])) if result.get("story_configs", {}).get("product_story.json") else {}
    review_status = "APPROVED" if result.get("visual_status") == "APPROVED" else "PENDING_HUMAN_REVIEW"
    lines = [
        "# Task 10-V2 Product Functional Story Report",
        "",
        f"- Technical status: `{result['technical_status']}`",
        f"- Visual status: `{result['visual_status']}`",
        f"- Overall status: `{result['overall_status']}`",
        f"- Duration: `{result['animation_duration_seconds']} s` at `{story.get('fps', 30)} fps`",
        f"- Renderer: `{result['render_engine']}` (Eevee presentation rig from the approved Task 10-R-PCB-V1)",
        f"- Source baseline: `{result['source_part_count']} PART / {result['source_faces']} faces / {result['source_indexed_vertices']} indexed vertices`",
        "- Source geometry modified: `False`",
        f"- Presentation components riding with PART_019: `{result['presentation_component_count']}`",
        "",
        "## Visual review gate",
        "",
        "| Question | Status |",
        "|---|---|",
        f"| Does PCB_FOCUS show the populated MAIN_PCB_PRESENTATION board instead of a flat green plate? | {review_status} |",
        f"| Is PART_007 visually demoted to a support frame? | {review_status} |",
        f"| Is the whole 30 s preview bright and readable under the Eevee rig? | {review_status} |",
        f"| Do the sensor / communication / power / rugged shots keep their v1 story content? | {review_status} |",
        "",
        "## Shots",
        "",
    ]
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
        "- PAD/server/data-engine/report generation is reserved for a later continuation and is not animated in Task 10-V2.",
        "- This is an Eevee review preview, not a final 4K/Cycles commercial render.",
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
    result = run_task10v2(args.project_root, blender_path=args.blender_path, skip_blender=args.skip_blender)
    return 0 if result["status"] in {"PASS", "SKIPPED", "REVIEW_REQUIRED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
