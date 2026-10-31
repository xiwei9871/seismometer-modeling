# Decision register

ACTIVE entries block conflicting requests — report, never silently implement.

| ID | Decision | Status |
| --- | --- | --- |
| D01 | Original STL immutable — never edit/repair/overwrite | **ACTIVE** |
| D02 | PART_ID deterministic from original STL | **ACTIVE** |
| D03 | No repair/merge/simplify/remesh/Join on geometry | **ACTIVE** |
| D04 | Fragments marked for review only — never deleted | **ACTIVE** |
| D05 | No guessed semantic names (enclosure/PCB/sensor/screw) | **ACTIVE** |
| D06 | mm is assumed unit, not verified metadata | **ACTIVE** |
| D07 | Every output reproducible from original STL | **ACTIVE** |
| D08 | Production/deploy actions require explicit human authorization | **ACTIVE** |
