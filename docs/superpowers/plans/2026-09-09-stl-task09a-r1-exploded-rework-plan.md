# Task 9A-R1 Exploded View Layout Rework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate a deterministic static exploded presentation layout from the original assembled Stage 02 scene, with a central Z-axis stack and compact Sensor/PCB/Battery branches, while retaining all 82 source PART meshes and creating no animation data.

**Architecture:** A pure-Python planner reads the frozen baseline, assembled transforms, manifest, and approved semantic mappings and writes the R1 JSON configuration. Blender scripts read that configuration, create a derived copy of Stage 02, apply only presentation transforms/visibility/collections/cameras/material presentation, and save/render the R1 outputs. A separate validator checks geometry totals, transform finiteness, visibility policy, camera coverage, warnings, and zero animation data.

**Tech Stack:** Python 3, JSON/CSV, pytest, Blender 5.2.1 `bpy`, Pillow for contact-sheet composition, existing `scripts.task08_data` and `scripts.task09_data` helpers.

---

## Files and responsibilities

Create the isolated R1 package and generated asset directories:

- Create: `stage_09A_R1_exploded_rework/__init__.py`
- Create: `stage_09A_R1_exploded_rework/scripts/__init__.py`
- Create: `stage_09A_R1_exploded_rework/scripts/analyze_assembly.py` — read-only assembled-state analysis and source PART facts.
- Create: `stage_09A_R1_exploded_rework/scripts/build_explosion_groups.py` — deterministic hierarchy, zones, axes, distances, and layout JSON.
- Create: `stage_09A_R1_exploded_rework/scripts/apply_explosion_layout.py` — Blender-only derived-scene builder.
- Create: `stage_09A_R1_exploded_rework/scripts/setup_explosion_cameras.py` — named Hero/Engineering/Top/Rear cameras.
- Create: `stage_09A_R1_exploded_rework/scripts/setup_explosion_render.py` — neutral materials, lighting, render settings, and PNG generation.
- Create: `stage_09A_R1_exploded_rework/scripts/validate_explosion.py` — pure and Blender validation contracts.
- Create: `stage_09A_R1_exploded_rework/scripts/pipeline.py` — orchestration, logging, report generation, and deterministic result JSON.
- Create: `run_task09a_r1.py` — project-level CLI wrapper.
- Create: `tests/test_task09a_r1_planning.py` — planner contract tests.
- Create: `tests/test_task09a_r1_scene_contract.py` — Blender scene-fact tests without requiring `bpy`.
- Create: `tests/test_task09a_r1_render_contract.py` — camera/render/output contracts.
- Create: `tests/test_run_task09a_r1.py` — runner, failure, report, and logging tests.
- Create: `stage_09A_R1_exploded_rework/config/.gitkeep` and `.../renders/.gitkeep` only if required to preserve empty directories in source control.
- Modify: `.gitignore` — ignore generated R1 binaries/renders/logs while keeping source scripts, configs, reports, and tests trackable.

Generated outputs, never treated as source of truth:

- `stage_09A_R1_exploded_rework/config/explosion_groups.json`
- `stage_09A_R1_exploded_rework/config/explosion_layout_config.json`
- `stage_09A_R1_exploded_rework/config/camera_config.json`
- `stage_09A_R1_exploded_rework/config/explosion_validation.json`
- `stage_09A_R1_exploded_rework/scene/exploded_layout_v2.blend`
- `stage_09A_R1_exploded_rework/renders/exploded_hero.png`
- `stage_09A_R1_exploded_rework/renders/exploded_engineering.png`
- `stage_09A_R1_exploded_rework/renders/exploded_top.png`
- `stage_09A_R1_exploded_rework/renders/exploded_rear.png`
- `stage_09A_R1_exploded_rework/renders/exploded_contact_sheet.png`
- `stage_09A_R1_exploded_rework/reports/exploded_layout_report.md`
- `stage_09A_R1_exploded_rework/reports/validation_report.md`
- `stage_09A_R1_exploded_rework/logs/task09a_r1.log`
- `data/explosion_validation_r1.json` and `data/task09a_r1_run_result.json` as project-level index files.

