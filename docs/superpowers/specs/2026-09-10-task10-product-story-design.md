# Task 10 Product Story Animation Design

## Status

Approved design with the Task 10 addendum from 2026-09-10.

This stage changes the purpose of the animation from a mechanical exploded
view to a product-functional story. The animation must explain why the field
device is valuable: accurate sensing, high-quality acquisition, real-time
communication, long endurance, and field adaptability.

## Frozen inputs and source traceability

Task 10 reads the validated Task 9C scene:

```text
stage_09C_refined_explosion/scene/exploded_animation_preview.blend
```

The following baseline is immutable:

```text
source PART objects: 82
faces: 444296
indexed vertices: 221902
```

The original STL, Stage 01, Stage 02, and Task 9C outputs are read-only
inputs. Task 10 writes a new scene and never overwrites those assets.

The product PDF is now available at the project root:

```text
幔壳迅勘智能勘察设备.pdf
```

It is a two-page PowerPoint-exported PDF. Its SHA256 is:

```text
d8555d751851d6e5f53027721c29eb701da27226bd1311b47bd1d1d1bbdb0d7e
```

The product source manifest records:

```text
pdf_status: VERIFIED_LOCAL_REFERENCE
claim_source: 幔壳迅勘智能勘察设备.pdf
```

The extracted product claims are carried with explicit page provenance:

```text
page 1: 99% data consistency; WIFI / NBIoT / 4G wording
page 2: 3 channels; 32bits ADC; 10 days standby; 3hrs charging
page 2: 2.5kg; -40 ~ +80°C
page 2: WIFI / NBIoT / Bluetooth wording
```

The PDF contains a communication-protocol conflict between page 1 and page 2.
The preview therefore keeps the protocol field as
`PENDING_PRODUCT_CONFIRMATION` and uses neutral communication wording. No
protocol combination is rendered as a final claim until the product owner
resolves the conflict.

## Story architecture

The implementation uses a state-driven story layer. Each shot is represented
in JSON by its state, frame range, camera treatment, transform emphasis,
material emphasis, annotation text, and validation target. Blender is a
generated presentation result, not the only source of truth.

The functional sequence is fixed:

```text
SENSOR
→ ACQUISITION
→ COMMUNICATION
→ POWER
→ RUGGED PLATFORM
```

Sensor and Acquisition receive the highest visual priority. The story does
not treat anonymous PART IDs as customer-facing narrative units.

## Functional modules

### SMART_3_AXIS_SENSING_SYSTEM

Source objects:

```text
PART_003
PART_012
PART_013
PART_014
```

Customer takeaway:

```text
Three-axis smart sensing; accurate and consistent data acquisition.
```

Preview copy:

```text
SMART 3-AXIS SENSING
3 Channels
99% Data Consistency
```

The three core fixture objects receive a small local X/Y/Z expansion during
the Sensor Focus state. No sensor geometry is rebuilt or split.

### HIGH_PRECISION_ACQUISITION_CORE

Source objects:

```text
PART_006
PART_007
PART_019
```

`PART_019` remains the main visual subject. Preview copy:

```text
HIGH-PRECISION ACQUISITION
32-bit ADC
3 Channels
```

The protective plate and support frame open locally around the unchanged PCB
object. The PCB receives a green presentation material in the Task 10 scene.

### REAL_TIME_COMMUNICATION_SYSTEM

Primary source objects:

```text
PART_005
PART_017
PART_018
```

`HANDLE` and the two top interfaces are the visual subjects. `PART_019` is a
low-weight context object only. The STL does not contain a separately
identified communication chip region, so the scene does not create one.

Preview copy:

```text
REAL-TIME WIRELESS TRANSMISSION
Multi-network communication
```

The protocol field is deliberately:

```json
{
  "communication_protocol_text": "PENDING_PRODUCT_CONFIRMATION"
}
```

The words `4G`, `Bluetooth`, and any final protocol combination are not
rendered until the product owner resolves the two-page conflict.

