"""Run the deterministic Task 9A planning and inspection pipeline."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from scripts.build_animation_plan import build_animation_plan
from scripts.build_task09a_review_page import build_review_page
from scripts.generate_explosion_validation import VIEW_NAMES
from scripts.task09_data import validate_task09_baseline, write_task09_json
from scripts.task09_planning import (
    build_disassembly_graph,
    build_exploded_state,
    build_explosion_guides,
    build_explosion_review_queue,
    build_fastener_group_mapping,
    build_future_visual_assets,
)


PROJECT_ROOT = Path(__file__).resolve().parent
BLENDER_SCRIPT = PROJECT_ROOT / "scripts/build_stage03_exploded_preview.py"
RENDER_SCRIPT = PROJECT_ROOT / "scripts/generate_explosion_validation.py"


def build_blender_command(
    blender_path: Path,
    project_root: Path,
    script: str | Path,
    state: str,
) -> list[str]:
    """Build an argv list with Blender's script-argument separator intact."""
    return [
        str(blender_path),
        "-b",
        "--python",
        str(script),
        "--",
        "--project-root",
        str(Path(project_root)),
        "--state",
        state,
    ]


def run_task09a(
    project_root: Path,
    *,
    blender_path: Path | None = None,
    skip_blender: bool = False,
) -> dict[str, Any]:
    """Run Task 9A and return the persisted run-result payload."""
    root = Path(project_root).expanduser().resolve()
    if not (root / "data/task08_run_result.json").is_file():
        raise ValueError("Task 8 result is missing; Task 8 must have status PASS")
    baseline = validate_task09_baseline(root)
    immutable_paths = [
        root / "source/智能地震仪-221128(1).STL",
        root / "output/stage01_split.blend",
        root / "output/stage02_semantic.blend",
    ]
    immutable_hashes_before = {str(path): _sha256(path) for path in immutable_paths}
    log_lines = [_log_line("Task 9A start"), _log_line(f"project_root={root}")]
    graph = build_disassembly_graph(root)
    fasteners = build_fastener_group_mapping(root)
    state = build_exploded_state(root)
    guides = build_explosion_guides(state)
    assets = build_future_visual_assets(root)
    review_queue = build_explosion_review_queue(state)
    plan = build_animation_plan(root)

    write_task09_json(root / "data/disassembly_graph.json", graph)
    write_task09_json(root / "data/fastener_group_mapping.json", fasteners)
    write_task09_json(root / "data/exploded_state.json", state)
    write_task09_json(root / "data/explosion_guides.json", guides)
    write_task09_json(root / "data/future_visual_assets.json", assets)
    write_task09_json(root / "data/animation_plan.json", plan)
    _write_review_csv(root / "data/explosion_review_queue.csv", review_queue)
    log_lines.append(_log_line("planning outputs written"))

    blender_status = "SKIPPED"
    stage03_result: dict[str, Any] | None = None
    render_result: dict[str, Any] | None = None
    if skip_blender:
        log_lines.append(_log_line("Blender steps skipped by request"))
    else:
        resolved_blender = Path(blender_path or "/opt/homebrew/bin/blender").expanduser()
        if not resolved_blender.is_file():
            raise ValueError(f"Blender executable not found: {resolved_blender}")
        stage03_command = build_blender_command(
            resolved_blender, root, BLENDER_SCRIPT, "exploded"
        )
        stage03_result, stage03_output = _run_json_command(stage03_command, root)
        log_lines.extend(_command_log(stage03_command, stage03_output))
        render_command = [
            str(resolved_blender),
            "-b",
            "--python",
            str(RENDER_SCRIPT),
            "--",
            "--project-root",
            str(root),
        ]
        render_result, render_output = _run_json_command(render_command, root)
        log_lines.extend(_command_log(render_command, render_output))
        blender_status = "PASS"

    views_payload = {"views": [f"{name}.png" for name in VIEW_NAMES]}
    page = build_review_page(
        root / "output/task09a_review",
        views_payload,
        graph,
        plan,
        project_root=root,
        exploded_state=state,
        assets=assets,
        review_queue=review_queue,
    )
    report = _write_report(
        root / "output/reports/task09a_explosion_plan.md",
        state,
        graph,
        fasteners,
        plan,
        review_queue,
    )
    immutable_hashes_after = {str(path): _sha256(path) for path in immutable_paths}
    if immutable_hashes_after != immutable_hashes_before:
        raise RuntimeError("immutable Stage 01/02 input changed during Task 9A")
    output_files = {
        "disassembly_graph": str(root / "data/disassembly_graph.json"),
        "fastener_group_mapping": str(root / "data/fastener_group_mapping.json"),
        "exploded_state": str(root / "data/exploded_state.json"),
        "explosion_guides": str(root / "data/explosion_guides.json"),
        "animation_plan": str(root / "data/animation_plan.json"),
        "future_visual_assets": str(root / "data/future_visual_assets.json"),
        "explosion_review_queue": str(root / "data/explosion_review_queue.csv"),
        "review_page": str(page),
        "report": str(report),
        "stage03_blend": str(root / "output/stage03_exploded_preview.blend"),
        "log": str(root / "logs/task09a.log"),
    }
    if render_result is not None:
        output_files["validation_render_directory"] = str(root / "output/explosion_validation")

    result = {
        "status": "PASS" if blender_status == "PASS" else "PARTIAL",
        "baseline": baseline,
        "animation_created": False,
        "source_geometry_modified": False,
        "immutable_inputs_unchanged": True,
        "immutable_input_hashes": immutable_hashes_after,
        "blender_status": blender_status,
        "keyframe_count": 0,
        "planned_part_count": len(state["parts"]),
        "duplicate_group_count": fasteners["group_count"],
        "collision_pair_count": state["collision_summary"]["collision_count"],
        "review_queue_count": len(review_queue),
        "output_files": output_files,
        "stage03": stage03_result,
        "renders": render_result,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    write_task09_json(root / "data/task09a_run_result.json", result)
    log_lines.append(_log_line(f"status={result['status']}"))
    _write_log(root / "logs/task09a.log", log_lines)
    return result


def _run_json_command(command: list[str], root: Path) -> tuple[dict[str, Any], str]:
    completed = subprocess.run(
        command,
        cwd=str(root),
        text=True,
        capture_output=True,
        check=False,
    )
    output = (completed.stdout or "") + (completed.stderr or "")
    if completed.returncode != 0:
        raise RuntimeError(
            f"Task 9A subprocess failed ({completed.returncode}): {' '.join(command)}\n{output}"
        )
    for line in reversed((completed.stdout or "").splitlines()):
        line = line.strip()
        if line.startswith("{"):
            payload = json.loads(line)
            if isinstance(payload, dict):
                return payload, output
    raise RuntimeError(f"Task 9A subprocess returned no JSON: {' '.join(command)}\n{output}")


def _write_review_csv(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    fields = [
        "part",
        "semantic_name",
        "explode_direction",
        "explode_distance_mm",
        "explode_order",
        "motion_type",
        "confidence",
        "collision_check",
        "review_question",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _csv_value(row.get(field)) for field in fields})


def _csv_value(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return json.dumps(list(value), ensure_ascii=False, separators=(",", ":"))
    return value


def _write_log(path: Path, lines: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_report(
    path: Path,
    state: dict[str, Any],
    graph: dict[str, Any],
    fasteners: dict[str, Any],
    plan: dict[str, Any],
    review_queue: Sequence[dict[str, Any]],
) -> Path:
    groups: dict[str, list[dict[str, Any]]] = {}
    for record in state["parts"].values():
        groups.setdefault(str(record["motion_group"]), []).append(record)
    lines = [
        "# Task 9A Explosion Plan",
        "",
        "Task 9A is a transform-only engineering preview. It creates no keyframes and does not modify source geometry.",
        "",
        "## Frozen baseline",
        "",
        "- Source PARTs: 82",
        "- Faces: 444296",
        "- Indexed vertices: 221902",
        "- Animation data: 0",
        "",
        "## Disassembly DAG",
        "",
        f"- Nodes: {len(graph['nodes'])}",
        f"- Edges: {len(graph['edges'])}",
        f"- Directed acyclic: {graph['directed_acyclic']}",
        "- Topological order: " + " → ".join(graph["topological_order"]),
        "",
        "## Motion groups",
        "",
        "| Group | Parts | Direction | Distance (mm) | Order | Confidence | Collision |",
        "|---|---:|---|---:|---:|---|---|",
    ]
    for group_id in sorted(groups):
        members = groups[group_id]
        vector = members[0]["explode_vector"]
        distance = members[0]["explode_distance_mm"]
        confidence = max(
            (str(member["confidence"]) for member in members),
            key=lambda value: {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "UNKNOWN": 3}.get(value, 3),
        )
        collision = "WARN" if any(member["collision_check"] == "WARN" for member in members) else "PASS"
        lines.append(
            f"| {group_id} | {len(members)} | {vector} | {distance} | "
            f"{min(member['explode_order'] for member in members)} | {confidence} | {collision} |"
        )
    lines.extend(
        [
            "",
            "## Collision screening",
            "",
            f"- Collision pairs at sampled times: {state['collision_summary']['collision_count']}",
            f"- Method: {state['collision_summary']['method']}",
            f"- Limitation: {state['collision_summary']['sampling_limitations']}",
            "",
            "## Duplicate/small accessories",
            "",
            f"- Duplicate groups retained: {fasteners['group_count']}",
            "- Every duplicate member remains an independent PART object.",
            "- Ambiguous fastener groups remain UNASSIGNED and require manual confirmation.",
            "",
            "## Animation schedule (planning only)",
            "",
            f"- FPS: {plan['fps']}",
            f"- Frame envelope: {plan['frame_range']}",
            f"- Easing policy: {plan['easing']}",
            f"- Animation created: {plan['animation_created']}",
            "",
            "| Stage | Frames | Groups |",
            "|---|---|---|",
        ]
    )
    for stage in plan["stages"]:
        lines.append(
            f"| {stage['stage_id']} | {stage['start_frame']}–{stage['end_frame']} | "
            f"{', '.join(stage['groups']) or 'hold'} |"
        )
    lines.extend(
        [
            "",
            "## Manual review",
            "",
            f"- Queue rows: {len(review_queue)}",
            "- Priority: collision warnings, unresolved top-port roles, PART_022, unknown/SMALL_ACCESSORY assignments.",
            "- Review the front/rear isometric validation renders before Task 9B.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _command_log(command: Sequence[str], output: str) -> list[str]:
    return [
        _log_line(f"command={' '.join(command)}"),
        _log_line(f"subprocess_output_bytes={len(output.encode('utf-8'))}"),
    ]


def _log_line(message: str) -> str:
    return f"{datetime.now(timezone.utc).isoformat()} {message}"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--blender-path", type=Path, default=None)
    parser.add_argument("--skip-blender", action="store_true")
    args = parser.parse_args(argv)
    result = run_task09a(
        args.project_root,
        blender_path=args.blender_path,
        skip_blender=args.skip_blender,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
