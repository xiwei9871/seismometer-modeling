"""Contract tests for the Task 10-V2 presentation-grade product story."""

from __future__ import annotations

from pathlib import Path

import pytest

from stage_10_product_story.scripts.build_story_scene import build_state_transforms
from stage_10_product_story.scripts.story_data import build_story_config
from stage_10V2_product_story.scripts import story_v2_data as v2


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_v2_paths_stay_inside_the_v2_stage_dir():
    for path in (
        v2.SCENE_OUTPUT,
        v2.STATE_OUTPUT,
        v2.LIGHTING_OUTPUT,
        v2.RENDER_DIR,
        v2.ASSET_TEXTURE,
        v2.VALIDATION_PATH,
        v2.REPORT_PATH,
        v2.LOG_PATH,
        v2.RUN_RESULT_PATH,
    ):
        assert path.startswith("stage_10V2_product_story/")
    assert v2.SCENE_OUTPUT.endswith("product_story_v2.blend")
    assert v2.PREVIEW_VIDEO == "product_story_v2_preview.mp4"


def test_v2_story_config_is_the_unchanged_v1_story():
    story = build_story_config()
    assert story["fps"] == 30
    assert story["frame_range"] == [1, 900]
    assert story["duration_seconds"] == 30.0
    assert [shot["shot_id"] for shot in story["shots"]] == [
        "ASSEMBLED", "PRIMARY_ARCHITECTURE", "SENSOR_FOCUS", "PCB_FOCUS",
        "COMMUNICATION_FOCUS", "POWER_FOCUS", "RUGGED_FOCUS", "REASSEMBLED",
        "FINAL_HERO",
    ]
    assert story["communication_protocol_text"] == "PENDING_PRODUCT_CONFIRMATION"
    rendered_text = " ".join(shot["title"] + " " + " ".join(shot["metrics"]) for shot in story["shots"])
    assert "4G" not in rendered_text
    assert "Bluetooth" not in rendered_text


def test_v2_state_transforms_keep_v1_part_motion_except_focus_layouts():
    v1 = build_state_transforms(PROJECT_ROOT)
    payload = v2.build_story_v2_state_transforms(PROJECT_ROOT)
    assert payload["version"] == "task10V2_story_states_v1"
    changed_states = set(v2.STATE_V2_OFFSETS)
    assert changed_states == {"PCB_FOCUS", "SENSOR_FOCUS"}
    for state_id, state in payload["states"].items():
        if state_id in changed_states:
            continue
        assert state["parts"] == v1["states"][state_id]["parts"]
    for state_id, offsets in v2.STATE_V2_OFFSETS.items():
        v1_parts = v1["states"][state_id]["parts"]
        v2_parts = payload["states"][state_id]["parts"]
        for part_id in v1_parts:
            if part_id in offsets:
                continue
            assert v2_parts[part_id] == v1_parts[part_id]
    # The V2 board slides +x out from under the protective plate.
    v1_pcb = v1["states"]["PCB_FOCUS"]["parts"]
    v2_pcb = payload["states"]["PCB_FOCUS"]["parts"]
    assert v2_pcb["PART_019"]["location"][0] > v1_pcb["PART_019"]["location"][0] + 40.0
    assert v2_pcb["PART_019"]["location"][2] < v1_pcb["PART_006"]["location"][2]


def test_v2_sensor_cluster_clears_the_housing_silhouette():
    v1 = build_state_transforms(PROJECT_ROOT)
    payload = v2.build_story_v2_state_transforms(PROJECT_ROOT)
    v1_sensor = v1["states"]["SENSOR_FOCUS"]["parts"]["PART_003"]
    v2_sensor = payload["states"]["SENSOR_FOCUS"]["parts"]["PART_003"]
    # Pulled further left (-x) and toward the camera (-y).
    assert v2_sensor["location"][0] < v1_sensor["location"][0] - 35.0
    assert v2_sensor["location"][1] < v1_sensor["location"][1]
    # Well clear of the housing left edge (housing spans roughly x -5..200).
    assert v2_sensor["location"][0] < -35.0


