# Task 10-V2 Implementation Plan

## Scope

New derived stage `stage_10V2_product_story/`. Frozen v1 Task 10 outputs stay
read-only. Reuse `stage_10_product_story/scripts/story_data.py` and the
`build_state_transforms` validator from v1; reuse the approved component
layout and texture from `stage_10R_pcb_presentation`.

## Steps

1. **Package + contract tests** (`tests/test_task10v2_story.py`)
   - V2 story config = v1 shots/timing/copy verbatim.
   - State transforms: 22 parts identical to v1, plus `components` section —
     each `PCB_COMP_*` transform = PART_019 transform + manifest
     `board_local_location` (asserted per state).
   - Light rig plan: 3 area lights + world + exposure constants.
   - PART_007 support flags.

2. **`story_v2_data.py`** — builds on `story_data` builders; adds component
   transform builder (pure Python, consumes the approved presentation
   manifest), lighting config, and per-role component materials.

3. **`build_story_scene_v2.py`** — same as v1 build but:
   - writes `stage_10V2_product_story/config/state_transforms.json`
     (v1 transforms + `components` per state),
   - creates `STORY_PCB_PRESENTATION` collection + the 15 component meshes
     (deterministic, from manifest),
   - sets `PART_007` support flags.

4. **`setup_story_presentation_v2.py`** — EEVEE engine, light rig, world,
   exposure; materials identical to v1 plus keyed Principled `Base Color`;
   PART_019 gets the textured soldermask material with a keyed dim color
   multiply; components get per-role keyed materials; same cameras,
   timeline markers, and annotations (emission raised for Eevee).

5. **`apply_story_animation_v2.py`** — same object keyframes as v1 plus one
   keyframe set per component per state (board transform + local offset),
   Bezier/auto-clamped.

6. **`render_product_story_v2.py`** — same 8 still frames + mp4 through
   EEVEE; same `storyboard_inputs` contract; storyboard via PIL.

7. **`validate_product_story_v2.py`** — v1 checks + component coverage,
   component-vs-board transform equality at every keyframe, PART_019 texture
   material present, PART_007 flags, EEVEE engine + lights, annotations only
   in `STORY_ANNOTATIONS`, protocol pending.

8. **`pipeline.py` + `run_task10V2.py`** — v1-stage parity
   (`01_configs → 02_scene → 03_presentation → 04_animation → 05_render →
   06_validate → 07_report`), stage logging, fail-closed gates,
   `data_task10V2_run_result.json`, report.

9. **Run end-to-end**, view renders, report; leave `visual_status` pending
   for human review. Update `.gitignore` for the new stage.

## Reuse map

| Reused from | What |
|---|---|
| `stage_10_product_story` | story shots/copy/cameras/annotations/state offsets via `story_data` + `build_story_scene` functions |
| `stage_10R_pcb_presentation` | `PCB_COMP_*` layout, board-local placements, texture PNG, light-rig parameters, exposure |
| `scripts/pipeline_support.py` | stage logging, runtime recording, report writing |
