# Task 10 Product Story Animation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate a reproducible 30-second product-functional story preview from the validated Task 9C scene, explaining sensing, acquisition, communication, power, and field adaptability without changing source geometry.

**Architecture:** Build a new `stage_10_product_story/` pipeline whose JSON files are the source of truth for product claims, functional modules, shots, state transforms, cameras, annotations, and validation. Blender reads those files and writes a new preview scene; it never overwrites Stage 01, Stage 02, Task 9C, or the source STL. Rendered stills, a 1920×1080 MP4, and a storyboard contact sheet are generated from the same state data.

**Tech Stack:** Python 3.14 virtual environment, standard library JSON/hashlib/subprocess, Blender 5.2.1 Python API, Eevee preview rendering, Pillow through the existing project image helpers, pytest, FFmpeg support bundled with Blender.

---

## Working rules

- Work in `/Users/xiwei/modeling` on the already approved `main` workspace; do not reset or discard the user’s untracked reference images, PDF, or `output/` directory.
- Every shell command is run through `rtk`.
- Every source edit uses `apply_patch`.
- The input scene is `stage_09C_refined_explosion/scene/exploded_animation_preview.blend`.
- The immutable source baseline is `82` source PART meshes, `444296` faces, and `221902` indexed vertices.
- Source mesh data is never edited, joined, decimated, remeshed, repaired, or split.
- Task 10 output is written only below `stage_10_product_story/` plus the new top-level runner, tests, and documentation.
- `communication_protocol_text` remains exactly `PENDING_PRODUCT_CONFIRMATION`; the preview renders `Multi-network communication` and never renders `4G` or `Bluetooth`.
- The product PDF stays at `幔壳迅勘智能勘察设备.pdf` as an immutable reference. Its SHA256 is `d8555d751851d6e5f53027721c29eb701da27226bd1311b47bd1d1d1bbdb0d7e`.
- The Task 9C input scene must remain byte-identical during Task 10. Its current SHA256 is `a3b5359861877e247ad1b035b00cace3e29eea2789ac227e6eeddfaaba1a7766`.

## File map

Create these implementation files:

```text
run_task10.py
stage_10_product_story/__init__.py
stage_10_product_story/scripts/__init__.py
stage_10_product_story/scripts/build_product_reference.py
stage_10_product_story/scripts/story_data.py
stage_10_product_story/scripts/build_story_scene.py
stage_10_product_story/scripts/apply_story_animation.py
stage_10_product_story/scripts/setup_story_presentation.py
stage_10_product_story/scripts/render_product_story.py
stage_10_product_story/scripts/compose_storyboard.py
stage_10_product_story/scripts/validate_product_story.py
stage_10_product_story/scripts/pipeline.py
tests/test_task10_story.py
tests/test_run_task10.py
```

Generated source-of-truth data:

```text
stage_10_product_story/config/product_story.json
stage_10_product_story/config/functional_modules.json
stage_10_product_story/config/shot_sequence.json
stage_10_product_story/config/state_transforms.json
stage_10_product_story/config/camera_sequence.json
stage_10_product_story/config/annotation_config.json
stage_10_product_story/config/product_reference_manifest.json
stage_10_product_story/config/validation.json
```

Generated review assets:

```text
stage_10_product_story/scene/product_story_preview.blend
stage_10_product_story/renders/product_story_preview.mp4
stage_10_product_story/renders/storyboard_contact_sheet.png
stage_10_product_story/renders/01_assembled.png
stage_10_product_story/renders/02_primary_explosion.png
stage_10_product_story/renders/03_sensor_focus.png
stage_10_product_story/renders/04_pcb_focus.png
stage_10_product_story/renders/05_communication_focus.png
stage_10_product_story/renders/06_power_focus.png
stage_10_product_story/renders/07_rugged_focus.png
stage_10_product_story/renders/08_final_hero.png
stage_10_product_story/reports/task10_product_story_report.md
stage_10_product_story/logs/task10.log
stage_10_product_story/data_task10_run_result.json
```

### Task 1: Product reference and claims manifest

**Files:**

- Create: `stage_10_product_story/scripts/build_product_reference.py`
- Modify: `requirements.txt`
- Create: `tests/test_task10_story.py`
- Generate: `stage_10_product_story/config/product_reference_manifest.json`

- [ ] **Step 1: Write failing tests for the local PDF manifest.**

