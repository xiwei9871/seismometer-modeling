"""Catalog and byte-preserve Task 8 photographic references."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import struct
from pathlib import Path
from typing import Any

SUPPORTED_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".webp"})
REFERENCE_DIRS = ("raw", "exterior", "pcb", "internal", "detail", "validation")

KNOWN_REFERENCE_MAP: dict[str, dict[str, Any]] = {
    "0c298077f84ad4b75253e4d5610e8a31.png": {
        "reference_id": "REF_EXT_001",
        "category": "EXTERIOR",
        "view_type": "front_side_top_composite",
        "visible_features": [
            "upper_housing",
            "lower_housing",
            "handle",
            "rope",
            "bubble_level",
            "connectors",
            "external_fasteners",
            "leveling_foot",
            "labels",
        ],
    },
    "Weixin Image_20260908104046_13_238.png": {
        "reference_id": "REF_EXT_002",
        "category": "EXTERIOR",
        "view_type": "perspective_exterior",
        "visible_features": [
            "upper_housing",
            "lower_housing",
            "handle",
            "rope",
            "bubble_level",
            "top_hardware",
            "leveling_foot",
        ],
    },
    "e57334ffbfe3beb84dfa2fa2fcf485c5.png": {
        "reference_id": "REF_EXT_003",
        "category": "EXTERIOR",
        "view_type": "exploded_reference",
        "visible_features": [
            "upper_housing",
            "lower_housing",
            "pcb_assembly",
            "internal_support_structure",
        ],
    },
    "23fc716fa2df8ac7c77038d3863ff9bd.png": {
        "reference_id": "REF_PCB_001",
        "category": "PCB",
        "view_type": "pcb_top",
        "visible_features": [
            "pcb_outline",
            "mounting_holes",
            "major_components",
            "connectors",
        ],
    },
    "3c23e4e38e8064718ce4f1835a7180b1.png": {
        "reference_id": "REF_PCB_002",
        "category": "PCB",
        "view_type": "pcb_underside",
        "visible_features": [
            "pcb_outline",
            "mounting_holes",
            "support_frame",
            "major_components",
        ],
    },
    "4256cb7f103e4f5c7ed5f67e35fefbd5.png": {
        "reference_id": "REF_PCB_003",
        "category": "PCB",
        "view_type": "pcb_perspective",
        "visible_features": [
            "pcb_outline",
            "mounting_holes",
            "major_components",
            "connectors",
            "spacers",
        ],
    },
}

USEFULNESS_BY_CATEGORY = {
    "EXTERIOR": {
        "geometry_validation": "HIGH",
        "semantic_identification": "HIGH",
        "mounting_relationship": "MEDIUM",
        "material_reference": "HIGH",
        "dimensional_reference": "LOW",
    },
    "PCB": {
        "geometry_validation": "HIGH",
        "semantic_identification": "HIGH",
        "mounting_relationship": "HIGH",
        "material_reference": "LOW",
        "dimensional_reference": "LOW",
    },
    "UNKNOWN": {
        "geometry_validation": "MEDIUM",
        "semantic_identification": "LOW",
        "mounting_relationship": "LOW",
        "material_reference": "LOW",
        "dimensional_reference": "LOW",
    },
}


def prepare_references(
    project_root: Path,
    *,
    import_root_images: bool = False,
    source_root: Path | None = None,
    mapping: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Prepare categorized copies and write the stable reference manifest."""
    root = Path(project_root).expanduser().resolve()
    directories = {name: root / "references" / name for name in REFERENCE_DIRS}
    for directory in directories.values():
        directory.mkdir(parents=True, exist_ok=True)
    raw_dir = directories["raw"]
    effective_mapping = dict(KNOWN_REFERENCE_MAP)
    if mapping:
        effective_mapping.update(mapping)

    origin_by_name: dict[str, Path] = {}
    if import_root_images:
        import_dir = (
            Path(source_root).expanduser().resolve()
            if source_root is not None
            else root
        )
        for filename in effective_mapping:
            source = import_dir / filename
            if not source.is_file():
                continue
            origin_by_name[filename] = source
            destination = raw_dir / filename
            _copy_if_identical_or_missing(source, destination)

    raw_files = sorted(
        (
            path
            for path in raw_dir.iterdir()
            if path.is_file() and path.suffix.casefold() in SUPPORTED_EXTENSIONS
        ),
        key=lambda path: path.name.casefold(),
    )
    known = [path for path in raw_files if path.name in effective_mapping]
    unknown = [path for path in raw_files if path.name not in effective_mapping]
    known.sort(
        key=lambda path: _reference_sort_key(effective_mapping[path.name]["reference_id"])
    )

    records: list[dict[str, Any]] = []
    category_counters: dict[str, int] = {}
    for path in (*known, *unknown):
        details = effective_mapping.get(path.name)
        if details is None:
            category = "UNKNOWN"
            category_counters[category] = category_counters.get(category, 0) + 1
            reference_id = f"REF_UNKNOWN_{category_counters[category]:03d}"
            details = {
                "reference_id": reference_id,
                "category": category,
                "view_type": "unknown",
                "visible_features": [],
            }
        category = str(details["category"]).upper()
        reference_id = str(details["reference_id"])
        category_directory = directories.get(category.casefold(), directories["validation"])
        categorized = category_directory / f"{reference_id}{path.suffix.lower()}"
        _copy_if_identical_or_missing(path, categorized)
        digest = _sha256(path)
        dimensions = _image_dimensions(path)
        records.append(
            {
                "reference_id": reference_id,
                "source_file": _relative_or_absolute(
                    root, origin_by_name.get(path.name, path)
                ),
                "raw_file": _relative_or_absolute(root, path),
                "file": _relative_or_absolute(root, categorized),
                "category": category,
                "view_type": details.get("view_type", "unknown"),
                "visible_features": list(details.get("visible_features", [])),
                "usefulness": dict(
                    USEFULNESS_BY_CATEGORY.get(
                        category, USEFULNESS_BY_CATEGORY["UNKNOWN"]
                    )
                ),
                "byte_size": path.stat().st_size,
                "sha256": digest,
                "dimensions": dimensions,
                "notes": details.get("notes", ""),
            }
        )

    records.sort(key=lambda record: _reference_sort_key(record["reference_id"]))
    manifest = {
        "reference_count": len(records),
        "references": records,
    }
    output = root / "data/reference_manifest.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return records


