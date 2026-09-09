"""Immutable-baseline and output-safety helpers for Task 9A."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from scripts.task08_data import load_json, validate_stage01_baseline, write_json


TASK09_BASELINE: dict[str, Any] = {
    "source_sha256": "fd2a7b78540245fd098724206d5ddf169fd2f44c07638e9a6459cd92fea717d1",
    "source_parts": 82,
    "faces": 444296,
    "indexed_vertices": 221902,
}

_TASK09_DATA_OUTPUTS = frozenset(
    {
        "disassembly_graph.json",
        "exploded_state.json",
        "explosion_guides.json",
        "animation_plan.json",
        "fastener_group_mapping.json",
        "future_visual_assets.json",
        "task09a_run_result.json",
        "explosion_review_queue.csv",
    }
)


def validate_task09_baseline(project_root: Path) -> dict[str, Any]:
    """Fail closed unless the frozen Stage 01 and Task 8 facts still match."""
    root = Path(project_root).expanduser().resolve()
    validate_stage01_baseline(root)

    result_path = root / "data/task08_run_result.json"
    if not result_path.is_file():
        raise ValueError("Task 8 result is missing; Task 8 must have status PASS")

    result = load_json(result_path)
    if not isinstance(result, Mapping):
        raise ValueError("Task 8 result must be an object with status PASS")
    if result.get("status") != "PASS":
        raise ValueError("Task 8 must have status PASS before Task 9A")

    blend_path = root / "output/stage02_semantic.blend"
    if not blend_path.is_file():
        raise ValueError("required Task 8 output is missing: stage02_semantic.blend")

    baseline = result.get("baseline")
    semantic_blend = result.get("semantic_blend")
    if not isinstance(baseline, Mapping) or not isinstance(semantic_blend, Mapping):
        raise ValueError("Task 8 baseline data is missing or malformed")

    baseline_checks = {
        "source_sha256": TASK09_BASELINE["source_sha256"],
        "source_parts": TASK09_BASELINE["source_parts"],
        "faces": TASK09_BASELINE["faces"],
        "indexed_vertices": TASK09_BASELINE["indexed_vertices"],
    }
    semantic_checks = {
        "source_part_count": TASK09_BASELINE["source_parts"],
        "polygons": TASK09_BASELINE["faces"],
        "vertices": TASK09_BASELINE["indexed_vertices"],
    }
    for key, expected in baseline_checks.items():
        if baseline.get(key) != expected:
            raise ValueError(
                f"Task 9A baseline mismatch for Task 8 baseline.{key}: "
                f"expected {expected!r}, got {baseline.get(key)!r}"
            )
    for key, expected in semantic_checks.items():
        if semantic_blend.get(key) != expected:
            raise ValueError(
                f"Task 9A baseline mismatch for Task 8 semantic_blend.{key}: "
                f"expected {expected!r}, got {semantic_blend.get(key)!r}"
            )

    return dict(TASK09_BASELINE)


def _find_project_root(path: Path) -> Path | None:
    """Find the owning project without requiring the candidate output to exist."""
    candidate = path.expanduser().resolve(strict=False)
    for parent in (candidate.parent, *candidate.parents):
        if (parent / "data/stage01_run_result.json").is_file():
            return parent
    return None


def is_allowed_task09_output(path: Path) -> bool:
    """Return whether a path belongs to the strict Task 9A output allowlist."""
    candidate = Path(path).expanduser().resolve(strict=False)
    root = _find_project_root(candidate)
    if root is None:
        return False

    try:
        relative = candidate.relative_to(root)
    except ValueError:
        return False

    parts = relative.parts
    if len(parts) == 2 and parts[0] == "data":
        return parts[1] in _TASK09_DATA_OUTPUTS
    if relative == Path("output/stage03_exploded_preview.blend"):
        return True
    if (
        len(parts) == 3
        and parts[:2] == ("output", "explosion_validation")
        and relative.suffix.lower() == ".png"
    ):
        return True
    if relative == Path("output/reports/task09a_explosion_plan.md"):
        return True
    if len(parts) >= 3 and parts[:2] == ("output", "task09a_review"):
        return True
    return relative == Path("logs/task09a.log")


def write_task09_json(path: Path, payload: Any) -> None:
    """Write deterministic UTF-8 Task 9A JSON with strict numeric values."""
    write_json(Path(path), payload)
