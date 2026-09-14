# Interactive Digital Product V1 — Architecture

Status: Phase 1 (core architecture) + Phase 2 (Sensor vertical slice) implemented and
verified in-browser. PCB and Power inspection data paths are wired end-to-end
(inspect layouts + cameras ship in the manifest); their interaction polish is
Phase 3/4.

## Pipeline

```text
scene/product_story_v2.blend
        │  export_story_glb_v1.py      (frame 1, no animation, extras-tagged)
        ▼
web-v1/product_v1.glb                  geometry + materials + semantic extras
        │
        │  build_web_manifest_v1.py    (from state_transforms + semantic_map)
        ▼
web-v1/manifest_v1.json                systems / components / camera presets
        │
        ▼
src/*.ts  ── esbuild ──▶  dist/app.js  runtime state machine
```

`scripts/semantic_map.py` is the single source of truth for the
SYS_/CMP_/GEO_ schema; both the exporter and the manifest builder import it.

## Key decisions vs the spec

- **Vanilla TS + three.js + esbuild**, not React/R3F: the project has no React
  stack and the spec's R3F suggestion was conditional on that. All seven
  deliverable modules are plain `.ts`.
- **GLB stays flat** — parts are NOT re-parented under SYS_ nodes. The
  semantic tree lives in node `extras` + `SemanticRegistry` (logical node ≠
  mesh, spec §2). Exception: `PCB_COMP_*` nodes carry `logicalParent:
  CMP_MAIN_PCB` and are `attach()`ed under the board at load so they ride
  along — real parenting, resolved at runtime.
- **No baked animation in the GLB.** Every transform is computed at runtime as
  `base + stateDelta × factor` (spec §6/§12): explode vectors from
  PRIMARY_ARCHITECTURE centroids, inspect layouts from the *_FOCUS states,
  per-core extraction from `extractDirection` in the manifest.
- **Units**: GLB nodes live in mm (node positions are mm); the scene root is
  scaled ×0.001 so camera/world are meters. `mm()` conversions apply only on
  the camera side; component targets use manifest mm directly.
- **Blender AUTO sensor fit**: `lens_mm` presets convert to vertical FOV via
  `vfov = 2·atan(tan(atan(18/lens))/aspect)` — applied per preset so inspect
  shots keep their fitted subject fraction (~60–70%).

## Module map (spec §61)

| file | spec section | role |
|---|---|---|
| `src/semantic-registry.ts` | §5/§16/§49 | one-time index; mesh→component→system resolution |
| `src/experience-store.ts` | §8/§35 | typed store, single interaction truth |
| `src/state-machine.ts` | §7/§9/§32 | overview / architecture / inspection, staged sequences |
| `src/camera-controller.ts` | §28–30 | presets, tweened position+target+lens, OrbitControls |
| `src/transition-manager.ts` | §31 | single tween scheduler, cancel-then-resolve |
| `src/interaction-controller.ts` | §15–17 | raycast→logical parent, restrained hover, click/dblclick |
| `src/material-state-manager.ts` | §14/§55 | FOCUS/RELATED/DISTANT/XRAY levels, stash+exact restore |
| `glb-node-schema.json` (manifest) | §3/§4 | semantic ids, roles, explode vectors, layouts |
| `architecture.md` | — | this file |

## Verified acceptance

- §50 transform regression: Overview→XRay→Inspect→extract core→Back leaves
  every component within **2.8e-17 m** of basePosition; 0 hidden nodes; all
  materials restored.
- §52 sensor acceptance: fixture centered, three cores fanned at
  30°/90°/150°, occupancy ≈ 55–65%, orbit enabled, click-core extraction.
- §55 x-ray: shells fade to 0.16 opacity then restore exactly on exit.
- Registry self-check (§49): no duplicate semanticIds, all 22 manifest
  components resolve to GLB nodes.

## Run

```bash
cd stage_10V2_product_story/web-v1
npm run build
python3 -m http.server 8941
# open http://127.0.0.1:8941/
```

Regenerate assets after scene changes:

```bash
blender -b --python scripts/export_story_glb_v1.py -- --project-root $PWD
python scripts/build_web_manifest_v1.py --project-root $PWD
```

## Deferred (per spec §59–60)

- Phase 3: PCB subcomponent picking polish, hover-per-IC
- Phase 4: Power 3×2 inspection array (positions already in manifest)
- Phase 5: info panel content, story autoplay, mobile tuning, `?debug=1` HUD
- gltfpack/meshopt compression; the 24 MB GLB is fine for local/dev
