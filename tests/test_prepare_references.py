from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.prepare_references import prepare_references


KNOWN_FILES = (
    "0c298077f84ad4b75253e4d5610e8a31.png",
    "Weixin Image_20260908104046_13_238.png",
    "e57334ffbfe3beb84dfa2fa2fcf485c5.png",
    "23fc716fa2df8ac7c77038d3863ff9bd.png",
    "3c23e4e38e8064718ce4f1835a7180b1.png",
    "4256cb7f103e4f5c7ed5f67e35fefbd5.png",
)


def _make_root_images(root: Path) -> dict[str, bytes]:
    payloads = {}
    for index, filename in enumerate(KNOWN_FILES, start=1):
        data = f"image-{index}".encode("ascii")
        (root / filename).write_bytes(data)
        payloads[filename] = data
    return payloads


def test_prepare_references_is_byte_preserving_and_stable(tmp_path):
    payloads = _make_root_images(tmp_path)

    first = prepare_references(
        tmp_path,
        import_root_images=True,
        source_root=tmp_path,
    )
    second = prepare_references(
        tmp_path,
        import_root_images=True,
        source_root=tmp_path,
    )

    assert first == second
    assert [record["reference_id"] for record in first] == [
        "REF_EXT_001",
        "REF_EXT_002",
        "REF_EXT_003",
        "REF_PCB_001",
        "REF_PCB_002",
        "REF_PCB_003",
    ]
    for filename, data in payloads.items():
        assert (tmp_path / "references/raw" / filename).read_bytes() == data
    assert (
        tmp_path / "references/exterior/REF_EXT_001.png"
    ).read_bytes() == payloads[KNOWN_FILES[0]]
    assert (
        tmp_path / "references/pcb/REF_PCB_001.png"
    ).read_bytes() == payloads[KNOWN_FILES[3]]
    manifest = json.loads(
        (tmp_path / "data/reference_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["reference_count"] == 6
    assert manifest["references"] == first
    assert first[0]["sha256"] == hashlib.sha256(payloads[KNOWN_FILES[0]]).hexdigest()


def test_prepare_references_keeps_originals_and_records_traceability(tmp_path):
    payloads = _make_root_images(tmp_path)
    original_hashes = {
        name: hashlib.sha256(data).hexdigest() for name, data in payloads.items()
    }

    records = prepare_references(tmp_path, import_root_images=True, source_root=tmp_path)

    for name, expected_hash in original_hashes.items():
        assert hashlib.sha256((tmp_path / name).read_bytes()).hexdigest() == expected_hash
    assert records[0]["category"] == "EXTERIOR"
    assert records[0]["source_file"] == KNOWN_FILES[0]
    assert records[0]["raw_file"] == f"references/raw/{KNOWN_FILES[0]}"
    assert records[0]["usefulness"]["geometry_validation"] == "HIGH"


def test_prepare_references_adds_unknown_raw_file_without_deleting_it(tmp_path):
    _make_root_images(tmp_path)
    raw = tmp_path / "references/raw"
    raw.mkdir(parents=True)
    unknown = raw / "new-view.webp"
    unknown.write_bytes(b"unknown")

    records = prepare_references(
        tmp_path,
        import_root_images=True,
        source_root=tmp_path,
    )

    assert unknown.read_bytes() == b"unknown"
    extra = records[-1]
    assert extra["category"] == "UNKNOWN"
    assert extra["reference_id"] == "REF_UNKNOWN_001"
    assert (tmp_path / extra["file"]).read_bytes() == b"unknown"


def test_prepare_references_rejects_different_existing_copy(tmp_path):
    _make_root_images(tmp_path)
    raw = tmp_path / "references/raw"
    raw.mkdir(parents=True)
    (raw / KNOWN_FILES[0]).write_bytes(b"different")

    with pytest.raises(ValueError, match="different bytes"):
        prepare_references(tmp_path, import_root_images=True, source_root=tmp_path)
