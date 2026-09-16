"""STEP 5 regression compare — diff state_v42.json vs state_v43.json.

Writes validation_v43/regression_report.json + regression_report.md.
Plain python, no blender:
  python3 scripts/compare_state_v43.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VAL = ROOT / "validation_v43"
a = json.loads((VAL / "state_v42.json").read_text())
b = json.loads((VAL / "state_v43.json").read_text())

TOL = 1e-3
# documented STEP-4 placement bugfix (see LOOKDEV_V43_NOTES):
KNOWN_FIXES = {"B_BK_CAP1", "B_BK_CAP1_TOP", "B_BK_CAP2", "B_BK_CAP2_TOP"}
issues, added, removed = [], [], []

for name, rec_a in a["objects"].items():
    rec_b = b["objects"].get(name)
    if rec_b is None:
        if rec_a.get("type") != "LIGHT":
            removed.append(name)
        continue
    for k in ("loc", "rot", "scale", "bbox_min", "bbox_max"):
        if k not in rec_a or k not in rec_b:
            continue
        d = max(abs(x - y) for x, y in zip(rec_a[k], rec_b[k]))
        if d > TOL and name not in KNOWN_FIXES:
            issues.append(f"{name}.{k}: max diff {d:.5f} "
                          f"{rec_a[k]} vs {rec_b[k]}")
    for k in ("verts", "uv_layers", "uv_sig"):
        if rec_a.get(k) != rec_b.get(k):
            issues.append(f"{name}.{k}: {rec_a.get(k)} vs {rec_b.get(k)}")

for name, rec_b in b["objects"].items():
    if name not in a["objects"] and rec_b.get("type") != "LIGHT":
        added.append(name)

cam_issues = []
for name, rec_a in a["cameras"].items():
    rec_b = b["cameras"].get(name)
    if rec_b is None:
        cam_issues.append(f"{name}: MISSING in v43")
        continue
    for k in ("loc", "rot"):
        d = max(abs(x - y) for x, y in zip(rec_a[k], rec_b[k]))
        if d > TOL:
            cam_issues.append(f"{name}.{k}: diff {d:.5f}")
    if abs(rec_a["lens"] - rec_b["lens"]) > TOL:
        cam_issues.append(f"{name}.lens: {rec_a['lens']} vs {rec_b['lens']}")

report = {
    "frozen_object_count_v42": len(a["objects"]),
    "geometry_diffs": issues,
    "objects_removed": removed,
    "objects_added": added,
    "camera_regressions": cam_issues,
    "verdict": "PASS" if not (issues or removed or cam_issues) else "FAIL",
}
(VAL / "regression_report.json").write_text(json.dumps(report, indent=1))
md = ["# STEP 5 geometry/camera/UV regression (v42 -> v43)",
      f"verdict: **{report['verdict']}**",
      f"frozen objects checked: {len(a['objects'])}",
      f"geometry diffs: {len(issues)}  removed: {len(removed)}",
      f"camera regressions: {len(cam_issues)}", "", "## diffs"]
md += [f"- {i}" for i in issues[:80]]
md += ["", "## removed"] + [f"- {i}" for i in removed]
md += ["", "## added (expected: lights/cams/swatches only)"]
md += [f"- {i}" for i in added]
md += ["", "## camera regressions"] + [f"- {i}" for i in cam_issues]
(VAL / "regression_report.md").write_text("\n".join(md))
print(json.dumps({"verdict": report["verdict"], "diffs": len(issues),
                  "added": len(added), "removed": len(removed),
                  "cam": len(cam_issues)}))
