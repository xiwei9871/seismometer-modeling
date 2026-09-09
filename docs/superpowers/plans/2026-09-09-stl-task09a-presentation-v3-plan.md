# STL Task 9A Hierarchical Presentation Explosion v3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate a deterministic static hierarchical exploded presentation that keeps all 82 source PARTs, visibly lays out only MAJOR/MEDIUM geometry, and produces a no-keyframe Blender scene plus four review renders.

**Architecture:** A pure Python planner reads the frozen Stage 02 manifests and writes `presentation_explosion_v3.json` and a visible-only CSV queue. A separate Blender builder applies those derived transforms/visibility flags to a copy of Stage 02, and a renderer creates four neutral inspection images without saving camera changes or creating animation data.

**Tech Stack:** Python standard library, existing project data helpers, Blender 5.2.1 `bpy`, pytest, and Pillow for PNG readability checks where available.

---

## Immutable boundary and output paths

Read only:

- `source/智能地震仪-221128(1).STL`
- `data/stage01_run_result.json`
- `data/task08_run_result.json`
- `data/parts_manifest.json`
- `data/semantic_parts.json`
- `data/assembly_initial.json`
- `data/assembly_semantic.json`
- `data/duplicate_groups.json`
- `output/stage01_split.blend`
- `output/stage02_semantic.blend`

Write only:

- `scripts/presentation_explosion_v3.py`
- `scripts/build_presentation_explosion_v3.py`
- `scripts/generate_presentation_explosion_v3.py`
- `scripts/run_presentation_v3.py`
- `tests/test_presentation_explosion_v3.py`
- `data/presentation_explosion_v3.json`
- `data/presentation_review_queue_v3.csv`
- `data/presentation_v3_run_result.json`
- `output/stage03_presentation_exploded_v3.blend`
- `output/explosion_validation_v3/*.png`
- `output/reports/presentation_explosion_v3.md`
- `logs/presentation_v3.log`

Do not overwrite `stage01_split.blend`, `stage02_semantic.blend`, or the old
`stage03_exploded_preview.blend`.

### Task 1: Lock the v3 pure planning contract with tests

**Files:**
- Create: `scripts/presentation_explosion_v3.py`
- Create: `tests/test_presentation_explosion_v3.py`

- [ ] **Step 1: Write the failing contract tests.**

Add tests that call `build_presentation_layout(project_root)` and assert:

```python
def test_layout_preserves_all_source_parts(project_root):
    result = build_presentation_layout(project_root)
    assert list(result["parts"]) == [f"PART_{index:03d}" for index in range(1, 83)]
    assert result["source_baseline"] == {
        "source_parts": 82,
        "faces": 444296,
        "indexed_vertices": 221902,
    }

def test_only_major_and_medium_parts_are_visible(project_root):
    result = build_presentation_layout(project_root)
    visible = [part for part in result["parts"].values() if part["presentation_visibility"] == "VISIBLE"]
    hidden = [part for part in result["parts"].values() if part["presentation_visibility"] == "HIDDEN"]
    assert len(visible) == 44
    assert len(hidden) == 38
    assert {part["size_class"] for part in visible} == {"MAJOR", "MEDIUM"}
    assert {part["size_class"] for part in hidden} <= {"SMALL", "FRAGMENT"}

def test_small_and_fragment_parts_are_absent_from_review_queue(project_root):
    result = build_presentation_layout(project_root)
    queued = {item["part_id"] for item in result["review_queue"]}
    assert not queued.intersection({f"PART_{index:03d}" for index in range(39, 83)})

def test_sensor_pcb_battery_use_hierarchical_offsets(project_root):
    result = build_presentation_layout(project_root)
    assert result["assemblies"]["SENSOR_ASSEMBLY"]["zone"] == "front-left"
    assert result["assemblies"]["PCB_ASSEMBLY"]["zone"] == "front-right"
    battery = [result["parts"][f"PART_{index:03d}"]["local_offset_mm"] for index in (8, 9, 10, 11, 15, 16)]
    assert len({tuple(offset) for offset in battery}) == 6
    assert result["parts"]["PART_001"]["presentation_location"] == result["parts"]["PART_001"]["assembled_location"]

def test_layout_rejects_unknown_zone_in_internal_validation():
    with pytest.raises(ValueError, match="zone"):
        validate_zone_name("diagonal")
```