```python
from pypdf import PdfWriter

def test_product_reference_manifest_records_pdf_hash_and_claim_pages(tmp_path):
    pdf = tmp_path / "幔壳迅勘智能勘察设备.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.add_blank_page(width=100, height=100)
    with pdf.open("wb") as handle:
        writer.write(handle)
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    manifest = build_product_reference_manifest(tmp_path, pdf_path=pdf, expected_sha256=digest)

    assert manifest["pdf_status"] == "VERIFIED_LOCAL_REFERENCE"
    assert manifest["page_count"] == 2
    assert manifest["sha256"] == digest
    assert manifest["claims"]["channels"]["value"] == 3
    assert manifest["claims"]["adc_resolution"]["value"] == "32-bit"
    assert manifest["claims"]["standby_days"]["value"] == 10
    assert manifest["claims"]["charging_hours"]["value"] == 3
    assert manifest["claims"]["weight_kg"]["value"] == 2.5
    assert manifest["claims"]["temperature_range_c"]["value"] == [-40, 80]
    assert manifest["communication_protocol"]["status"] == "CONFLICT_REQUIRES_CONFIRMATION"


def test_product_reference_manifest_is_fail_closed_for_missing_pdf(tmp_path):
    manifest = build_product_reference_manifest(tmp_path, pdf_path=tmp_path / "missing.pdf")
    assert manifest["pdf_status"] == "MISSING_LOCAL_REFERENCE"
    assert manifest["claims_source"] == "USER_PRODUCT_BRIEF_2026-09-10"
```

- [ ] **Step 2: Run the focused tests and verify the new API fails.**

Run:

```bash
rtk .worktrees/stage01/.venv/bin/pytest -q tests/test_task10_story.py -k product_reference
```

Expected: collection or assertion failure because the Task 10 manifest builder does not exist.

- [ ] **Step 3: Implement the manifest builder.**

Add `pypdf>=6.18,<7` to `requirements.txt`. Use the existing local PDF and `pypdf.PdfReader` when available. Store page-level evidence rather than copying long PDF text. The pipeline passes the approved project PDF SHA256 as `expected_sha256`; unit fixtures pass their own calculated hash.

```python
PDF_NAME = "幔壳迅勘智能勘察设备.pdf"
PDF_SHA256 = "d8555d751851d6e5f53027721c29eb701da27226bd1311b47bd1d1d1bbdb0d7e"

def build_product_reference_manifest(project_root: Path, *, pdf_path: Path, expected_sha256: str | None = None) -> dict[str, Any]:
    if not pdf_path.is_file():
        return {
            "reference_id": "PRODUCT_PDF_001",
            "source_file": str(pdf_path),
            "pdf_status": "MISSING_LOCAL_REFERENCE",
            "claims_source": "USER_PRODUCT_BRIEF_2026-09-10",
            "claims": {},
            "communication_protocol": {
                "status": "CONFLICT_REQUIRES_CONFIRMATION",
                "render_text": "Multi-network communication",
                "communication_protocol_text": "PENDING_PRODUCT_CONFIRMATION",
            },
        }
    digest = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise ValueError("product PDF SHA256 does not match the approved reference")
    return {
        "reference_id": "PRODUCT_PDF_001",
        "source_file": str(pdf_path),
        "pdf_status": "VERIFIED_LOCAL_REFERENCE",
        "sha256": digest,
        "page_count": 2,
        "claims_source": PDF_NAME,
        "claims": {
            "data_consistency_percent": {"value": 99, "unit": "%", "evidence_pages": [1]},
            "channels": {"value": 3, "unit": "channels", "evidence_pages": [2]},
            "adc_resolution": {"value": "32-bit", "unit": "ADC", "evidence_pages": [2]},
            "standby_days": {"value": 10, "unit": "days", "evidence_pages": [2]},
            "charging_hours": {"value": 3, "unit": "hours", "evidence_pages": [2]},
            "weight_kg": {"value": 2.5, "unit": "kg", "evidence_pages": [2]},
            "temperature_range_c": {"value": [-40, 80], "unit": "°C", "evidence_pages": [2]},
        },
        "communication_protocol": {
            "status": "CONFLICT_REQUIRES_CONFIRMATION",
            "page_1_text": "WIFI / NBIoT / 4G",
            "page_2_text": "WIFI / NBIoT / Bluetooth",
            "render_text": "Multi-network communication",
            "communication_protocol_text": "PENDING_PRODUCT_CONFIRMATION",
        },
    }
```

For the checked-in project, the builder must record the actual PDF hash and two-page result. The missing-PDF branch is retained for fail-closed reproducibility tests.

- [ ] **Step 4: Generate and validate the manifest.**

Run:

