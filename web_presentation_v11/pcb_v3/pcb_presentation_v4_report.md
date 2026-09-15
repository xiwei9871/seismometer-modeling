# PCB Presentation V4 — Build Report (A2.2)

Registration-driven rebuild: instead of hand-placed approximate geometry,
the V4 board meshes, hole set, surface marks and major-component placement
are all derived from the A2.1 registration (`registration/board_map.json`,
`registered_*.png`, overlays).

## Pipeline

```
photo_pcb_{a,b}_{front,back}.jpg
        |  register_photos.py            (A2.1, approved)
        v
board_map.json + registered_*.png + overlays
        |  precompute_board_geometry.py  (venv: cv2 + mapbox_earcut)
        v
board_mesh.json   <-- earcut triangles; Blender curve fill CANNOT
        |              tessellate the traced contours (self-touching
        |              at 1-px necks -> missing cap faces -> dark board)
        |  bake_textures_v4.py           (venv: real silkscreen /
        |                               trace-shadow / mottle extract)
        v
build_pcb_v4.py   (Blender: mesh.from_pydata, level A/B/C parts)
        |
        v
render_pcb_v4.py  (9 shots + 2 ortho top-downs)
        |
        v
compare_v4.py     (overlay + IoU vs registered photos)
```

## Validation results

| Board | IoU (mask) | What it means |
|---|---|---|
| A front | 0.68 | contours track within ~2% on 3 of 4 edges; right edge drifts — comes from the pxmm assumption in registration, not the mesh |
| B front | 0.61 | same story; smaller board amplifies pixel error |

**IoU caveat**: the metric thresholds a green mask on a lit render and uses
single-scale centre alignment. A darker render can halve it without any
geometry change. The overlay images (`validation/compare_*.png`) are the
real review artifact — judge visually.

## What V4 fixed vs V3

1. **Real outline** — 476-pt traced polygon incl. wavy undulation and deep
   notches (V3 had a hand-drawn approximation, wrong proportions 104×88 vs
   real ~104×101)
2. **Real hole set** — 2 large interior holes registered front/back at
   1.31mm mean offset; perimeter plated holes read from overlays, nudged
   to fit inside traced lobes; right-centre kidney slot added
3. **Measured component placement** — CLMP module 44×32 top-centre,
   ceramic antenna (-25,-28), daughter zone 28×40 flush to bottom edge,
   wound coil Ø16 inside zone, 2R2 inductors right-of-centre, SN strip
4. **Real board surface** — silkscreen marks and trace-shadows extracted
   from the registered photos and baked into TEX4_* textures; procedural
   Manhattan routing only where photo signal is too weak
5. **Mesh integrity** — earcut triangulation replaced curve fill after a
   debugging pass showed large cap areas missing (rays hit the floor
   through the board face)

## Honest inventory

- **Measured**: outlines, interior holes, slot, silkscreen marks, board
  tone, major-component bboxes/positions listed in the manifest
- **Inferred from overlay**: perimeter plated holes (2 dropped as
  unverifiable), JST rotations, coil stack geometry
- **Procedural**: trace linework, via dots, SMT scatter (outline-contained),
  mid ICs, tantalum caps, cable/plug geometry, back-side sparse features
- **Not modelled**: the SN barcode contents, component pin counts,
  die-internal markings (a plain label plate stands in)

## Known limitations

- B-board back registration remains REVIEW (near-bare face, too few
  correspondences) — the single detected centre hole anchors the model
- Right-edge silhouette drift ~2% (homography scale assumption)
- Two speculative perimeter holes were dropped rather than forced outside
  the traced outline — if the overlay shows them clearly they can be
  re-added with measured centres

## Deliverables

- `pcb_presentation_v4.blend` — `PRESENTATION_PCB_V4` + `RIG_V4`
- `registration/board_mesh.json` — earcut geometry (rebuildable)
- `textures/TEX4_*.png` — photo-derived board surfaces (packed too)
- `renders_v4/` — 9-shot validation set + ortho top-downs
- `validation/` — photo-vs-render overlays

## STOP — human review

A2.2 is complete pending your sign-off. Checklist:

- [ ] `validation/compare_a_front.png` — silhouette + big parts align
- [ ] `renders_v4/03` / `07` — main board reads as a real industrial PCB
- [ ] `renders_v4/05` / `08` — small board reads correctly
- [ ] Accept ~2% right-edge drift as presentation-sufficient
- [ ] Approve replacing the abstract PCB in `web_presentation_master.blend`
      (next step after approval: swap in V4, demote PART_007 to support
      frame, re-render architecture/inspection/close-up views)
