# v44 — board correction pass

Source of truth for this pass: user-supplied AI-corrected top view of board A
(replaces the flawed photo-based surface that had the centre crack and wrong
hole positions).

## What changed vs v43

| Item | v43 | v44 |
|---|---|---|
| A-front texture | stitched photo pair, visible centre crack | single corrected plate, no seam |
| A outline | 476-pt photo trace (lobes, bottom rectangular notch) | 69-pt trace of corrected image (chamfered corners) |
| hole0+hole4 | overlapping pair (-41.5,0)/(-45.5,0.5) | merged single hole (-45.6,2.6,r3.0) |
| hole1 | (40.28,-1.35) | (47.8,-12.8,r3.1) |
| hole5 | (44,0.5) | (46.0,3.2,r2.9) |
| hole11 | (46,-30) — position was bare soldermask in corrected image | moved to the real large cutout (32.9,-24.4,r5.0) |
| kidney slot | (28,-14) 14x8 | removed — absent in corrected image |
| hole9 | (38,40) | (43,29) |
| hole7 | (23,-42.5) | (28.1,-43.7) |
| bottom-left edge | — | added (-29.3,-48.2) -> fitted (-28.5,-45.8) |

## Synced files

- `registration/board_map.json` — a_front outline re-traced from corrected
  plate (backup: `board_map_v42_backup.json`)
- `registration/board_mesh.json` — regenerated (A: 405 verts / 427 tris,
  0 dropped holes; one perimeter hole nudged 2.4mm to fit outline)
- `registration/registered_a_front.png` — corrected plate, hole voids painted
  at model positions (backup: `registered_a_front_v42_backup.png`)
- `scripts/precompute_board_geometry.py`, `scripts/bake_textures_v42.py`,
  `scripts/build_pcb_v4.py` — A_HOLES/A_SLOT kept in sync
- `scripts/build_v44.py` — surgical rebuild: board mesh swap + packed-texture
  refresh + collision scan

## Component collision result

Removed 9 scatter passives/pads whose centres now sit inside through-holes
(SMT42_* + A_EM_PAD_-1_0). Named components unaffected; antenna screw hole
(-24,-42) kept.

## Known deltas to review

- Outline edge details simplified by the AI reference (bottom notch under
  daughterboard no longer traced — hidden in normal views).
- Unmodelled printed pads remain as texture-only details.
- White connector overhang at right edge pre-existed in v43 (unchanged).
