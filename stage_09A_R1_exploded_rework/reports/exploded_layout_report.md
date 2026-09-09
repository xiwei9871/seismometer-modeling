# Task 9A-R1 Exploded Layout Report

## 1. Assembly hierarchy

- Main stack: `MAIN_STACK` — PART_001, PART_002, PART_004, PART_005.
- Sensor branch: `SENSOR_BRANCH` — PART_003, PART_012–PART_014.
- PCB branch: `PCB_BRANCH` — PART_006, PART_007, PART_019.
- Battery branch: `BATTERY_BRANCH` — PART_008–PART_011, PART_015–PART_016.
- Top interface branch: `TOP_INTERFACE_BRANCH` — PART_017–PART_018.
- Leveling branch: `LEVELING_BRANCH` — PART_020–PART_022.

## 2. Explosion logic

- Primary axis: global Z, anchored by `PART_001` (`LOWER_HOUSING`).
- Sensor and PCB use compact lateral branches; Battery is a compact 3×2 array.
- Leveling cones preserve the original three-point XY footprint and move downward.
- Hidden source PARTs are retained but do not enter motion/collision review.

## 3. Camera strategy

- Hero: elevated 3/4 perspective with a medium/long lens.
- Engineering: controlled near-isometric view.
- Top and rear: validation views for alignment and occlusion.

## 4. Changes from previous exploded layout

- Rebuilt from original assembled transforms instead of v4 presentation offsets.
- Replaced flat scattering with a central vertical skeleton and secondary branches.
- Kept secondary geometry compact and reduced visual competition from small parts.
- Kept leveling cones near their actual mounting relationship.

## 5. Remaining ambiguities

- This is a presentation layout, not a confirmed physical disassembly sequence.
- PART_017/PART_018 remain a paired interface group without charge/data assignment.
- Neutral presentation materials are not the final product palette.

## Validation summary

- Source PART meshes: 82
- Faces: 444296
- Indexed vertices: 221902
- Visible presentation parts: 22
- Hidden source parts: 60
- Animation data: 0
- Status: `PASS`
- Derived scene: `/Users/xiwei/modeling/stage_09A_R1_exploded_rework/scene/exploded_layout_v2.blend`
