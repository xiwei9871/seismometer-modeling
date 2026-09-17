"""Precompute board meshes via earcut (runs in .venv — cv2 + mapbox_earcut).

Blender's curve tessellator fails on the traced contours (findContours can
self-touch at 1px necks), so triangulation happens here where we control it:
outer ring + hole/slot rings -> earcut -> board_mesh.json consumed by
build_pcb_v4.py.

Run: .venv/bin/python scripts/precompute_board_geometry.py
"""
import json
import math
from pathlib import Path

import cv2
import numpy as np
import mapbox_earcut as earcut

HERE = Path(__file__).resolve().parents[1]
REG = HERE / "registration"

BMAP = json.loads((REG / "board_map.json").read_text())["detail"]

# hole sets must match build_pcb_v4.py / bake_textures_v4.py (centred mm)
# v44: corrected against the AI-revised top view — hole4 merged into hole0,
# hole11 moved onto the real large cutout, kidney slot removed (no slot in
# the corrected image), bottom-edge holes added/snapped
A_HOLES = [(-45.6, 2.6, 3.0), (47.8, -12.8, 3.1), (46.0, 3.2, 2.9),
           (32.9, -24.4, 5.0),
           (-39.0, 38.0, 2.0), (-26.7, 42.7, 2.2), (23.0, 44.0, 2.2),
           (43.0, 29.0, 2.0),
           (-46.0, -22.0, 2.0), (-24.0, -42.0, 2.2), (28.1, -43.7, 2.2),
           (-29.3, -48.2, 2.2)]
A_SLOT = None

B_HOLES = [(-0.97, -0.16, 2.3),
           (-23, 20, 2.0), (23, 20, 2.0),
           (-23, -20, 2.0), (23, -19, 2.0), (-26.5, 0, 2.0)]


def outline_centered(key):
    d = BMAP[key]
    w, h = d["board_size_px"]
    return [(x - w / 2, h / 2 - y) for x, y in d["outline_points_mm"]], (w, h)


def ring(cx, cy, rx, ry, rot=0.0, n=28):
    pts = []
    for i in range(n):
        a = 2 * math.pi * i / n
        ux, uy = rx * math.cos(a), ry * math.sin(a)
        pts.append((cx + ux * math.cos(rot) - uy * math.sin(rot),
                    cy + ux * math.sin(rot) + uy * math.cos(rot)))
    return pts


def inside(outline, pts):
    """all ring points strictly inside the traced outline?"""
    cnt = np.array(outline, np.float32)
    return all(cv2.pointPolygonTest(cnt, p, False) > 0 for p in pts)


def fit_ring(outline, cx, cy, rx, ry, rot=0.0):
    """perimeter holes sit in edge lobes — nudge the centre toward the
    board centroid until the ring fits inside the traced outline."""
    gx = sum(p[0] for p in outline) / len(outline)
    gy = sum(p[1] for p in outline) / len(outline)
    for scale in (1.0, 0.9, 0.8):
        for t in np.linspace(0.0, 0.18, 13):
            nx, ny = cx + (gx - cx) * t, cy + (gy - cy) * t
            r = ring(nx, ny, rx * scale, ry * scale, rot)
            if inside(outline, r):
                return r, (nx, ny, rx * scale)
    return None, (cx, cy, rx)


def build(key, holes, slot):
    outline, size = outline_centered(key)
    rings = [outline]
    dropped = []
    moved = []
    for hx, hy, hr in holes:
        r, fitted = fit_ring(outline, hx, hy, hr, hr)
        if r is not None:
            rings.append(r)
            if abs(fitted[0] - hx) > 0.3 or abs(fitted[1] - hy) > 0.3:
                moved.append((round(hx, 1), round(hy, 1), "->",
                              round(fitted[0], 1), round(fitted[1], 1)))
        else:
            dropped.append((hx, hy, hr))
    if slot:
        sx, sy, sw_, sh_, srot = slot
        r, _f = fit_ring(outline, sx, sy, sw_ / 2, sh_ / 2, srot)
        if r is not None:
            rings.append(r)
        else:
            dropped.append(("slot", sx, sy))

    verts = np.array([p for rg in rings for p in rg], np.float64)
    ends = np.cumsum([len(rg) for rg in rings]).astype(np.uint32)
    tris = earcut.triangulate_float64(verts, ends)
    if len(tris) == 0:
        raise RuntimeError(f"earcut failed on {key}")
    return {"outline": outline, "size": list(size),
            "verts": verts.tolist(), "ring_ends": ends.tolist(),
            "tris": tris.tolist(), "dropped": dropped, "moved": moved}


def main():
    out = {
        "a": build("a_front", A_HOLES, A_SLOT),
        "b": build("b_front", B_HOLES, None),
    }
    dst = REG / "board_mesh.json"
    dst.write_text(json.dumps(out))
    for k, v in out.items():
        print(f"[geom] {k}: {len(v['verts'])} verts, "
              f"{len(v['tris']) // 3} tris, dropped={v['dropped']}, "
              f"moved={v['moved']}")
    print(f"[geom] wrote {dst}")


if __name__ == "__main__":
    main()
