# Stage 01 rules

- The original STL is immutable: never edit, repair, or overwrite it.
- Generate stable `PART_ID` values deterministically from the original STL.
- Do not repair, clean up, merge, simplify, remesh, or use `Join` on geometry.
- Suspected fragments are marked for review only; never delete them.
- Do not guess semantic names such as enclosure, PCB, sensor, or screw.
- `mm` is an assumed unit label, not verified source metadata.
- Every generated result must be reproducible from the original STL.

## Project Continuity (Devin V1.0.1)
- Session start: read `docs/agent_governance/{PROJECT_STATE.yaml,DECISIONS.md,HANDOFF.md}` — repo files override chat memory.
- `python3 tools/gov/seis_gates.py all` before status claims; unverified ⇒ NOT_VERIFIED.
