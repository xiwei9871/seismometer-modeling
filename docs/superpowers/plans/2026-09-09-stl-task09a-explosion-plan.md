# STL Task 9A Exploded Assembly Planning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate a reproducible, non-destructive exploded-state plan and static review package from the frozen Task 8 assembly without creating animation keyframes.

**Architecture:** Pure Python owns all Task 9A planning JSON/CSV and performs deterministic DAG, motion, distance, and swept-AABB calculations. Blender reads the plan from `stage02_semantic.blend` and writes only a derived `stage03_exploded_preview.blend`; a separate renderer and static HTML page expose the result for visual inspection.

**Tech Stack:** Python 3.14, standard library JSON/CSV/math, existing project data helpers, Blender 5.2.1 `bpy`, pytest, and Pillow only where already available for image/page assembly.

---

## Immutable boundary and output allowlist

Read only:

- `source/智能地震仪-221128(1).STL`
- `data/stage01_run_result.json`
- `data/parts_manifest.json`
- `data/duplicate_groups.json`
- `data/mesh_quality_report.json`
- `data/assembly_initial.json`
- `data/semantic_parts.json`
- `data/assembly_semantic.json`
- `data/mounting_relationships.json`
- `data/disassembly_dependencies.json`
- `data/reference_missing_features.json`
- `output/stage01_split.blend`
- `output/stage02_semantic.blend`

Task 9A may write only the listed `data/`, `output/`, `logs/`, and review-page
paths in this plan. It must not overwrite either Stage 01/02 blend.

### Task 1: Add the Task 9A design contract and generated-file hygiene

**Files:**
- Create: `scripts/task09_data.py`
- Create: `tests/test_task09_data.py`
- Modify: `.gitignore`

- [ ] **Step 1: Write failing tests for the baseline and path contract.**

Test these exact behaviors:

```python
def test_task09_baseline_accepts_frozen_task08_inputs(tmp_path):
    # copy the Task 8 fixture inputs into tmp_path
    assert validate_task09_baseline(tmp_path)["source_parts"] == 82

def test_task09_baseline_rejects_changed_stage02_facts(tmp_path):
    # modify only the copied task08 run result
    with pytest.raises(ValueError, match="baseline"):
        validate_task09_baseline(tmp_path)

def test_task09_output_allowlist_rejects_stage01_and_stage02_paths(tmp_path):
    assert is_allowed_task09_output(tmp_path / "data/exploded_state.json")
    assert not is_allowed_task09_output(tmp_path / "output/stage01_split.blend")
    assert not is_allowed_task09_output(tmp_path / "output/stage02_semantic.blend")
```

- [ ] **Step 2: Run the focused tests and confirm the expected missing-module failure.**

```bash
.worktrees/stage01/.venv/bin/pytest -q tests/test_task09_data.py
```

Expected: collection failure because `scripts/task09_data.py` does not yet exist.

- [ ] **Step 3: Implement the minimal data helper.**

Expose these exact values/functions:

```python
TASK09_BASELINE = {
    "source_sha256": "fd2a7b78540245fd098724206d5ddf169fd2f44c07638e9a6459cd92fea717d1",
    "source_parts": 82,
    "faces": 444296,
    "indexed_vertices": 221902,
}

def validate_task09_baseline(project_root: Path) -> dict[str, Any]:
    raise NotImplementedError

def is_allowed_task09_output(path: Path) -> bool:
    raise NotImplementedError

def write_task09_json(path: Path, payload: Any) -> None:
    raise NotImplementedError
```

The validator must call `validate_stage01_baseline` first, then require
`data/task08_run_result.json` to report `PASS`, `output/stage02_semantic.blend`
to exist, and the Task 8 source-only totals to equal the frozen baseline.
Add `.blend1` and `.blend2` patterns to `.gitignore`; do not delete the
existing backup file.

- [ ] **Step 4: Run focused tests and commit the contract slice.**

