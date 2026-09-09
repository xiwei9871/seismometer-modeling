# Task 9C Refined Exploded Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate a more open Z-axis exploded layout and a review-only Blender animation preview from the frozen R1 scene.

**Architecture:** A pure Python planner derives refined transforms, group membership, and timing from R1 JSON. A Blender script opens the R1 scene and applies only the new transforms, then a separate animation script adds keyframes to the Task 9C copy. Render and validation scripts are independent; the pipeline writes all configs/reports and reopens the final scene for factual checks.

**Tech Stack:** Python, pytest, Blender 5.2.1 CLI, bpy, numpy-free bbox math, FFmpeg through Blender's FFMPEG video output.

---

### Task 1: Add failing Task 9C contracts

**Files:**
- Create: `tests/test_task09c_refined_explosion.py`
- Create: `tests/test_run_task09c.py`

- [ ] **Step 1: Write failing tests**

Cover the exact contract: 22 visible IDs, 60 hidden IDs, all 82 source IDs, refined Z separations greater than R1 for the main stack and PCB layer, leveling XY preservation, no hidden-part animation membership, 30 fps, 15–22 seconds, no bounce policy, stable output names, and fail-closed validation when actual scene facts are missing.

- [ ] **Step 2: Run focused tests**

Run: `rtk .worktrees/stage01/.venv/bin/pytest -q tests/test_task09c_refined_explosion.py tests/test_run_task09c.py`

Expected: FAIL because the Task 9C modules and runner do not yet exist.

### Task 2: Implement the pure refined layout planner

**Files:**
- Create: `stage_09C_refined_explosion/__init__.py`
- Create: `stage_09C_refined_explosion/scripts/__init__.py`
- Create: `stage_09C_refined_explosion/scripts/build_refined_layout.py`
- Modify: `tests/test_task09c_refined_explosion.py`

- [ ] **Step 1: Implement deterministic layout generation**

Read R1 layout and `assembly_initial.json`, preserve the exact 82-part ordering, derive main-stack Z gaps from bbox heights, add configurable PCB/sensor/battery local spacing factors, preserve leveling X/Y, and write `config/refined_layout.json` without touching R1.

- [ ] **Step 2: Run focused tests**

Run: `rtk .worktrees/stage01/.venv/bin/pytest -q tests/test_task09c_refined_explosion.py`

Expected: PASS for pure layout and policy contracts.

### Task 3: Add Blender static scene builder

**Files:**
- Create: `stage_09C_refined_explosion/scripts/build_refined_scene.py`
- Modify: `tests/test_task09c_refined_explosion.py`

- [ ] **Step 1: Implement scene-copy builder**

Open `stage_09A_R1_exploded_rework/scene/exploded_layout_v2.blend`, validate its 82 source meshes and frozen totals, apply refined locations only to visible parts, keep hidden parts hidden, create the four presentation/detail cameras, and save only `stage_09C_refined_explosion/scene/exploded_animation_preview.blend` before keyframes.

- [ ] **Step 2: Run Blender static build**

Run: `rtk /opt/homebrew/bin/blender -b --python stage_09C_refined_explosion/scripts/build_refined_scene.py -- --project-root /Users/xiwei/modeling`

Expected: exit 0 and a non-empty Task 9C blend with zero animation data at this intermediate step.

### Task 4: Add animation plan and keyframe builder

**Files:**
- Create: `stage_09C_refined_explosion/scripts/build_animation_preview.py`
- Modify: `tests/test_task09c_refined_explosion.py`

- [ ] **Step 1: Implement timing and keyframes**

Use 30 fps and 540 frames (18 seconds): frames 1–60 assembled hold, 61–210 primary Z stack, 181–330 PCB/sensor local expansion, 301–420 battery and leveling refinement, 421–480 full exploded settle, and 481–540 hold. Insert location/rotation keyframes only on the 22 visible source objects. Set Bezier interpolation with automatic handles and no extrapolation. Save the same Task 9C blend after keyframes.

- [ ] **Step 2: Re-open and validate animation facts**

Run: `rtk /opt/homebrew/bin/blender -b --python stage_09C_refined_explosion/scripts/build_animation_preview.py -- --project-root /Users/xiwei/modeling`

Expected: exit 0, frame range 1–540, 22 animated visible parts, no hidden-part animation, and frame 1 transforms equal the assembled positions.

### Task 5: Render refined stills, MP4, and contact sheet

**Files:**
- Create: `stage_09C_refined_explosion/scripts/render_refined_outputs.py`
- Create: `stage_09C_refined_explosion/scripts/compose_keyframes_contact_sheet.py`
- Modify: `tests/test_run_task09c.py`

- [ ] **Step 1: Implement deterministic render settings**

Use the current tilted 3/4 engineering camera, neutral workbench presentation, 1200×900 stills, and a review MP4 at 600×450/30 fps. Render the hero and engineering views at the refined exploded state, crop/detail via camera targets without changing objects, render the MP4 from frame 1–540, and compose frames 1/120/240/360/480/540 into `exploded_keyframes_contact_sheet.png`.

- [ ] **Step 2: Run render command**

Run: `rtk /opt/homebrew/bin/blender -b --python stage_09C_refined_explosion/scripts/render_refined_outputs.py -- --project-root /Users/xiwei/modeling`

Expected: all seven requested output names exist and are non-empty.

### Task 6: Add factual Blender validation and pipeline runner

**Files:**
- Create: `stage_09C_refined_explosion/scripts/validate_refined_scene.py`
- Create: `stage_09C_refined_explosion/scripts/pipeline.py`
- Create: `run_task09c.py`
- Modify: `tests/test_run_task09c.py`

- [ ] **Step 1: Implement fail-closed validation**

Re-open the generated blend, count actual source meshes/faces/vertices, compare visible IDs, count animated source objects, verify frame 1 assembled transforms and frame 540 refined transforms, check output files, and return `PASS` only when every required file and invariant is valid.

- [ ] **Step 2: Implement one-command runner**

Run pure planner, static builder, animation builder, render, contact sheet, Blender validation, JSON configs, Markdown report, and log in that order. Never overwrite R1/Stage01/Stage02.

- [ ] **Step 3: Run focused tests**

Run: `rtk .worktrees/stage01/.venv/bin/pytest -q tests/test_task09c_refined_explosion.py tests/test_run_task09c.py`

Expected: PASS.

### Task 7: Full verification and final review package

**Files:**
- Modify: `stage_09C_refined_explosion/reports/task09c_report.md`
- Modify: `stage_09C_refined_explosion/config/validation.json`

- [ ] **Step 1: Run complete pipeline twice**

Run: `rtk .worktrees/stage01/.venv/bin/python run_task09c.py` twice and compare refined layout/animation-plan/config hashes.

Expected: both runs return `status=PASS` and deterministic config hashes match.

- [ ] **Step 2: Run full regression suite**

Run: `rtk .worktrees/stage01/.venv/bin/pytest -q`

Expected: all existing and new tests pass.

- [ ] **Step 3: Verify frozen assets**

Run: `rtk sha256sum output/stage01_split.blend output/stage02_semantic.blend output/stage03_presentation_exploded_v4.blend`; verify the known hashes remain unchanged and verify the source STL hash from the R1 baseline.

- [ ] **Step 4: Inspect images and stop**

Open `exploded_hero_refined.png`, `exploded_engineering_refined.png`, `pcb_detail_refined.png`, `sensor_detail_refined.png`, and the animation contact sheet. Report visual review points and stop before final commercial rendering or another task.
