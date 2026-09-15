# PCB Presentation V3 — Build Report

Phase A2 of the interactive digital product pipeline. Goal: replace the
abstract "green board + black blocks" PCB with a photo-grounded,
presentation-grade board that survives close-up inspection — **visual
credibility, not electrical reconstruction**.

## Inputs used

Authoritative references (real photos, supplied by user):

| File | Used for |
|---|---|
| `reference/photo_pcb_a_front.jpg` | PCB-A front: big compute module, coax antenna lead, ceramic patch antenna, green shield/daughter zone + coil, white ribbon at right edge, 2 large interior holes |
| `reference/photo_pcb_a_back.jpg` | PCB-A back: near-bare soldermask, faint traces, ribbon at left edge (page-turn flip confirmed), SN label, ground tab + wire loop |
| `reference/photo_pcb_b_front.jpg` | PCB-B front: 7 white JST connectors, 3R3 gray power inductor, dense small ICs, centre hole |
| `reference/photo_pcb_b_back.jpg` | PCB-B back: near-bare, one red-top bulk cap |

Earlier CAD renders (`pcb_a_*.png`, `exploded_assembly.png`) are kept as
supporting evidence only — the real photos govern.

## What is certain (photo-grounded)

- Both boards have **irregular outlines** with chamfered corners and edge
  notches; A ≈ 104×88, B ≈ 62×56 (mm, assumed)
- A: 6 plated mounting holes, **2 large interior holes**, small top hole
- B: 4 corner holes + left-edge hole + centre hole
- A front: large black compute module (top-centre), white coax antenna lead,
  white ceramic patch antenna (lower-left), green raised shield/daughter zone
  with a visible coil, white ribbon exiting right edge
- B front: white JST connectors around the perimeter, central gray power
  inductor, dense small ICs and passives
- Back sides are **near-bare** — mostly soldermask, faint traces, very few
  components (A: tab + wire loop + label; B: one red-top cap)

## What is presentation reconstruction

- Exact trace/pad/via layout — procedural Manhattan-style routing that reads
  like real fanout around holes and connectors
- Exact component positions — approximate, density-matched to photos
- Silkscreen graphics — generic outlines/bars, no fabricated labels
- The 3R3 inductor marking is a plain strip (no text, no part number claim)

## Conservative choices

- No chip model assignments; module labelled `MAIN_COMPUTE_MODULE`, `UNKNOWN`
  areas stay neutral (`MID_IC`, `SMT_PASSIVE`, `JST_CONNECTOR`)
- `PART_007` is absent from the PCB hero layer entirely (support frame only,
  per spec)
- Back sides intentionally sparse — matches photos, not laziness
- `mm` remains an assumed unit label

## Close-up enhancements

- Front textures baked at 2048px with trace/via/pad/silkscreen layers
- Level A components are real geometry (module, dies, connectors, coil tori,
  cable curves); Level B instanced-style boxes; Level C via texture speckle
- Bump + roughness modulation on soldermask so traces catch light correctly

## Deliverables

- `pcb_presentation_v3.blend` — `PRESENTATION_PCB_V3` + `RIG_V3` collections,
  semantic empties for web mapping, 8 cameras
- `renders/01..09` — overview / architecture / A front / A back / B front /
  B back / main closeup / secondary closeup / contact sheet
- `pcb_presentation_v3_manifest.json`
- Textures in `textures/` (also packed into the .blend)

## Baseline integrity

No source STL, Stage 01/02, or `PART_*` geometry was touched. V3 assets are
additive in a standalone blend; integration into
`web_presentation_master.blend` is a later, reviewable step.