```bash
.worktrees/stage01/.venv/bin/pytest -q tests/test_task09_data.py
git add scripts/task09_data.py tests/test_task09_data.py .gitignore
git commit -m "feat: add Task 9A baseline contract"
```

### Task 2: Build the disassembly DAG and fastener mapping

**Files:**
- Create: `scripts/task09_planning.py`
- Create: `tests/test_task09_planning.py`

- [ ] **Step 1: Write failing tests for deterministic graph and group expansion.**

Use the real Task 8 fixtures and assert:

```python
def test_disassembly_graph_is_acyclic_and_stable(project_root):
    result = build_disassembly_graph(project_root)
    assert result["directed_acyclic"] is True
    assert result["topological_order"] == sorted_topological_order(result)
    assert any(edge["before"] == "UPPER_HOUSING" and edge["after"] == "MAIN_PCB"
               for edge in result["edges"])

def test_sensor_fixture_dependency_is_retained(project_root):
    result = build_disassembly_graph(project_root)
    assert any(edge["before"] == "TRI_AXIS_SENSOR_FIXTURE"
               and edge["after"] == "SENSOR_CORE_FIXTURE_X"
               for edge in result["edges"])

def test_fastener_mapping_keeps_every_duplicate_member_independent(project_root):
    groups = build_fastener_group_mapping(project_root)["groups"]
    dg011 = next(group for group in groups if group["group_id"] == "DG_011")
    assert dg011["quantity"] == 29
    assert len(dg011["member_parts"]) == 29
    assert dg011["motion_policy"] in {"GROUP_LINEAR", "UNASSIGNED"}
```

- [ ] **Step 2: Run the focused tests and verify they fail for missing planning functions.**

```bash
.worktrees/stage01/.venv/bin/pytest -q tests/test_task09_planning.py
```

- [ ] **Step 3: Implement deterministic DAG construction.**

Implement:

```python
def build_disassembly_graph(project_root: Path) -> dict[str, Any]:
    raise NotImplementedError

def build_fastener_group_mapping(project_root: Path) -> dict[str, Any]:
    raise NotImplementedError
```

Expand the existing dependency records without inventing relationships.
Represent unresolved semantic groups as virtual nodes, attach real PART IDs
when a mapping exists, preserve evidence/confidence/manual flags, sort nodes
and edges deterministically, and reject cycles with a clear `ValueError`.
For duplicate groups, preserve all member PART IDs, choose a representative
by numeric PART order, use nearest semantic assembly only when the distance
margin is unambiguous, otherwise emit `UNASSIGNED` with `LOW` confidence.

- [ ] **Step 4: Run focused tests and commit.**

```bash
.worktrees/stage01/.venv/bin/pytest -q tests/test_task09_planning.py
git add scripts/task09_planning.py tests/test_task09_planning.py
git commit -m "feat: plan Task 9A disassembly graph"
```

### Task 3: Plan exploded transforms, distances, guides, and collisions

**Files:**
- Modify: `scripts/task09_planning.py`
- Modify: `tests/test_task09_planning.py`

- [ ] **Step 1: Write failing tests for motion policy and collision output.**

```python
def test_exploded_state_covers_all_parts_and_preserves_assembled_values(project_root):
    state = build_exploded_state(project_root)
    assert list(state["parts"]) == [f"PART_{i:03d}" for i in range(1, 83)]
    assert state["parts"]["PART_004"]["explode_vector"] == [0.0, 0.0, 1.0]
    assert state["parts"]["PART_004"]["motion_type"] == "LINEAR"
    assert state["parts"]["PART_004"]["explode_distance_mm"] > 0

def test_group_members_share_translation_and_small_parts_are_reviewable(project_root):
    state = build_exploded_state(project_root)
    assert state["parts"]["PART_020"]["explode_vector"] == state["parts"]["PART_021"]["explode_vector"]
    assert state["parts"]["PART_039"]["requires_manual_confirmation"] is True

def test_collision_check_reports_new_overlaps_not_initial_touching(project_root):
    state = build_exploded_state(project_root)
    assert "collisions" in state["collision_summary"]
    assert all("part_a" in item and "part_b" in item for item in state["collision_summary"]["collisions"])
```

