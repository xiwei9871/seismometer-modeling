# Plan: Task 10-V3 Frustum-Aware Layout & Occlusion Gate

Spec: docs/superpowers/specs/2026-09-14-task10v3-frustum-layout-design.md

## Step 1 — `frustum_math.py` (pure Python) + tests

New file `stage_10V2_product_story/scripts/frustum_math.py`. Tuple-based vec3
math; no bpy/mathutils so plain pytest covers it.

Functions (per spec §A). Key derivations:

- camera basis: `back = norm(loc - target)`, `right = norm(up × back)`,
  `cam_up = back × right`. Point → camera space via dot products.
- `fov_x = 2·atan(sensor/(2·lens))`; `fov_y = 2·atan(tan(fov_x/2)/aspect)`.
- planes (camera space, looking -Z): right `(-cos hx,0,-sin hx)`,
  left `(cos hx,0,-sin hx)`, top `(0,-cos hy,-sin hy)`, bottom `(0,cos hy,-sin hy)`.
- `offscreen_distance`: per plane, `o(t)=n·p + t·(n·d)`; exits at
  `t=(-r·m - o)/(n·d)` for `n·d<0`; need `min` over planes = first exit.
  Already outside → 0. No exiting plane → None.
- `screen_disc`: angular center `acos(dir·fwd)`, angular radius `asin(r/|p|)`
  (clamp |p|>r).
- `clear_subject_distance`: t-scan 64 steps on `[0, t_off]`; predicate = disc
  separation ≥ sum angular radii + margin, OR context out of frustum; bisect
  first passing bracket.
- `framing_distance(radius, fov_y, fraction)` = `radius / (sin(fov_y/2)·fraction)`.
- `assign_ranks`: sort projections, split on gap > tolerance, index clusters.
- `staggered_window(i,n,lo,hi,overlap)`: `seg=span/(n-(n-1)·ov)`; window
  `[lo+i·seg·(1-ov), +seg]`.
- `choose_entry_side(natural, to_cam)`: keep natural unless its side vector
  points too much at camera (> CAMERA_FACING_LIMIT); else pick candidate side
  facing away, nearest to natural.

Tests `tests/test_v2_frustum_math.py`: known-geometry cases — point ahead of
camera, disc angles, offscreen on each axis, rank clustering, stagger windows,
entry-side choice, determinism (same inputs → identical outputs).

## Step 2 — focus layout solver (`focus_layout.py`)

`solve_focus_layout(state_transforms, layout, camera_fn, focus_part_ids,
direction, base_offsets)` → `{part_id: offset}`; grid+bisect on common
translation `t·d`; camera_fn maps subject centroid → camera record (so the
gate evaluates the rendered camera, decoupled from setup).

`story_v2_data.py`: replace `PCB_FOCUS_V2_OFFSETS`/`SENSOR_FOCUS_V2_OFFSETS`
constants with solver output at build time (still frozen to JSON — determinism
kept). Keep constants' *directions* as solver inputs.

## Step 3 — camera auto-fit

`_build_camera_config`: sensor/pcb distances via `framing_distance` at
`FOCUS_SCREEN_FRACTION=0.45` from the focus module's bounding-sphere radius in
that state. Hero unchanged.

## Step 4 — occlusion gate in validator

`validate_product_story_v2.py` gains `_occlusion_report(state_data, camera_cfg,
layout)` per spec §D; warnings `FOCUS_OCCLUSION`, `FOCUS_SUBJECT_OFFFRAME`,
`FOCUS_SUBJECT_SCALE`; report included in pipeline JSON.

## Step 5 — stagger + idle float

`apply_story_animation_v2.py`: explode transition windows per module rank;
focus-hold idle float ±1.5 mm via 2 extra keys per hold. Off by config flags
default on for V3 behavior inside V2 package (still `stage_10V2_*` — iteration
in place while V2 is unapproved).

## Step 6 — regenerate + render + verify + commit

pipeline → stills → contact sheet → MP4 → validation (occlusion gate green) →
ocular check → commit. Human approval unchanged (still required).
