# Task 10-R-PCB-V1 Presentation PCB Reconstruction & Reclassification

## Goal

Build a product-presentation PCB layer (`MAIN_PCB_PRESENTATION`) on top of the
frozen source `PART_019` board, using the user-supplied reference images as the
visual model. Demote `PART_007` from PCB hero to support role. Static review
assets only; no animation.

## Status

Task definition supplied by the user on 2026-09-13. Task 10-R visual review
was approved by the user on 2026-09-13; the PCB inspection state is superseded
by this task's presentation layer.

## Frozen inputs and source traceability

- Source scene: `stage_09C_refined_explosion/scene/exploded_animation_preview.blend`
  (SHA256 `a3b5359861877e247ad1b035b00cace3e29eea2789ac227e6eeddfaaba1a7766`)
- Frozen baseline: 82 source PART objects, 444296 faces, 221902 indexed vertices.
- `PART_006` PCB_PROTECTIVE_PLATE, `PART_007` PCB_SUPPORT_FRAME, `PART_019`
  MAIN_PCB remain unmodified source meshes. No remesh, decimate, boolean,
  topology edit, delete, or join on source geometry.
- Reference images (read-only, user supplied):
  - `references/pcb/REF_PCB_002.png` — primary layout reference: overall board
    outline, major device distribution, long connectors, component density.
  - `references/pcb/REF_PCB_001.png` / `REF_PCB_003.png` — detail supplements:
    large-device height relations, trace/pad surface feel, local volume.
  - References are visual models, not pixel-accurate targets.

## PART_007 reclassification

Recorded in the presentation manifest:

```text
PART_007  semantic_name            = PCB_CONNECTING_FRAME (support frame)
          functional_importance    = LOW
          presentation_priority    = SUPPORT
          independent_focus        = false
          follow_parent            = PCB_ASSEMBLY
          presentation_weight      = 0.10
```

`PART_007` is no longer a PCB focus subject. It is hidden in the clean and top
renders and kept only as a weak engineering-context object in the context view.
`PART_006` keeps `SECONDARY` status at weight 0.15 and appears only in the
context view beneath the board. `MAIN_PCB_PRESENTATION` carries weight 0.75.

## Presentation layer

`MAIN_PCB_PRESENTATION` is the assembly of:

- the untouched `PART_019` board mesh with a presentation PCB material, plus
- fifteen generated presentation components (`PCB_COMP_*`), simple beveled
  boxes and cylinders placed on the board top surface.

Presentation objects are new mesh objects with
`source = "photographic_presentation_reconstruction"`. They never touch source
geometry and are recorded separately in the manifest.

### Component plan

Component placement uses a board-local frame: origin at the board centroid,
X/Y in millimetres, octagon keep-out derived from the real PART_019 outline
(|x| <= 51, |y| <= 51, |x|+|y| <= 70.05) with an 8 mm safety margin and a
4x6-edge serration allowance on the chamfered edges.

| id | shape | centre (mm) | size (mm) | height | role |
|---|---|---|---|---|---|
| CONN_MAIN | bevel box | (0, -35) | 44 x 8 | 7 | long edge connector |
| CONN_TOP | bevel box | (-4, 33) | 30 x 7 | 5 | top connector |
| SHIELD_MAIN | bevel box | (13, -3) | 30 x 30 | 9 | dominant shield can |
| SHIELD_LEFT | bevel box | (-26, 6) | 18 x 15 | 7 | secondary shield |
| MODULE_RT | bevel box | (23, 23) | 18 x 13 | 7 | right-top module |
| MODULE_LB | bevel box | (-26, -22) | 16 x 10 | 6 | left-bottom module |
| CAP_L1 / CAP_L2 | cylinder r4 | (-39, -6) / (-39, 14) | h 11 | tall caps |
| CAP_R1 / CAP_R2 | cylinder r4 | (38, -8) / (38, 8) | h 11 | tall caps |
| IC_B1..B3 | bevel box | (-12/-1/10, -23.5) | 9 x 6 | 2.5 | bottom IC row |
| IC_T1 / IC_T2 | bevel box | (-8, 16) / (2, 22) | 8 x 6 | 2.5 | top IC pair |

Every component footprint is validated twice: by the pure-Python planner
against the octagon keep-out plus pairwise AABB overlap, and by the Blender
builder via downward raycast of footprint corners and centre onto PART_019.
Any miss fails the build closed.

### Board surface detail

`PART_019` receives a presentation material (`PCB_SOLDERMASK_PRESENTATION`)
driven by a deterministic generated texture
(`stage_10R_pcb_presentation/assets/pcb_surface_detail.png`, 1024 px, seeded
PIL render): soldermask base, trace-like Manhattan runs, pad/via impressions,
silkscreen-like rectangles, kept clear of a plain border so board edges stay
readable. Mapping uses Generated coordinates; no UVs or mesh edits are added.
Mounting holes and the chamfered outline come from the untouched source mesh.

## Scene and cameras

One derived scene: `scene/pcb_presentation_assembly.blend`.

- `HERO`: PART_019 + 15 `PCB_COMP_*`, moved to a dedicated inspection zone at
  assembled Z but offset +175 mm in X from the device anchor.
- `SECONDARY`: PART_006 at its assembled offset below the board in the zone.
- `SUPPORT`: PART_007 at its assembled location, weak weight.
- `CONTEXT`: the other 19 story parts at assembled locations, reduced weight.
- `SOURCE_HIDDEN`: PART_023..PART_082, preserved and hidden.
- `CAMERAS`: CAM_PCB_CLEAN (3/4 hero on the board), CAM_PCB_TOP (top-down),
  CAM_PCB_CONTEXT (device plus inspection zone).
- `LIGHTS`: a deterministic two-area-light rig (Eevee needs scene lights for
  the textured material; lights are the only non-MESH/CAMERA objects allowed).

Render engine: `BLENDER_EEVEE` at 1920x1080 (Workbench cannot show the
textured soldermask detail). No keyframes, frame range [1,1], no FONT objects.

## Outputs

All under `stage_10R_pcb_presentation/`:

- `config/pcb_presentation_manifest.json` — source vs reconstruction registry,
  PART_007 reclassification, per-component reference provenance
- `config/pcb_presentation_materials.json` — material roles and weights
- `config/pcb_presentation_cameras.json`
- `config/pcb_presentation_validation.json`
- `assets/pcb_surface_detail.png`
- `scene/pcb_presentation_assembly.blend`
- `renders/pcb_presentation_clean.png`
- `renders/pcb_presentation_context.png`
- `renders/pcb_presentation_top.png`
- `renders/pcb_presentation_reference_comparison.png` — generated clean render
  beside `REF_PCB_002` for human review
- `reports/task10R_pcb_visual_review.md`
- `data_task10R_pcb_run_result.json`
- `logs/task10R_pcb.log`

## Validation

`technical_status` can reach PASS; `visual_status` stays
`PENDING_HUMAN_REVIEW` and `overall_status` stays `REVIEW_REQUIRED` until the
user approves the renders. Validation checks the frozen baseline, per-part
geometry fingerprints, the hidden-part policy, absence of animation data and
FONT objects, the 15-component manifest coverage, footprint raycast results,
and the presence of all renders and configs.

## Explicit non-goals (stop boundary)

No animation, communication state, rugged state, annotations, sales copy,
timeline, reassembly, or commercial final rendering. The pipeline stops after
the static presentation assets and waits for human review.