- [ ] **Step 2: Run the focused tests and confirm the new behavior fails.**

```bash
.worktrees/stage01/.venv/bin/pytest -q tests/test_task09_planning.py
```

- [ ] **Step 3: Implement the deterministic motion planner.**

Expose:

```python
def build_exploded_state(project_root: Path) -> dict[str, Any]:
    raise NotImplementedError

def build_explosion_guides(exploded_state: Mapping[str, Any]) -> dict[str, Any]:
    raise NotImplementedError

def check_swept_aabb_collisions(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    raise NotImplementedError
```

Use explicit directions for the known groups in the design document. For
members of `BATTERY_ASSEMBLY` and `LEVELING_ASSEMBLY`, preserve the group
direction while allowing signed axis selection from centroid position. For
unknown and small accessories, use a deterministic radial fallback and mark
`LOW`/manual review. Calculate distance from projected bbox extent, minimum
clearance, and class bounds. Evaluate preferred, inverse, and alternate axes
at five interpolation samples; choose the first candidate with the fewest
new AABB overlaps, and mark unresolved warnings instead of hiding them.
Store both assembled and exploded transforms for every PART. Never change
`assembly_initial.json`.

- [ ] **Step 4: Add output builders and run focused tests.**

Implement:

```python
def build_future_visual_assets(project_root: Path) -> dict[str, Any]:
    raise NotImplementedError

def build_explosion_review_queue(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    raise NotImplementedError
```

Write JSON/CSV only through the deterministic helper. Keep the single
fragment, non-watertight parts, unresolved port order, and `PART_022`
medium-confidence status visible in the queue when their records qualify.

```bash
.worktrees/stage01/.venv/bin/pytest -q tests/test_task09_planning.py
git add scripts/task09_planning.py tests/test_task09_planning.py
git commit -m "feat: plan Task 9A exploded transforms"
```

### Task 4: Create the no-keyframe Stage 03 Blender preview

**Files:**
- Create: `scripts/build_stage03_exploded_preview.py`
- Create: `tests/test_stage03_exploded_preview.py`

- [ ] **Step 1: Write failing Blender contract tests.**

Test pure helpers first:

```python
def test_stage03_state_argument_accepts_only_assembled_or_exploded():
    assert VALID_STATES == ("assembled", "exploded")

def test_stage03_transform_contract_rejects_missing_part_or_animation():
    with pytest.raises(ValueError, match="source PART"):
        validate_stage03_source_scene([], vertices=0, polygons=0)
```

The integration assertion must require source-only counts `82/444296/221902`,
zero source-object animation data, and exact assembled transforms when the
scene is built with `--state assembled`.

- [ ] **Step 2: Run focused tests and verify the missing-builder failure.**

```bash
.worktrees/stage01/.venv/bin/pytest -q tests/test_stage03_exploded_preview.py
```

- [ ] **Step 3: Implement the derived-scene builder.**

Expose:

```python
VALID_STATES = ("assembled", "exploded")

def validate_stage03_source_scene(
    facts: Sequence[Mapping[str, Any]],
    *,
    vertices: int,
    polygons: int,
) -> dict[str, Any]:
    raise NotImplementedError

def build_stage03_scene(project_root: Path, state: str = "exploded") -> dict[str, Any]:
    raise NotImplementedError
```

Open `output/stage02_semantic.blend`, validate source objects using the
existing Stage 02 contract, read the planned state, set only object
transforms for `exploded`, restore `assembly_initial.json` for `assembled`,
add `task09_state` and plan custom properties, and save only
`output/stage03_exploded_preview.blend`. Do not call any keyframe API, do not
edit mesh vertices/polygons, and do not save Stage 02.

