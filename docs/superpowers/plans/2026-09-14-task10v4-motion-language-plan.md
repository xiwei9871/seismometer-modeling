# Task 10-V4 Motion Language Implementation Plan

> **For agentic workers:** Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the slideshow-style V2/V3 animation into a minimalist
continuous exploded animation (easing + stagger + two-phase + idle float +
camera drift + hidden context in isolate shots).

**Architecture:** A new pure-Python `motion_timing.py` computes all
keyframe schedules deterministically (arrive windows, hide schedule, idle
offsets, camera drift endpoints). `apply_story_animation_v2.py` rewrites
to key real travel instead of boundary cuts; `setup_story_presentation_
v2.py` gains context-hiding, gradient world, scaled annotations, motion
blur. Solver and validator adapt to hidden context.

**Tech Stack:** Blender 5.2.1 bpy, EEVEE Next, pure-Python timing module,
pytest.

**Spec:** `docs/superpowers/specs/2026-09-14-task10v4-motion-language-design.md`

## Global Constraints

- Source geometry immutable: 82 PARTs / 444296 faces / 221902 verts,
  fingerprint checks must keep passing.
- `state_transforms.json` remains the pose source of truth; V4 only
  changes how poses are reached and what is visible.
- All new pure-Python logic gets pytest coverage first (TDD).
- Frame range stays 1–900 @ 30fps; 9 shots unchanged.

---

### Task 1: `motion_timing.py` — deterministic keyframe schedules

**Files:**
- Create: `stage_10V2_product_story/scripts/motion_timing.py`
- Test: `tests/test_v4_motion_timing.py`

**Interfaces:**
- Consumes: `assign_ranks`, `staggered_window`, `v_dot`, `v_norm`,
  `v_sub`, `v_add`, `v_scale` from `frustum_math.py`;
  `FOCUS_SHOT_POLICY` from `story_v2_data.py`.
- Produces:
  - `MOTION_TIMING: dict` — `arrive_len=36, rank_tolerance_mm=8.0,
    stagger_overlap=0.35, two_phase_gap=12, idle_amplitude_mm=1.5,
    camera_push_fraction=0.10, camera_orbit_deg=7.0`
  - `SHELL_PARTS: frozenset` — `RUGGED_FOCUS` policy parts
  - `arrival_windows(shots, states, movers) -> dict[(shot_idx, part_id), (f_start, f_end)]`
  - `hide_schedule(shots, all_ids) -> dict[id, list[(frame, hidden)]]`
  - `idle_offsets(sign) -> list[float]` (5 values: 0,±A,0,∓A,0)
  - `idle_frames(hold_start, hold_end) -> list[int]` (5 evenly spaced)

- [ ] **Step 1: failing tests**

```python
def test_arrival_windows_stagger_by_rank_and_shell_first():
    # two shell parts + two interior parts exploding +z by different amounts
    # shell windows must start no later than interior windows
def test_hide_schedule_isolate_only():
    # part not in SENSOR focus: hidden on [165,299], visible at 164 & 300
    # PART_003 (subject): never hidden by SENSOR; hidden during PCB_FOCUS
def test_idle_offsets_full_cycle_returns_zero():
    offs = idle_offsets(+1); assert offs[0] == 0 and offs[-1] == 0
def test_reassembled_shell_last():
    # in REASSEMBLED shot, interior part windows precede shell windows
```

- [ ] **Step 2:** run tests → FAIL (module missing)
- [ ] **Step 3:** implement `motion_timing.py`
- [ ] **Step 4:** tests PASS
- [ ] **Step 5:** commit `feat: add V4 motion timing schedules`

### Task 2: camera drift endpoints in `camera_plan.py`

**Files:**
- Modify: `stage_10V2_product_story/scripts/camera_plan.py`
- Test: `tests/test_v4_motion_timing.py` (append)

**Interfaces:**
- Produces: `drifted_pose(record, push_fraction, orbit_deg) ->
  (location_end, target)` — end location = target + Rz(orbit) @
  ((loc−target)·(1−push)). Pure tuple math via `frustum_math`.

- [ ] **Step 1:** test — drifted end is `1−push`× start distance and
  azimuth rotated by `orbit_deg`
- [ ] **Step 2:** FAIL
- [ ] **Step 3:** implement
- [ ] **Step 4:** PASS
- [ ] **Step 5:** commit `feat: camera drift endpoints`

### Task 3: rewrite `apply_story_animation_v2.py`

**Files:**
- Modify: `stage_10V2_product_story/scripts/apply_story_animation_v2.py`