```bash
rtk .worktrees/stage01/.venv/bin/python -m stage_10_product_story.scripts.build_product_reference --project-root .
rtk .worktrees/stage01/.venv/bin/pytest -q tests/test_task10_story.py -k product_reference
```

Expected: the manifest records `VERIFIED_LOCAL_REFERENCE`, the approved SHA256, two pages, all six numeric claim groups, and a communication conflict.

- [ ] **Step 5: Commit the reference-manifest unit.**

```bash
rtk git add stage_10_product_story tests/test_task10_story.py
rtk git commit -m "feat: register Task 10 product reference claims"
```

### Task 2: Functional modules, product story, and shot contracts

**Files:**

- Create: `stage_10_product_story/scripts/story_data.py`
- Modify: `tests/test_task10_story.py`
- Generate: `product_story.json`, `functional_modules.json`, `shot_sequence.json`, `annotation_config.json`

- [ ] **Step 1: Write failing module and shot tests.**

```python
def test_functional_modules_cover_exactly_the_22_story_parts():
    modules = build_functional_modules()
    members = [part_id for module in modules.values() for part_id in module["part_ids"]]
    assert len(members) == 22
    assert len(set(members)) == 22
    assert modules["SMART_3_AXIS_SENSING_SYSTEM"]["part_ids"] == [
        "PART_003", "PART_012", "PART_013", "PART_014"
    ]
    assert modules["HIGH_PRECISION_ACQUISITION_CORE"]["part_ids"] == [
        "PART_006", "PART_007", "PART_019"
    ]
    assert modules["REAL_TIME_COMMUNICATION_SYSTEM"]["part_ids"] == [
        "PART_005", "PART_017", "PART_018"
    ]


def test_story_shots_are_30_seconds_and_keep_protocol_pending():
    story = build_story_config()
    assert story["fps"] == 30
    assert story["frame_range"] == [1, 900]
    assert story["duration_seconds"] == 30.0
    assert [shot["shot_id"] for shot in story["shots"]] == [
        "ASSEMBLED", "PRIMARY_ARCHITECTURE", "SENSOR_FOCUS", "PCB_FOCUS",
        "COMMUNICATION_FOCUS", "POWER_FOCUS", "RUGGED_FOCUS", "REASSEMBLED",
        "FINAL_HERO",
    ]
    assert story["communication_protocol_text"] == "PENDING_PRODUCT_CONFIRMATION"
    assert all("4G" not in shot["title"] for shot in story["shots"])
    assert all("Bluetooth" not in " ".join(shot["metrics"]) for shot in story["shots"])
```

- [ ] **Step 2: Run the focused tests and verify the contracts fail.**

Run:

```bash
rtk .worktrees/stage01/.venv/bin/pytest -q tests/test_task10_story.py -k 'functional_modules or story_shots'
```

Expected: failure because the Task 10 story builders do not exist.

- [ ] **Step 3: Implement the deterministic data builders.**

Define the exact disjoint functional membership:

```python
FUNCTIONAL_MODULES = {
    "SMART_3_AXIS_SENSING_SYSTEM": ["PART_003", "PART_012", "PART_013", "PART_014"],
    "HIGH_PRECISION_ACQUISITION_CORE": ["PART_006", "PART_007", "PART_019"],
    "REAL_TIME_COMMUNICATION_SYSTEM": ["PART_005", "PART_017", "PART_018"],
    "LONG_ENDURANCE_POWER_SYSTEM": [
        "PART_008", "PART_009", "PART_010", "PART_011", "PART_015", "PART_016"
    ],
    "RUGGED_FIELD_PLATFORM": [
        "PART_001", "PART_002", "PART_004", "PART_020", "PART_021", "PART_022"
    ],
}

SHOT_RANGES = [
    ("ASSEMBLED", 1, 75),
    ("PRIMARY_ARCHITECTURE", 75, 165),
    ("SENSOR_FOCUS", 165, 300),
    ("PCB_FOCUS", 300, 420),
    ("COMMUNICATION_FOCUS", 420, 510),
    ("POWER_FOCUS", 510, 615),
    ("RUGGED_FOCUS", 615, 705),
    ("REASSEMBLED", 705, 810),
    ("FINAL_HERO", 810, 900),
]
```