### LONG_ENDURANCE_POWER_SYSTEM

Source objects:

```text
PART_008
PART_009
PART_010
PART_011
PART_015
PART_016
```

The six battery objects are treated as one power system. They receive a
compact, orderly local array rather than six independent narratives.

Preview copy:

```text
LONG-ENDURANCE POWER
10-day standby
3-hour charging
```

### RUGGED_FIELD_PLATFORM

Source objects:

```text
PART_001
PART_002
PART_004
PART_020
PART_021
PART_022
```

The housing and three-point leveling system remain the visual anchor for the
field-use message. Preview copy:

```text
BUILT FOR FIELD WORK
-40°C to +80°C
2.5 kg
```

This chapter communicates stable setup and field adaptability. It does not
claim a terrain or weather certification that is not present in the supplied
product brief.

## Presentation scope

All 82 source PART objects remain in the generated scene. The current
presentation policy remains:

```text
PART_001..PART_022: visible, functional-story participants
PART_023..PART_082: hidden or follow-parent context, not narrative subjects
```

The latter group receives no independent story animation. It is not deleted,
joined, simplified, or geometrically modified.

The first architecture shot uses only four visual modules:

```text
TOP / EXTERIOR
ELECTRONICS / POWER
SENSOR
LOWER FIELD PLATFORM
```

It does not fully explode every MAJOR or MEDIUM part. Details are deferred to
the relevant Focus states.

## Story states and timing

The preview is 30 seconds at 30 fps, frames 1–900:

| State | Time | Frames | Purpose |
|---|---:|---:|---|
| ASSEMBLED | 0.0–2.5 s | 1–75 | Establish the product and silhouette |
| PRIMARY_ARCHITECTURE | 2.5–5.5 s | 75–165 | Explain four high-level layers |
| SENSOR_FOCUS | 5.5–10.0 s | 165–300 | Make three-axis sensing the first technical hero |
| PCB_FOCUS | 10.0–14.0 s | 300–420 | Make green MAIN_PCB and 32-bit acquisition clear |
| COMMUNICATION_FOCUS | 14.0–17.0 s | 420–510 | Highlight handle and top interfaces |
| POWER_FOCUS | 17.0–20.5 s | 510–615 | Show six-unit long-endurance power system |
| RUGGED_FOCUS | 20.5–23.5 s | 615–705 | Show housing, leveling, weight and temperature range |
| REASSEMBLED | 23.5–27.0 s | 705–810 | Return modules in a readable layered sequence |
| FINAL_HERO | 27.0–30.0 s | 810–900 | Re-establish the complete product |

All mechanical movement uses ease-in/ease-out interpolation. Sensor axes may
use a 4–8 frame stagger and battery units a 3–5 frame stagger. There is no
bounce, spring, or overshoot.

The assembled state and final hero preserve the product context. The final
hero leaves clean visual space for a future continuation toward PAD/server,
zero-time-difference processing, and report generation, but Task 10 does not
animate those downstream systems.

## Transform model

The generated JSON source of truth stores, for each source PART and each story
state:

```text
assembled_location
assembled_rotation
assembled_scale
state_location
state_rotation
visibility
focus_weight
functional_module_ids
```

State transforms are derived from the Task 9C assembled/refined transforms and
small deterministic local offsets. No state is authored only by manually
moving objects in the Blender UI.

The primary architecture uses the global Z axis. Sensor, PCB, and Battery
states add only compact module-local offsets. The communication state focuses
the existing handle/interface geometry and does not fabricate a PCB region.

## Material and emphasis model

Task 10 introduces basic product LookDev in the new scene only:

```text
upper exterior / handle: matte black
lower housing: industrial orange
MAIN_PCB: green
sensor: dark metallic
battery: charcoal
supports / plates: neutral gray or metal
```

Each Focus state changes visual weight, not source geometry:

