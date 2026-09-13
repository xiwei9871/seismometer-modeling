# Task 10-R-PCB-V1 Presentation PCB Implementation Plan

**Goal:** Build `MAIN_PCB_PRESENTATION` (PART_019 + 15 generated presentation
components + soldermask detail texture), demote PART_007 to SUPPORT, and emit
four review images plus a validated `.blend`, then stop for human review.

**Architecture:** A pure-Python planner writes manifest/material/camera JSON
and a deterministic PIL surface-detail texture. One Blender script builds the
derived scene from the frozen Stage 9C file, one renders clean/top/context
stills with Eevee, one PIL script composes the reference comparison, and a
Blender validator checks the frozen baseline and policies fail-closed.

**Tech Stack:** Python, pytest, Pillow, Blender 5.2.1 `bpy` (`BLENDER_EEVEE`).

---

### Task 1: Contract tests and package skeleton

**Files:**
- Create: `stage_10R_pcb_presentation/__init__.py`
- Create: `stage_10R_pcb_presentation/scripts/__init__.py`
- Create: `stage_10R_pcb_presentation/scripts/pcb_presentation_data.py`
- Create: `tests/test_task10r_pcb_presentation.py`

- [ ] **Step 1:** Write failing tests: 15-component contract, octagon
  keep-out with 8 mm margin (|x|<=43, |y|<=43, |x|+|y|<=62), pairwise AABB
  non-overlap, PART_007 demotion fields, 75/15/10 weights, frozen baseline
  constants, required output names, status contract REVIEW_REQUIRED.
- [ ] **Step 2:** Verify tests fail (package missing).
- [ ] **Step 3:** Implement `pcb_presentation_data.py` contract builders.
- [ ] **Step 4:** Verify tests pass. **Step 5:** Commit.

### Task 2: Planner, materials config, surface texture

**Files:**
- Create: `stage_10R_pcb_presentation/scripts/build_presentation_plan.py`
- Create: `stage_10R_pcb_presentation/scripts/generate_surface_texture.py`
- Modify: `tests/test_task10r_pcb_presentation.py`

- [ ] **Step 1:** Failing tests: planner reads `refined_layout.json` assembled
  transforms; board placed at +175 mm X inspection zone at assembled Z;
  component world positions = board zone centre + board-local offsets;
  texture generation deterministic (same bytes on regenerate).
- [ ] **Step 2:** Implement planner writing
  `config/pcb_presentation_manifest.json`,
  `config/pcb_presentation_materials.json`,
  `config/pcb_presentation_cameras.json`.
- [ ] **Step 3:** Implement `generate_surface_texture.py` (1024 px PIL:
  soldermask base, Manhattan traces, pads/vias, silkscreen marks, plain
  border) writing `assets/pcb_surface_detail.png`.
- [ ] **Step 4:** Run tests, generate configs + texture. **Step 5:** Commit.

### Task 3: Blender scene builder

**Files:**
- Create: `stage_10R_pcb_presentation/scripts/build_presentation_scene.py`
- Modify: `tests/test_task10r_pcb_presentation.py`

- [ ] **Step 1:** Failing tests for the scene contract (single blend, 82
  source parts, 15 PCB_COMP objects, no animation, no FONT, collections
  HERO/SECONDARY/SUPPORT/CONTEXT/SOURCE_HIDDEN/CAMERAS/LIGHTS).
- [ ] **Step 2:** Implement builder: verify 9C SHA256, strip non-source
  objects, apply zone transforms, copy mesh data for visible story parts,
  create beveled boxes/cylinders for the 15 components, raycast each
  footprint onto PART_019 (fail closed), assign node materials incl. the
  Generated-coords image texture on PART_019, create cameras and the light
  rig, save `scene/pcb_presentation_assembly.blend`, reopen and verify.
- [ ] **Step 3:** Run headless build. **Step 4:** Commit.

### Task 4: Renders and reference comparison

**Files:**
- Create: `stage_10R_pcb_presentation/scripts/render_presentation.py`
- Create: `stage_10R_pcb_presentation/scripts/compose_reference_comparison.py`
- Modify: `tests/test_task10r_pcb_presentation.py`

- [ ] **Step 1:** Failing tests for required render names and the comparison
  sheet contract.
- [ ] **Step 2:** Implement Eevee 1920x1080 renders: clean (HERO only), top
  (HERO only, top-down), context (all context collections, weighted).
- [ ] **Step 3:** Implement comparison: clean render | REF_PCB_002 side by
  side with GENERATED / REFERENCE captions.
- [ ] **Step 4:** Run renders. **Step 5:** Commit.

### Task 5: Validator, pipeline, entry point, report

**Files:**
- Create: `stage_10R_pcb_presentation/scripts/validate_presentation.py`
- Create: `stage_10R_pcb_presentation/scripts/pipeline.py`
- Create: `run_task10R_pcb.py`
- Modify: `tests/test_task10r_pcb_presentation.py`

- [ ] **Step 1:** Failing tests for fail-closed prerequisite (Task 9C PASS),
  technical PASS vs PENDING_HUMAN_REVIEW, report contents.
- [ ] **Step 2:** Implement validator (baseline, fingerprints, visibility,
  animation/font absence, manifest coverage, footprint raycast results,
  allowed object types MESH/CAMERA/LIGHT).
- [ ] **Step 3:** Implement `pipeline.py` and `run_task10R_pcb.py`; write
  `reports/task10R_pcb_visual_review.md` with explicit review questions.
- [ ] **Step 4:** Run end to end; run full test suite; inspect renders.
- [ ] **Step 5:** Commit code/config/report; leave user assets untouched.

### Task 6: Final verification and handoff

- [ ] Reopen the blend: no animation, no FONT, 82 source parts, 15 comps.
- [ ] Verify source STL and Stage 9C SHA256 unchanged.
- [ ] Verify PNGs are 1920x1080; comparison sheet has both panels.
- [ ] Report `technical_status=PASS`, `visual_status=PENDING_HUMAN_REVIEW`,
  `overall_status=REVIEW_REQUIRED`; stop before any animation work.