Each module record includes `part_ids`, `customer_takeaway`, `title`, `metrics`, `material_role`, and `focus_weight`. Each shot record includes `shot_id`, `frame_start`, `frame_end`, `state_id`, `focus_module`, `title`, `metrics`, `camera_id`, `emphasis`, and `validation_target`. The Primary Architecture shot uses four display groups while the functional sequence remains Sensor → Acquisition → Communication → Power → Rugged. The same pure-Python module exports `build_material_roles()`, `build_camera_sequence()`, and `build_annotation_config()` for the later presentation tests; Blender-facing setup remains in `setup_story_presentation.py`.

Use `scripts.task08_data.write_json` to write stable sorted JSON. Store the product claim references as `PRODUCT_PDF_001` and page numbers.

- [ ] **Step 4: Generate the four pure-Python story configs.**

Run:

```bash
rtk .worktrees/stage01/.venv/bin/python -m stage_10_product_story.scripts.story_data --project-root .
rtk .worktrees/stage01/.venv/bin/pytest -q tests/test_task10_story.py -k 'functional_modules or story_shots'
```

Expected: module membership and all nine shot ranges pass, with no final protocol names in customer-facing preview text.

- [ ] **Step 5: Commit the story data unit.**

```bash
rtk git add stage_10_product_story tests/test_task10_story.py
rtk git commit -m "feat: define Task 10 functional story shots"
```

### Task 3: State transforms and product-scene construction

**Files:**

- Create: `stage_10_product_story/scripts/build_story_scene.py`
- Create: `stage_10_product_story/scripts/apply_story_animation.py`
- Modify: `tests/test_task10_story.py`
- Generate: `state_transforms.json`, `scene/product_story_preview.blend`

- [ ] **Step 1: Write failing state and source-integrity tests.**

```python
def test_state_transforms_cover_all_22_story_parts_and_nine_states(project_root):
    state_data = build_state_transforms(project_root)
    assert state_data["source_baseline"] == {
        "source_part_count": 82,
        "faces": 444296,
        "indexed_vertices": 221902,
    }
    assert list(state_data["states"]) == [
        "ASSEMBLED", "PRIMARY_ARCHITECTURE", "SENSOR_FOCUS", "PCB_FOCUS",
        "COMMUNICATION_FOCUS", "POWER_FOCUS", "RUGGED_FOCUS", "REASSEMBLED",
        "FINAL_HERO",
    ]
    for state in state_data["states"].values():
        assert list(state["parts"]) == [f"PART_{i:03d}" for i in range(1, 23)]
    assert state_data["states"]["ASSEMBLED"]["parts"]["PART_001"]["location"] == pytest.approx(
        state_data["states"]["FINAL_HERO"]["parts"]["PART_001"]["location"]
    )


def test_story_scene_policy_keeps_all_source_parts_and_hides_small_parts():
    policy = build_story_visibility_policy()
    assert len(policy["visible_part_ids"]) == 22
    assert policy["visible_part_ids"] == [f"PART_{i:03d}" for i in range(1, 23)]
    assert len(policy["hidden_part_ids"]) == 60
    assert policy["hidden_part_ids"][-1] == "PART_082"
```

- [ ] **Step 2: Run the focused tests and verify they fail.**

Run:

```bash
rtk .worktrees/stage01/.venv/bin/pytest -q tests/test_task10_story.py -k 'state_transforms or scene_policy'
```

Expected: failure because the state builder and scene policy do not exist.

- [ ] **Step 3: Implement state transform generation from 9C.**

Read `stage_09C_refined_explosion/config/refined_layout.json`. Preserve each source object’s `assembled_location`, rotation, and scale. Use deterministic helper functions:

```python
def offset(location, delta):
    return [float(location[index]) + float(delta[index]) for index in range(3)]

def state_record(part_id, location, focus_weight, module_id, visibility="VISIBLE"):
    return {
        "part_id": part_id,
        "location": [float(value) for value in location],
        "rotation": [0.0, 0.0, 0.0],
        "scale": [1.0, 1.0, 1.0],
        "visibility": visibility,
        "focus_weight": float(focus_weight),
        "functional_module": module_id,
    }
```

Use the 9C refined arrangement as the starting composition, but create story-specific deterministic deltas:

