# Task 10-R Functional Inspection State Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build four independent, subtitle-free functional inspection states that make the primary architecture, sensor assembly, PCB hierarchy, and six-cell power system visually readable before any new animation work.

**Architecture:** A pure-Python planner reads only the frozen Stage 9C assembled layout and writes deterministic module/state/camera/validation JSON. Blender scripts build four derived no-keyframe scenes from the Stage 9C scene, apply state transforms and presentation materials, render clean/context/top images, and a final validator reports technical integrity separately from the pending human visual review.

**Tech Stack:** Python, pytest, Blender 5.2.1 `bpy`, NumPy-free projected-bounds diagnostics, PNG rendering, Pillow contact-sheet composition.

---

### Task 1: Establish the Task 10-R contract tests and package skeleton

**Files:**
- Create: `stage_10R_functional_inspection/__init__.py`
- Create: `stage_10R_functional_inspection/scripts/__init__.py`
- Create: `stage_10R_functional_inspection/scripts/inspection_data.py`
- Create: `tests/test_task10r_inspection.py`

- [ ] **Step 1: Write failing tests** for the four state IDs, exact macro-module coverage, subtitle-free policy, 82/444296/221902 baseline, no-animation policy, and `visual_status=PENDING_HUMAN_REVIEW`.
- [ ] **Step 2: Run the focused tests and verify they fail** because the new package does not exist.
- [ ] **Step 3: Implement the pure contract builders** for module groups, state metadata, material roles, and visibility policy.
- [ ] **Step 4: Run the focused tests and confirm they pass.**
- [ ] **Step 5: Commit the contract unit.**

### Task 2: Build independent state transforms and screen-space diagnostics

**Files:**
- Create: `stage_10R_functional_inspection/scripts/build_inspection_plan.py`
- Modify: `stage_10R_functional_inspection/scripts/inspection_data.py`
- Modify: `tests/test_task10r_inspection.py`

- [ ] **Step 1: Write failing tests** proving the planner reads assembled transforms from `stage_09C_refined_explosion/config/refined_layout.json`, does not read Task 10 state transforms, covers only PART_001..PART_022 as visible story geometry, and gives each state an independent camera/transform plan.
- [ ] **Step 2: Run the tests and verify the new planner API fails.**
- [ ] **Step 3: Implement deterministic transforms:** a separated four-layer Z stack for Primary; a dedicated lateral sensor inspection zone with explicit X/Y/Z local offsets; a PCB plate/board/frame stack with visible board top; and a compact 3x2 battery array near the electronics context.
- [ ] **Step 4: Implement diagnostic projected bounds/occupancy/overlap calculations** using recorded orthographic camera basis vectors, without claiming those diagnostics equal human visual approval.
- [ ] **Step 5: Run focused tests and confirm they pass.**
- [ ] **Step 6: Generate `config/module_groups.json`, `inspection_states.json`, `inspection_cameras.json`, and `visual_validation.json`.**
- [ ] **Step 7: Commit the planner unit.**

### Task 3: Build four independent no-keyframe Blender scenes

**Files:**
- Create: `stage_10R_functional_inspection/scripts/build_inspection_scenes.py`
- Modify: `tests/test_task10r_inspection.py`

- [ ] **Step 1: Write failing tests** for four separate scene paths, 82 source objects per scene, hidden small/fragment policy, no animation data, geometry fingerprints, no FONT objects, and no mutation of Stage 9C.
- [ ] **Step 2: Run tests and verify the Blender integration contract is initially absent.**
- [ ] **Step 3: Implement a Blender builder** that opens the frozen Stage 9C scene for each state, clears inherited animation in the derived copy, preserves all source PARTs, hides PART_023..PART_082, applies only the Task 10-R JSON transforms, creates separate state scenes, and saves them without overwriting any earlier stage.
- [ ] **Step 4: Apply presentation-only materials and context weighting** through copied mesh datablocks or other non-destructive presentation data; never edit source vertices, polygons, or topology.
- [ ] **Step 5: Run Blender headless scene builds and reopen each file for factual validation.**
- [ ] **Step 6: Commit the scene-builder unit.**

### Task 4: Render clean/context/top inspection images and contact sheet

**Files:**
- Create: `stage_10R_functional_inspection/scripts/render_inspection_states.py`
- Create: `stage_10R_functional_inspection/scripts/compose_inspection_contact_sheet.py`
- Modify: `tests/test_task10r_inspection.py`

- [ ] **Step 1: Write failing tests** for required render names, clean images containing no text objects, per-state independent cameras, and one four-panel contact sheet.
- [ ] **Step 2: Run tests and verify the renderer contract fails.**
- [ ] **Step 3: Implement deterministic Workbench preview renders** at 1920x1080 for all required clean/context/top images, using no annotation objects and separate cameras per state.
- [ ] **Step 4: Compose the four primary clean images into `task10R_contact_sheet.png`.**
- [ ] **Step 5: Run image existence and dimension tests.**
- [ ] **Step 6: Commit the render unit.**

### Task 5: Validate, report, and expose the fail-closed entrypoint

**Files:**
- Create: `stage_10R_functional_inspection/scripts/validate_inspection.py`
- Create: `stage_10R_functional_inspection/scripts/pipeline.py`
- Create: `run_task10R.py`
- Create: `stage_10R_functional_inspection/reports/task10R_visual_review.md`
- Create: `.gitignore` entry for Task 10-R generated binaries if needed
- Modify: `tests/test_task10r_inspection.py`

- [ ] **Step 1: Write failing tests** for fail-closed input verification, technical PASS versus pending visual review, report contents, and immutable Stage 9C hash checks.
- [ ] **Step 2: Run tests and verify they fail.**
- [ ] **Step 3: Implement the pipeline**: verify the frozen Stage 9C prerequisite, build configs, build four scenes, render outputs, compose contact sheet, run validation, and set `overall_status=REVIEW_REQUIRED` until human approval.
- [ ] **Step 4: Implement the factual report** with occupancy/overlap diagnostics, scene/render paths, source baseline, and explicit visual review questions.
- [ ] **Step 5: Run Task 10-R end to end.**
- [ ] **Step 6: Run the complete repository test suite and inspect the four clean images/contact sheet.**
- [ ] **Step 7: Commit the code/config/report unit, leaving user-owned reference images, PDF, and top-level `output/` untouched.**

### Task 6: Final verification and handoff

- [ ] **Step 1:** Reopen all four `.blend` files with Blender 5.2.1 and verify no animation data, no text, 82 source parts, and frozen totals.
- [ ] **Step 2:** Verify source STL and Stage 9C SHA256 values.
- [ ] **Step 3:** Verify all required PNGs are 1920x1080 and the contact sheet contains exactly four primary images.
- [ ] **Step 4:** Verify `technical_status=PASS`, `visual_status=PENDING_HUMAN_REVIEW`, and `overall_status=REVIEW_REQUIRED`.
- [ ] **Step 5:** Report the required nine visual review answers and stop before Communication/Rugged/annotations/timeline animation.