**Core algorithm** (replaces `_key_transforms`):

```python
def _key_part_v4(obj, part_id, state_data, shots, windows):
    obj.animation_data_clear()
    for i, shot in enumerate(shots):
        prev = states[shots[i-1]["state_id"]] if i else states[shot["state_id"]]
        pose = states[shot["state_id"]]["parts"][part_id]
        _insert(obj, prev_pose_for(part_id, prev), shot["frame_start"])
        w = windows.get((i, part_id))
        arrive_end = w[1] if w else shot["frame_start"]
        _insert(obj, pose, arrive_end)
        # idle float during hold
        axis = unit(pose.location - assembled_pose(part_id).location)
        if length(axis) > 0:  # exploded part breathes
            sign = +1 if rank_parity(part_id) else -1
            for f, off in zip(idle_frames(arrive_end, shot["frame_end"]),
                              idle_offsets(sign)):
                if f > arrive_end:
                    _insert(obj, shifted(pose, axis, off), f)
    _set_bezier(obj)
```

Hidden parts animate identically (transforms only). PCB components follow
`PART_019`'s windows (rank of the board). Shot 0 (`ASSEMBLED`) has no
movers → pure hold, no float (parts are at assembled pose).

- [ ] **Step 1:** extend `test_task10v2_story.py` — assert
  `keyframe_count > 2*len(KEYFRAME_STATES)` (arrive+idle keys exist) via
  a scene-inspection note in validator output; plus pure tests for the
  schedule builder used here
- [ ] **Step 2:** FAIL / implement
- [ ] **Step 3:** implement rewrite
- [ ] **Step 4:** pipeline stage runs, validator sees motion (adjacent
  frames differ during hold — checked in Task 6 ocular pass)
- [ ] **Step 5:** commit `feat: continuous motion keyframes`

### Task 4: `setup_story_presentation_v2.py` — hide context, gradient world, annotations, motion blur

**Files:**
- Modify: `stage_10V2_product_story/scripts/setup_story_presentation_v2.py`
- Modify: `stage_10V2_product_story/scripts/story_v2_data.py` (add
  `ANNOTATION_SCALE = 0.45`, `WORLD_GRADIENT` stops)

**Changes:**

```python
def _key_context_visibility(objects, components):
    schedule = hide_schedule(build_story_config()["shots"], all_ids)
    for pid, obj in {**objects, **components}.items():
        for frame, hidden in schedule[pid]:
            obj.hide_render = hidden; obj.hide_viewport = hidden
            obj.keyframe_insert("hide_render", frame=frame)
            obj.keyframe_insert("hide_viewport", frame=frame)
```

- World nodes: `ShaderNodeTexCoord.Normal → SeparateXYZ.Z → MapRange
  (−1..1 → 0..1) → ColorRamp(#262b33, #101216) → Background`.
- `scene.render.use_motion_blur = True` inside `hasattr` guard.
- `layout["font_size_mm"] *= ANNOTATION_SCALE` where annotation layout is
  consumed.

- [ ] **Step 1:** test — hide schedule covers all non-focus ids; gradient
  constants defined; annotation scale applied
- [ ] **Step 2:** FAIL
- [ ] **Step 3:** implement
- [ ] **Step 4:** PASS + stage runs in Blender
- [ ] **Step 5:** commit `feat: isolate context hiding + gradient world`

### Task 5: solver + validator adapt to hidden context

**Files:**
- Modify: `stage_10V2_product_story/scripts/solve_focus_layouts.py`
- Modify: `stage_10V2_product_story/scripts/validate_product_story_v2.py`
- Test: `tests/test_v2_focus_solver.py` (update contract)

- Solver: isolate shots → `context = []`; solve subject framing/scale only
  (minimal travel that keeps subject inside frame margin + height range).
  `layer` shots unchanged.
- Validator: isolate midframe — assert `hide_render` True for every
  non-focus id, subject framed; `layer` keeps depth-aware overlap check.
- [ ] tests updated → FAIL → implement → PASS → commit
  `feat: isolate-aware solver and gate`

### Task 6: end-to-end regenerate + ocular review + commit

- [ ] `pytest -q` green
- [ ] `python run_task10V2.py` (or pipeline.py) → all stages PASS,
  `warnings: []`
- [ ] Ocular: all 8 stills; extract 2 frames inside each focus hold and
  confirm they DIFFER (motion is live); check 04 has zero context.
- [ ] Commit regenerated configs + any code fixes.
