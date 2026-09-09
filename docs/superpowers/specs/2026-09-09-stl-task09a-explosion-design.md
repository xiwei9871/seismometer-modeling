# STL Task 9A Exploded Assembly Planning Design

## Scope

Task 9A converts the frozen Task 8 semantic assembly into a deterministic
explosion plan. It creates disassembly data, per-PART exploded transforms,
collision/path findings, a schedule, a derived Blender preview, validation
renders, and a static local review page.

Task 9A does not create animation keyframes, animation data, materials,
lighting for a final render, CAD geometry, repaired meshes, or edits to any
Stage 01/02 source file.

## Immutable baseline

The following values are a fail-closed input contract:

- Source SHA-256: `fd2a7b78540245fd098724206d5ddf169fd2f44c07638e9a6459cd92fea717d1`
- Source PART meshes: 82
- Faces: 444296
- Indexed vertices: 221902
- Connected components: 82

Read-only scene inputs are `output/stage02_semantic.blend`,
`data/semantic_parts.json`, `data/assembly_semantic.json`,
`data/mounting_relationships.json`, `data/disassembly_dependencies.json`,
`data/assembly_initial.json`, `data/parts_manifest.json`,
`data/duplicate_groups.json`, and `data/reference_missing_features.json`.

`output/stage01_split.blend`, the STL files, and all Stage 01/02 manifests
remain untouched. The only Blender scene written by Task 9A is the derived
`output/stage03_exploded_preview.blend`.

## Architecture

### Python planning layer

`scripts/task09_planning.py` is pure Python and owns the source of truth. It
loads and validates Task 8 data, expands semantic dependencies into a DAG,
assigns deterministic group/part motion plans, performs an approximate swept
AABB check, and writes all Task 9A JSON/CSV outputs. It never imports Blender,
mutates meshes, or writes a `.blend` file.

The planner uses semantic groups as the primary motion units. Each source
PART still receives a record in `exploded_state.json`, preserving its
permanent `PART_ID`, initial transform, final transform, group, direction,
distance, order, confidence, and collision result. Group members share the
same translation unless a record explicitly states otherwise, so relative
geometry is preserved.

### Blender derived-scene layer

`scripts/build_stage03_exploded_preview.py` opens the immutable
`stage02_semantic.blend`, validates the 82 source objects and frozen totals,
reads `exploded_state.json`, and writes a separate Stage 03 scene. The
`--state assembled` mode restores the exact values from `assembly_initial.json`;
the `--state exploded` mode applies only planned object transforms. Neither
mode creates keyframes or edits mesh data.

### Visual validation layer

`scripts/generate_explosion_validation.py` opens the derived scene in its
current state and renders five fixed inspection views under
`output/explosion_validation/`. `scripts/build_task09a_review_page.py` creates
a lightweight static HTML page with relative links to those images and the
planning JSON/CSV. The page is an inspection surface only; closing it does not
lose any decision or finding.

## Data contracts

### `disassembly_graph.json`

```json
{
  "directed_acyclic": true,
  "nodes": [
    {
      "node_id": "MAIN_PCB",
      "kind": "semantic_group",
      "parts": ["PART_019"],
      "confidence": "HIGH",
      "requires_manual_confirmation": false
    }
  ],
  "edges": [
    {
      "before": "UPPER_HOUSING",
      "after": "MAIN_PCB",
      "confidence": "LOW",
      "evidence": ["REF_EXT_003"],
      "requires_manual_confirmation": true
    }
  ],
  "topological_order": []
}
```

Virtual unresolved nodes such as `EXTERNAL_HOUSING_FASTENERS` and
`PCB_FASTENERS` are retained and marked as non-part nodes. No unresolved
relationship is silently upgraded to a physical PART mapping.

### `exploded_state.json`

The top-level document records baseline and state metadata. It contains one
record for every `PART_001` through `PART_082`:

```json
{
  "state": "EXPLODED",
  "unit_assumption": "mm",
  "source_baseline": {"source_parts": 82, "faces": 444296, "indexed_vertices": 221902},
  "parts": {
    "PART_004": {
      "semantic_name": "UPPER_HOUSING_TOP_COVER",
      "assembly_group": "ENCLOSURE",
      "assembled_location": [0, 0, 0],
      "assembled_rotation_euler": [0, 0, 0],
      "assembled_scale": [1, 1, 1],
      "explode_vector": [0, 0, 1],
      "explode_distance_mm": 110,
      "exploded_location": [0, 0, 110],
      "motion_type": "LINEAR",
      "explode_order": 3,
      "confidence": "HIGH",
      "collision_check": "PASS",
      "requires_manual_confirmation": false
    }
  }
}
```

