"""V1 Interactive Digital Product — single source of semantic truth.

Both export_story_glb_v1.py (writes node extras) and build_web_manifest_v1.py
(runtime states, explode vectors, inspect layouts) consume this module so the
GLB and the manifest can never disagree about the SYS_/CMP_/GEO_ schema.

Logical structure (spec §1/§3):

    DEVICE_ROOT
    ├── SYS_TOP               handle, upper shell, top cover, ports
    ├── SYS_ACQUISITION       main PCB (HERO) + plate + frame
    ├── SYS_POWER             six battery compartments
    ├── SYS_SENSOR            tri-axis fixture + three cores
    └── SYS_FIELD_PLATFORM    lower housing + leveling cones
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Functional systems. explodeDirection is normalized by the manifest builder
# from the PRIMARY_ARCHITECTURE state; the values below are per-system flags
# only. Order matters: it is the architecture-mode vertical order (top first).
# ---------------------------------------------------------------------------

SYSTEMS: dict[str, dict[str, object]] = {
    "SYS_TOP": {
        "displayName": "Top Assembly",
        "oneLiner": "Carry handle, top cover and field interface ports.",
        "order": 0,
        "parts": ("PART_002", "PART_004", "PART_005", "PART_017", "PART_018"),
    },
    "SYS_ACQUISITION": {
        "displayName": "Acquisition System",
        "oneLiner": "High-precision acquisition core and its protective stack.",
        "order": 1,
        "parts": ("PART_019", "PART_006", "PART_007"),
    },
    "SYS_POWER": {
        "displayName": "Power System",
        "oneLiner": "Six-cell long-endurance power pack.",
        "order": 2,
        "parts": ("PART_008", "PART_009", "PART_010", "PART_011", "PART_015", "PART_016"),
    },
    "SYS_SENSOR": {
        "displayName": "Sensing System",
        "oneLiner": "Smart three-axis sensing: one fixture, three orthogonal cores.",
        "order": 3,
        "parts": ("PART_003", "PART_012", "PART_013", "PART_014"),
    },
    "SYS_FIELD_PLATFORM": {
        "displayName": "Field Platform",
        "oneLiner": "Rugged base and three-point leveling.",
        "order": 4,
        "parts": ("PART_001", "PART_020", "PART_021", "PART_022"),
    },
}

# ---------------------------------------------------------------------------
# Logical components. semanticId is the stable id used by raycast resolution,
# selection and the registry — never derived at runtime from mesh names.
# ---------------------------------------------------------------------------

COMPONENTS: dict[str, dict[str, object]] = {
    # SYS_TOP
    "PART_002": {"semanticId": "CMP_UPPER_HOUSING", "displayName": "Upper Housing",
                 "role": "SECONDARY", "systemId": "SYS_TOP"},
    "PART_004": {"semanticId": "CMP_TOP_COVER", "displayName": "Top Cover",
                 "role": "SECONDARY", "systemId": "SYS_TOP"},
    "PART_005": {"semanticId": "CMP_HANDLE", "displayName": "Carry Handle",
                 "role": "SECONDARY", "systemId": "SYS_TOP"},
    "PART_017": {"semanticId": "CMP_INTERFACE_PORT_01", "displayName": "Interface Port A",
                 "role": "SUPPORT", "systemId": "SYS_TOP"},
    "PART_018": {"semanticId": "CMP_INTERFACE_PORT_02", "displayName": "Interface Port B",
                 "role": "SUPPORT", "systemId": "SYS_TOP"},
    # SYS_ACQUISITION
    "PART_019": {"semanticId": "CMP_MAIN_PCB", "displayName": "Acquisition Core Board",
                 "role": "HERO", "systemId": "SYS_ACQUISITION"},
    "PART_006": {"semanticId": "CMP_PCB_PROTECTIVE_PLATE", "displayName": "PCB Protective Plate",
                 "role": "SUPPORT", "systemId": "SYS_ACQUISITION"},
    "PART_007": {"semanticId": "CMP_PCB_CONNECTING_FRAME", "displayName": "PCB Connecting Frame",
                 "role": "SUPPORT", "systemId": "SYS_ACQUISITION",
                 "inspectable": False},
    # SYS_POWER
    "PART_008": {"semanticId": "CMP_CELL_01", "displayName": "Cell 01",
                 "role": "PRIMARY", "systemId": "SYS_POWER"},
    "PART_009": {"semanticId": "CMP_CELL_02", "displayName": "Cell 02",
                 "role": "PRIMARY", "systemId": "SYS_POWER"},
    "PART_010": {"semanticId": "CMP_CELL_03", "displayName": "Cell 03",
                 "role": "PRIMARY", "systemId": "SYS_POWER"},
    "PART_011": {"semanticId": "CMP_CELL_04", "displayName": "Cell 04",
                 "role": "PRIMARY", "systemId": "SYS_POWER"},
    "PART_015": {"semanticId": "CMP_CELL_05", "displayName": "Cell 05",
                 "role": "PRIMARY", "systemId": "SYS_POWER"},
    "PART_016": {"semanticId": "CMP_CELL_06", "displayName": "Cell 06",
                 "role": "PRIMARY", "systemId": "SYS_POWER"},
    # SYS_SENSOR
    "PART_003": {"semanticId": "CMP_SENSOR_FIXTURE", "displayName": "Sensor Fixture",
                 "role": "PRIMARY", "systemId": "SYS_SENSOR"},
    "PART_012": {"semanticId": "CMP_SENSOR_X", "displayName": "Sensing Core X",
                 "role": "HERO", "systemId": "SYS_SENSOR"},
    "PART_013": {"semanticId": "CMP_SENSOR_Y", "displayName": "Sensing Core Y",
                 "role": "HERO", "systemId": "SYS_SENSOR"},
    "PART_014": {"semanticId": "CMP_SENSOR_Z", "displayName": "Sensing Core Z",
                 "role": "HERO", "systemId": "SYS_SENSOR"},
    # SYS_FIELD_PLATFORM
    "PART_001": {"semanticId": "CMP_LOWER_HOUSING", "displayName": "Lower Housing",
                 "role": "SECONDARY", "systemId": "SYS_FIELD_PLATFORM"},
    "PART_020": {"semanticId": "CMP_LEVELING_01", "displayName": "Leveling Cone 01",
                 "role": "SUPPORT", "systemId": "SYS_FIELD_PLATFORM"},
    "PART_021": {"semanticId": "CMP_LEVELING_02", "displayName": "Leveling Cone 02",
                 "role": "SUPPORT", "systemId": "SYS_FIELD_PLATFORM"},
    "PART_022": {"semanticId": "CMP_LEVELING_03", "displayName": "Leveling Cone 03",
                 "role": "SUPPORT", "systemId": "SYS_FIELD_PLATFORM"},
}

# PCB presentation components become GEO_* children of CMP_MAIN_PCB.
PCB_COMP_PREFIX = "PCB_COMP_"


def system_of(part_id: str) -> str:
    comp = COMPONENTS[part_id]
    return str(comp["systemId"])


def component_extras(part_id: str) -> dict[str, object]:
    """glTF extras payload written onto each part node (spec §4)."""
    comp = COMPONENTS[part_id]
    role = str(comp["role"])
    return {
        "semanticId": comp["semanticId"],
        "type": "component",
        "systemId": comp["systemId"],
        "sourcePart": part_id,
        "displayName": comp["displayName"],
        "role": role,
        "selectable": True,
        "hoverable": True,
        "inspectable": bool(comp.get("inspectable", True)),
        "presentationPriority": {"HERO": 100, "PRIMARY": 70, "SECONDARY": 40,
                                 "SUPPORT": 15, "HIDDEN": 0}[role],
    }


def pcb_component_extras(component_id: str, material_role: str) -> dict[str, object]:
    """glTF extras for presentation PCB components — GEO_ children of the board."""
    return {
        "semanticId": "GEO_" + component_id,
        "type": "geometry",
        "systemId": "SYS_ACQUISITION",
        "sourcePart": "PART_019",
        "displayName": component_id.replace("PCB_COMP_", "").replace("_", " ").title(),
        "role": "SUPPORT",
        "materialRole": material_role,
        "selectable": True,
        "hoverable": True,
        "inspectable": False,
        "presentationPriority": 30,
        "logicalParent": "CMP_MAIN_PCB",
    }


def validate_semantic_map() -> None:
    parts: set[str] = set()
    for sys_id, spec in SYSTEMS.items():
        for pid in spec["parts"]:  # type: ignore[index]
            if pid in parts:
                raise ValueError(f"{pid} assigned to two systems")
            parts.add(pid)
            if COMPONENTS[pid]["systemId"] != sys_id:
                raise ValueError(f"{pid} systemId disagrees with SYSTEMS[{sys_id}]")
    if len(parts) != 22:
        raise ValueError(f"semantic map covers {len(parts)} parts, expected 22")
