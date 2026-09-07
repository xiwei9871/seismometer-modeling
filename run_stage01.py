from pathlib import Path


def ensure_project_dirs(project_root: Path) -> None:
    """Create the required project directories for Stage 01."""
    for relative_path in ("source", "scripts", "data", "output/reports", "logs"):
        (project_root / relative_path).mkdir(parents=True, exist_ok=True)


def choose_source_file(project_root: Path) -> tuple[Path, list[str]]:
    """Choose an STL from source/ first, or from the project root as fallback."""
    source_dir = project_root / "source"
    source_candidates = _stl_files(source_dir)
    if source_candidates:
        selected = select_largest_stl(source_candidates)
        if len(source_candidates) == 1:
            return selected, []
        warning = (
            "Multiple STL source files found in source/; selection order is "
            "file size, then filename.casefold(), then original filename."
        )
        return selected, [warning]

    root_candidates = _stl_files(project_root)
    if not root_candidates:
        raise FileNotFoundError("No STL source file found in source/ or project root")

    selected = select_largest_stl(root_candidates)
    if len(root_candidates) == 1:
        warning = (
            "Using the unique STL source file in the project root; "
            "copy logic is not implemented."
        )
    else:
        warning = (
            "Multiple STL source files found in the project root; selection order is "
            "file size, then filename.casefold(), then original filename."
        )
    return selected, [warning]


def _stl_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return [
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.casefold() == ".stl"
    ]


def select_largest_stl(candidates: list[Path]) -> Path:
    return max(
        candidates,
        key=lambda path: (path.stat().st_size, path.name.casefold(), path.name),
    )