- [ ] **Step 2: Run the focused tests and confirm the expected missing-module failure.**

Run:

```bash
rtk pytest -q tests/test_presentation_explosion_v3.py
```

Expected: collection failure because `scripts/presentation_explosion_v3.py`
does not yet exist.

- [ ] **Step 3: Implement the minimal deterministic planner.**

Expose:

```python
ALLOWED_ZONES = ("top", "bottom", "left", "right", "front-left", "front-right")

def validate_zone_name(zone: str) -> str:
    if zone not in ALLOWED_ZONES:
        raise ValueError(f"invalid presentation zone: {zone!r}")
    return zone

def build_presentation_layout(project_root: Path) -> dict[str, Any]:
    """Return the complete v3 static layout without importing bpy."""
```

Validate the frozen baseline through `validate_task09_baseline`, load the
manifest/semantic/initial JSON, require exactly `PART_001` through
`PART_082`, and sort all records numerically. Define the eight deterministic
assembly records from the design: enclosure, handle, top interface, PCB,
sensor, battery, leveling, and unresolved medium. Keep `PART_001` as the
anchor with zero offsets. For parts 023-038 use visible unresolved-medium
records without semantic renaming. For parts 039-082 use
`HIDDEN_NO_PARENT`, keep assembled coordinates, and omit them from the
review queue. Write finite numeric vectors and a no-animation policy into the
returned document.

- [ ] **Step 4: Run focused tests to reach green and inspect the generated data in memory.**

Run:

```bash
rtk pytest -q tests/test_presentation_explosion_v3.py
```

Expected: all pure planner tests pass, with 44 visible records, 38 hidden
records, and no small/fragment review records.

- [ ] **Step 5: Commit the pure planner slice.**

```bash
rtk git add scripts/presentation_explosion_v3.py tests/test_presentation_explosion_v3.py
rtk git commit -m "feat: plan hierarchical presentation explosion v3"
```

### Task 2: Add deterministic JSON/CSV outputs and v3 run contract

**Files:**
- Modify: `scripts/presentation_explosion_v3.py`
- Create: `scripts/run_presentation_v3.py`
- Modify: `tests/test_presentation_explosion_v3.py`

- [ ] **Step 1: Add failing tests for serialization and visible-only review output.**

Test these exact behaviors:

```python
def test_write_presentation_outputs_is_deterministic(project_root, tmp_path):
    result = build_presentation_layout(project_root)
    paths = write_presentation_outputs(project_root, result)
    first = paths["layout"].read_bytes()
    write_presentation_outputs(project_root, result)
    assert paths["layout"].read_bytes() == first

def test_review_csv_contains_only_major_medium(project_root):
    result = build_presentation_layout(project_root)
    assert all(item["size_class"] in {"MAJOR", "MEDIUM"} for item in result["review_queue"])
    assert all(item["review_question"] == "Is the important component visible, unobstructed, and clearly laid out?" for item in result["review_queue"])
```

- [ ] **Step 2: Run the focused tests and verify they fail for missing output helpers.**

```bash
rtk pytest -q tests/test_presentation_explosion_v3.py
```

- [ ] **Step 3: Implement stable writers and the runner.**

Implement:

```python
def write_presentation_outputs(project_root: Path, layout: Mapping[str, Any]) -> dict[str, Path]:
    """Write sorted JSON and a visible-only CSV using existing helpers."""

def run_presentation_v3(project_root: Path, *, skip_blender: bool = False) -> dict[str, Any]:
    """Plan, serialize, build, render, and record a PASS/FAIL result."""
```

