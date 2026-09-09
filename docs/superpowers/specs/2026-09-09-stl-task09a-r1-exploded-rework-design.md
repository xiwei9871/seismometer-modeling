# Task 9A-R1 Exploded View Layout Rework — Design

## Goal

Create a reproducible static exploded presentation layout from the original
assembled state, with a clear central Z-axis structure and compact secondary
branches, while preserving all 82 source PART meshes and leaving Stage 01,
Stage 02, v4, and the source STL untouched.

## Scope and immutable inputs

The source contract is:

- STL SHA256: `fd2a7b78540245fd098724206d5ddf169fd2f44c07638e9a6459cd92fea717d1`
- source PART meshes: 82
- faces: 444296
- indexed vertices: 221902

The implementation reads:

- `output/stage02_semantic.blend`
- `data/assembly_initial.json`
- `data/semantic_parts.json`
- `data/parts_manifest.json`
- frozen baseline metadata from `scripts/task09_data.py`

It never edits the STL, Stage 01, Stage 02, or the existing v4 files. All
presentation changes are transforms, visibility, collections, cameras,
non-semantic neutral presentation materials, lights, and optional helpers in
a newly generated scene.

## Presentation policy

All 82 source PART objects remain in the derived scene and retain their
geometry and source identity. Only the confirmed important set
`PART_001` through `PART_022` is visible in the Hero and Engineering modes.
`PART_023` through `PART_082` remain present but hidden. Hidden small parts,
the fragment, and unresolved medium parts do not enter collision checks,
animation planning, or motion review.

The R1 scene is static. It must contain zero animation data and no keyframes.
It is a final layout proposal for later animation, not a physical
disassembly-order claim.

## Hierarchical composition

The layout is rebuilt from assembled transforms, not offset from the rejected
v4 positions. `PART_001` (`LOWER_HOUSING`) is the presentation anchor.

### Main vertical stack

The main stack uses global Z as its primary axis and keeps the major enclosure
elements approximately centered over the anchor:

1. `PART_001` — `LOWER_HOUSING`, anchor;
2. `PART_002` — `UPPER_HOUSING`;
3. `PART_004` — `UPPER_HOUSING_TOP_COVER`;
4. `PART_005` — `HANDLE` / antenna shroud.

Their XY placement is derived from the anchor center and their original
assembled Z levels. Vertical separation is proportional to component extent
and uses a consistent primary spacing level.

### Secondary branches

- Sensor: `PART_003` plus `PART_012`–`PART_014`; first translated as one
  coherent branch to the left/front, then given short local X/Y/Z offsets.
- PCB: `PART_006`, `PART_007`, and `PART_019`; first translated to a
  right/front branch, then separated as a compact protective-plate / PCB /
  support-frame stack.
- Battery: `PART_008`–`PART_011` and `PART_015`–`PART_016`; translated as a
  coherent branch and shown in a compact deterministic 3×2 array.
- Top interfaces: `PART_017` and `PART_018`; kept as a small paired branch
  near the top structure and visually secondary.
- Leveling: `PART_020`–`PART_022`; kept close to the original mounting XY
  locations, arranged as the existing three-point footprint, with a limited
  downward Z offset. They are not spread across the frame.

The exact offsets are generated from measured bounds and fixed configuration
factors. No arbitrary per-run or random placement is allowed.

## Data flow and source of truth

The planner creates:

- `stage_09A_R1_exploded_rework/config/explosion_groups.json`
- `stage_09A_R1_exploded_rework/config/explosion_layout_config.json`
- `stage_09A_R1_exploded_rework/config/camera_config.json`

Each PART record stores its assembled transform, presentation transform,
group, parent group, axis/sign, distance, visibility mode, confidence, and
notes. A derived validation file records bounds, group coverage, occupancy,
overlap warnings, floating-component warnings, edge-on warnings, and camera
clipping checks.

Blender reads these deterministic configuration files and materializes the
scene. It does not become the only source of truth.

## Scene and output layout

The new scene is:

`stage_09A_R1_exploded_rework/scene/exploded_layout_v2.blend`

It contains all source PART objects, the `PRESENTATION_R1` collection, group
collections, four named cameras, and optional toggleable
`EXPLOSION_GUIDES` / `EXPLOSION_LABELS` collections. Object names retain the
technical identity using the form `PART_###__SEMANTIC_NAME`; custom
properties retain `part_id`, source component index, assembled location,
presentation location, semantic metadata, and `source = original_stl`.

The four required renders are:

- `exploded_hero.png` — elevated 3/4 perspective for presentation;
- `exploded_engineering.png` — controlled near-isometric technical view;
- `exploded_top.png` — top validation view for XY alignment;
- `exploded_rear.png` — rear validation view when useful.

The pipeline also creates `exploded_contact_sheet.png`, a layout report,
validation report, and a run log under the R1 directory.

## Camera and presentation style

The Hero camera is a medium/long-lens elevated 3/4 perspective, tuned from
the generated bounds. It shows top, front/side surfaces and internal depth
without extreme wide-angle distortion. Engineering is near-isometric and
prioritizes correspondence. Top and rear views are validation views.

The scene uses restrained neutral materials with tonal differences between
the main stack, internal branches, and secondary parts. It uses soft product
lighting, readable contact shadows, and a dark neutral background. No formal
product palette, decals, rope reconstruction, or geometry reconstruction is
introduced in R1.

## Validation and failure handling

The runner validates the frozen baseline before generating anything. It fails
explicitly if the source PART set, face count, indexed vertex count, source
hash, or Stage 02 input is inconsistent. It also fails on missing group
assignments, non-finite transforms, camera clipping, severe Hero occlusion,
or unexpected animation data.

Warnings are retained in validation JSON and reports, including
`FLOATING_COMPONENT_WARNING`, `EDGE_ON_VISIBILITY_WARNING`,
`UNDERFILLED_FRAME`, and `HERO_OCCLUSION_WARNING`. Hidden parts are excluded
from presentation-specific collision and review metrics by policy.

The assembled transforms remain in `data/assembly_initial.json` and in each
R1 PART record. A validation pass compares the source geometry totals and
confirms that switching/rebuilding the static layout does not alter geometry
or create animation data.

## Testing strategy

Pure Python tests cover:

- exact 82-PART coverage and immutable baseline checks;
- deterministic group membership and transforms;
- central stack, sensor, PCB, battery, interface, and leveling policies;
- hidden small/fragment policy;
- finite values, warning generation, and output contracts.

Blender integration checks open the generated R1 blend and verify source mesh
totals, visible/hidden policy, named cameras, neutral presentation objects,
and zero animation data. Render checks verify all required PNG outputs and
the contact sheet. Repeated pipeline runs compare deterministic JSON and
transform hashes; generated binaries are not treated as the source of truth.

## Explicit non-goals

R1 does not create keyframes, animation timing, camera animation, explosion
motion tests, real disassembly sequencing, materials for final rendering,
CAD reconstruction, mesh repair, simplification, remeshing, joining,
deletion, or semantic guesses beyond the approved PART mappings.