- [ ] **Step 4: Run Blender headless for both states and commit.**

```bash
/opt/homebrew/bin/blender -b --python scripts/build_stage03_exploded_preview.py -- --project-root . --state exploded
/opt/homebrew/bin/blender -b --python scripts/build_stage03_exploded_preview.py -- --project-root . --state assembled
.worktrees/stage01/.venv/bin/pytest -q tests/test_stage03_exploded_preview.py
git add scripts/build_stage03_exploded_preview.py tests/test_stage03_exploded_preview.py
git commit -m "feat: build Task 9A exploded preview scene"
```

After the assembled check, rebuild the official preview with `--state exploded`.

### Task 5: Add schedule, validation renders, and static review page

**Files:**
- Create: `scripts/build_animation_plan.py`
- Create: `scripts/generate_explosion_validation.py`
- Create: `scripts/build_task09a_review_page.py`
- Create: `tests/test_task09a_outputs.py`

- [ ] **Step 1: Write failing output-contract tests.**

```python
def test_animation_plan_has_no_keyframe_payload(project_root):
    plan = build_animation_plan(project_root)
    assert plan["fps"] == 30
    assert plan["animation_created"] is False
    assert "keyframes" not in plan

def test_review_page_contains_relative_links_to_required_views(tmp_path):
    page = build_review_page(
        tmp_path,
        {"views": ["exploded_iso_front.png", "exploded_iso_rear.png"]},
        {"assemblies": []},
        {"fps": 30, "animation_created": False},
    )
    html = page.read_text(encoding="utf-8")
    assert "exploded_iso_front.png" in html
    assert "exploded_iso_rear.png" in html
```

- [ ] **Step 2: Run focused tests and confirm failure.**

```bash
.worktrees/stage01/.venv/bin/pytest -q tests/test_task09a_outputs.py
```

- [ ] **Step 3: Implement schedule and future-asset output.**

Create `data/animation_plan.json` with a 30 FPS schedule, 1–570 frame
envelope, parallel group IDs, `BEZIER_EASE_IN_OUT`, assembled/exploded holds,
and no keyframe list. Create `data/future_visual_assets.json` from Task 8
missing features. Keep port role unresolved and do not reconstruct the rope,
labels, color, or PCB texture.

- [ ] **Step 4: Implement five fixed validation renders.**

`generate_explosion_validation.py` must use the current Stage 03 state and
write exactly:

```text
output/explosion_validation/exploded_front.png
output/explosion_validation/exploded_side.png
output/explosion_validation/exploded_top.png
output/explosion_validation/exploded_iso_front.png
output/explosion_validation/exploded_iso_rear.png
```

Use neutral inspection lighting and fixed cameras. No materials or scene
geometry are added to the source PART set.

- [ ] **Step 5: Implement the static local HTML review page.**

Write `output/task09a_review/index.html` with embedded CSS and relative image
links. It must show the five views, an assembly/group table, direction and
distance fields, collision warnings, the DAG order, and links to the JSON/CSV
files. It must not contain the only copy of any decision. The page must work
as a static file served by a local HTTP server; no Three.js or external CDN is
required.

- [ ] **Step 6: Run focused tests and commit.**

```bash
.worktrees/stage01/.venv/bin/pytest -q tests/test_task09a_outputs.py
git add scripts/build_animation_plan.py scripts/generate_explosion_validation.py scripts/build_task09a_review_page.py tests/test_task09a_outputs.py
git commit -m "feat: add Task 9A schedule and review outputs"
```

### Task 6: Add the Task 9A orchestrator

**Files:**
- Create: `run_task09a.py`
- Create: `tests/test_run_task09a.py`

- [ ] **Step 1: Write failing orchestrator tests.**

