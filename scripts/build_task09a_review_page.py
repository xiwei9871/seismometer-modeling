"""Create a dependency-free static Task 9A inspection page."""

from __future__ import annotations

import html
import os
from pathlib import Path
from typing import Any


def build_review_page(
    output_dir: Path,
    views_payload: dict[str, Any],
    graph: dict[str, Any],
    animation_plan: dict[str, Any],
    *,
    project_root: Path | None = None,
    exploded_state: dict[str, Any] | None = None,
    assets: dict[str, Any] | None = None,
    review_queue: list[dict[str, Any]] | None = None,
) -> Path:
    """Write a self-contained HTML inspection page with relative links only."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    views = [str(view) for view in views_payload.get("views", [])]
    view_cards = "\n".join(
        f'<figure><img src="../explosion_validation/{html.escape(view, quote=True)}" '
        f'alt="{html.escape(view)}"><figcaption>{html.escape(view)}</figcaption></figure>'
        for view in views
    )
    order = graph.get("topological_order", [])
    edges = graph.get("edges", [])
    queue = review_queue or []
    state = exploded_state or {}
    parts = state.get("parts", {}) if isinstance(state, dict) else {}
    rows = []
    if isinstance(parts, dict):
        for part_id in sorted(parts):
            record = parts[part_id]
            rows.append(
                "<tr>"
                f"<td>{html.escape(part_id)}</td>"
                f"<td>{html.escape(str(record.get('semantic_name', 'UNKNOWN')))}</td>"
                f"<td>{html.escape(str(record.get('assembly_group', 'UNKNOWN')))}</td>"
                f"<td>{html.escape(str(record.get('explode_vector', '')))}</td>"
                f"<td>{html.escape(str(record.get('explode_distance_mm', '')))} mm</td>"
                f"<td>{html.escape(str(record.get('collision_check', '')))}</td>"
                "</tr>"
            )
    edge_rows = "\n".join(
        f"<li>{html.escape(str(edge.get('before')))} → {html.escape(str(edge.get('after')))} "
        f"({html.escape(str(edge.get('confidence', 'UNKNOWN')))}, "
        f"manual={html.escape(str(edge.get('requires_manual_confirmation', True)))})</li>"
        for edge in edges
    )
    queue_rows = "\n".join(
        f"<tr><td>{html.escape(str(row.get('part')))}</td>"
        f"<td>{html.escape(str(row.get('semantic_name')))}</td>"
        f"<td>{html.escape(str(row.get('confidence')))}</td>"
        f"<td>{html.escape(str(row.get('review_question')))}</td></tr>"
        for row in queue[:100]
    )
    asset_count = (assets or {}).get("feature_count", 0)
    plan_json = html.escape(str(animation_plan.get("animation_created", False)))
    data_root = Path(project_root) / "data" if project_root is not None else output.parent / "data"
    data_href = html.escape(os.path.relpath(data_root, output), quote=True)
    content = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Task 9A Explosion Review</title>
<style>
body{{font:14px system-ui,sans-serif;background:#f4f6f8;color:#18212b;margin:24px}}
main{{max-width:1440px;margin:auto}} section{{background:#fff;border:1px solid #d9e0e7;border-radius:10px;padding:16px;margin:16px 0}}
.views{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}} figure{{margin:0}} img{{width:100%;background:#eef1f4;border-radius:6px}} figcaption{{padding:6px 0;color:#53606d}}
table{{border-collapse:collapse;width:100%;font-size:12px}} th,td{{border-bottom:1px solid #e4e9ee;padding:6px;text-align:left;vertical-align:top}} th{{background:#f0f3f6}}
code{{background:#eef1f4;padding:2px 4px;border-radius:4px}} .warn{{color:#9b3d00}}
</style></head><body><main>
<h1>Task 9A — Exploded Assembly Review</h1>
<p><code>Inspection only</code>; no animation keyframes, mesh edits, materials, or final render were created.</p>
<section><h2>Validation views</h2><div class="views">{view_cards}</div></section>
<section><h2>Plan status</h2><p>FPS: {html.escape(str(animation_plan.get('fps', '')))} · Frames: {html.escape(str(animation_plan.get('frame_range', '')))} · animation_created: <code>{plan_json}</code></p>
<p>Collision pairs: {html.escape(str(animation_plan.get('collision_count', '')))} · Future visual assets: {asset_count}</p>
<p>Data: <a href="{data_href}/exploded_state.json">exploded_state.json</a> · <a href="{data_href}/explosion_guides.json">explosion_guides.json</a> · <a href="{data_href}/animation_plan.json">animation_plan.json</a> · <a href="{data_href}/explosion_review_queue.csv">explosion_review_queue.csv</a></p></section>
<section><h2>Disassembly order</h2><ol>{''.join(f'<li>{html.escape(str(node))}</li>' for node in order)}</ol><h3>Dependency edges</h3><ul>{edge_rows}</ul></section>
<section><h2>PART movement plan</h2><table><thead><tr><th>PART</th><th>Semantic</th><th>Group</th><th>Direction</th><th>Distance</th><th>Collision</th></tr></thead><tbody>{''.join(rows)}</tbody></table></section>
<section><h2>Manual review queue</h2><table><thead><tr><th>PART</th><th>Semantic</th><th>Confidence</th><th>Question</th></tr></thead><tbody>{queue_rows}</tbody></table></section>
</main></body></html>
"""
    page = output / "index.html"
    page.write_text(content, encoding="utf-8")
    return page
