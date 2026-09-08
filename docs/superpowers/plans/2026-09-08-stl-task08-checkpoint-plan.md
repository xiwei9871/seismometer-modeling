# STL Task 8 Checkpoint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reproducible, evidence-backed Task 8 first-checkpoint package that compares the frozen Stage 01 assembly with the six supplied reference images, produces inspection renders for all 82 PARTs and 13 duplicate groups, and records initial semantic/PCB/quality findings without entering animation.

**Architecture:** `run_task08.py` is the fail-closed orchestrator. Python prepares traceable reference metadata and source-of-truth JSON/CSV reports; Blender reads the frozen Stage 01 scene and creates only derived renders and a separate semantic scene. The 82 permanent `PART_xxx` IDs remain unchanged, uncertain conclusions remain explicit, and the process stops after the checkpoint.

**Tech Stack:** Python 3.14, trimesh, numpy, Blender 5.2.1 headless Python API, pytest, ffmpeg for mechanical contact-sheet assembly when available, PNG/JPEG/WebP references.

---

## Immutable boundary

Read-only inputs:

- `source/智能地震仪-221128(1).STL`
- `data/stage01_run_result.json`
- `data/source_model_report.json`
- `data/parts_manifest.json`
- `data/parts_manifest.csv`
- `data/duplicate_groups.json`
- `data/suspicious_fragments.json`
- `data/mesh_quality_report.json`
- `data/assembly_initial.json`
- `output/stage01_split.blend`
- the six existing root-level reference images

Generated Task 8 files may be written only under `references/`, Task 8 JSON/CSV data paths, `output/reference_renders/`, `output/part_id_renders/`, `output/part_previews/`, `output/reports/duplicate_groups/`, `output/reports/part_contact_sheet*.png`, `output/semantic_validation/`, `output/stage02_semantic.blend`, and `logs/task08.log`.

### Task 1: Frozen baseline gate and common data helpers

**Files:**
- Create: `scripts/task08_data.py`
- Create: `tests/test_task08_data.py`
- Modify: `.gitignore`

- [ ] **Step 1: Write failing tests.** Test that a Stage 01 fixture is accepted only when `status == PASS`, both source hashes equal `fd2a7b78540245fd098724206d5ddf169fd2f44c07638e9a6459cd92fea717d1`, and counts equal 82 components/PARTs, 444296 faces, and 221902 indexed vertices. Test rejection of changed hash/counts, missing files, non-list manifests, and missing PART IDs.

- [ ] **Step 2: Run the focused tests and verify the expected missing-module failure.**

```bash
.venv/bin/pytest -q tests/test_task08_data.py
```

- [ ] **Step 3: Implement `validate_stage01_baseline(project_root)`, strict `load_json/write_json`, `load_manifest`, `stable_part_ids`, `sorted_bbox`, and confidence validation. The gate must read only and raise a clear `ValueError` on any mismatch.

- [ ] **Step 4: Run the focused tests and commit.**

```bash
.venv/bin/pytest -q tests/test_task08_data.py
git add scripts/task08_data.py tests/test_task08_data.py .gitignore
git commit -m "feat: add Task 8 baseline data gate"
```

### Task 2: Reference catalog

**Files:**
- Create: `scripts/prepare_references.py`
- Create: `tests/test_prepare_references.py`
- Create: `references/raw/.gitkeep`
- Create: `references/exterior/.gitkeep`
- Create: `references/pcb/.gitkeep`
- Create: `references/internal/.gitkeep`
- Create: `references/detail/.gitkeep`
- Create: `references/validation/.gitkeep`

- [ ] **Step 1: Write failing tests** for byte-preserving copy, deterministic IDs, source traceability, idempotent reruns, supported extensions, and rejection without deletion of unsupported files.

- [ ] **Step 2: Run `.venv/bin/pytest -q tests/test_prepare_references.py` and confirm failure.

- [ ] **Step 3: Implement data-driven classification with an explicit mapping. The six known files must map to `REF_EXT_001..003` and `REF_PCB_001..003`; do not infer semantic meaning from image pixels in this module. Write `data/reference_manifest.json` with source path, category, view type, visible features, usefulness, dimensions, byte size, and SHA-256.