```text
focused module: full color and contrast
neighbour modules: reduced contrast, retained context
distant modules: muted neutral treatment, retained context
```

Materials are assigned to copied-scene objects and are not applied as mesh
edits. The PCB is highlighted as one existing object; no internal face split
is created.

## Camera and annotation model

The presentation uses one main 3/4 hero camera with controlled target and
distance changes. Sensor and PCB receive restrained push-ins. The final hero
returns to the product framing. No fast orbit or dramatic focal-length jump
is used.

Each shot has at most one title and two metrics. Text and lightweight
inspection helpers live in separate collections so they can be toggled or
regenerated. Communication uses the neutral phrase `Multi-network
communication` and the pending protocol value remains in JSON only.

## Product reference manifest

The generated product reference manifest records:

```text
reference_id
source_file
sha256
pdf_status
claim_source
claims
notes
```

The manifest records the local PDF path, page count, SHA256, extracted claim
pages, and the communication-protocol conflict. The original PDF remains
unchanged; no web search result is substituted for it.

## Output structure

Task 10 writes only under:

```text
stage_10_product_story/
```

Configuration:

```text
config/product_story.json
config/functional_modules.json
config/shot_sequence.json
config/state_transforms.json
config/camera_sequence.json
config/annotation_config.json
config/product_reference_manifest.json
config/validation.json
```

Scene and preview:

```text
scene/product_story_preview.blend
renders/product_story_preview.mp4
renders/storyboard_contact_sheet.png
renders/01_assembled.png
renders/02_primary_explosion.png
renders/03_sensor_focus.png
renders/04_pcb_focus.png
renders/05_communication_focus.png
renders/06_power_focus.png
renders/07_rugged_focus.png
renders/08_final_hero.png
```

The preview target is 1920×1080, 30 fps, Eevee or an equivalent fast preview
renderer. Cycles, 4K final output, sound, voiceover, and commercial
compositing are outside this task.

## Pipeline and validation

The entry point is:

```bash
python run_task10.py
```

The pipeline must fail closed if the Task 9C source scene cannot be opened or
its source totals do not match the frozen baseline. It validates:

1. all 82 source PART IDs remain present;
2. source mesh totals remain 444296 faces and 221902 indexed vertices;
3. Stage 01, Stage 02, and Task 9C inputs are not overwritten;
4. only the intended 22 story participants have narrative transforms;
5. focus-state modules are visible in their focus shots;
6. the communication protocol remains pending;
7. all eight storyboard stills, contact sheet, MP4, and scene exist;
8. frame 1 and frame 900 return to the configured assembled/final-hero states;
9. animation duration is 30 seconds at 30 fps;
10. no mesh topology operation or source geometry rewrite occurred.

Unit tests cover the JSON contracts, module membership, claim provenance,
shot timing, communication guard, and source baseline. A Blender headless
integration validation reopens the generated blend and checks the source mesh
totals and story animation scope.

## Acceptance criteria

Task 10 is ready for human review when:

- the customer can identify the five functional chapters from the storyboard;
- Sensor and Acquisition have the strongest visual weight;
- the primary architecture shot reads as four modules, not a full parts dump;
- HANDLE and TOP_INTERFACE_PORT_01/02 explain communication without a fake PCB
  submodule;
- MAIN_PCB is visibly green and legible in PCB Focus;
- the six battery objects read as one power system;
- housing and three-point leveling communicate field use;
- the final product still reads as the same device;
- the source geometry baseline is unchanged;
- the preview is reproducible from JSON and scripts;
- the output stops at preview quality and does not begin final commercial work.

## Explicit non-goals

Task 10 does not:

- reconstruct or repair CAD geometry;
- add the rope, labels, QR code, or PCB silkscreen;
- infer a final communication protocol;
- animate PAD, server, data engine, or report generation;
- show every fastener or small fragment as a story subject;
- create final Cycles/4K renders;
- add sound design, voiceover, or complex compositing.