### Task 1: Freeze the R1 contracts with failing tests

**Files:**
- Create: `tests/test_task09a_r1_planning.py`
- Create: `tests/test_task09a_r1_scene_contract.py`
- Create: `tests/test_task09a_r1_render_contract.py`
- Create: `tests/test_run_task09a_r1.py`

- [ ] **Step 1: Write failing planner tests for the approved policy.**

```python
from pathlib import Path

from stage_09A_R1_exploded_rework.scripts.build_explosion_groups import (
    IMPORTANT_PART_IDS,
    build_explosion_layout,
    validate_explosion_layout,
)

ROOT = Path(__file__).resolve().parents[1]


def test_r1_has_82_source_parts_but_22_visible_presentation_parts():
    layout = build_explosion_layout(ROOT)
    assert list(layout["parts"]) == [f"PART_{i:03d}" for i in range(1, 83)]
    visible = [p for p in layout["parts"].values() if p["presentation_visibility"] == "VISIBLE"]
    assert len(visible) == 22
    assert set(p["part_id"] for p in visible) == set(IMPORTANT_PART_IDS)


def test_r1_main_stack_is_centered_and_monotonic_on_global_z():
    layout = build_explosion_layout(ROOT)
    parts = layout["parts"]
    anchor = parts["PART_001"]["presentation_location"]
    for part_id in ("PART_002", "PART_004", "PART_005"):
        location = parts[part_id]["presentation_location"]
        assert abs(location[0] - anchor[0]) < 1e-6
        assert abs(location[1] - anchor[1]) < 1e-6
    assert parts["PART_001"]["presentation_location"][2] < parts["PART_002"]["presentation_location"][2]
    assert parts["PART_002"]["presentation_location"][2] < parts["PART_004"]["presentation_location"][2]
    assert parts["PART_004"]["presentation_location"][2] < parts["PART_005"]["presentation_location"][2]


def test_r1_keeps_leveling_triangle_near_original_xy_and_moves_down():
    layout = build_explosion_layout(ROOT)
    for part_id in ("PART_020", "PART_021", "PART_022"):
        part = layout["parts"][part_id]
        original = part["assembled_location"]
        shown = part["presentation_location"]
        assert abs(shown[0] - original[0]) <= 80.0
        assert abs(shown[1] - original[1]) <= 80.0
        assert shown[2] < original[2]


def test_r1_hides_nonimportant_parts_without_review_or_collision_entries():
    layout = build_explosion_layout(ROOT)
    hidden = [p for p in layout["parts"].values() if p["presentation_visibility"] == "HIDDEN"]
    assert len(hidden) == 60
    assert all(p["review_scope"] is None for p in hidden)
    assert all(p["collision_scope"] is False for p in hidden)
    assert {item["part_id"] for item in layout["review_queue"]} == set(IMPORTANT_PART_IDS)


def test_r1_layout_is_deterministic_and_validates_against_frozen_baseline():
    first = validate_explosion_layout(build_explosion_layout(ROOT))
    second = validate_explosion_layout(build_explosion_layout(ROOT))
    assert first == second
    assert first["source_baseline"] == {"source_parts": 82, "faces": 444296, "indexed_vertices": 221902}
    assert first["animation_created"] is False
```

- [ ] **Step 2: Write failing scene, render, and runner contract tests.**

```python
from stage_09A_R1_exploded_rework.scripts.apply_explosion_layout import validate_r1_scene_facts
from stage_09A_R1_exploded_rework.scripts.setup_explosion_render import R1_VIEW_NAMES, render_result_contract
from stage_09A_R1_exploded_rework.scripts.pipeline import blender_stage_succeeded


def test_scene_contract_requires_all_source_parts_and_frozen_totals():
    facts = [
        {"part_id": f"PART_{i:03d}", "source": "original_stl", "type": "MESH", "hidden": i > 22, "animation_data": None}
        for i in range(1, 83)
    ]
    result = validate_r1_scene_facts(facts, vertices=221902, polygons=444296)
    assert result["source_part_count"] == 82
    assert result["visible_part_count"] == 22
    assert result["animation_data_count"] == 0


def test_required_render_names_are_stable_and_static():
    assert R1_VIEW_NAMES == ("exploded_hero", "exploded_engineering", "exploded_top", "exploded_rear")
    assert render_result_contract({"animation_created": False})["animation_created"] is False


def test_blender_traceback_is_failure_even_when_process_code_is_zero():
    assert blender_stage_succeeded(0, "") is True
    assert blender_stage_succeeded(0, "Traceback (most recent call last):\nValueError") is False
```

