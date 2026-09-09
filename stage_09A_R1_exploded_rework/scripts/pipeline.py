"""Run the deterministic Task 9A-R1 static exploded-layout pipeline."""

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

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.task08_data import load_json, write_json
from scripts.task09_data import validate_task09_baseline

from stage_09A_R1_exploded_rework.scripts.build_explosion_groups import (
    build_explosion_layout,
    write_explosion_configs,
)
from stage_09A_R1_exploded_rework.scripts.compose_contact_sheet import compose_contact_sheet
from stage_09A_R1_exploded_rework.scripts.validate_explosion import (
    build_explosion_validation,
    build_layout_report,
    build_validation_report,
)


R1_DIR = "stage_09A_R1_exploded_rework"
BLEND_PATH = f"{R1_DIR}/scene/exploded_layout_v2.blend"
RENDER_DIR = f"{R1_DIR}/renders"
REPORT_DIR = f"{R1_DIR}/reports"
LOG_PATH = f"{R1_DIR}/logs/task09a_r1.log"
VALIDATION_PATH = "data/explosion_validation_r1.json"
CONFIG_VALIDATION_PATH = f"{R1_DIR}/config/explosion_validation.json"
RUN_RESULT_PATH = "data/task09a_r1_run_result.json"
REQUIRED_RENDER_NAMES = ("exploded_hero", "exploded_engineering", "exploded_top", "exploded_rear")


def blender_stage_succeeded(returncode: int, stderr: str) -> bool:
    """Treat non-zero exits and unhandled Blender tracebacks as failures."""
    return int(returncode) == 0 and "Traceback (most recent call last):" not in (stderr or "")