Directions are restricted to the six world-axis directions. Known major
groups use explicit engineering candidates; unknown/small groups use a
deterministic radial fallback and remain `LOW` confidence. Distances are
computed from the direction-projected bounding-box extent plus a minimum
clearance, with bounded category-specific limits. No universal fixed
distance is used.

### Other outputs

- `explosion_guides.json`: source/target group, axis, start/end anchor, and
  confidence for future guide-line display.
- `animation_plan.json`: 30 FPS frame ranges, parallel groups, easing labels,
  pause frames, and total duration. It contains no keyframes.
- `fastener_group_mapping.json`: duplicate group membership, representative
  PART, nearest semantic anchor, motion policy, and confidence. Ambiguous
  groups are `UNASSIGNED`.
- `future_visual_assets.json`: missing Task 8 reference features and their
  future category/action, without creating those assets.
- `explosion_review_queue.csv`: only `MEDIUM`, `LOW`, `UNKNOWN`, collision,
  or unusual-motion records, with a concrete review question.
- `data/task09a_run_result.json`: baseline, output counts, Blender status,
  keyframe count, and source-geometry safety result.

## Direction and distance policy

The first deterministic plan uses these high-confidence motion candidates:

| Group/semantic | Direction | Rationale |
|---|---:|---|
| `HANDLE` | `+Z` | lifts away from the top housing |
| `UPPER_HOUSING_TOP_COVER` | `+Z` | separates from the PCB-side top plane |
| `TOP_INTERFACE_PORT_PAIR` | `+Z` | follows the visible top interface axis |
| `UPPER_HOUSING` | `+Z` | exposes the internal assembly |
| `PCB_PROTECTIVE_PLATE` | `-Z` | separates from the board layer |
| `MAIN_PCB` | `+Y` | exposes the board without stacking it on the covers |
| `PCB_SUPPORT_FRAME` | `-Y` | separates the support layer from the board |
| `BATTERY_ASSEMBLY` | radial `±X/±Y` by member | preserves the six-cell spatial arrangement |
| `SENSOR_ASSEMBLY` | `-X` | exposes the central sensor fixture from the enclosure |
| `LEVELING_ASSEMBLY` | `-Z` | follows the support direction below the housing |
| `LOWER_HOUSING` | `-Z` | reveals the final lower enclosure layer |

These are planning candidates, not claims about the physical tool path. The
planner records evidence and manual-review flags, and collision checking may
select an alternate signed axis if it materially reduces newly introduced
overlap.

## Collision/path policy

The check uses each manifest centroid and axis-aligned bounding-box dimensions
as an approximate proxy. It samples the synchronized translation from
assembled to exploded state at `t = 0, .25, .5, .75, 1.0`. Initial overlaps
that already exist in the assembled device are not reported as new collisions;
new pair overlaps are reported with the two PART IDs, sample time, and group
IDs. The planner tests the preferred direction, its inverse, and the other
world axes in a deterministic order. If no candidate is clean, the preferred
direction remains and the record is marked `WARN` for manual review.

This is an inspection heuristic, not a manufacturing-grade motion planner.

## Animation schedule policy

The first schedule is 30 FPS and 570 frames maximum. It has an assembled
hold, staggered external/cover/PCB/sensor stages, parallel battery and
leveling motion where the graph permits it, and a final exploded hold. It
stores `BEZIER_EASE_IN_OUT` as the future interpolation policy but creates no
keyframes.

## Failure handling and reproducibility

The planner fails closed if the Stage 01/02 baseline, PART coverage, or input
JSON contracts do not match. It writes deterministic JSON with sorted keys and
stable PART/group ordering. Blender failure is logged with command, stdout,
stderr, return code, and stage. A generated preview is never treated as valid
unless it reopens with 82 source PART meshes, 444296 faces, 221902 vertices,
and zero animation data.

## Verification

Tests cover DAG acyclicity/topological order, stable direction/distance
planning, group preservation, collision reporting, assembled/exploded
round-trip transforms, review-queue filtering, static-page links, and
fail-closed baseline checks. The acceptance run additionally verifies source
SHA256 equality, unchanged Stage 01/02 files, five validation renders, and
zero Blender keyframes/animation data.

