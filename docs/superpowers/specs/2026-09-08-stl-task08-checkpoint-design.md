# STL Task 08 Checkpoint Design

## Scope

This design covers only the first Task 8 checkpoint: reference-data
organization, reproducible visual inspection renders, all-part and
duplicate-group previews, and evidence-backed semantic candidates for the
18 MAJOR parts plus the PCB/non-watertight/fragment review queue.

It does not create animation keyframes, move source PART geometry, modify
`stage01_split.blend`, repair meshes, reconstruct CAD, or assign semantic
names to all MEDIUM/SMALL parts.

## Immutable baseline

The Stage 01 baseline is read-only:

- Source SHA-256: `fd2a7b78540245fd098724206d5ddf169fd2f44c07638e9a6459cd92fea717d1`
- Source PART objects: 82
- Faces: 444296
- Indexed vertices: 221902
- Connected components: 82

`source/*.STL`, `data/parts_manifest.json`, `data/parts_manifest.csv`, and
`output/stage01_split.blend` are inputs only. Task 8 generated scenes must
be separate from Stage 01.

## Architecture

`run_task08.py` is the reproducible entry point. It validates the Stage 01
PASS gate, builds a stable reference manifest from `references/raw/`, and
orchestrates Python report generation followed by optional headless Blender
rendering.

Python owns source-of-truth data and reports:

- `scripts/prepare_references.py` copies and classifies reference images
  without changing originals.
- `scripts/task08_data.py` provides strict JSON/CSV loading, baseline
  validation, geometry-derived summaries, and evidence record helpers.
- `scripts/build_task08_reports.py` creates feature validation, semantic
  candidates, non-watertight review, missing/conflict records, assembly
  candidates, mounting/dependency placeholders, and the manual review CSV.

Blender owns only derived visual outputs:

- `scripts/generate_reference_views.py` renders six orthographic views and
  four isometric views in the unchanged assembled state.
- `scripts/generate_part_previews.py` renders each PART in isolation and
  creates contact sheets, duplicate-group sheets, and assembled highlights.
- `scripts/build_stage02_semantic_blend.py` reads the JSON source of truth,
  copies Stage 01 data into a new scene, adds only semantic custom
  properties/collections, and saves `stage02_semantic.blend`.

All Blender scripts use the exact indexed source PART meshes from Stage 01;
any helper cameras, lights, labels, or materials are excluded from source
geometry counts.

## Evidence and uncertainty

Every non-UNKNOWN semantic candidate stores `evidence`, `confidence`, and
`reason`. Candidate mappings are restricted to geometry/position/reference
evidence already available; no photo-only precision dimensions are emitted.
Unknown or conflicting observations remain explicit and enter
`manual_review_queue.csv`.

The first checkpoint concentrates on:

- 18 MAJOR PART candidates;
- `PART_003` and `PART_005` without repair;
- the 13 existing HIGH-confidence duplicate groups, using a representative
  PART and inheritance only when evidence supports it;
- MAIN_PCB candidate and PCB Level 2 observations;
- the sole FRAGMENT with isolated/assembled previews and neighbor data.

No semantic conclusion is allowed to alter the permanent `PART_xxx` ID.

## Data flow

```text
Stage 01 PASS + raw references
        |
        v
reference_manifest.json
        |
        +--> standard/part/duplicate/highlight renders
        |
        +--> checkpoint JSON reports + manual_review_queue.csv
        |
        +--> stage02_semantic.blend (derived, no source geometry changes)
```

## Failure handling

The entry point fails closed if `data/stage01_run_result.json` is absent or
not `PASS`, if the immutable baseline hashes/counts do not match, or if any
reference/source file cannot be read. Stale Task 8 outputs are removed only
from an explicit generated-output allowlist; Stage 01 outputs and source STL
files are never removed or overwritten.

Blender failures are recorded with command, stdout, stderr, return code,
and stage. Python reports remain available only when their inputs are
complete; the run result records `PASS`, `PARTIAL`, or `FAIL` and the exact
failure reason.

## Verification

Tests cover reference classification, immutable-baseline gating, stable
reference IDs, JSON/CSV schema, semantic confidence/evidence validation,
fragment neighbor calculation, and generated-output safety. The checkpoint
acceptance run must verify:

1. all six supplied images are represented and traceable;
2. standard/part/duplicate/highlight renders exist;
3. all 82 PART IDs appear in previews and semantic records;
4. 18 MAJOR candidates and the two non-watertight reviews are present;
5. MAIN_PCB is a documented candidate or explicit UNKNOWN;
6. `stage02_semantic.blend` reopens and still contains 82 source PART
   meshes, 444296 faces, and 221902 vertices;
7. Stage 01 files and the source STL hash are unchanged.

The process stops after the checkpoint report and waits for human review.
