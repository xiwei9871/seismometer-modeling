# Task 9C Refined Exploded Preview Design

## Goal

Create a refined static exploded layout and a review-only Blender animation preview from the validated Task 9A-R1 scene, while preserving the immutable STL, all 82 source PART meshes, Stage 01, Stage 02, and the R1 scene.

## Scope

Task 9C is an incremental presentation refinement. It increases separation along the primary global Z assembly axis, keeps the PCB and sensor groups coherent, keeps the battery group close to the electronic layer, and keeps the three leveling feet aligned to their original XY mounting footprint while lowering them on Z. SMALL and FRAGMENT parts remain outside the presentation motion set. No final commercial materials, final lighting, or production-quality animation is included.

The animation preview is intentionally disposable/review-only: it contains keyframes and a low-resolution MP4, but it is generated only in the new Task 9C directory and never changes R1 or Stage 02.

## Design

1. Read `stage_09A_R1_exploded_rework/config/explosion_layout_config.json` and `exploded_layout_v2.blend` as inputs.
2. Build a new deterministic refined layout from R1 presentation transforms. The main stack remains centered on `PART_001` and uses Z offsets derived from the component heights plus configurable gap factors. PCB and sensor local offsets are likewise derived from bbox dimensions. Battery parts use a measured 3x2 pitch. Leveling feet retain assembled X/Y and receive a larger negative-Z drop.
3. Save the refined static scene as `exploded_animation_preview.blend` before adding animation metadata. The original mesh datablocks and source custom properties are reused without mesh edits.
4. Add keyframes only to the new Task 9C copy. The anchor is `PART_001`; each visible part interpolates from its assembled transform at frame 1 to its refined presentation transform during a 15–22 second schedule at 30 fps. Easing is Bezier ease-in/ease-out without bounce or overshoot. Hidden parts receive no keyframes.
5. Render two refined stills and two detail stills from deterministic cameras. Render a low-resolution review MP4 from the hero camera using the same animation data, then build a contact sheet from representative animation frames.
6. Re-open the generated `.blend` in Blender and validate source totals, visible IDs, animation presence only in the Task 9C copy, frame range, camera names, and output files.

## Source-of-truth files

- `stage_09C_refined_explosion/config/refined_layout.json`
- `stage_09C_refined_explosion/config/animation_plan.json`
- `stage_09C_refined_explosion/config/camera_config.json`
- `stage_09C_refined_explosion/config/validation.json`

The Blender scene and MP4 are derived outputs. Re-running `python run_task09c.py` regenerates them from the validated R1 input.

## Acceptance criteria

- R1, Stage 01, Stage 02, and source STL remain unchanged.
- The refined scene contains all 82 source PART meshes and exactly 22 visible presentation PARTs.
- Source totals remain 444296 faces and 221902 indexed vertices.
- The refined static layout has no hidden SMALL/FRAGMENT objects in the animation set.
- The main vertical layer spacing is measurably larger than the R1 layout, with no severe Hero overlap.
- PCB, sensor, battery, and leveling groups remain readable.
- The animation preview is 15–22 seconds at 30 fps, with no bounce/overshoot policy, and can return to assembled state at frame 1.
- `exploded_hero_refined.png`, `exploded_engineering_refined.png`, `pcb_detail_refined.png`, `sensor_detail_refined.png`, `exploded_animation_preview.blend`, `exploded_preview.mp4`, and `exploded_keyframes_contact_sheet.png` exist and are non-empty.
- The workflow stops after review outputs; no final commercial render or later task is started.
