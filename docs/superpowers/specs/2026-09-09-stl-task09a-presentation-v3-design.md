# STL Task 9A Hierarchical Presentation Explosion v3

## Scope

This revision replaces the first flat per-PART presentation layout with a
static, hierarchical exploded presentation. The source assembly remains the
82-part immutable Stage 02 scene. Only MAJOR and MEDIUM parts participate in
the visible presentation layout; SMALL and FRAGMENT parts remain source
objects but are hidden when no evidence-backed parent assembly is available.

This is a presentation layout, not a physical disassembly simulation. It
does not create keyframes, animation data, collision queues, motion-review
items for small parts, materials, or geometry edits.

## Immutable baseline and boundaries

The following facts are fail-closed inputs:

- Source SHA-256: `fd2a7b78540245fd098724206d5ddf169fd2f44c07638e9a6459cd92fea717d1`
- Source PART objects: 82
- Faces: 444296
- Indexed vertices: 221902
- Connected components: 82

The STL, `output/stage01_split.blend`, `output/stage02_semantic.blend`, and
all Stage 01/02 manifests are read-only. The new derived scene is
`output/stage03_presentation_exploded_v3.blend`; the old flat
`stage03_exploded_preview.blend` is not overwritten.

## Architecture

### Pure planning layer

`scripts/presentation_explosion_v3.py` loads the frozen manifests and initial
transforms, validates complete PART coverage, assigns major functional
assemblies and six fixed presentation zones, and calculates deterministic
hierarchical transforms. It writes one record for every source PART and
separate assembly records. The JSON is the source of truth for presentation
visibility, parent policy, zone, group offset, local component offset, and
final static location.

The planner preserves the source transform for every hidden part. A visible
part's presentation location is computed as:

```text
assembled_location + assembly_zone_offset + component_local_offset
```

The lower housing (`PART_001`) is the anchor and remains at its assembled
transform. SENSOR and PCB use a group-level zone offset followed by explicit
component offsets. BATTERY uses a deterministic 3-by-2 component array.

### Blender derived-scene layer

`scripts/build_presentation_explosion_v3.py` opens Stage 02, validates the
source-only totals, reads the presentation JSON, applies only object
transforms and visibility flags, adds v3 custom properties and presentation
collections, and saves the new derived blend. It never changes mesh data and
never calls a keyframe API. Hidden SMALL/FRAGMENT objects remain in the scene
and continue to count toward the source baseline.

### Render layer

`scripts/generate_presentation_explosion_v3.py` opens the v3 blend and
renders four neutral inspection images using temporary cameras. The required
outputs are:

- `output/explosion_validation_v3/exploded_iso_front_v3.png`
- `output/explosion_validation_v3/exploded_iso_rear_v3.png`
- `output/explosion_validation_v3/exploded_front_v3.png`
- `output/explosion_validation_v3/exploded_top_v3.png`

The renderer does not save scene changes. It validates that no object has
animation data and that the source-only totals remain unchanged.

## Functional assemblies and zones

The initial deterministic groups are:

| Assembly | Parts | Zone | Presentation rule |
|---|---|---|---|
| `ENCLOSURE_ASSEMBLY` | `PART_001`, `PART_002`, `PART_004` | `bottom` | `PART_001` is the fixed anchor; upper housing and cover receive clear local offsets |
| `HANDLE_ASSEMBLY` | `PART_005` | `top` | move to a separate top area |
| `TOP_INTERFACE_ASSEMBLY` | `PART_017`, `PART_018` | `right` | keep the pair visible with a separated local pair layout |
| `PCB_ASSEMBLY` | `PART_006`, `PART_007`, `PART_019` | `front-right` | move the assembly, then separate plate, board, and frame |
| `SENSOR_ASSEMBLY` | `PART_003`, `PART_012`-`PART_014` | `front-left` | move the fixture group, then expand X/Y/Z fixture members |
| `BATTERY_ASSEMBLY` | `PART_008`-`PART_011`, `PART_015`, `PART_016` | `left` | move the group, then show a 3-by-2 array |
| `LEVELING_ASSEMBLY` | `PART_020`-`PART_022` | `bottom` | keep three cones separated in a triangular layout |
| `UNRESOLVED_MEDIUM_ASSEMBLY` | `PART_023`-`PART_038`, `PART_040`-`PART_045` | `right` | keep medium geometry visible without semantic guesses, using a reviewable grid |

The six allowed zone names are exactly `top`, `bottom`, `left`, `right`,
`front-left`, and `front-right`. Multiple assemblies may use one zone with
distinct explicit anchor offsets; this keeps the zone vocabulary fixed while
preventing visual stacking.

## Visibility and hierarchy policy

- `MAJOR` and `MEDIUM`: visible and included in the presentation review queue.
- `SMALL` and `FRAGMENT`: never independently exploded.
- A small/fragment part follows a parent only when a parent is explicitly
  present in the v3 parent map. No such evidence-backed parent is currently
  available for the small/fragment records, so they are recorded as
  `HIDDEN_NO_PARENT` and remain at assembled transforms.
- Small/fragment parts never enter collision, animation, or manual motion
  review queues.
- Duplicate groups remain physically separate PART objects; duplicate
  grouping does not cause a Join operation.

Every source PART record contains its permanent ID, size class, semantic
metadata, visibility mode, parent assembly, zone, assembled location,
presentation location, and offsets. Unknown medium parts remain
`UNKNOWN`/`MEDIUM_UNRESOLVED` rather than receiving guessed names.

## Output contracts

The primary data file is `data/presentation_explosion_v3.json`. It records:

- `layout_version: "v3"`
- `mode: "STATIC_HIERARCHICAL_PRESENTATION"`
- `animation_created: false`
- `animation_anchor: "PART_001"`
- all six zone definitions
- all assembly records and hierarchy levels
- all 82 PART records
- the visible-only review item list
- the frozen source baseline

Additional outputs are:

- `data/presentation_review_queue_v3.csv`
- `data/presentation_v3_run_result.json`
- `output/reports/presentation_explosion_v3.md`
- the four v3 validation images
- `logs/presentation_v3.log`

The review queue contains only visible MAJOR/MEDIUM items and asks only
whether the important component is visible, unobstructed, and clearly laid
out. It has no realistic disassembly-order or small-part motion questions.

## Failure handling and reproducibility

The planner and Blender builder fail closed on missing baseline files,
changed source hash, incomplete PART coverage, invalid size classes, unknown
zone names, duplicate PART records, non-finite vectors, or changed geometry
totals. JSON/CSV ordering is deterministic. Every subprocess failure is
reported with its stage and return code. The generated scene is accepted only
after reopening and checking 82 source PARTs, 444296 faces, 221902 indexed
vertices, zero source animation data, and zero total animation data.

## Verification

Tests cover complete source coverage, MAJOR/MEDIUM visibility, hidden
SMALL/FRAGMENT policy, exact six-zone vocabulary, anchor preservation,
hierarchical SENSOR/PCB offsets, six-cell BATTERY array spacing, review queue
filtering, no-keyframe contracts, output names, and source-baseline
preservation. The acceptance run additionally verifies the STL and Stage
01/02 hashes are unchanged and the four PNGs are readable.
