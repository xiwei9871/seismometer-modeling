# Task 10-V4 — Motion Language & Isolate Presentation

Status: approved design (user confirmed direction + three decisions)
Date: 2026-09-14
Stage: `stage_10V2_product_story/` (in-place iteration; V2 assets unapproved)

## Problem

V3 (commit 60b786e) solved *correctness* — projected-silhouette layout,
depth-aware occlusion, fail-closed gate — but the video still reads as a
slideshow: every shot is a static hold tableau with a 1-frame hard cut
between states, a nailed-down camera, dead-still exploded holds, oversized
text overlays, and dimmed-but-visible context parts crowding focus shots
(04_pcb_focus still shows a battery slab and the PART_007 rail touching the
board's left edge).

User-approved direction: **"抖音极简AI" minimalist product-animation style**
— clean gradient studio backdrop, floating subject, generous negative
space, slow continuous camera drift, one subject per shot, soft studio
light, minimal text.

## Approved decisions

1. Style: professional continuous exploded animation (easing + stagger +
   two-phase + camera drift + idle float).
2. Isolate focus shots hide non-focus parts entirely (no ghosting, no
   dimming — actually hidden via `hide_render`/`hide_viewport`).
3. Reference style: 极简AI minimalist product clips; no specific video
   provided — follow researched professional conventions.

## Design

### A. Motion model (replaces hold-tableau keyframes)

Each shot keeps its `[frame_start, frame_end]` span and its target state
in `state_transforms.json` (unchanged source of truth). Inside each shot:

- **Arrive window** `[start, start + arrive_len)`: each part travels from
  its previous state pose to the shot state. Per-part windows stagger by
  rank — the shot's explode axis is `normalize(Σ displacement)` over all
  moving parts; each part's scalar rank key is `dot(displacement, axis)`
  clustered via `assign_ranks(projections, tolerance=8mm)`; rank windows
  come from `staggered_window(rank, n_ranks, start, start+arrive_len,
  overlap=0.35)`.
- **Two-phase rule**: `SHELL_PARTS` = the `RUGGED_FOCUS` policy parts
  (housing class). In explode-direction shots (`PRIMARY_ARCHITECTURE`,
  and the subject's fly-in during isolate shots) shell parts occupy the
  earliest ranks; in `REASSEMBLED` the ordering reverses — interior parts
  return first, shell parts last. In isolate shots context is hidden and
  only the subject moves, so staggering applies within the subject module
  and the two-phase rule is moot.
- **Hold window** `[start + arrive_len, end]`: idle float — each moving
  part gets 5 keys over the hold, offset `sign·A·sin(π·j/2)` (j = 0..4 →
  0, +A, 0, −A, 0) along its unit assembled→shot displacement axis, so the
  pose is exact at both shot boundaries; `sign` alternates by rank parity
  for de-synced bobbing. Parts within 1 mm of their ASSEMBLED pose get no
  float (the device never "breathes" while assembled). Camera drifts for
  the whole shot (below).
- All location keys keep BEZIER AUTO_CLAMPED interpolation (already set).

Timing constants (new `MOTION_TIMING` table in `story_v2_data.py`):
`arrive_len = 36f` (1.2 s), `rank_gap` via `staggered_window(overlap=0.35)`,
`two_phase_gap = 12f` (0.4 s), `IDLE_AMPLITUDE_MM = 1.5`,
`IDLE_KEYS_PER_HOLD = 2` oscillations.

### B. Camera drift (replaces nailed-down cameras)

Per `camera_segments` entry, the active camera gets two keys:

- start: solved camera pose (unchanged `camera_plan.py` output)
- end: pushed toward its target by `CAMERA_PUSH_FRACTION = 0.10` of the
  start distance, plus a lateral orbit of `CAMERA_ORBIT_DEG = 7°` around
  the target's vertical axis. Rotation at the end pose is recomputed with
  the same `to_track_quat('-Z','Y')` convention — no constraints, pure
  keyframes, deterministic.
- Cuts between shots stay (minimalist videos cut between scenes); motion
  inside every shot never stops.

### C. Isolate shots hide context

For each `mode: "isolate"` shot, every part and presentation component NOT
in `policy["parts"]` (+ components when `focus_components`) is keyed
`hide_render/hide_viewport = True` over `[start, end]`, `False` outside —
same pattern as annotation visibility. `RUGGED_FOCUS` (`layer`) is
untouched. Hidden parts still animate their transforms (they reappear in
later shots in the right places).

### D. Presentation changes

- World: flat color → node gradient (TexCoord Normal → SeparateXYZ Z →
  ColorRamp `#262b33 → #101216`) — vertical falloff studio backdrop.
- Motion blur: `scene.render.use_motion_blur = True` if the engine honors
  it (EEVEE Next 5.2); skipped gracefully if the attribute is absent.
- Annotations: `ANNOTATION_SCALE = 0.45` multiplier on
  `annotation_screen_layout` font size; same positions, single-shot
  visibility unchanged.
- Lighting rig, exposure 1.7, soldermask texture, component materials:
  unchanged.

### E. Solver & gate adapt to hidden context

- `solve_focus_layouts.py`: for isolate shots the context set is empty
  (all context hidden during the shot) — solving reduces to subject
  framing/scale; the solved travel still decides the fly-in direction.
- `validate_product_story_v2.py` occlusion gate: isolate shots assert
  (a) every non-focus part/component reports `hide_render == True` at
  shot midframe, (b) subject hull inside frame with margin, (c) subject
  height within `[FOCUS_MIN_HEIGHT_NDC, FOCUS_MAX_HEIGHT_NDC]`.
  `layer` shots keep the existing depth-aware overlap check.

## Non-goals

- No source-geometry changes (82 PARTs / fingerprints invariant).
- No state semantics changes — `state_transforms.json` stays the pose
  truth; V4 only changes *how* poses are reached and what is visible.
- No new shots, no duration change (900f / 30 s / 30 fps).
- No literal code copied from the GPL plugin — clean-room math only.

## Verification

- `pytest -q` — new pure-Python tests: `motion_timing` window builder,
  hide schedule builder, camera drift endpoints, solver contract updates.
- Pipeline end-to-end: solve → animate → present → render → validate,
  `technical_status = PASS`, warnings `[]`.
- Ocular review: all 8 stills + 5 mid-shot mp4 frames — continuous motion
  verified by diffing adjacent frames inside a hold (parts/camera move).
- Human approval: unchanged mechanism (`config/human_approval.json`).