- [ ] **Step 3: Run the focused tests and verify they fail because the R1 modules do not exist.**

Run: `rtk .worktrees/stage01/.venv/bin/pytest tests/test_task09a_r1_planning.py tests/test_task09a_r1_scene_contract.py tests/test_task09a_r1_render_contract.py tests/test_run_task09a_r1.py -q`

Expected: FAIL with import errors for `stage_09A_R1_exploded_rework`.

### Task 2: Implement deterministic assembled-state analysis and layout planning

**Files:**
- Create: `stage_09A_R1_exploded_rework/scripts/analyze_assembly.py`
- Create: `stage_09A_R1_exploded_rework/scripts/build_explosion_groups.py`
- Modify: `tests/test_task09a_r1_planning.py`

- [ ] **Step 1: Implement read-only source analysis.**

`analyze_assembly.py` must load the frozen baseline with
`validate_task09_baseline`, index `parts_manifest.json`, `semantic_parts.json`,
and `assembly_initial.json`, and return ordered `PART_001..PART_082` records.
Each record must include assembled location/rotation/scale, bbox, face count,
vertex count, semantic name/category/confidence, and source identity. Reject
missing or duplicate PART IDs and non-finite numeric values.

- [ ] **Step 2: Implement the approved R1 group table.**

Use these exact visible groups and IDs:

```python
R1_GROUPS = {
    "MAIN_STACK": ("PART_001", "PART_002", "PART_004", "PART_005"),
    "SENSOR_BRANCH": ("PART_003", "PART_012", "PART_013", "PART_014"),
    "PCB_BRANCH": ("PART_006", "PART_007", "PART_019"),
    "BATTERY_BRANCH": ("PART_008", "PART_009", "PART_010", "PART_011", "PART_015", "PART_016"),
    "TOP_INTERFACE_BRANCH": ("PART_017", "PART_018"),
    "LEVELING_BRANCH": ("PART_020", "PART_021", "PART_022"),
}
IMPORTANT_PART_IDS = tuple(f"PART_{i:03d}" for i in range(1, 23))
```

`PART_001` is the anchor. Main-stack parts use global Z and anchor XY.
Sensor uses a compact left/front branch, PCB uses a compact right/front
branch, Battery uses a deterministic compact 3×2 array, interfaces remain a
small top-side pair, and leveling parts preserve their assembled XY pattern
with only bounded downward/clearance offsets.

- [ ] **Step 3: Implement proportional, deterministic offsets and warning records.**

Compute primary spacing from the anchor footprint and each group extent using
fixed factors stored in the layout config. Store for every part:
`assembled_location`, `presentation_location`, `original_rotation`,
`presentation_rotation`, `group`, `parent_group`, `probable_parent_object`,
`explosion_axis`, `explosion_sign`, `explosion_distance`,
`presentation_visibility`, `follow_parent_assembly`, `review_scope`,
`collision_scope`, `confidence`, and `notes`.

The planner must emit `FLOATING_COMPONENT_WARNING` and
`EDGE_ON_VISIBILITY_WARNING` only as explicit validation warnings; it must not
delete or rotate geometry to silence a warning.

- [ ] **Step 4: Implement `validate_explosion_layout` and config writers.**

Require layout version `r1`, mode `STATIC_HIERARCHICAL_PRESENTATION_R1`, exact
baseline values, exact 82-PART coverage, exact 22 visible IDs, no hidden-part
review/collision entries, finite transforms, no keyframes, and non-overlapping
group IDs. Write the three requested config files under the R1 `config/`
directory with stable sorted keys and UTF-8 JSON.

- [ ] **Step 5: Run planner tests until they pass.**

Run: `rtk .worktrees/stage01/.venv/bin/pytest tests/test_task09a_r1_planning.py -q`

