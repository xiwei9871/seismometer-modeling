# Research: How Others Build Exploded-View Product Animations

Date: 2026-09-14
Context: Task 10-V2 surfaced a class of defects (focus-subject occlusion, weak
framing) that hand-tuned transform JSONs could not prevent. This note surveys
how established tools and studios solve the same problems, and what to borrow
without giving up determinism or source-geometry immutability.

## 1. The closest prior art: ehsun-sh/blender-exploded-assembly-studio

GPL-2.0 Blender add-on, ~2100 lines of plain `bpy` Python, tested on Blender
5.1.2 (we run 5.2.1). Built for exactly our case: PCBs, enclosures, layered
mechanical products. Repo cloned for study only — do NOT copy code into this
repo (GPL-2.0). The algorithms below are short enough to reimplement cleanly.

Design contract (same as ours):
- Assembled state is ground truth, stored per-object; explode/assemble are
  computed from it and restore exactly. Only transforms + keyframes are
  written. Never meshes, materials, origins.

Algorithms worth borrowing:

### a) Layered ranking (`_assign_ranks`)
Parts are projected onto the explosion axis and clustered into ranks with a
tolerance band (`assembly_radius * layer_tolerance`). All parts in a band share
one rank and lift as a sheet — prevents the staircase scatter our per-part
offsets produce. `distance = base * rank`.

### b) Frustum clearance (`offscreen_distance`, camera.py)
The fix for our occlusion defect class. Camera frustum = 4 planes in camera
space. For each part, solve analytically (one linear equation per plane, no
search) how far along its explosion direction it must travel to leave the
frame. Push parts out until `offset >= needed`. ~30 lines of plane algebra.

### c) Enclosure/camera avoidance (`choose_entry_side`, `apply_enclosure_camera_rules`)
Shell panels pick the entry side that faces AWAY from the camera, evaluated at
the worst camera position over the whole shot — directly prevents "context
part intrudes into frame". If the natural side can never clear the frustum,
walk candidate sides by descending alignment and take the first that clears.

### d) Subject-fit framing (`framing_distance`)
`d = radius * margin / sin(fov/2)` — put the focus subject at a fixed screen
size instead of hand-aiming cameras. Fixes the 10R "subject too small" issue.

### e) Two-phase timing + stagger (`build_timing`, `_staggered`)
Enclosure opens first, then parts, with an explicit gap so the shell never
moves while parts land. Stagger window formula:
`segment = span / (count - (count-1) * overlap)` — one window per GROUP, so a
5-piece component takes one stagger slot, not five.

### f) Camera rig
Empty pivot + camera parented at local offset; orbit = one rotation channel =
perfect circle. Framing measures the subject's ASSEMBLED bounds so a flying
part never breaks the frame.

## 2. Commercial / other Blender tools

- **Smart Explode** (Gumroad): procedural slider 0→1 per collection system;
  proximity/cascade ("wave") triggering; IDLE MOTION — subtle float/rotation on
  exploded parts that fades in/out. The float is the "premium" feel our static
  exploded hold lacks. Bakes to plain keyframes for render farms.
- **Xplod** (Superhive): Geometry-Nodes, non-destructive; 6 modes incl.
  surface-normal explosion (parts fly along their own face normal — good for
  radial enclosures).
- **AssemblMe** (bblanimation): build-up animations, step/layer ordering,
  curve-follow paths.

## 3. DCC / CAD practice (SolidWorks, KeyShot, Fusion 360, Visualize)

- Exploded view = ORDERED explode steps stored on the config; the Animation
  Wizard just converts steps to keyframes. Our `state_transforms.json` as
  pure-data steps is the same architecture — keep it.
- Rule repeated everywhere: GROUP FIRST. Parts that move together are grouped
  before animating (our FUNCTIONAL_MODULES = their groups; drive sequencing by
  module, not by part).
- "Assembly by disassembly": explode order = reverse of real assembly order;
  top/fasteners leave first, chassis last.
- Production house notes (xo3d): hero explode 6–15 s; timing is a craft pass;
  block the explode in a low-res playblast before rendering; cameras FOLLOW
  the explode; final render adds motion blur + depth of field.

## 4. Academic baseline

Li et al. 2008 (Automated Generation of Interactive 3D Exploded View
Diagrams): build an explosion graph by iteratively removing the part with the
smallest escape distance among unblocked parts; respects blocking constraints
and part hierarchies. Overkill for 22 parts but explains why fully automatic
direction-finding needs blocking analysis — our per-state overrides are a
legitimate manual substitute at this scale.

## 5. Agent-side tooling

- Blender MCP servers exist (RFingAdam/mcp-blender: 218 tools; PatrykIti/
  blender-ai-mcp: goal-first routing + deterministic inspection). A live MCP
  session would let the agent run render → inspect → refine loops and catch
  occlusion BEFORE handing renders to the user. Worth evaluating as a dev-time
  QA tool only — pipeline stays headless/deterministic.
- AI image/video-gen exploded views (Nano Banana + Kling first/last-frame):
  hallucinate geometry, violate traceability — explicitly NOT applicable.

## 6. Why their results read better — root causes of our defects

| Defect we shipped | Their mechanism that prevents it |
|---|---|
| Focus subject occluded by context parts | `offscreen_distance` + enclosure-camera rules — frustum clearance computed, not eyeballed |
| Subject small / excess margin (10R) | `framing_distance` — camera distance derived from subject bounds |
| Per-part staircase scatter | `_assign_ranks` layered clustering |
| Context competes during focus shots | two-phase timing: shell/context fully clears before parts move; group-level stagger |
| Static exploded hold feels dead | idle float micro-motion (Smart Explode) |
| Flat "diagram" look | motion blur + DOF + studio light rig (we have the rig; not blur/DOF) |

## 7. Proposed adoption into this pipeline (determinism preserved)

1. **Occlusion gate (highest value, fail-closed)**: port the frustum math —
   for each focus shot, compute each non-focus part's required clearance along
   its offset direction; assert in `validate_product_story_v2.py` that no
   non-focus part's screen-space bounds intersect the focus subject's. Turns
   yesterday's human-caught bug into a machine check.
2. **Camera auto-fit**: derive per-shot camera distance from focus-module
   bounds via `framing_distance`, keep hand-aimed angles as overrides.
3. **Layered explosion**: replace hand-written per-part explode offsets with
   axis-split + rank clustering; compute once, freeze into
   `state_transforms.json` (determinism kept — JSON remains source of truth).
4. **Two-phase + group stagger**: enclosure parts always precede internals;
   stagger by module group.
5. **Idle float**: subtle sinusoidal drift on exploded parts during hold
   states (presentation-only, keyframed, deterministic).
6. Optional: motion blur + DOF for the hero shot; Blender MCP dev-loop for
   self-review of renders.

## 8. License note

blender-exploded-assembly-studio is GPL-2.0 — reference algorithms only, clean
reimplementation, no copied code in this repo. Smart Explode / Xplod are paid;
buy only if we want the addon itself, not needed for the math.
