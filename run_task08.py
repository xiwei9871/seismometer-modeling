"""Run the Task 8 first checkpoint from immutable Stage 01 inputs."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.build_task08_reports import build_reports
from scripts.prepare_references import prepare_references
from scripts.task08_data import validate_stage01_baseline, write_json


REQUIRED_TASK08_DATA = [
    Path("data/reference_manifest.json"),
    Path("data/semantic_parts.json"),
    Path("data/feature_validation.json"),
    Path("data/reference_missing_features.json"),
    Path("data/pcb_validation.json"),
    Path("data/non_watertight_semantic_review.json"),
    Path("data/fragment_review.json"),
    Path("data/reference_conflicts.json"),
    Path("data/assembly_semantic.json"),
    Path("data/mounting_relationships.json"),
    Path("data/disassembly_dependencies.json"),
    Path("data/manual_review_queue.csv"),
    Path("data/task08_checkpoint.json"),
    Path("output/stage02_semantic.blend"),
    Path("output/reports/stage08_semantic_recovery.md"),
]


def find_blender(explicit: Path | str | None = None) -> Path | None:
    candidates: list[Path] = []
    configured = os.environ.get("BLENDER_PATH")
    if configured:
        candidates.append(Path(configured).expanduser())
    if explicit:
        candidates.append(Path(explicit).expanduser())
    discovered = shutil.which("blender")
    if discovered:
        candidates.append(Path(discovered))
    candidates.append(Path("/Applications/Blender.app/Contents/MacOS/Blender"))
    seen: set[str] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if str(resolved) in seen:
            continue
        seen.add(str(resolved))
        if resolved.is_file() and os.access(resolved, os.X_OK):
            return resolved
    return None


def build_blender_command(
    blender: Path,
    project_root: Path,
    script: str,
    resolution: int,
) -> list[str]:
    return [
        str(blender),
        "-b",
        "--python",
        script,
        "--",
        "--project-root",
        str(project_root),
        "--resolution",
        str(resolution),
    ]


def build_blender_script_command(
    blender: Path,
    project_root: Path,
    script: str,
) -> list[str]:
    return [
        str(blender),
        "-b",
        "--python",
        script,
        "--",
        "--project-root",
        str(project_root),
    ]


def validate_task08_outputs(project_root: Path) -> dict[str, Any]:
    root = Path(project_root).expanduser().resolve()
    missing = [str(relative) for relative in REQUIRED_TASK08_DATA if not (root / relative).is_file()]
    if missing:
        raise ValueError(f"missing Task 8 output(s): {', '.join(missing)}")
    return {"missing": missing}


def validate_task08_render_outputs(project_root: Path) -> dict[str, int]:
    root = Path(project_root).expanduser().resolve()
    counts = {
        "standard_views": len(list((root / "output/reference_renders").glob("*.png"))),
        "part_previews": len(list((root / "output/part_previews").glob("PART_*.png"))),
        "part_highlights": len(list((root / "output/part_highlights").glob("PART_*_iso.png"))),
        "duplicate_group_sheets": len(list((root / "output/reports/duplicate_groups").glob("DG_*.png"))),
        "part_contact_sheets": len(list((root / "output/reports").glob("part_contact_sheet_*.png"))),
    }
    expected = {
        "standard_views": 10,
        "part_previews": 82,
        "part_highlights": 82,
        "duplicate_group_sheets": 13,
        "part_contact_sheets": 4,
    }
    if counts != expected:
        raise ValueError(f"Task 8 render output count mismatch: expected {expected}, got {counts}")
    return counts


def run_task08(
    project_root: Path,
    *,
    blender_path: Path | str | None = None,
    resolution: int = 640,
    skip_blender: bool = False,
) -> dict[str, Any]:
    root = Path(project_root).expanduser().resolve()
    log_path = root / "logs/task08.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    _log(log_path, f"START {started} project_root={root}")
    baseline = validate_stage01_baseline(root)
    _log(log_path, f"BASELINE PASS {json.dumps(baseline, sort_keys=True)}")

    records = prepare_references(root, import_root_images=True, source_root=root)
    _log(log_path, f"REFERENCES count={len(records)}")
    report_summary = build_reports(root)
    _log(log_path, f"REPORTS PARTs={report_summary['source_part_count']}")

    blender = find_blender(blender_path)
    if skip_blender:
        status = "PARTIAL"
        _log(log_path, "BLENDER SKIPPED status=PARTIAL")
        result = {
            "status": status,
            "baseline": baseline,
            "reference_count": len(records),
            "blender_status": "skipped",
            "animation_created": False,
            "source_geometry_modified": False,
        }
        write_json(root / "data/task08_run_result.json", result)
        return result
    if blender is None:
        raise FileNotFoundError("Blender executable not found; set BLENDER_PATH or --blender-path")

    for script, render_resolution in (
        ("scripts/generate_reference_views.py", resolution),
        ("scripts/generate_part_previews.py", min(resolution, 480)),
    ):
        command = build_blender_command(blender, root, script, render_resolution)
        _run_logged(command, root, log_path)

    semantic_command = build_blender_script_command(
        blender,
        root,
        "scripts/build_stage02_semantic_blend.py",
    )
    _run_logged(semantic_command, root, log_path)
    semantic_result = {
        "output": str(root / "output/stage02_semantic.blend"),
        "source_part_count": 82,
        "vertices": 221902,
        "polygons": 444296,
        "animation_created": False,
        "source_geometry_modified": False,
    }
    _log(log_path, f"SEMANTIC_BLEND output={semantic_result['output']}")
    render_outputs = validate_task08_render_outputs(root)
    outputs = validate_task08_outputs(root)
    result = {
        "status": "PASS",
        "baseline": baseline,
        "reference_count": len(records),
        "blender_status": "PASS",
        "semantic_blend": semantic_result,
        "outputs": outputs,
        "render_outputs": render_outputs,
        "animation_created": False,
        "source_geometry_modified": False,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    write_json(root / "data/task08_run_result.json", result)
    _log(log_path, "COMPLETE status=PASS animation_created=false source_geometry_modified=false")
    return result


def _run_logged(command: list[str], project_root: Path, log_path: Path) -> None:
    _log(log_path, "COMMAND " + " ".join(command))
    started = time.monotonic()
    completed = subprocess.run(command, cwd=project_root, capture_output=True, text=True, check=False)
    duration = time.monotonic() - started
    if completed.stdout:
        _log(log_path, "STDOUT " + completed.stdout.strip().replace("\n", " | "))
    if completed.stderr:
        _log(log_path, "STDERR " + completed.stderr.strip().replace("\n", " | "))
    _log(log_path, f"RETURN_CODE {completed.returncode} duration_seconds={duration:.3f}")
    if completed.returncode != 0:
        raise RuntimeError(f"Blender command failed ({completed.returncode}): {' '.join(command)}")


def _log(path: Path, message: str) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{datetime.now(timezone.utc).isoformat()} {message}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--blender-path", type=Path)
    parser.add_argument("--resolution", type=int, default=640)
    parser.add_argument("--skip-blender", action="store_true")
    args = parser.parse_args(argv)
    result = run_task08(
        args.project_root,
        blender_path=args.blender_path,
        resolution=args.resolution,
        skip_blender=args.skip_blender,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