Expected: PASS for source coverage, central stack, sensor/PCB/battery groups,
leveling placement, hidden policy, determinism, and frozen baseline.

### Task 3: Implement the derived Blender scene without animation

**Files:**
- Create: `stage_09A_R1_exploded_rework/scripts/apply_explosion_layout.py`
- Modify: `tests/test_task09a_r1_scene_contract.py`

- [ ] **Step 1: Implement input and source-scene validation before scene edits.**

Open only `output/stage02_semantic.blend`, discover source objects by
`part_id` custom property, and validate 82 source mesh objects plus 444296
polygons and 221902 indexed vertices before applying the layout. Fail with the
PART ID and validation stage if any object is missing or malformed.

- [ ] **Step 2: Implement presentation collections and visibility policy.**

Create `PRESENTATION_R1` and child collections for `MAIN_STACK`,
`SENSOR_BRANCH`, `PCB_BRANCH`, `BATTERY_BRANCH`, `TOP_INTERFACE_BRANCH`, and
`LEVELING_BRANCH`, plus disabled `EXPLOSION_GUIDES` and `EXPLOSION_LABELS`.
Keep all 82 source objects in the scene. Set only `PART_001..PART_022` to
visible in the presentation view and hide `PART_023..PART_082` from viewport
and render. Do not delete, join, duplicate, or alter source mesh datablocks.

- [ ] **Step 3: Apply only configured transforms and metadata.**

Set object locations/rotations from `explosion_layout_config.json`; preserve
scale and mesh data. Rename visible objects as
`PART_###__SEMANTIC_NAME`, retain `part_id` as the primary custom property,
and add `assembled_location`, `presentation_location`, `r1_group`,
`r1_visibility`, and `source = original_stl`. Hidden objects keep their
assembled transforms and source names/properties.

- [ ] **Step 4: Add neutral presentation materials and save a new blend.**

Create only derived neutral materials with restrained value differences for
main stack, sensor, PCB, battery, interface, and leveling groups. Do not use
the reference product colors, decals, rope, or texture reconstruction. Save to
`stage_09A_R1_exploded_rework/scene/exploded_layout_v2.blend` and never save
over Stage 02 or v4.

- [ ] **Step 5: Run the scene contract tests.**

Run: `rtk .worktrees/stage01/.venv/bin/pytest tests/test_task09a_r1_scene_contract.py -q`

Expected: PASS for exact source totals, exact visible/hidden policy, preserved
source identity, unchanged scale, and zero animation data.

### Task 4: Implement camera and render generation

**Files:**
- Create: `stage_09A_R1_exploded_rework/scripts/setup_explosion_cameras.py`
- Create: `stage_09A_R1_exploded_rework/scripts/setup_explosion_render.py`
- Create: `stage_09A_R1_exploded_rework/scripts/compose_contact_sheet.py`
- Modify: `tests/test_task09a_r1_render_contract.py`

- [ ] **Step 1: Write the named camera configuration.**

Create `CAM_EXPLODED_HERO`, `CAM_EXPLODED_ENGINEERING`,
`CAM_EXPLODED_TOP`, and `CAM_EXPLODED_REAR`. Derive the target and distance
from the visible R1 bounds. Hero uses elevated 3/4 perspective, approximately
35–50° azimuth, 25–40° elevation, and a 70–110 mm lens; Engineering is
near-isometric/low-perspective; Top is orthographic validation; Rear is the
reverse validation view. Store all transforms and camera settings in
`camera_config.json`.

- [ ] **Step 2: Configure restrained render presentation.**

Use Blender Workbench or the existing stable headless render path with a dark
neutral background, studio lighting, shadows, cavity, and 1200×900 PNG output.
Configure a long enough clip range from measured bounds. Ensure camera
orientation uses a target-based track quaternion and no geometry rotation is
performed for readability.

- [ ] **Step 3: Render the four required views and build the contact sheet.**

Render `exploded_hero.png`, `exploded_engineering.png`, `exploded_top.png`, and
`exploded_rear.png` from the same static scene. Use the existing Pillow tile
pattern to create `exploded_contact_sheet.png`; label each cell with its view
name. Do not create keyframes or temporary motion data.

