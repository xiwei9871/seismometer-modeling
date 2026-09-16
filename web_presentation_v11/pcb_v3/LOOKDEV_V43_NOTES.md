# STEP 5 — Final Industrial LookDev notes (pcb_v43)

Scope: materials / lighting / AO / color management / cameras only.
Zero geometry, transform, UV or registration changes vs `pcb_v42_surface`
(see `validation_v43/regression_report.md` — 821 frozen objects, 0 diffs,
18 validation cameras unchanged).

## Soldermask (MAT_PCB_GREEN_{A,B}_{FRONT,BACK})

Layered node graph over the frozen TEX42 plates — same registration,
different material behaviour:

- `TEX42_*` base colour → HueSaturation (sat ×0.78, val ×0.88) →
  industrial deep green instead of vivid game green
- luminance → MapRange 0.32–0.50 → roughness variation (~±0.05)
- `TEX42_*_silk` mask → silk pixels pulled to warm off-white ink
  (0.74/0.71/0.66), roughness lifted to 0.56, dieslectric response
- `TEX42_*_metal` mask → exposed pads/rings get metallic 0.92,
  roughness 0.28
- micro-bump: lum + silk×0.30 → Bump strength 0.10 / dist 0.03
  (breaks planar highlight up close, invisible at normal distance)
- clear-coat 0.15 / coat-rough 0.32, IOR 1.46 — reads as resin layer,
  not car paint

New bake outputs `TEX42_*_silk.png` / `TEX42_*_metal.png` come from
`bake_textures_v42.py` — silk and metal are now separate masks so the
same photo-derived content drives different PBR responses.
Module/daughterboard neutral fills switched to Gaussian-blurred local
tone (no hard photo-patch edges); neutralisation expanded ~0.8 mm to
hide residual image halos around geometry.

## Flat material retune (STEP5 ranges)

| family | material | base / rough / metal |
|---|---|---|
| solder pads | MAT_TERMINAL_METAL | 0.52,0.54,0.58 / 0.28 / 0.95 |
| gold contacts | MAT_GOLD_PAD | 0.42,0.32,0.12 / 0.26 / 1.0 |
| edge half-holes | MAT_EDGE_GOLD | 0.42,0.34,0.18 / 0.35 / 0.85 |
| copper ring | MAT_COPPER_PATCH | 0.38,0.20,0.065 / 0.27 / 1.0 |
| screws | MAT_METAL_SCREW | 0.19,0.21,0.25 / 0.30 / 0.95 |
| coil wire | MAT_COIL_METAL | 0.58,0.56,0.51 / 0.30 / 0.95 |
| cap top | MAT_CAP_TOP_METAL | 0.60,0.62,0.66 / 0.27 / 0.95 |
| shield plate | MAT_SHIELD_PLATE / MAT_shield_metal | 0.44,0.46,0.50 / 0.38 / 0.90 |
| braid loop | MAT_BRAID_METAL | 0.50,0.52,0.56 / 0.34 / 0.95 |
| IC matte | MAT_IC_BLACK_MATTE | 0.020 / 0.45 |
| IC semi-matte | MAT_IC_BLACK_SEMIMATTE | 0.016 / 0.34 |
| IC variant | MAT_IC_BLACK_02 | 0.012 / 0.40 |
| module pcb | MAT_MODULE_PCB_BLACK | 0.016,0.021,0.019 / 0.44 |
| connector plastic | MAT_CONNECTOR_WHITE | 0.50,0.47,0.42 / 0.55 |
| connector cavity | MAT_CONJ_CAVITY | 0.016 / 0.72 |
| wire insulation | MAT_CABLE_WHITE | 0.62,0.59,0.54 / 0.44 |
| ceramic | MAT_CERAMIC_WHITE | 0.80,0.77,0.70 / 0.48 |
| inductor body | MAT_INDUCTOR_GREY | 0.16,0.16,0.18 / 0.52 |
| cap sleeve | MAT_CAP_SLEEVE_RED | 0.30,0.045,0.035 / 0.48 |
| labels | MAT_LABEL_WHITE | 0.66 / 0.62 |

## Lighting rig (replaces V4_*)

- `L43_KEY` area 130mm @ (-170,-170,240) → 52 kW, warm neutral
- `L43_FILL` area 150mm @ (190,-120,150) → 22 kW, cool
- `L43_RIM` area 110mm @ (60,200,230) → 26 kW — connector/antenna edges
- `L43_TOP` area 260mm overhead → 9 kW weak fill
- `L43_RAKE` area 160mm near-grazing @ (210,-60,22) → 42 kW,
  only enabled for the raking-light shots (13/14)
- world: neutral 0.048/0.050/0.058 × strength 1.0
- ground plane at z = −9.5 (contact shadow, no mirror floor)

AO comes from real GI in Cycles — contact-only darkening, no broad
halo pass added.

## Color management

AgX + Medium High Contrast, exposure +3.3 (mm-unit scene needs the
same energy scale V4 used). No LUT, no teal/orange, no crushed blacks.

## Cameras

Validation cams untouched (`CAM_V4_*`, `CAM_V41_*`, DOF forced off for
sharp regression views). Added:

`CAM_V43_HERO_A`, `CAM_V43_HERO_B`, `CAM_V43_HERO_PAIR`,
`CAM_V43_MACRO_{MODULE,ANT,COIL,B_CONN,B_POWER}`,
`CAM_V43_RAKE_{A,B}`, `CAM_V43_SWATCH`

## Renderer

Cycles for hero/macro/rake/contact shots (96 spp + denoise +
adaptive), EEVEE for the four registration final views (fast,
consistent with v42 pipeline).

## Known residuals

- EEVEE validation tops render slightly flatter than Cycles shots
  (engine difference, registration still exact).
- A-side silk is denser than back — matches photos.
- `A_CERAMIC_PATCH_ANT` name kept neutral per STEP-3 gate.

## STEP-4 placement bugfix (rendering bug found in STEP-5 review)

`B_BK_CAP1(+_TOP)` and `B_BK_CAP2(+_TOP)` were built at raw image
coordinates without the B-board −80 mm offset — they floated up to
70 mm off the board edge (visible as detached red cylinders in
`02_B_hero` / `14_B_material_raking_light`, hidden under the flipped
board in `07_B_back_final`).  Photo-verified board-local targets
(cap1: +4.1, −19.9 / cap2: +3.5, −16.6) re-measured from
`registered_b_back.png`; objects translated in
`lookdev_pcb_v43.py` and source `build_pcb_v42.py` coords corrected
(`board_local − 80`).  Whitelisted in the regression report —
all other frozen objects diff-clean.