def _copy_if_identical_or_missing(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if _sha256(source) != _sha256(destination):
            raise ValueError(f"different bytes at existing reference copy: {destination}")
        return
    shutil.copy2(source, destination)
    if _sha256(source) != _sha256(destination):
        raise ValueError(f"reference copy hash mismatch: {destination}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative_or_absolute(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return str(path.resolve())


def _reference_sort_key(reference_id: str) -> tuple[int, int, str]:
    pieces = reference_id.rsplit("_", 1)
    number = int(pieces[1]) if len(pieces) == 2 and pieces[1].isdigit() else 0
    prefix_order = {"REF_EXT": 0, "REF_PCB": 1, "REF_UNKNOWN": 2}
    prefix = pieces[0] if len(pieces) == 2 else reference_id
    return prefix_order.get(prefix, 3), number, reference_id


def _image_dimensions(path: Path) -> dict[str, int] | None:
    data = Path(path).read_bytes()
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        width, height = struct.unpack(">II", data[16:24])
        return {"width": width, "height": height}
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP" and len(data) >= 30:
        if data[12:16] == b"VP8X":
            width = 1 + int.from_bytes(data[24:27], "little")
            height = 1 + int.from_bytes(data[27:30], "little")
            return {"width": width, "height": height}
    if data.startswith(b"\xff\xd8"):
        return _jpeg_dimensions(data)
    return None


def _jpeg_dimensions(data: bytes) -> dict[str, int] | None:
    position = 2
    while position + 9 < len(data):
        if data[position] != 0xFF:
            position += 1
            continue
        marker = data[position + 1]
        position += 2
        if marker in {0xD8, 0xD9}:
            continue
        if position + 2 > len(data):
            return None
        length = int.from_bytes(data[position:position + 2], "big")
        if marker in range(0xC0, 0xC4) and length >= 7:
            height = int.from_bytes(data[position + 3:position + 5], "big")
            width = int.from_bytes(data[position + 5:position + 7], "big")
            return {"width": width, "height": height}
        position += length
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--import-root-images", action="store_true")
    parser.add_argument("--source-root", type=Path)
    args = parser.parse_args()
    records = prepare_references(
        args.project_root,
        import_root_images=args.import_root_images,
        source_root=args.source_root,
    )
    print(f"Prepared {len(records)} reference images.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