- [ ] **Step 4: Run render contract tests.**

Run: `rtk .worktrees/stage01/.venv/bin/pytest tests/test_task09a_r1_render_contract.py -q`

Expected: PASS for stable view names, static render contract, camera names,
and required output paths.

### Task 5: Implement validation, reports, and the reproducible CLI

**Files:**
- Create: `stage_09A_R1_exploded_rework/scripts/validate_explosion.py`
- Create: `stage_09A_R1_exploded_rework/scripts/pipeline.py`
- Create: `run_task09a_r1.py`
- Modify: `tests/test_run_task09a_r1.py`
- Modify: `.gitignore`

- [ ] **Step 1: Implement source and presentation validation.**

Validate all of the following and serialize them to
`config/explosion_validation.json` and `data/explosion_validation_r1.json`:

```python
{
    "source_part_count": 82,
    "source_faces": 444296,
    "source_indexed_vertices": 221902,
    "visible_part_count": 22,
    "hidden_part_count": 60,
    "animation_data_count": 0,
    "unassigned_objects": [],
    "group_counts": {},
    "exploded_bounds": {"min": [], "max": [], "dimensions": []},
    "warnings": [],
    "hero_frame_occupancy": {},
    "hero_occlusion_warnings": [],
    "camera_clipping_warnings": [],
    "status": "PASS",
}
```

For Hero checks, estimate projected frame occupancy from visible object bounds,
flag `UNDERFILLED_FRAME` outside the configured target band, and flag severe
major-object overlaps as `HERO_OCCLUSION_WARNING`. Keep all warnings in the
report instead of changing geometry automatically.

- [ ] **Step 2: Implement report generation.**

Write `exploded_layout_report.md` with hierarchy, central-axis logic, branch
zones, spacing factors, camera strategy, changes from v4, and remaining
ambiguities. Write `validation_report.md` with immutable baseline evidence,
visibility policy, bounds, occupancy, warnings, render paths, and explicit
zero-animation evidence.

- [ ] **Step 3: Implement pipeline orchestration and explicit Blender failures.**

`pipeline.py` must:

1. validate the frozen Stage 01/Task 8 baseline;
2. build and write R1 layout/configs;
3. invoke Blender to apply the layout;
4. invoke Blender to render views;
5. compose the contact sheet;
6. validate output files and scene facts;
7. write `data/task09a_r1_run_result.json` and the R1 log.

Use `BLENDER_PATH` or `/opt/homebrew/bin/blender`. Treat a non-zero return
code or a stderr traceback as failure even when Blender exits with code zero.
Log source path/hash, dependency versions, component totals, group counts,
render paths, warnings, command lines, and the exact failing PART/stage.

- [ ] **Step 4: Add the project-level CLI wrapper and ignore generated binaries.**

`run_task09a_r1.py` must delegate to the package pipeline and return exit code
0 only for `status == PASS`. Add only R1 generated `.blend`, `.png`, and log
patterns to `.gitignore`; keep R1 scripts, JSON config, reports, tests, and
the source reference images untouched. Do not alter the existing v4 ignore
rules.

- [ ] **Step 5: Run runner unit tests and then the full test suite.**

Run: `rtk .worktrees/stage01/.venv/bin/pytest tests/test_run_task09a_r1.py tests/test_task09a_r1_planning.py tests/test_task09a_r1_scene_contract.py tests/test_task09a_r1_render_contract.py -q`

Expected: PASS for orchestration, output contracts, deterministic result
metadata, and explicit Blender failure handling.

Run: `rtk .worktrees/stage01/.venv/bin/pytest -q`

Expected: all existing Stage 01/02, Task 8, Task 9A, v3, and v4 tests remain
green in addition to the new R1 tests.

### Task 6: Execute Blender integration and inspect the visual result

**Files:**
- Generate: `stage_09A_R1_exploded_rework/config/*`
- Generate: `stage_09A_R1_exploded_rework/scene/exploded_layout_v2.blend`
- Generate: `stage_09A_R1_exploded_rework/renders/*`
- Generate: `stage_09A_R1_exploded_rework/reports/*`
- Generate: `stage_09A_R1_exploded_rework/logs/task09a_r1.log`
- Generate: `data/explosion_validation_r1.json`
- Generate: `data/task09a_r1_run_result.json`