def run_task09a_r1(
    project_root: Path,
    *,
    blender_path: str | None = None,
    skip_blender: bool = False,
) -> dict[str, Any]:
    """Plan, build, render, validate, report, and log the R1 result."""
    root = Path(project_root).expanduser().resolve()
    baseline = validate_task09_baseline(root)
    layout = build_explosion_layout(root)
    config_paths = write_explosion_configs(root, layout)
    log_path = root / LOG_PATH
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_lines = [
        f"start_utc={datetime.now(timezone.utc).isoformat()}",
        f"project_root={root}",
        f"source_sha256={baseline['source_sha256']}",
        f"source_parts={baseline['source_parts']}",
        f"faces={baseline['faces']}",
        f"indexed_vertices={baseline['indexed_vertices']}",
        "blender_version_expected=5.2.1",
        f"config_paths={json.dumps({key: str(path) for key, path in config_paths.items()}, ensure_ascii=False, sort_keys=True)}",
    ]
    failures: list[dict[str, Any]] = []
    scene_result: dict[str, Any] | None = None
    render_result: dict[str, Any] | None = None
    actual_scene_validation: dict[str, Any] | None = None
    if skip_blender:
        status = "SKIPPED"
        log_lines.append("blender_status=SKIPPED_BY_REQUEST")
    else:
        executable = blender_path or os.environ.get("BLENDER_PATH") or "/opt/homebrew/bin/blender"
        builder_command = [
            executable, "-b", "--python",
            str(root / f"{R1_DIR}/scripts/apply_explosion_layout.py"),
            "--", "--project-root", str(root),
        ]
        builder = _run_stage("build_scene", builder_command, root, log_lines)
        if builder["returncode"] != 0:
            failures.append(builder)
        else:
            scene_result = _last_json(builder["stdout"])
            renderer_command = [
                executable, "-b", "--python",
                str(root / f"{R1_DIR}/scripts/setup_explosion_render.py"),
                "--", "--project-root", str(root),
            ]
            renderer = _run_stage("render_views", renderer_command, root, log_lines)
            if renderer["returncode"] != 0:
                failures.append(renderer)
            else:
                render_result = _last_json(renderer["stdout"])
                render_paths = [root / RENDER_DIR / f"{name}.png" for name in REQUIRED_RENDER_NAMES]
                try:
                    compose_contact_sheet(
                        root / RENDER_DIR,
                        root / RENDER_DIR / "exploded_contact_sheet.png",
                    )
                except Exception as exc:
                    failures.append({"stage": "compose_contact_sheet", "returncode": 1, "error": str(exc)})
                else:
                    missing = [
                        str(path) for path in render_paths + [root / RENDER_DIR / "exploded_contact_sheet.png"]
                        if not path.is_file() or path.stat().st_size == 0
                    ]
                    if missing:
                        failures.append({"stage": "render_outputs", "returncode": 1, "error": f"missing outputs: {missing}"})
            if not failures:
                validator_command = [
                    executable, "-b", "--python",
                    str(root / f"{R1_DIR}/scripts/validate_explosion.py"),
                    "--", "--project-root", str(root),
                ]
                validator = _run_stage("validate_blender_scene", validator_command, root, log_lines)
                if validator["returncode"] != 0:
                    failures.append(validator)
                else:
                    actual_scene_validation = _last_json(validator["stdout"])
        status = "PASS" if not failures else "FAIL"

    camera_config = load_json(root / f"{R1_DIR}/config/camera_config.json")
    render_paths = [root / RENDER_DIR / f"{name}.png" for name in REQUIRED_RENDER_NAMES]
    render_paths.append(root / RENDER_DIR / "exploded_contact_sheet.png")
    validation = build_explosion_validation(
        layout,
        camera_config=camera_config,
        render_paths=render_paths,
        scene_validation=actual_scene_validation,
    )
    if status == "PASS" and validation["status"] != "PASS":
        status = "REVIEW"
    validation = {**validation, "pipeline_status": status}
    write_json(root / VALIDATION_PATH, validation)
    write_json(root / CONFIG_VALIDATION_PATH, validation)
    report_path = root / REPORT_DIR / "exploded_layout_report.md"
    validation_report_path = root / REPORT_DIR / "validation_report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        build_layout_report(layout, validation, scene_output=str(root / BLEND_PATH)),
        encoding="utf-8",
    )
    validation_report_path.write_text(build_validation_report(validation), encoding="utf-8")
    log_lines.extend(
        [
            f"visible_part_count={sum(p['presentation_visibility'] == 'VISIBLE' for p in layout['parts'].values())}",
            f"hidden_part_count={sum(p['presentation_visibility'] == 'HIDDEN' for p in layout['parts'].values())}",
            f"duplicate_groups_not_used=0",
            f"warnings={json.dumps(validation['warnings'], ensure_ascii=False, sort_keys=True)}",
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
        "visible_part_count": validation["visible_part_count"],
        "hidden_part_count": validation["hidden_part_count"],
        "animation_created": False,
        "keyframe_count": 0,
        "source_geometry_modified": False,
        "scene": scene_result,
        "renders": render_result,
        "config": {key: str(path) for key, path in config_paths.items()},
        "validation": str(root / VALIDATION_PATH),
        "config_validation": str(root / CONFIG_VALIDATION_PATH),
        "report": str(report_path),
        "validation_report": str(validation_report_path),
        "log": str(log_path),
        "failures": failures,
    }
    write_json(root / RUN_RESULT_PATH, result)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return result


def _run_stage(stage: str, command: Sequence[str], cwd: Path, log_lines: list[str]) -> dict[str, Any]:
    completed = subprocess.run(list(command), cwd=str(cwd), capture_output=True, text=True, check=False)
    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    effective = completed.returncode if blender_stage_succeeded(completed.returncode, stderr) else 1
    record = {
        "stage": stage,
        "command": list(command),
        "returncode": effective,
        "process_returncode": completed.returncode,
        "stdout": stdout[-6000:],
        "stderr": stderr[-6000:],
    }
    log_lines.extend(
        [
            f"stage={stage}",
            f"command={json.dumps(list(command), ensure_ascii=False)}",
            f"process_returncode={completed.returncode}",
            f"returncode={effective}",
            f"stdout={stdout[-6000:]}",
            f"stderr={stderr[-6000:]}",
        ]
    )
    return record


def _last_json(output: str) -> dict[str, Any]:
    for line in reversed((output or "").splitlines()):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, Mapping):
            return dict(payload)
    raise ValueError("Blender stage did not emit a JSON result")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--blender-path", default=None)
    parser.add_argument("--skip-blender", action="store_true")
    args = parser.parse_args(argv)
    result = run_task09a_r1(args.project_root, blender_path=args.blender_path, skip_blender=args.skip_blender)
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
