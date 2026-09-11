# Task 10-R Functional Inspection State Rebuild

## Goal

Create four independently readable, subtitle-free functional inspection states from the frozen source assembly: Primary Architecture, Sensor, PCB, and Power. These states are static visual review assets, not a new animation.

## Constraints

- The source STL, Stage 01, Stage 02, Stage 9C, and Task 10 outputs are read-only inputs.
- The frozen source baseline remains 82 PART objects, 444296 faces, and 221902 indexed vertices.
- PART_023..PART_082 remain preserved but are hidden from presentation; they never become independent inspection subjects.
- Task 10-R must not reuse Task 10 presentation transforms, cameras, timing, annotations, or sales copy.
- No subtitles, title text, metrics, leader lines, animation keyframes, reassembly, communication state, or rugged state are generated in this phase.
- `visual_status` remains `PENDING_HUMAN_REVIEW` until the user approves the contact sheet.

## State design

Each state is built from the assembled transforms in the frozen 9C layout and has its own deterministic transform plan and camera.

1. `PRIMARY_ARCHITECTURE`: four macro layers on a global Z stack: Top/Exterior, Electronics/Power, 3-Axis Sensor, and Lower Field Platform. The four projected module silhouettes must be separated enough to read as four layers.
2. `SENSOR_INSPECTION`: the device remains a low-weight context; the sensor fixture and X/Y/Z cores move into a dedicated inspection zone. The three cores are arranged around the fixture with clear, non-overlapping silhouettes.
3. `PCB_INSPECTION`: the device remains a low-weight context; the PCB module moves into a dedicated inspection zone. The protective plate, MAIN_PCB, and support frame form a visibly separated three-layer stack, with the green MAIN_PCB top surface exposed.
4. `POWER_INSPECTION`: the device remains a low-weight context; six battery compartments move into a compact 3x2 inspection array. All six cells remain individually countable and associated as one power system.

## Presentation policy

Focus geometry uses product-neutral presentation materials with only enough color to distinguish orange housing, black exterior, green PCB, dark-metal sensor, and charcoal battery. Context geometry uses reduced material value/contrast but remains visible. No text is used to establish structural meaning.

## Validation

The pure-Python planner reports module screen occupancy, projected overlap ratio, visible-surface proxy, frame margins, and silhouette separation as diagnostic metrics. These metrics can flag a review issue but cannot set `visual_status` to PASS. Blender validation independently checks source totals, fingerprints, hidden policy, no animation data, four scene outputs, and the absence of FONT/helper annotation objects.

## Outputs

All generated assets live under `stage_10R_functional_inspection/`:

- `config/module_groups.json`
- `config/inspection_states.json`
- `config/inspection_cameras.json`
- `config/visual_validation.json`
- four state `.blend` files
- the required clean/context/top renders
- `renders/task10R_contact_sheet.png`
- `reports/task10R_visual_review.md`
- `data_task10R_run_result.json`

The source-of-truth files are the JSON configs. Blender scenes are reproducible derivatives.