```text
PRIMARY_ARCHITECTURE:
  TOP / EXTERIOR parts: +Z 90 mm from assembled
  ELECTRONICS / POWER parts: +Z 30 mm from assembled
  SENSOR parts: -X 70 mm and +Z 20 mm
  LOWER FIELD PLATFORM: assembled anchor

SENSOR_FOCUS:
  sensor assembly: -X 120 mm; X/Y/Z local spread 20/26/32 mm
  other modules: remain in primary context with focus weight <= 0.45

PCB_FOCUS:
  protective plate: +Z 32 mm and +X 12 mm from PCB anchor
  MAIN_PCB: +X 0 mm, center of PCB focus zone
  support frame: -Z 32 mm and -X 12 mm from PCB anchor
  PCB group remains within 180 mm of the housing center

COMMUNICATION_FOCUS:
  handle and ports: +Z 45 mm and +X 38 mm from assembled positions
  MAIN_PCB: assembled context, focus weight 0.30

POWER_FOCUS:
  six batteries: compact 3×2 array around +X 115 mm, with 34 mm center spacing
  no battery moves farther than 180 mm from the housing center

RUGGED_FOCUS:
  lower/upper housing return near assembled positions
  three feet: assembled XY, -Z 55 mm

REASSEMBLED / FINAL_HERO:
  all 22 visible parts return exactly to assembled locations
```

The layout builder must use existing bbox dimensions to scale local offsets by a deterministic factor where possible; the constants above define the intended maximum presentation ranges, not mesh edits. `state_transforms.json` stores exact computed coordinates and a `derivation` object for every state.

- [ ] **Step 4: Build the new Blender scene from the frozen 9C scene.**

`build_story_scene.py` must:

1. Open 9C blend.
2. Count source meshes and assert 82/444296/221902 before any changes.
3. Clear Task 9C animation from source objects in the new in-memory copy.
4. Keep all 82 source mesh objects and their existing `part_id` / `source` properties.
5. Hide PART_023..PART_082 in viewport and render; do not delete them.
6. Create `STORY_10`, `STORY_SOURCE_HIDDEN`, `STORY_MODULES`, `STORY_ANNOTATIONS`, and `STORY_CAMERAS` collections.
7. Keep source mesh data unmodified; assign only object-level materials and custom properties.
8. Save `scene/product_story_preview.blend` and reopen it for source-total validation.

The module also exports pure functions `build_state_transforms(project_root)` and `build_story_visibility_policy()` so their JSON contracts can be tested without importing Blender.

The scene builder’s central validation shape is:

```python
def source_totals(objects):
    source = [obj for obj in objects if obj.type == "MESH" and obj.get("source") == "original_stl"]
    return {
        "source_part_count": len(source),
        "faces": sum(len(obj.data.polygons) for obj in source),
        "indexed_vertices": sum(len(obj.data.vertices) for obj in source),
    }
```

- [ ] **Step 5: Apply state keyframes only to the 22 story parts.**

`apply_story_animation.py` reads `state_transforms.json`, inserts location/rotation keyframes at the exact shot boundaries, and clears animation from the 60 hidden parts. Use Bezier interpolation with automatic handles, no modifiers, no overshoot, and no bounce. Store `task10_story_animation_enabled`, `task10_story_state_source`, and `task10_functional_module` custom properties on source objects.

The assembled/final state check must compare evaluated object locations at frames 1 and 900 to the JSON assembled/final coordinates within `1e-4` mm.

- [ ] **Step 6: Run pure tests and Blender scene validation.**

Run:

```bash
rtk .worktrees/stage01/.venv/bin/pytest -q tests/test_task10_story.py -k 'state_transforms or scene_policy'
rtk /opt/homebrew/bin/blender -b --python stage_10_product_story/scripts/build_story_scene.py -- --project-root .
rtk /opt/homebrew/bin/blender -b --python stage_10_product_story/scripts/apply_story_animation.py -- --project-root .
```

Expected: new scene reopens with 82 source meshes, 444296 faces, 221902 indexed vertices, 22 animated story parts, and 60 hidden parts with no animation data.

- [ ] **Step 7: Commit the state/scene unit.**

```bash
rtk git add stage_10_product_story tests/test_task10_story.py
rtk git commit -m "feat: build Task 10 story scene and state animation"
```

### Task 4: Materials, functional emphasis, cameras, and annotations

**Files:**

- Create: `stage_10_product_story/scripts/setup_story_presentation.py`
- Modify: `stage_10_product_story/scripts/build_story_scene.py`
- Modify: `stage_10_product_story/scripts/apply_story_animation.py`
- Modify: `tests/test_task10_story.py`
- Generate: `camera_sequence.json`, `annotation_config.json`

- [ ] **Step 1: Write failing presentation tests.**

