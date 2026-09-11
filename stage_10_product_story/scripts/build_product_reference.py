"""Register the local product PDF as the Task 10 claims source.

The PDF is treated as immutable evidence.  This module stores only compact,
page-level claims in the generated manifest; it never modifies the source
document or embeds long passages from it.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from scripts.task08_data import write_json


PDF_NAME = "幔壳迅勘智能勘察设备.pdf"
PDF_SHA256 = "d8555d751851d6e5f53027721c29eb701da27226bd1311b47bd1d1d1bbdb0d7e"
MANIFEST_RELATIVE_PATH = Path("stage_10_product_story/config/product_reference_manifest.json")


def _pending_communication() -> dict[str, Any]:
    return {
        "status": "CONFLICT_REQUIRES_CONFIRMATION",
        "render_text": "Multi-network communication",
        "communication_protocol_text": "PENDING_PRODUCT_CONFIRMATION",
    }


def _verified_manifest(pdf_path: Path, source_file: str, digest: str, page_count: int) -> dict[str, Any]:
    if page_count != 2:
        raise ValueError(f"approved product PDF must contain 2 pages, got {page_count}")
    return {
        "reference_id": "PRODUCT_PDF_001",
        "source_file": source_file,
        "pdf_status": "VERIFIED_LOCAL_REFERENCE",
        "sha256": digest,
        "page_count": page_count,
        "claims_source": PDF_NAME,
        "claims": {
            "data_consistency_percent": {
                "value": 99,
                "unit": "%",
                "evidence_pages": [1],
            },
            "channels": {
                "value": 3,
                "unit": "channels",
                "evidence_pages": [2],
            },
            "adc_resolution": {
                "value": "32-bit",
                "unit": "ADC",
                "evidence_pages": [2],
            },
            "standby_days": {
                "value": 10,
                "unit": "days",
                "evidence_pages": [2],
            },
            "charging_hours": {
                "value": 3,
                "unit": "hours",
                "evidence_pages": [2],
            },
            "weight_kg": {
                "value": 2.5,
                "unit": "kg",
                "evidence_pages": [2],
            },
            "temperature_range_c": {
                "value": [-40, 80],
                "unit": "°C",
                "evidence_pages": [2],
            },
        },
        "communication_protocol": {
            **_pending_communication(),
            "page_1_text": "WIFI / NBIoT / 4G",
            "page_2_text": "WIFI / NBIoT / Bluetooth",
        },
    }


def build_product_reference_manifest(
    project_root: Path,
    *,
    pdf_path: Path,
    expected_sha256: str | None = None,
) -> dict[str, Any]:
    """Build a deterministic product-reference manifest.

    Missing input is represented explicitly so callers can fail closed while
    preserving the user brief as the provisional source.  A supplied expected
    hash is checked before any claims are accepted.
    """
    root = Path(project_root).expanduser().resolve()
    source = Path(pdf_path).expanduser()
    if not source.is_absolute():
        source = root / source
    source = source.resolve()
    source_file = _stable_source_file(root, source)

    if not source.is_file():
        return {
            "reference_id": "PRODUCT_PDF_001",
            "source_file": source_file,
            "pdf_status": "MISSING_LOCAL_REFERENCE",
            "claims_source": "USER_PRODUCT_BRIEF_2026-09-10",
            "claims": {},
            "communication_protocol": _pending_communication(),
        }

    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise ValueError("product PDF SHA256 does not match the approved reference")

    page_count = len(PdfReader(str(source)).pages)
    return _verified_manifest(source, source_file, digest, page_count)


def _stable_source_file(root: Path, source: Path) -> str:
    try:
        return source.relative_to(root).as_posix()
    except ValueError:
        return str(source)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--pdf", type=Path, default=None)
    args = parser.parse_args(argv)

    root = args.project_root.expanduser().resolve()
    pdf_path = args.pdf if args.pdf is not None else root / PDF_NAME
    manifest = build_product_reference_manifest(
        root,
        pdf_path=pdf_path,
        expected_sha256=PDF_SHA256,
    )
    output = root / MANIFEST_RELATIVE_PATH
    write_json(output, manifest)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
