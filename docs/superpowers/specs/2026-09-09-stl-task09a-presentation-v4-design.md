# STL Task 9A Focused Presentation Explosion v4

## Purpose

v4 is a visual-clarity correction to the static hierarchical presentation.
The first v3 render made the algorithmically classified but semantically
unknown medium geometry look like a cloud of small, unimportant parts. v4
therefore uses the currently confirmed important-part set as the presentation
allowlist while keeping every source PART intact in the derived scene.

## Immutable source contract

- Source STL SHA-256: `fd2a7b78540245fd098724206d5ddf169fd2f44c07638e9a6459cd92fea717d1`
- Source PART meshes: 82
- Faces: 444296
- Indexed vertices: 221902

The source STL, Stage 01 blend, Stage 02 blend, and Stage 01/02 manifests are
read-only. v4 writes a new derived blend and never overwrites v3 or the
earlier flat preview.

## Presentation policy

The visible v4 allowlist is `PART_001` through `PART_022`, representing the
currently confirmed important components. This set contains 18 MAJOR parts
and 4 named MEDIUM parts. `PART_023` through `PART_045` that remain UNKNOWN,
plus `PART_039` and `PART_046` through `PART_082`, are retained as source
objects but hidden from presentation. They receive no collision, animation,
or manual motion-review entries and are not renamed semantically.

`PART_001` (`LOWER_HOUSING`) remains the scene anchor at its assembled
transform. The layout is static and has no keyframes, animation data, or
physical disassembly-order claim.

## Hierarchical layout

The visible parts are arranged in seven functional assemblies using the six
fixed zones `top`, `bottom`, `left`, `right`, `front-left`, and `front-right`:

- enclosure: lower anchor, upper housing, top cover;
- handle: separate top zone;
- top interface: separated charging/data port pair;
- PCB: group move followed by protective plate, support frame, and main PCB;
- sensor: group move followed by X/Y/Z fixture expansion;
- battery: six compartments in a 3-by-2 array;
- leveling: three cones in a widely spaced triangle in a separate bottom/front area.

Each PART record stores assembled location, presentation location, assembly
zone offset, local component offset, parent assembly, visibility mode, and
review scope. The JSON is the source of truth; Blender only materializes it.

## Outputs

- `data/presentation_explosion_v4.json`
- `data/presentation_review_queue_v4.csv`
- `output/stage03_presentation_exploded_v4.blend`
- `output/explosion_validation_v4/exploded_iso_front_v4.png`
- `output/explosion_validation_v4/exploded_iso_rear_v4.png`
- `output/explosion_validation_v4/exploded_front_v4.png`
- `output/explosion_validation_v4/exploded_top_v4.png`
- `output/reports/presentation_explosion_v4.md`
- `logs/presentation_v4.log`

The review queue contains exactly the visible important PARTs and asks only
whether each important component is visible, unobstructed, and clearly laid
out. Formal materials and the black/orange product palette remain deferred to
the later presentation stage.