- [ ] **Step 4: Import the six root images byte-for-byte into `references/raw/` and run the catalog command.**

```bash
cp -p 0c298077f84ad4b75253e4d5610e8a31.png references/raw/
cp -p "Weixin Image_20260908104046_13_238.png" references/raw/
cp -p e57334ffbfe3beb84dfa2fa2fcf485c5.png references/raw/
cp -p 23fc716fa2df8ac7c77038d3863ff9bd.png references/raw/
cp -p 3c23e4e38e8064718ce4f1835a7180b1.png references/raw/
cp -p 4256cb7f103e4f5c7ed5f67e35fefbd5.png references/raw/
.venv/bin/python scripts/prepare_references.py --project-root .
```

- [ ] **Step 5: Run focused tests and commit the reference slice.

```bash
.venv/bin/pytest -q tests/test_prepare_references.py
git add scripts/prepare_references.py tests/test_prepare_references.py references
git commit -m "feat: catalog Task 8 reference images"
```

### Task 3: Standard views, PART previews, and contact sheets

**Files:**
- Create: `scripts/generate_reference_views.py`
- Create: `scripts/generate_part_previews.py`
- Create: `tests/test_task08_render_contract.py`

- [ ] **Step 1: Write failing contract tests** for required CLI arguments, allowed output paths, six orthographic views, four iso views, 82 numeric PART previews, 13 duplicate-group representatives, labels, and no keyframes/source-transform changes.

- [ ] **Step 2: Run `.venv/bin/pytest -q tests/test_task08_render_contract.py` and confirm failure.

- [ ] **Step 3: Implement standard views by opening `output/stage01_split.blend` read-only, using source objects where `source == original_stl`, calculating world-space bounds, and rendering front/rear/left/right/top/bottom orthographically plus four fixed iso views. Never save over Stage 01.

- [ ] **Step 4: Implement isolated PART previews, assembled highlights, group sheets, and deterministic 5×5 contact-sheet pages. Use temporary inspection colors/text only; keep transforms and geometry untouched. Required outputs include `PART_001.png` through `PART_082.png`, `part_id_{front,side,top,iso}.png`, class variants, and one sheet per duplicate group.

- [ ] **Step 5: Run smoke renders, focused tests, and commit.

```bash
blender -b --python scripts/generate_reference_views.py -- --project-root .
blender -b --python scripts/generate_part_previews.py -- --project-root .
.venv/bin/pytest -q tests/test_task08_render_contract.py
git add scripts/generate_reference_views.py scripts/generate_part_previews.py tests/test_task08_render_contract.py
git commit -m "feat: generate Task 8 inspection renders"
```

### Task 4: Conservative checkpoint findings

**Files:**
- Create: `scripts/build_task08_reports.py`
- Create: `tests/test_task08_reports.py`

- [ ] **Step 1: Write failing tests** requiring 82 semantic records, exactly 18 MAJOR records, evidence/confidence/reason for every non-UNKNOWN record, explicit `PART_003`/`PART_005` review with `repair_performed: false`, fragment neighbors/default UNKNOWN, explicit PCB candidate or UNKNOWN, and manual queue restricted to MEDIUM/LOW/UNKNOWN.

- [ ] **Step 2: Run `.venv/bin/pytest -q tests/test_task08_reports.py` and confirm failure.

- [ ] **Step 3: Implement report builders for:

```text
data/semantic_parts.json
data/feature_validation.json
data/reference_missing_features.json
data/pcb_validation.json
data/non_watertight_semantic_review.json
data/reference_conflicts.json
data/assembly_semantic.json
data/mounting_relationships.json
data/disassembly_dependencies.json
data/manual_review_queue.csv
data/task08_checkpoint.json
```

All 82 PARTs must retain permanent IDs and receive a record. Only evidence-supported MAJOR candidates may be seeded. Duplicate groups get representative records; inheritance is allowed only with evidence. Include exterior features (housings, handle, rope, bubble level, connectors, fasteners, feet, labels), PCB Level 2 features (board, outline, holes, major modules, connectors, spacers, fasteners), missing-feature classifications, and fragment bounding box/centroid/nearest neighbors.