Write JSON with the project’s deterministic UTF-8 helper and CSV with a
fixed header. The CSV contains only visible MAJOR/MEDIUM parts and exactly
the one visibility/occlusion question. The runner must validate the Stage 01
and Task 8 baseline before doing any work, use `BLENDER_PATH` when set and
otherwise `/opt/homebrew/bin/blender`, record command/return-code/stderr on
failure, and never report PASS when `--skip-blender` is used for final output.
Use paths relative to the project root in generated result metadata where
possible.

- [ ] **Step 4: Run focused tests and commit the data/output slice.**

```bash
rtk pytest -q tests/test_presentation_explosion_v3.py
rtk git add scripts/presentation_explosion_v3.py scripts/run_presentation_v3.py tests/test_presentation_explosion_v3.py
rtk git commit -m "feat: serialize presentation explosion v3 outputs"
```

### Task 3: Build the derived no-keyframe Blender scene

**Files:**
- Create: `scripts/build_presentation_explosion_v3.py`
- Modify: `tests/test_presentation_explosion_v3.py`

- [ ] **Step 1: Add failing pure Blender-contract tests.**

Add:

```python
def test_validate_presentation_scene_facts_rejects_animation():
    with pytest.raises(ValueError, match="animation"):
        validate_presentation_scene_facts(
            [{"part_id": "PART_001", "source": "original_stl", "animation_data": True}],
            vertices=221902,
            polygons=444296,
        )

def test_validate_presentation_scene_facts_requires_frozen_geometry():
    with pytest.raises(ValueError, match="frozen geometry"):
        validate_presentation_scene_facts([], vertices=0, polygons=0)
```

- [ ] **Step 2: Run the focused tests and confirm the missing-builder failure.**

```bash
rtk pytest -q tests/test_presentation_explosion_v3.py
```

- [ ] **Step 3: Implement the derived-scene builder.**

Expose:

```python
def validate_presentation_scene_facts(
    facts: Sequence[Mapping[str, Any]], *, vertices: int, polygons: int
) -> dict[str, Any]:
    """Require 82 source objects, frozen totals, and zero animation data."""

def build_presentation_scene(project_root: Path) -> dict[str, Any]:
    """Open Stage 02 and save only the v3 derived presentation scene."""
```

Open `output/stage02_semantic.blend`, map source objects by their existing
`part_id`, and validate source-only counts. For visible records, set only
`obj.location` to the planned presentation location; retain rotation and
scale. For hidden records, retain assembled transforms and set only
`hide_viewport`/`hide_render`. Add v3 custom properties without changing
mesh data. Link objects into a derived `PRESENTATION_V3` collection and
assembly subcollections. Do not unlink/delete source meshes, Join objects,
or invoke any keyframe method. Save
`output/stage03_presentation_exploded_v3.blend`, reopen it, and revalidate
counts, hidden policy, and zero animation data.

- [ ] **Step 4: Run Blender headless and focused tests.**

```bash
rtk /opt/homebrew/bin/blender -b --python scripts/build_presentation_explosion_v3.py -- --project-root .
rtk pytest -q tests/test_presentation_explosion_v3.py
```

Expected: the new blend opens successfully with 82 source PART meshes,
444296 faces, 221902 indexed vertices, zero animation data, 44 visible
major/medium source objects, and hidden-only small/fragment objects.

- [ ] **Step 5: Commit the derived-scene builder.**

```bash
rtk git add scripts/build_presentation_explosion_v3.py tests/test_presentation_explosion_v3.py
rtk git commit -m "feat: build static presentation explosion v3 scene"
```

### Task 4: Render the four v3 inspection views

**Files:**
- Create: `scripts/generate_presentation_explosion_v3.py`
- Modify: `scripts/run_presentation_v3.py`
- Modify: `tests/test_presentation_explosion_v3.py`