```python
def test_run_task09a_refuses_nonpass_task08(tmp_path):
    with pytest.raises(ValueError, match="Task 8"):
        run_task09a(tmp_path, skip_blender=True)

def test_run_task09a_writes_checkpoint_result_without_animation(tmp_path):
    result = run_task09a(tmp_path, skip_blender=True)
    assert result["animation_created"] is False

def test_run_task09a_command_keeps_project_root_after_blender_separator():
    command = build_blender_command(Path("/opt/homebrew/bin/blender"), Path("/tmp/project"), "scripts/build_stage03_exploded_preview.py", "exploded")
    assert command[-4:] == ["--project-root", "/tmp/project", "--state", "exploded"]
```

- [ ] **Step 2: Run the focused tests and confirm failure.**

```bash
.worktrees/stage01/.venv/bin/pytest -q tests/test_run_task09a.py
```

- [ ] **Step 3: Implement fail-closed orchestration.**

The entry point must execute in this order:

```text
validate Task 9A baseline
→ build disassembly graph
→ build fastener mapping
→ build exploded state and collision summary
→ write guides/review queue/future assets
→ write animation plan
→ build Stage 03 exploded preview
→ render five validation views
→ build static review page
→ reopen and validate Stage 03 source totals and animation data
→ write data/task09a_run_result.json and logs/task09a.log
```

The runner must support `--skip-blender` as `PARTIAL`, must never claim
`PASS` in that mode, and must log every subprocess command and failure.

- [ ] **Step 4: Run the focused tests and commit.**

```bash
.worktrees/stage01/.venv/bin/pytest -q tests/test_run_task09a.py
git add run_task09a.py tests/test_run_task09a.py
git commit -m "feat: orchestrate Task 9A planning"
```

### Task 7: Execute the real Task 9A checkpoint

- [ ] **Step 1: Run the complete pipeline from the frozen Task 8 inputs.**

```bash
.worktrees/stage01/.venv/bin/python run_task09a.py --project-root . --blender-path /opt/homebrew/bin/blender
```

Expected result: `status=PASS`, `animation_created=false`,
`source_geometry_modified=false`, and all required JSON/CSV/PNG/HTML paths
present.

- [ ] **Step 2: Inspect the static review page and validation renders.**

Open the local review page in the approved browser companion. Check at least
`exploded_iso_front.png` and `exploded_iso_rear.png` against the assembled
reference view. Record visual findings in the terminal or, if a direction is
changed, update the JSON source of truth and regenerate the derived outputs.

- [ ] **Step 3: Run complete verification.**

```bash
.worktrees/stage01/.venv/bin/pytest -q
rtk git diff --check
rtk shasum -a 256 智能地震仪-221128\(1\).STL source/智能地震仪-221128\(1\).STL
/opt/homebrew/bin/blender -b output/stage03_exploded_preview.blend --python-expr 'import bpy; p=[o for o in bpy.data.objects if o.type=="MESH" and o.get("source")=="original_stl"]; print(len(p),sum(len(o.data.polygons) for o in p),sum(len(o.data.vertices) for o in p),sum(1 for o in p if o.animation_data))'
```

The Blender command must print `82 444296 221902 0`; the two STL hashes must
remain the frozen SHA256.

- [ ] **Step 4: Request read-only code review before reporting the checkpoint.**

Review source safety, DAG correctness, uncertainty flags, collision policy,
render outputs, static-page links, and the absence of keyframes. Fix any
Critical or Important issue, rerun the full verification, and only then report.

### Task 8: Stop at Task 9A

- [ ] **Step 1:** Confirm no `keyframes`, `animation_data`, camera animation,
  explosion timing implementation, final materials, or final render exists.
- [ ] **Step 2:** Report the requested directions/distances/collisions,
  review-page path, and the five validation image paths.
- [ ] **Step 3:** Stop and wait for human approval before Task 9B.