- [ ] **Step 4: Visually compare references, standard views, contact sheets, and highlights using the approved visual companion/local image viewer. Record every conclusion in JSON with evidence/confidence/reason; do not use it for precision dimensions.

- [ ] **Step 5: Run focused tests and commit.

```bash
.venv/bin/pytest -q tests/test_task08_reports.py
git add scripts/build_task08_reports.py tests/test_task08_reports.py
git commit -m "feat: record Task 8 checkpoint semantic findings"
```

### Task 5: Derived semantic Blender scene

**Files:**
- Create: `scripts/build_stage02_semantic_blend.py`
- Create: `tests/test_stage02_semantic_blend.py`

- [ ] **Step 1: Write failing tests** asserting a separate output file, 82 source meshes, 444296 polygons, 221902 vertices, preserved PART IDs/transforms, semantic custom properties/collections, and zero keyframes.

- [ ] **Step 2: Run `.venv/bin/pytest -q tests/test_stage02_semantic_blend.py` and confirm failure.

- [ ] **Step 3: Implement a builder that reads Stage 01 and semantic JSON, adds only derived semantic properties/collections, renames objects `PART_xxx__NAME` or `PART_xxx__UNKNOWN`, and saves `output/stage02_semantic.blend` without altering Stage 01.

- [ ] **Step 4: Reopen the generated scene headlessly, verify source-only totals, run focused tests, and commit.

```bash
blender -b --python scripts/build_stage02_semantic_blend.py -- --project-root .
blender -b output/stage02_semantic.blend --python-expr 'import bpy; p=[o for o in bpy.data.objects if o.type=="MESH" and o.get("source")=="original_stl"]; print(len(p),sum(len(o.data.polygons) for o in p),sum(len(o.data.vertices) for o in p))'
.venv/bin/pytest -q tests/test_stage02_semantic_blend.py
git add scripts/build_stage02_semantic_blend.py tests/test_stage02_semantic_blend.py
git commit -m "feat: build derived Task 8 semantic scene"
```

### Task 6: Orchestrator and checkpoint report

**Files:**
- Create: `run_task08.py`
- Create: `tests/test_run_task08.py`

- [ ] **Step 1: Write failing end-to-end tests** for refusing non-PASS Stage 01, partial status without Blender, safe output allowlist, source immutability, and logged checkpoint status.

- [ ] **Step 2: Run `.venv/bin/pytest -q tests/test_run_task08.py` and confirm failure.

- [ ] **Step 3: Implement fail-closed orchestration: validate baseline before cleanup; prepare references; run reports/renders/derived scene; log commands/stdout/stderr/return codes; write `data/task08_checkpoint.json`; render `output/reports/task08_checkpoint.md`; and never create animation data.

- [ ] **Step 4: Run the complete checkpoint.

```bash
.venv/bin/python run_task08.py --project-root . --blender-path /opt/homebrew/bin/blender
```

- [ ] **Step 5: Run all tests, diff check, and commit.

```bash
.venv/bin/pytest -q
git diff --check
git add run_task08.py tests/test_run_task08.py
git commit -m "feat: orchestrate Task 8 checkpoint"
```

### Task 7: Final checkpoint verification and stop

- [ ] **Step 1:** Verify root/source STL hashes and all Stage 01 input file hashes are unchanged.
- [ ] **Step 2:** Reopen `output/stage02_semantic.blend` and assert source-only totals are `82 444296 221902`.
- [ ] **Step 3:** Verify 6 references, 10 standard views, 82 previews, 13 group sheets, 18 MAJOR records, both non-watertight reviews, one fragment review, and an explicit PCB result.
- [ ] **Step 4:** Run `.venv/bin/pytest -q` and `git diff --check`.
- [ ] **Step 5:** Request read-only review for source immutability, evidence discipline, output coverage, and absence of animation. Stop at the checkpoint and wait for human review.
