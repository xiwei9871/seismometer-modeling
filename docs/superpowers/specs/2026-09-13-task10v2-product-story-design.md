# Task 10-V2 Product Story Preview — Presentation-Grade Rebuild

## Goal

Rebuild the approved Task 10 product-story preview at presentation quality:
Eevee rendering with the Task 10-R-PCB-V1 lighting model, the populated
`MAIN_PCB_PRESENTATION` board riding with `PART_019` in every state, and
`PART_007` demoted to support weight throughout. Story structure, timing,
shot copy, and the pending-protocol guard are unchanged.

## Status

Approved direction by the user on 2026-09-13. Task 10 (Workbench preview)
remains untouched as the frozen v1 baseline; V2 writes only under
`stage_10V2_product_story/`.

## Frozen inputs

- `stage_09C_refined_explosion/scene/exploded_animation_preview.blend`
  (SHA256 `a3b5359861877e247ad1b035b00cace3e29eea2789ac227e6eeddfaaba1a7766`)
- Frozen baseline: 82 source PART objects, 444296 faces, 221902 indexed vertices.
- `stage_10_product_story/config/*.json` — read-only story contract source.
- `stage_10R_pcb_presentation/config/pcb_presentation_manifest.json` and
  `assets/pcb_surface_detail.png` — read-only presentation PCB definition
  (15 `PCB_COMP_*` components, board-local placements, reference provenance).
- Product PDF claims remain provenance-bound; the communication protocol
  stays `PENDING_PRODUCT_CONFIRMATION`.

## What changes vs Task 10 v1

1. **Renderer**: `BLENDER_WORKBENCH` -> `BLENDER_EEVEE`, with a deterministic
   three-area-light rig, node world background, and exposure 1.7 (the values
   approved in the PCB presentation review).
2. **MAIN_PCB_PRESENTATION**: the 15 `PCB_COMP_*` presentation objects are
   imported into the story scene and keyframed with the *same* per-state
   transform as `PART_019` (board-local offsets applied on top), so the
   populated board rides with the board in every state — invisible inside the
   closed housing when assembled, a dense product board in PCB_FOCUS and the
   exploded architecture shot.
3. **PART_007 demotion**: `presentation_priority=SUPPORT`,
   `independent_focus=false`, weight 0.10; it keeps its exploded offset for
   engineering context but renders at support weight in all states.
4. **Focus dimming in Eevee**: v1 keyframed `material.diffuse_color` (Workbench
   only). V2 additionally keyframes the Principled `Base Color` input per shot
   boundary. The board's textured material gets an equivalent keyed dim through
   a multiply node so it follows the same focus-weight policy.
5. **Presentation components** get per-shot dimmed materials by role
   (`ic`, `connector`, `shield`, `cap`), same factors as source parts.

## What does not change

- Nine shots, frames 1–900 at 30 fps, identical titles/metrics/annotations,
  identical camera segmentation (hero + sensor + pcb focus cameras), identical
  state transforms for the 22 story parts — with one deliberate exception:
  in `PCB_FOCUS` the V2 layout slides `PART_019` +x out from under `PART_006`
  (the plate previously occluded the populated board surface) while `PART_007`
  stays low as context. All other states keep v1 motion verbatim.
- No changes to source geometry, no animation on PART_023..PART_082.
- Still a preview: no Cycles, no 4K, no sound, no compositing.

## Outputs

All under `stage_10V2_product_story/`:

- `config/` — V2 story config, state transforms (with component transforms),
  camera sequence, annotation config, material config, validation
- `scene/product_story_v2.blend`
- `renders/` — the same eight stills, `storyboard_contact_sheet.png`,
  `product_story_v2_preview.mp4`
- `reports/task10V2_product_story_report.md`
- `data_task10V2_run_result.json`, `logs/task10V2.log`

## Validation

Same fail-closed contract as v1 plus: 15 presentation components present with
manifest coverage, per-frame component transforms equal board transform +
board-local offset, PART_019 carries the image-texture material, PART_007
support flags set, EEVEE engine recorded, light rig present, protocol text
still pending, fonts only inside the annotation collection.

`technical_status` may PASS; `visual_status` stays `PENDING_HUMAN_REVIEW`
until the user approves the new storyboard.

## Stop boundary

No new story chapters, no protocol decision, no PAD/server continuation, no
final commercial render. Stop after the V2 preview for human review.