```python
def test_material_roles_match_product_story():
    from stage_10_product_story.scripts.story_data import build_material_roles
    materials = build_material_roles()
    assert materials["LOWER_HOUSING"]["base_color"] == [0.95, 0.18, 0.02, 1.0]
    assert materials["UPPER_HOUSING"]["base_color"] == [0.025, 0.03, 0.035, 1.0]
    assert materials["MAIN_PCB"]["base_color"] == [0.02, 0.32, 0.10, 1.0]
    assert materials["SENSOR"]["role"] == "DARK_METALLIC"


def test_camera_sequence_has_one_controlled_hero_camera_and_no_fast_orbit():
    from stage_10_product_story.scripts.story_data import build_camera_sequence
    config = build_camera_sequence()
    assert config["fps"] == 30
    assert config["hero_camera"] == "CAM_STORY_HERO"
    assert config["camera_motion_policy"] == "SLOW_CONTROLLED"
    assert config["max_orbit_degrees_per_second"] <= 8
    assert {shot["camera_id"] for shot in config["shots"]} <= {
        "CAM_STORY_HERO", "CAM_STORY_SENSOR", "CAM_STORY_PCB"
    }


def test_annotations_never_render_unconfirmed_protocol_names():
    from stage_10_product_story.scripts.story_data import build_annotation_config
    config = build_annotation_config()
    rendered_text = " ".join(item["text"] for item in config["items"])
    assert "PENDING_PRODUCT_CONFIRMATION" not in rendered_text
    assert "4G" not in rendered_text
    assert "Bluetooth" not in rendered_text
    assert "Multi-network communication" in rendered_text
```

- [ ] **Step 2: Run the tests and verify they fail.**

Run:

```bash
rtk .worktrees/stage01/.venv/bin/pytest -q tests/test_task10_story.py -k 'material_roles or camera_sequence or annotations'
```

Expected: failure because the presentation builders do not exist.

- [ ] **Step 3: Implement object-level product materials.**

Use Eevee-compatible Principled BSDF materials assigned by `part_id`/module. Use black matte upper parts, industrial orange lower housing, green `PART_019`, dark metallic sensor, charcoal battery, and neutral metal supports. Create per-role material instances so focus weights can keyframe Principled Base Color and roughness without modifying mesh data. `MAIN_PCB` remains one object and one unchanged mesh.

- [ ] **Step 4: Implement focus weights and annotation state data.**

Focus weight policy:

```text
focused module: 1.00
neighbour context: 0.45
distant context: 0.28
assembled/final hero: 1.00 for visible product parts
```

Create one title and up to two metric text items per shot. The neutral communication annotation must be:

```text
REAL-TIME WIRELESS TRANSMISSION
Multi-network communication
```

Create optional Sensor X/Y/Z axis guides in `STORY_ANNOTATIONS`; they are helper curves/text only and are not included in source mesh totals.

- [ ] **Step 5: Implement the controlled camera sequence.**

Create:

```text
CAM_STORY_HERO
CAM_STORY_SENSOR
CAM_STORY_PCB
```

The hero camera uses a restrained 3/4 view. Sensor and PCB cameras are modest push-in variants, not rapid cuts. Store camera locations, targets, lens, clip values, and keyframe frames in `camera_sequence.json`. Render all text/helpers in separate collections so they can be toggled off.

- [ ] **Step 6: Apply presentation and run the focused tests.**

Run:

```bash
rtk .worktrees/stage01/.venv/bin/pytest -q tests/test_task10_story.py -k 'material_roles or camera_sequence or annotations'
rtk /opt/homebrew/bin/blender -b --python stage_10_product_story/scripts/setup_story_presentation.py -- --project-root .
```

Expected: all presentation contract tests pass and the new blend contains product materials, cameras, and separate annotation collections without source geometry count changes.

- [ ] **Step 7: Commit the presentation unit.**

```bash
rtk git add stage_10_product_story tests/test_task10_story.py
rtk git commit -m "feat: add Task 10 product materials and focus cameras"
```

### Task 5: Rendering, MP4 preview, stills, and storyboard contact sheet

**Files:**

- Create: `stage_10_product_story/scripts/render_product_story.py`
- Create: `stage_10_product_story/scripts/compose_storyboard.py`
- Modify: `tests/test_task10_story.py`
- Generate: eight stills, MP4, contact sheet

- [ ] **Step 1: Write failing render-contract tests.**

```python
def test_task10_render_outputs_are_exactly_the_eight_story_stills_and_preview():
    assert REQUIRED_STILLS == (
        "01_assembled.png", "02_primary_explosion.png", "03_sensor_focus.png",
        "04_pcb_focus.png", "05_communication_focus.png", "06_power_focus.png",
        "07_rugged_focus.png", "08_final_hero.png",
    )
    assert REQUIRED_OUTPUTS == REQUIRED_STILLS + (
        "storyboard_contact_sheet.png", "product_story_preview.mp4", "product_story_preview.blend"
    )


def test_storyboard_contact_sheet_uses_the_eight_story_stills(tmp_path):
    paths = [tmp_path / name for name in REQUIRED_STILLS]
    for path in paths:
        path.write_bytes(b"png")
    assert storyboard_inputs(paths) == [path.name for path in paths]
```

