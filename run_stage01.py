"""Run the repeatable, non-destructive Stage 01 STL recovery pipeline."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any

from scripts import analyze_parts, analyze_stl, detect_duplicate_parts
from scripts.import_and_split_blender import build_assembly_initial_payload


DEFAULT_BLENDER_PATH = Path("/Applications/Blender.app/Contents/MacOS/Blender")
STANDARD_OUTPUTS = (
    Path("data/source_model_report.json"),
    Path("data/parts_manifest.csv"),
    Path("data/parts_manifest.json"),
    Path("data/duplicate_groups.json"),
    Path("data/suspicious_fragments.json"),
    Path("data/mesh_quality_report.json"),
    Path("data/assembly_initial.json"),
    Path("data/stage01_run_result.json"),
    Path("output/reports/stage01_report.md"),
    Path("output/stage01_split.blend"),
)
TEMP_OUTPUTS = (
    Path("data/.parts_manifest_predup.json"),
    Path("data/.parts_manifest_predup.csv"),
)


def ensure_project_dirs(project_root: Path) -> None:
    """Create the directories used by Stage 01 generated data."""
    for relative_path in ("source", "scripts", "data", "output/reports", "logs"):
        (Path(project_root) / relative_path).mkdir(parents=True, exist_ok=True)


def choose_source_file(project_root: Path) -> tuple[Path, list[str]]:
    """Choose an STL from source/ first, or from the project root as fallback."""
    project_root = Path(project_root)
    source_candidates = _stl_files(project_root / "source")
    if source_candidates:
        selected = select_largest_stl(source_candidates)
        if len(source_candidates) == 1:
            return selected, []
        return selected, [
            "Multiple STL source files found in source/; selection order is "
            "file size, then filename.casefold(), then original filename."
        ]

    root_candidates = _stl_files(project_root)
    if not root_candidates:
        raise FileNotFoundError("No STL source file found in source/ or project root")

    selected = select_largest_stl(root_candidates)
    if len(root_candidates) == 1:
        warning = (
            "Using the unique STL source file in the project root; it will be "
            "copied byte-for-byte into source/."
        )
    else:
        warning = (
            "Multiple STL source files found in the project root; selection order is "
            "file size, then filename.casefold(), then original filename."
        )
    return selected, [warning]


def select_largest_stl(candidates: list[Path]) -> Path:
    """Select an STL deterministically by size and case-stable filename."""
    return max(
        candidates,
        key=lambda path: (path.stat().st_size, path.name.casefold(), path.name),
    )


def write_stage_log(
    path: Path,
    level: str,
    message: str,
    *,
    part_id: str | None = None,
    stage: str | None = None,
) -> None:
    """Append one structured, single-line entry to the Stage 01 log."""
    fields = [
        datetime.now(timezone.utc).isoformat(),
        f"level={str(level).upper()}",
    ]
    if stage is not None:
        fields.append(f"stage={stage}")
    if part_id is not None:
        fields.append(f"part_id={part_id}")
    fields.append(f"message={_one_line(message)}")
    log_path = Path(path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(" ".join(fields) + "\n")


def copy_root_source_if_needed(project_root: Path, selected: Path) -> Path:
    """Copy a selected root STL to source/ without overwriting a differing copy."""
    project_root = Path(project_root).expanduser().resolve()
    selected = Path(selected).expanduser().resolve()
    source_dir = project_root / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    destination = source_dir / selected.name

    if destination.exists():
        if not destination.is_file():
            raise ValueError(f"canonical source path is not a file: {destination}")
        if _file_identity(destination) != _file_identity(selected):
            raise ValueError(
                "canonical source already exists with different bytes/hash; "
                f"refusing to overwrite: {destination}"
            )
        return destination

    before = _file_identity(selected)
    shutil.copy2(selected, destination)
    after = _file_identity(selected)
    if after != before:
        raise RuntimeError("root STL changed while copying it to source/")
    if _file_identity(destination) != before:
        raise RuntimeError("canonical source copy failed byte/hash verification")
    return destination


def find_blender(explicit: str | Path | None = None) -> Path | None:
    """Find Blender in the requested precedence order.

    The project deliberately gives BLENDER_PATH precedence over the explicit
    CLI option, matching the Stage 01 runbook.
    """
    candidates: list[Path] = []
    environment = os.environ.get("BLENDER_PATH")
    if environment:
        candidates.append(Path(environment).expanduser())
    if explicit:
        candidates.append(Path(explicit).expanduser())
    path_candidate = shutil.which("blender")
    if path_candidate:
        candidates.append(Path(path_candidate))
    candidates.append(DEFAULT_BLENDER_PATH)

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


def run_python_stage(
    project_root: Path,
    blender_path: Path | str | None = None,
    *,
    source_file: Path | str | None = None,
    skip_blender: bool = False,
) -> dict[str, Any]:
    """Run Python analysis, duplicate/report closure, and optional Blender stage."""
    root = Path(project_root).expanduser().resolve()
    ensure_project_dirs(root)
    log_path = root / "logs/stage01.log"
    run_started = time.monotonic()
    write_stage_log(log_path, "INFO", "===== Stage 01 run started =====", stage="pipeline")
    write_stage_log(
        log_path,
        "INFO",
        "start_time_utc=" + datetime.now(timezone.utc).isoformat(),
        stage="pipeline",
    )
    write_stage_log(
        log_path,
        "INFO",
        "dependencies=" + json.dumps(_dependency_versions(), sort_keys=True),
        stage="pipeline",
    )

    state: dict[str, Any] = {
        "python_exit_code": 1,
        "blender_exit_code": None,
        "blender_status": "not_run",
        "source_file": None,
        "source_sha256_before": None,
        "source_sha256_after": None,
        "component_count": None,
        "manifest_count": None,
        "duplicate_group_count": None,
        "fragment_count": None,
        "face_count": None,
        "indexed_vertex_count": None,
        "output_blend": str(root / "output/stage01_split.blend"),
        "exit_code": 1,
    }
    current_stage = "source_selection"
    selected_source: Path | None = None

    try:
        _clear_generated_outputs(
            root,
            None,
            extra_sources=_requested_source_candidates(root, source_file),
        )
        selected_source, warnings = _resolve_requested_source(root, source_file)
        for warning in warnings:
            write_stage_log(log_path, "WARNING", warning, stage="source_selection")

        if selected_source.parent == root:
            selected_source = copy_root_source_if_needed(root, selected_source)
        state["source_file"] = str(selected_source)
        _clear_generated_outputs(root, selected_source)
        source_identity = _file_identity(selected_source)
        state["source_sha256_before"] = source_identity[1]
        write_stage_log(
            log_path,
            "INFO",
            f"source={selected_source} source_sha256_before={source_identity[1]} "
            f"source_size_bytes={source_identity[0]}",
            stage="source_selection",
        )

        current_stage = "analyze_stl"
        source_report = _run_stage(
            log_path,
            "analyze_stl",
            lambda: analyze_stl.analyze_source_file(selected_source),
        )
        if source_report.get("file_sha256") != source_identity[1]:
            raise ValueError("analyze_stl source hash does not match pre-run hash")
        state["face_count"] = source_report.get("faces")
        state["indexed_vertex_count"] = source_report.get("vertices")
        _run_stage(
            log_path,
            "analyze_stl",
            lambda: analyze_stl.write_json(root / "data/source_model_report.json", source_report),
        )

        current_stage = "analyze_parts"
        records, _metadata = _run_stage(
            log_path,
            "analyze_parts",
            lambda: analyze_parts.build_part_records(source_report),
        )
        quality_report = _run_stage(
            log_path,
            "analyze_parts",
            lambda: analyze_parts.build_mesh_quality_report(source_report),
        )
        predup_json = root / TEMP_OUTPUTS[0]
        predup_csv = root / TEMP_OUTPUTS[1]
        _run_stage(
            log_path,
            "analyze_parts",
            lambda: analyze_parts.write_manifest_json(predup_json, records),
        )
        _run_stage(
            log_path,
            "analyze_parts",
            lambda: analyze_parts.write_manifest_csv(predup_csv, records),
        )
        _run_stage(
            log_path,
            "analyze_parts",
            lambda: analyze_parts.write_suspicious_fragments(
                root / "data/suspicious_fragments.json", records
            ),
        )
        _run_stage(
            log_path,
            "analyze_parts",
            lambda: analyze_parts.write_mesh_quality_report(
                root / "data/mesh_quality_report.json", quality_report
            ),
        )

        current_stage = "detect_duplicate_parts"
        predup_records = _load_json_list(predup_json)
        duplicate_report = _run_stage(
            log_path,
            "detect_duplicate_parts",
            lambda: detect_duplicate_parts.group_duplicate_parts(predup_records),
        )
        final_records = _run_stage(
            log_path,
            "detect_duplicate_parts",
            lambda: detect_duplicate_parts.apply_duplicate_groups(
                predup_records, duplicate_report
            ),
        )
        _run_stage(
            log_path,
            "detect_duplicate_parts",
            lambda: analyze_parts.write_manifest_json(
                root / "data/parts_manifest.json", final_records
            ),
        )
        _run_stage(
            log_path,
            "detect_duplicate_parts",
            lambda: analyze_parts.write_manifest_csv(
                root / "data/parts_manifest.csv", final_records
            ),
        )
        _write_strict_json(root / "data/duplicate_groups.json", duplicate_report)
        _remove_generated_path(predup_json, selected_source)
        _remove_generated_path(predup_csv, selected_source)

        current_stage = "manifest_validation"
        component_count = source_report.get("connected_component_count")
        if component_count != len(final_records):
            raise ValueError(
                "component count mismatch: source report has "
                f"{component_count}, manifest has {len(final_records)}"
            )
        state["component_count"] = component_count
        state["manifest_count"] = len(final_records)
        state["duplicate_group_count"] = duplicate_report.get("group_count", 0)
        state["fragment_count"] = sum(
            record.get("suspected_fragment") is True for record in final_records
        )
        write_stage_log(
            log_path,
            "INFO",
            f"component_count={component_count} manifest_count={len(final_records)} "
            f"duplicate_groups={state['duplicate_group_count']} "
            f"fragments={state['fragment_count']}",
            stage="manifest_validation",
        )

        current_stage = "assembly_initial"
        assembly_payload = build_assembly_initial_payload(
            final_records,
            source_file=str(selected_source),
            source_sha256=source_identity[1],
        )
        _write_strict_json(root / "data/assembly_initial.json", assembly_payload)
        source_after_python = _file_identity(selected_source)
        if source_after_python != source_identity:
            raise RuntimeError("source STL changed during Python stages")

        current_stage = "blender"
        if skip_blender:
            state["blender_status"] = "skipped"
            state["blender_exit_code"] = None
            write_stage_log(
                log_path,
                "WARNING",
                "BLENDER_SKIPPED by --skip-blender",
                stage="blender",
            )
        else:
            resolved_blender = find_blender(blender_path)
            if resolved_blender is None:
                state["blender_status"] = "not_found"
                state["blender_exit_code"] = 2
                write_stage_log(
                    log_path,
                    "WARNING",
                    "BLENDER_NOT_FOUND; Python outputs are available but no .blend was generated",
                    stage="blender",
                )
            else:
                state["blender_path"] = str(resolved_blender)
                blender_code = run_blender_stage(root, resolved_blender, selected_source)
                state["blender_exit_code"] = blender_code
                state["blender_status"] = "available" if blender_code == 0 else "failed"

        source_after = _file_identity(selected_source)
        state["source_sha256_after"] = source_after[1]
        if source_after != source_identity:
            raise RuntimeError("source STL changed during Stage 01")

        state["python_exit_code"] = 0
        state["exit_code"] = {
            "not_found": 2,
            "skipped": 2,
            "failed": 1,
            "available": 0,
        }.get(state["blender_status"], 1)
        report_text = analyze_parts.render_stage01_report(
            source_report,
            final_records,
            duplicate_report,
            quality_report,
            pipeline_status=_report_pipeline_status(root, state),
        )
        analyze_parts.write_stage01_report(
            root / "output/reports/stage01_report.md", report_text
        )
        state["status"] = _run_status(state)
        state["finished_at"] = _finished_at()
        _write_run_result(root / "data/stage01_run_result.json", state)
        write_stage_log(
            log_path,
            "INFO" if state["exit_code"] == 0 else "WARNING",
            f"pipeline_complete={str(state['exit_code'] == 0).lower()} "
            f"blender_status={str(state['blender_status']).upper()} "
            f"elapsed_seconds={time.monotonic() - run_started:.3f}",
            stage="pipeline",
        )
        return state
    except Exception as exc:
        state["error"] = f"{type(exc).__name__}: {exc}"
        state["exit_code"] = 1
        write_stage_log(
            log_path,
            "ERROR",
            f"{type(exc).__name__}: {exc}",
            stage=current_stage,
        )
        if selected_source is not None:
            try:
                state["source_sha256_after"] = _file_identity(selected_source)[1]
            except OSError:
                pass
            try:
                _clear_generated_outputs(root, selected_source)
            except Exception as cleanup_exc:
                write_stage_log(
                    log_path,
                    "ERROR",
                    f"cleanup failed: {type(cleanup_exc).__name__}: {cleanup_exc}",
                    stage="cleanup",
                )
        state["status"] = "FAIL"
        state["finished_at"] = _finished_at()
        state["failure_reason"] = f"{type(exc).__name__}: {exc}"
        try:
            _write_run_result(root / "data/stage01_run_result.json", state)
        except OSError as result_exc:
            write_stage_log(
                log_path,
                "ERROR",
                f"run result write failed: {type(result_exc).__name__}: {result_exc}",
                stage="run_result",
            )
        return state


def run_blender_stage(project_root: Path, blender_path: Path, source_file: Path) -> int:
    """Run Blender headless, capture all process output, and verify its outputs."""
    root = Path(project_root).expanduser().resolve()
    blender = Path(blender_path).expanduser().resolve()
    source = Path(source_file).expanduser().resolve()
    log_path = root / "logs/stage01.log"
    output = root / "output/stage01_split.blend"
    assembly = root / "data/assembly_initial.json"
    manifest = root / "data/parts_manifest.json"
    script = root / "scripts/import_and_split_blender.py"
    command = [
        str(blender),
        "--background",
        "--python",
        str(script),
        "--",
        "--source",
        str(source),
        "--manifest",
        str(manifest),
        "--output",
        str(output),
        "--assembly-output",
        str(assembly),
        "--log",
        str(log_path),
    ]
    write_stage_log(
        log_path,
        "INFO",
        "subprocess_command=" + json.dumps(command, ensure_ascii=False),
        stage="blender",
    )
    try:
        completed = subprocess.run(
            command,
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        write_stage_log(
            log_path,
            "ERROR",
            f"subprocess launch failed: {type(exc).__name__}: {exc}",
            stage="blender",
        )
        _remove_generated_path(output, source)
        return 1

    write_stage_log(
        log_path,
        "INFO",
        f"stdout={completed.stdout.rstrip()} stderr={completed.stderr.rstrip()} "
        f"return_code={completed.returncode} output={output}",
        stage="blender",
    )
    if completed.returncode != 0:
        write_stage_log(
            log_path,
            "ERROR",
            f"BLENDER_STAGE_FAILED return_code={completed.returncode} output={output}",
            stage="blender",
        )
        _remove_generated_path(output, source)
        return completed.returncode or 1
    if not output.is_file() or output.stat().st_size == 0:
        write_stage_log(
            log_path,
            "ERROR",
            f"Blender returned 0 but output is missing or empty: {output}",
            stage="blender",
        )
        _remove_generated_path(output, source)
        return 1

    try:
        manifest_records = _load_json_list(manifest)
        assembly_payload = json.loads(assembly.read_text(encoding="utf-8"))
        assembly_count = assembly_payload.get("part_count")
        if assembly_count != len(manifest_records):
            raise ValueError(
                f"assembly count mismatch: {assembly_count} vs {len(manifest_records)}"
            )
    except Exception as exc:
        write_stage_log(
            log_path,
            "ERROR",
            f"Blender output verification failed: {type(exc).__name__}: {exc}",
            stage="blender",
        )
        _remove_generated_path(output, source)
        return 1

    write_stage_log(
        log_path,
        "INFO",
        f"BLENDER_STAGE_OK object_count={len(manifest_records)} output={output}",
        stage="blender",
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the complete Stage 01 pipeline and return its process status."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parent,
    )
    parser.add_argument("--source", type=Path)
    parser.add_argument("--blender-path", type=Path)
    parser.add_argument("--skip-blender", action="store_true")
    args = parser.parse_args(argv)
    result = run_python_stage(
        args.project_root,
        blender_path=args.blender_path,
        source_file=args.source,
        skip_blender=args.skip_blender,
    )
    if result.get("error"):
        print(f"Stage 01 failed: {result['error']}", file=sys.stderr)
    elif result.get("exit_code") == 2:
        print(
            "Stage 01 Python outputs completed; Blender stage is unavailable or skipped.",
            file=sys.stderr,
        )
    else:
        print("Stage 01 pipeline completed successfully.")
    return int(result.get("exit_code", 1))


def _resolve_requested_source(
    project_root: Path, requested: Path | str | None
) -> tuple[Path, list[str]]:
    if requested is None:
        return choose_source_file(project_root)
    candidate = Path(requested)
    if not candidate.is_absolute():
        candidate = project_root / candidate
    candidate = candidate.expanduser().resolve()
    if candidate.suffix.casefold() != ".stl":
        raise ValueError(f"explicit source is not an STL file: {candidate}")
    if not candidate.is_file():
        raise FileNotFoundError(f"explicit STL source does not exist: {candidate}")
    return candidate, [f"Using explicit --source: {candidate}"]


def _run_stage(log_path: Path, name: str, operation: Callable[[], Any]) -> Any:
    started = time.monotonic()
    write_stage_log(log_path, "INFO", "stage_started", stage=name)
    try:
        result = operation()
    except Exception as exc:
        write_stage_log(
            log_path,
            "ERROR",
            f"stage_failed {type(exc).__name__}: {exc}",
            stage=name,
        )
        raise
    write_stage_log(
        log_path,
        "INFO",
        f"stage_completed elapsed_seconds={time.monotonic() - started:.3f}",
        stage=name,
    )
    return result


def _report_pipeline_status(root: Path, state: Mapping[str, Any]) -> dict[str, Any]:
    status = str(state.get("blender_status", "not_run"))
    display = {
        "not_found": "UNAVAILABLE",
        "skipped": "SKIPPED",
        "available": "AVAILABLE",
        "failed": "FAILED",
    }.get(status, status.upper())
    return {
        "blender_status": display,
        "blender_path": state.get("blender_path"),
        "output_blend": str(root / "output/stage01_split.blend"),
        "pipeline_complete": state.get("exit_code") == 0,
        "python_exit_code": state.get("python_exit_code"),
    }


def _clear_generated_outputs(
    root: Path,
    source: Path | None,
    *,
    extra_sources: Sequence[Path] = (),
) -> None:
    protected_sources: list[Path] = list(extra_sources)
    if source is not None:
        protected_sources.append(source)
    else:
        protected_sources.extend(_stl_files(root))
        protected_sources.extend(_stl_files(root / "source"))
    for relative in (*STANDARD_OUTPUTS, *TEMP_OUTPUTS):
        _remove_generated_path(root / relative, protected_sources)


def _remove_generated_path(
    path: Path, source: Path | Sequence[Path] | None
) -> None:
    path = Path(path)
    if not path.exists() and not path.is_symlink():
        return
    protected_sources = [] if source is None else (
        [source] if isinstance(source, Path) else list(source)
    )
    for protected in protected_sources:
        try:
            if os.path.samefile(path, protected):
                raise ValueError(f"generated path aliases source STL: {path}")
        except FileNotFoundError:
            continue
    if path.is_dir() and not path.is_symlink():
        raise ValueError(f"refusing to remove generated directory: {path}")
    path.unlink()


def _load_json_list(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"expected a JSON list: {path}")
    if not all(isinstance(item, Mapping) for item in payload):
        raise ValueError(f"JSON list contains a non-object record: {path}")
    return [dict(item) for item in payload]


def _write_strict_json(path: Path, payload: Any) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _file_identity(path: Path) -> tuple[int, str]:
    path = Path(path)
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return path.stat().st_size, digest.hexdigest()


def _dependency_versions() -> dict[str, str]:
    versions: dict[str, str] = {"python": sys.version.split()[0]}
    for package in ("numpy", "trimesh", "pytest"):
        try:
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            versions[package] = "unavailable"
    return versions


def _run_status(state: Mapping[str, Any]) -> str:
    """Apply the Stage 01 completion gate to the final pipeline state."""
    python_ok = state.get("python_exit_code") == 0
    blender_ok = (
        state.get("blender_status") == "available"
        and state.get("blender_exit_code") == 0
    )
    source_hash_ok = (
        state.get("source_sha256_before") is not None
        and state.get("source_sha256_before") == state.get("source_sha256_after")
    )
    counts_ok = (
        state.get("component_count") is not None
        and state.get("component_count") == state.get("manifest_count")
    )
    blend_path = Path(str(state.get("output_blend", "")))
    blend_ok = blend_path.is_file() and blend_path.stat().st_size > 0
    if python_ok and blender_ok and source_hash_ok and counts_ok and blend_ok:
        return "PASS"
    if (
        python_ok
        and state.get("blender_status") in {"skipped", "not_found"}
        and source_hash_ok
        and counts_ok
    ):
        return "PARTIAL"
    return "FAIL"


def _finished_at() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_run_result(path: Path, state: Mapping[str, Any]) -> None:
    """Write the auditable final status without emitting non-standard JSON."""
    payload = {
        "status": state.get("status", "FAIL"),
        "failure_reason": state.get("failure_reason"),
        "source_file": state.get("source_file"),
        "source_sha256_before": state.get("source_sha256_before"),
        "source_sha256_after": state.get("source_sha256_after"),
        "component_count": state.get("component_count"),
        "manifest_count": state.get("manifest_count"),
        "face_count": state.get("face_count"),
        "indexed_vertex_count": state.get("indexed_vertex_count"),
        "duplicate_group_count": state.get("duplicate_group_count"),
        "fragment_count": state.get("fragment_count"),
        "blender_status": {
            "not_run": "NOT_RUN",
            "skipped": "SKIPPED",
            "not_found": "UNAVAILABLE",
            "available": "AVAILABLE",
            "failed": "FAILED",
        }.get(str(state.get("blender_status")), str(state.get("blender_status", "NOT_RUN")).upper()),
        "blender_path": state.get("blender_path"),
        "blender_output": state.get("output_blend"),
        "finished_at": state.get("finished_at"),
    }
    _write_strict_json(path, payload)


def _requested_source_candidates(
    project_root: Path, requested: Path | str | None
) -> list[Path]:
    if requested is None:
        return []
    candidate = Path(requested)
    if not candidate.is_absolute():
        candidate = project_root / candidate
    return [candidate.expanduser().resolve()]


def _stl_files(directory: Path) -> list[Path]:
    if not Path(directory).is_dir():
        return []
    return [
        path
        for path in Path(directory).iterdir()
        if path.is_file() and path.suffix.casefold() == ".stl"
    ]


def _one_line(value: Any) -> str:
    return str(value).replace("\\", "\\\\").replace("\r", "\\r").replace("\n", "\\n")


if __name__ == "__main__":
    raise SystemExit(main())