- [ ] **Step 1: Add failing render-contract tests.**

Assert the exact view names and no-keyframe contract:

```python
def test_v3_view_names_are_fixed():
    assert V3_VIEW_NAMES == (
        "exploded_iso_front_v3",
        "exploded_iso_rear_v3",
        "exploded_front_v3",
        "exploded_top_v3",
    )

def test_render_result_does_not_claim_animation():
    assert render_result_contract({"animation_created": False})["animation_created"] is False
```

- [ ] **Step 2: Run the focused tests and confirm the missing renderer failure.**

```bash
rtk pytest -q tests/test_presentation_explosion_v3.py
```

- [ ] **Step 3: Implement fixed neutral rendering.**

Implement `generate_presentation_views(project_root)`. Open the new v3 blend,
validate source facts and total animation absence, create a temporary
orthographic camera for front/top and fixed isometric cameras for front/rear,
calculate framing from visible source objects only, render the four exact
PNG names, and remove temporary camera objects in `finally`. Use neutral
Workbench inspection shading. Do not change source meshes or save the scene.

- [ ] **Step 4: Run renders and verify the four files are readable.**

```bash
rtk /opt/homebrew/bin/blender -b --python scripts/generate_presentation_explosion_v3.py -- --project-root .
rtk file output/explosion_validation_v3/exploded_iso_front_v3.png output/explosion_validation_v3/exploded_iso_rear_v3.png output/explosion_validation_v3/exploded_front_v3.png output/explosion_validation_v3/exploded_top_v3.png
rtk pytest -q tests/test_presentation_explosion_v3.py
```

Expected: four non-empty PNG images and all tests green.

- [ ] **Step 5: Commit the renderer.**

```bash
rtk git add scripts/generate_presentation_explosion_v3.py scripts/run_presentation_v3.py tests/test_presentation_explosion_v3.py
rtk git commit -m "feat: render hierarchical presentation views"
```

### Task 5: Add report, hygiene, and full acceptance run

**Files:**
- Modify: `scripts/run_presentation_v3.py`
- Modify: `.gitignore`
- Modify: `tests/test_presentation_explosion_v3.py`

- [ ] **Step 1: Add failing report and hygiene tests.**

Assert the report includes the visible/hidden counts, anchor, exact output
names, and explicit no-keyframe wording; assert v3 generated directories
are ignored while the six user PNGs remain untracked and untouched.

- [ ] **Step 2: Run focused tests and confirm the missing report behavior.**

```bash
rtk pytest -q tests/test_presentation_explosion_v3.py
```

- [ ] **Step 3: Implement report generation and output hygiene.**

Generate `output/reports/presentation_explosion_v3.md` with source baseline,
assembly zones, 44/38 visibility summary, anchor, view paths, no-keyframe
status, and the single human-review criterion. Add only v3 generated output
directories/files to `.gitignore`; do not add root reference PNGs or modify
their contents.

- [ ] **Step 4: Run the complete v3 pipeline and full regression suite.**

```bash
rtk python scripts/run_presentation_v3.py --project-root .
rtk pytest -q
rtk git status --short --branch
```

Verify the run reports PASS, all four PNGs exist, the blend reopens with
82/444296/221902 and zero animation data, visible source objects are exactly
MAJOR/MEDIUM, no small/fragment appears in the CSV queue, and STL/Stage
01/Stage 02 SHA-256 values equal the frozen values.

- [ ] **Step 5: Commit the implementation and report source changes.**

```bash
rtk git add scripts/run_presentation_v3.py .gitignore tests/test_presentation_explosion_v3.py
rtk git commit -m "feat: complete hierarchical presentation explosion v3"
```

Do not stage ignored generated data, blend, images, logs, or the six existing
root PNG references. Finish by reporting the v3 output paths and stop before
Task 9B or any animation keyframe work.