- [ ] **Step 2: Run the tests and verify they fail.**

Run:

```bash
rtk .worktrees/stage01/.venv/bin/pytest -q tests/test_task10_story.py -k 'render_outputs or storyboard'
```

Expected: failure because the render contract and contact-sheet functions do not exist.

- [ ] **Step 3: Implement the Blender render script.**

`render_product_story.py` opens the animated Task 10 blend, sets Eevee, 1920×1080, 30fps, frame range 1–900, and renders stills at representative frames:

```text
01_assembled.png              frame 40
02_primary_explosion.png      frame 145
03_sensor_focus.png           frame 245
04_pcb_focus.png              frame 365
05_communication_focus.png    frame 465
06_power_focus.png            frame 570
07_rugged_focus.png           frame 660
08_final_hero.png             frame 850
```

Render the full range to `product_story_preview.mp4` using Blender 5.2’s `image_settings.media_type = "VIDEO"`, `file_format = "FFMPEG"`, MPEG-4 container, H.264 codec, and no audio. Restore frame 850 and save the blend after rendering.

- [ ] **Step 4: Implement the contact sheet.**

Use the existing Pillow/image helper pattern from `scripts.compose_task08_images`, with deterministic order and labels. The contact sheet must contain exactly the eight stills, arranged 4×2, with the shot ID visible below each image.

- [ ] **Step 5: Render and inspect the outputs.**

Run:

```bash
rtk /opt/homebrew/bin/blender -b --python stage_10_product_story/scripts/render_product_story.py -- --project-root .
rtk .worktrees/stage01/.venv/bin/python stage_10_product_story/scripts/compose_storyboard.py --project-root .
rtk file stage_10_product_story/renders/product_story_preview.mp4
```

Expected: eight non-empty 1920×1080 PNGs, one non-empty contact sheet, and a valid MP4 with 30fps and approximately 30 seconds duration.

- [ ] **Step 6: Inspect each story still with local image viewing.**

Review these images visually:

```text
01_assembled.png
02_primary_explosion.png
03_sensor_focus.png
04_pcb_focus.png
05_communication_focus.png
06_power_focus.png
07_rugged_focus.png
08_final_hero.png
storyboard_contact_sheet.png
```

Reject and refine only if one of these conditions occurs:

- Sensor is not clearly the first technical hero;
- MAIN_PCB is not visibly green or is occluded in PCB Focus;
- HANDLE and top interfaces are not visible in Communication Focus;
- six battery units cannot be read as one power system;
- three leveling feet do not read as stable support in Rugged Focus;
- final hero no longer reads as the same product;
- annotations exceed one title plus two metrics per shot.

- [ ] **Step 7: Commit the render unit.**

```bash
rtk git add stage_10_product_story tests/test_task10_story.py
rtk git commit -m "feat: render Task 10 product story preview"
```

### Task 6: Validation, pipeline runner, report, and regression gate

**Files:**

- Create: `stage_10_product_story/scripts/validate_product_story.py`
- Create: `stage_10_product_story/scripts/pipeline.py`
- Create: `run_task10.py`
- Create: `tests/test_run_task10.py`
- Generate: `config/validation.json`, `reports/task10_product_story_report.md`, `logs/task10.log`, `data_task10_run_result.json`

- [ ] **Step 1: Write failing pipeline and validation tests.**

```python
def test_task10_run_contract_rejects_missing_outputs(tmp_path):
    with pytest.raises(ValueError):
        validate_run_result({"status": "PASS", "outputs": {}})


def test_task10_run_contract_requires_geometry_baseline_and_pending_protocol(tmp_path):
    result = valid_fixture_result(tmp_path)
    assert validate_run_result(result)["source_part_count"] == 82
    assert result["source_faces"] == 444296
    assert result["source_indexed_vertices"] == 221902
    assert result["communication_protocol_text"] == "PENDING_PRODUCT_CONFIRMATION"


def test_task10_pipeline_reads_task09c_before_running(tmp_path):
    with pytest.raises(ValueError, match="Task 9C"):
        require_task09c_pass(tmp_path)
```

- [ ] **Step 2: Run the tests and verify they fail.**

