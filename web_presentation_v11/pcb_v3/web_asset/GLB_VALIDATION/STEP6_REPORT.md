# STEP 6 — GLB FREEZE / WEB ASSET MASTER — VALIDATION REPORT

## Source of truth
- Blender master (frozen): pcb_v44_lookdev.blend (v44 = corrected AI-image: crack removed, 13-hole layout, kidney slot removed)
- Export source: web_asset/EXPORT_SOURCE/device_master.blend
- Runtime: web_asset/GLB_RUNTIME/smart_field_device_master.glb

## Export metrics
| metric | value | target |
|---|---|---|
| GLB size | 41.46 MB | 40–60 MB ✓ |
| nodes | 898 | semantic hierarchy ✓ |
| meshes | 629 | — |
| materials | 63 | — |
| textures/images | 14/12 | — |
| triangles | 525,760 | HERO kept ✓ |
| draw-call est | 635 | — |
| semantic nodes | 866 | extras preserved ✓ |
| FPS (desktop, DPR≤2) | 60.7 | ≥55 ✓ |
| console/network errors | 0 | 0 ✓ |

## Fidelity gate (7-view Blender↔WebGL comparison)
| check | result |
|---|---|
| Geometry silhouette | PASS |
| Component hierarchy | PASS |
| Material category | PASS |
| PCB reads as PCB | PASS (fixed: baseColor was wired to silk mask) |
| Black IC separation | PASS |
| White connector separation | PASS |
| Metal/plastic differentiation | PASS |
| Coil metallic readability | PASS |
| Antenna ceramic/metal differentiation | PASS |
| Contact hierarchy | PASS |
| flat green board / black blob / overexposed white / glass PCB / chrome screws / washed texture | none observed |

## Critical fix applied (material translation)
The Cycles multi-mask node graphs for the 4 board-face materials were garbled by the
glTF exporter (baseColor→silk mask, MR→metal mask, normal→color image).
Rebuilt as web-safe Principled: baseColor=TEX42 color image, metallic=TEX42 *_metal
mask (per-pixel via SeparateColor), roughness=0.5, no normal. Soldermask now exports
as non-metallic green; plated pads keep metallic from mask.

## Semantic registry
- DEVICE_ROOT → SYS_* → MAIN_PCB_PRESENTATION → PCB_A / PCB_B
- All nodes carry extras: semanticId, semanticName, systemId, presentationPriority,
  selectable, hoverable, focusable, explodable, source_type
- PCB sub-grouping: BOARD / TOP / BOTTOM / MODULES / CONNECTORS / CABLES

## Known deltas vs Cycles (accepted)
- Board green slightly more saturated in WebGL (lookdev mix vs straight texture)
- Subboard reads darker green — still green FR4, not glass (verified OPAQUE, metallic=0)
- Coil spiral reflection visible on main board — consistent in both renders
- Overview framing updated to include companion PCB_B on platform lobe

## Status
GLB_FREEZE_GATE = PASS — submitted for human review
Viewer: http://localhost:8942/glb-validation/ (orbit / HDRI env / ACES / ref-compare / 7 presets)
