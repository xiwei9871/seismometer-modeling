from __future__ import annotations

from pathlib import Path

from scripts.build_animation_plan import build_animation_plan
from scripts.build_task09a_review_page import build_review_page


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_animation_plan_has_no_keyframe_payload():
    plan = build_animation_plan(PROJECT_ROOT)

    assert plan["fps"] == 30
    assert plan["animation_created"] is False
    assert "keyframes" not in plan
    assert plan["frame_range"] == [1, 570]
    assert plan["stages"]
    assert all("keyframes" not in stage for stage in plan["stages"])


def test_review_page_contains_relative_links_to_required_views(tmp_path):
    page = build_review_page(
        tmp_path,
        {"views": ["exploded_iso_front.png", "exploded_iso_rear.png"]},
        {"topological_order": ["UPPER_HOUSING", "MAIN_PCB"], "edges": []},
        {"fps": 30, "animation_created": False},
    )

    html = page.read_text(encoding="utf-8")
    assert page == tmp_path / "index.html"
    assert "exploded_iso_front.png" in html
    assert "exploded_iso_rear.png" in html
    assert "animation_created" in html
    assert "../data/animation_plan.json" in html
    assert "https://" not in html