def test_v2_components_ride_with_part019_in_every_state():
    payload = v2.build_story_v2_state_transforms(PROJECT_ROOT)
    registry = payload["presentation"]["components"]
    assert len(registry) == 15
    local_by_id = {c["component_id"]: c["board_local_location"] for c in registry}
    for state in payload["states"].values():
        assert set(state["components"]) == set(local_by_id)
        board = state["parts"]["PART_019"]
        for component_id, transform in state["components"].items():
            assert transform["location"] == pytest.approx(
                [board["location"][axis] + local_by_id[component_id][axis] for axis in range(3)]
            )
            assert transform["scale"] == [1.0, 1.0, 1.0]


def test_v2_component_registry_is_reference_driven():
    payload = v2.build_story_v2_state_transforms(PROJECT_ROOT)
    for component in payload["presentation"]["components"]:
        assert component["component_id"].startswith("PCB_COMP_")
        assert component["mounted_on"] == "PART_019"
        assert component["reference_source"].startswith("REF_PCB_")
        # Components sit on the board top surface, above the board origin.
        assert component["board_local_location"][2] > 0.0


def test_v2_part007_stays_support_not_hero():
    payload = v2.build_story_v2_state_transforms(PROJECT_ROOT)
    reclass = payload["presentation"]["part_reclassification"]
    assert reclass["PART_007"]["presentation_priority"] == "SUPPORT"
    assert reclass["PART_007"]["independent_focus"] is False
    assert reclass["PART_007"]["presentation_weight"] == pytest.approx(0.10)
    hierarchy = payload["presentation"]["presentation_hierarchy"]
    assert hierarchy["MAIN_PCB_PRESENTATION"]["tier"] == "HERO"
    assert hierarchy["PART_007"]["tier"] == "SUPPORT"
    assert payload["presentation"]["part_emphasis_cap"]["PART_007"] == pytest.approx(0.55)


def test_v2_presentation_provenance_is_recorded():
    payload = v2.build_story_v2_state_transforms(PROJECT_ROOT)
    presentation = payload["presentation"]
    assert presentation["source_manifest"] == v2.PCB_MANIFEST_PATH
    assert len(presentation["source_manifest_sha256"]) == 64
    assert presentation["surface_texture"] == v2.ASSET_TEXTURE
    manifest = v2.load_pcb_manifest(PROJECT_ROOT)
    assert manifest["component_count"] == 15


def test_v2_lighting_uses_the_approved_eevee_rig():
    state_data = v2.build_story_v2_state_transforms(PROJECT_ROOT)
    config = v2.build_lighting_config(PROJECT_ROOT, state_data=state_data)
    assert config["engine"] == "BLENDER_EEVEE"
    assert config["exposure"] == pytest.approx(1.7)
    assert config["world"]["strength"] == pytest.approx(0.85)
    assert [light["name"] for light in config["lights"]] == [
        "STORY_LIGHT_KEY", "STORY_LIGHT_FILL", "STORY_LIGHT_RIM",
    ]
    assert [light["energy"] for light in config["lights"]] == [65000.0, 28000.0, 36000.0]
    assert all(light["type"] == "AREA" for light in config["lights"])
    # Lights anchor on the story bounds, not on a single part.
    bounds = config["bounds"]
    center = [(bounds["min"][i] + bounds["max"][i]) / 2.0 for i in range(3)]
    for light in config["lights"]:
        assert light["location"][2] > center[2]


def test_v2_component_material_roles_match_the_approved_set():
    roles = v2.build_component_material_roles()
    assert set(roles) == {"ic", "connector", "shield", "cap"}
    assert roles["shield"]["metallic"] == pytest.approx(0.72)


def test_v2_texture_copy_is_deterministic(tmp_path):
    import shutil

    source = tmp_path / v2.PCB_TEXTURE_SOURCE
    source.parent.mkdir(parents=True)
    source.write_bytes(b"deterministic-png")
    first = v2.copy_surface_texture(tmp_path)
    second = v2.copy_surface_texture(tmp_path)
    assert first["sha256"] == second["sha256"] == first["source_sha256"]
    assert (tmp_path / v2.ASSET_TEXTURE).read_bytes() == b"deterministic-png"
    shutil.rmtree(tmp_path / "stage_10V2_product_story")