- [ ] **Step 1: Run the R1 pipeline from the project root.**

Run: `rtk python run_task09a_r1.py`

Expected: `TASK_09A_R1_STATUS=PASS`, a generated R1 scene, four non-empty PNG
renders, contact sheet, config files, reports, and log.

- [ ] **Step 2: Re-open the generated blend headlessly and verify immutable facts.**

Run: `rtk /opt/homebrew/bin/blender -b stage_09A_R1_exploded_rework/scene/exploded_layout_v2.blend --python-expr "import bpy; src=[o for o in bpy.data.objects if o.type=='MESH' and o.get('source')=='original_stl']; print('R1_SOURCE', len(src), sum(len(o.data.polygons) for o in src), sum(len(o.data.vertices) for o in src)); print('R1_ANIM', sum(1 for o in bpy.data.objects if o.animation_data is not None))"`

Expected: `R1_SOURCE 82 444296 221902` and `R1_ANIM 0`.

- [ ] **Step 3: Inspect Hero, Engineering, Top, Rear, and contact-sheet images locally.**

Use the local image viewer on `exploded_hero.png` and `exploded_contact_sheet.png`. Confirm visually that the housing/cover/handle read as a central vertical skeleton, Sensor and PCB are coherent side branches, Battery is a compact array, and all three leveling cones remain a bounded triangle near their mounting relationship. If the layout is visually unclear, record the specific warning and revise only the deterministic layout config/tests before regenerating.

- [ ] **Step 4: Confirm no frozen asset changed.**

Run: `rtk git status --short`

Run: `rtk shasum -a 256 source/智能地震仪-221128\(1\).STL output/stage01_split.blend output/stage02_semantic.blend output/stage03_presentation_exploded_v4.blend`

Expected: only the new R1 files and pre-existing user reference images are
untracked/changed; source hash and frozen Stage 01/02/v4 assets are unchanged.

### Task 7: Final verification and commit source changes

**Files:**
- Modify: only the R1 source scripts, tests, `.gitignore`, and plan/spec docs as applicable.

- [ ] **Step 1: Run formatting/whitespace and contract checks.**

Run: `rtk git diff --check`

Run: `rtk .worktrees/stage01/.venv/bin/pytest -q`

Expected: no whitespace errors and all tests passing.

- [ ] **Step 2: Compare two planner runs for stable JSON and transform hashes.**

Run: `rtk python -c "from pathlib import Path; import hashlib; from stage_09A_R1_exploded_rework.scripts.build_explosion_groups import build_explosion_layout; import json; root=Path('.').resolve(); a=json.dumps(build_explosion_layout(root), sort_keys=True, separators=(',', ':')).encode(); b=json.dumps(build_explosion_layout(root), sort_keys=True, separators=(',', ':')).encode(); print('R1_LAYOUT_HASH_EQUAL', hashlib.sha256(a).hexdigest()==hashlib.sha256(b).hexdigest())"`

Expected: `R1_LAYOUT_HASH_EQUAL True`.

- [ ] **Step 3: Commit the reproducible R1 implementation.**

Run: `rtk git add stage_09A_R1_exploded_rework run_task09a_r1.py tests/test_task09a_r1_planning.py tests/test_task09a_r1_scene_contract.py tests/test_task09a_r1_render_contract.py tests/test_run_task09a_r1.py .gitignore docs/superpowers/plans/2026-09-09-stl-task09a-r1-exploded-rework-plan.md`

Run: `rtk git commit -m "feat: rework static exploded presentation layout"`

Expected: a commit containing only the R1 implementation, tests, plan, and
ignore rules; user-provided reference PNGs are not staged.

- [ ] **Step 4: Report the review status and stop before animation.**

Report `TASK 9A-R1 STATUS: PASS` only after the verification commands above
pass and the four required renders have been visually inspected. Report
`REVIEW` if warnings remain or the composition needs human layout feedback.
Do not create keyframes, animation timing, camera animation, or Task 9B
assets.