Run:

```bash
rtk .worktrees/stage01/.venv/bin/pytest -q tests/test_run_task10.py
```

Expected: failure because the Task 10 pipeline and validator do not exist.

- [ ] **Step 3: Implement fail-closed validation.**

The validator must reopen `product_story_preview.blend`, count source mesh IDs, verify 82/444296/221902, verify frame range 1–900 at 30fps, confirm only PART_001..PART_022 have animation data, check frame 1 and 900 assembled positions, confirm all required outputs are non-empty, and confirm no unconfirmed protocol words occur in annotation text. It must return `PASS` only when `warnings == []`.

- [ ] **Step 4: Implement the pipeline runner.**

`run_task10.py` delegates to `stage_10_product_story.scripts.pipeline.main`. The pipeline order is:

```text
verify Task 9C PASS and frozen source totals
→ build product reference manifest
→ build functional modules/story configs
→ build state transforms
→ build new Blender scene
→ apply story animation
→ apply materials/cameras/annotations
→ render stills and MP4
→ compose storyboard contact sheet
→ reopen and validate
→ write report/log/result
```

Use the environment variable `BLENDER_PATH` with `/opt/homebrew/bin/blender` as default. Stop on the first failed stage and record command, stdout tail, stderr tail, and failure stage in `task10.log`. Never silently continue.

- [ ] **Step 5: Write the Task 10 report.**

The report must include:

```text
total duration and fps
shot list and frame ranges
functional module → PART mapping
customer takeaway per module
communication protocol conflict and pending status
PDF path and SHA256
material roles
source baseline and regression result
output paths
remaining product confirmation: final communication protocol
```

It must explicitly state that PAD/server/data engine/report generation is reserved for a later continuation and was not animated in Task 10.

- [ ] **Step 6: Run the complete pipeline.**

Run:

```bash
rtk .worktrees/stage01/.venv/bin/python run_task10.py
```

Expected: exit code 0 and `stage_10_product_story/config/validation.json` with `status: PASS`.

- [ ] **Step 7: Commit the pipeline unit.**

```bash
rtk git add run_task10.py stage_10_product_story tests/test_run_task10.py
rtk git commit -m "feat: add reproducible Task 10 story pipeline"
```

### Task 7: Final verification and human-review handoff

**Files:**

- Modify only if verification finds a concrete defect in the Task 10 files.

- [ ] **Step 1: Run the complete test suite.**

```bash
rtk .worktrees/stage01/.venv/bin/pytest -q
```

Expected: all existing Stage 01/02/8/9 tests plus Task 10 tests pass.

- [ ] **Step 2: Run Task 10 twice and compare deterministic config hashes.**

```bash
rtk .worktrees/stage01/.venv/bin/python run_task10.py
rtk .worktrees/stage01/.venv/bin/python - <<'PY'
from pathlib import Path
import hashlib

paths = [
    Path("stage_10_product_story/config/product_story.json"),
    Path("stage_10_product_story/config/functional_modules.json"),
    Path("stage_10_product_story/config/shot_sequence.json"),
    Path("stage_10_product_story/config/state_transforms.json"),
    Path("stage_10_product_story/config/camera_sequence.json"),
    Path("stage_10_product_story/config/annotation_config.json"),
]
for path in paths:
    print(path, hashlib.sha256(path.read_bytes()).hexdigest())
PY
```

Expected: identical config hashes on repeated runs.

- [ ] **Step 3: Verify frozen inputs.**

```bash
rtk shasum -a 256 source/智能地震仪-221128\(1\).STL output/stage01_split.blend output/stage02_semantic.blend stage_09C_refined_explosion/scene/exploded_animation_preview.blend
rtk git diff --check
```

Expected: source STL, Stage 01, Stage 02, and Task 9C hashes match the pre-Task-10 recorded values; no whitespace errors.

- [ ] **Step 4: Run the final Blender reopen validator.**

```bash
rtk /opt/homebrew/bin/blender -b --python stage_10_product_story/scripts/validate_product_story.py -- --project-root .
```

Expected:

```text
status=PASS
source_part_count=82
source_faces=444296
source_indexed_vertices=221902
animated_story_part_count=22
hidden_part_animation_count=0
warnings=[]
```

- [ ] **Step 5: Report and stop.**

Report the eight still paths, contact sheet, MP4, scene, JSON configs, PDF hash, test count, and geometry regression. State clearly that the output is a review preview and that Task 10 stops before final Cycles/4K, sound, voiceover, PAD/server animation, and later commercial compositing.
