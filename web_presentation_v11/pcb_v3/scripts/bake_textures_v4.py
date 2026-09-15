"""Bake TEX4_* board-surface textures (runs in .venv — cv2 + numpy).

Layers per face:
  1. soldermask green, mottled by the real photo's green luminance
  2. faint real trace-shadows extracted from the photo
  3. procedural Manhattan routing + via field
  4. plated rings around registered hole positions
  5. REAL silkscreen extracted from the photo (thin white features only)

Run: .venv/bin/python scripts/bake_textures_v4.py
"""
import json
import math
import random
from pathlib import Path

import cv2
import numpy as np

random.seed(20260915)
HERE = Path(__file__).resolve().parents[1]
REG = HERE / "registration"
TEX = HERE / "textures"
TEX.mkdir(exist_ok=True)

BMAP = json.loads((REG / "board_map.json").read_text())["detail"]


def board_size(key):
    return BMAP[key]["board_size_px"]          # [w_mm, h_mm]


# hole sets must match build_pcb_v4.py (board-centred mm)
A_HOLES = [(-41.46, -0.03, 3.07), (40.28, -1.35, 3.34),
           (-32, 43.0, 2.2), (23, 44.0, 2.2),
           (-45.5, 0.5, 2.2), (44, 0.5, 2.2),
           (-24, -42.0, 2.2), (23, -42.5, 2.2),
           # additional plated perimeter holes read from the overlay
           (-38, 36, 2.0), (38, 40, 2.0), (-46, -22, 2.0), (46, -30, 2.0)]
A_SLOT = (28, -14, 14, 8, -0.5)
# the "white spiral" was a misread — the zone's real marks are a vertical
# SN label strip + a dark etched logo, both modelled as geometry, not
# baked into the board texture (the zone box would cover them anyway)
A_SPIRAL = None

B_HOLES = [(-0.97, -0.16, 2.3),
           (-23, 20, 2.0), (23, 20, 2.0),
           (-23, -20, 2.0), (23, -19, 2.0), (-26.5, 0, 2.0)]


def extract_layers(reg_png, tw, th):
    """silk (thin white), ridge (trace shadows), mott (green mottling)."""
    img = cv2.imread(str(reg_png))
    img = cv2.resize(img, (tw, th))
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    green = cv2.inRange(hsv, (30, 30, 15), (95, 255, 255))

    white = ((hsv[:, :, 2] > 150) & (hsv[:, :, 1] < 70)).astype(np.uint8) * 255
    white = cv2.morphologyEx(white, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    silk = np.zeros_like(white)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(white)
    for i in range(1, n):
        x, y, w_, h_, a = stats[i]
        if min(w_, h_) <= 14 and a < 320:        # thin strokes only
            silk[lab == i] = 255

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (0, 0), 3)
    ridge = cv2.subtract(blur, gray)
    ridge[green == 0] = 0
    ridge = cv2.normalize(ridge, None, 0, 255, cv2.NORM_MINMAX)

    gonly = cv2.bitwise_and(gray, gray, mask=green)
    mott = cv2.GaussianBlur(gonly, (0, 0), 6)
    mott[green == 0] = 0
    return silk, ridge, mott


def draw_ring(img, cx, cy, r, w_, color):
    cv2.circle(img, (cx, cy), r, color, w_)


def bake(name, size_mm, holes, slot, side, reg_png, res=2048, spiral=None):
    bw, bh = size_mm
    w, h = res, int(res * bh / bw)
    pxmm = w / bw

    silk, ridge, mott = extract_layers(reg_png, w, h)

    # 1. mottled soldermask
    base = np.zeros((h, w, 3), np.float32)
    base[:, :] = (52, 142, 66)[::-1]             # BGR — vivid soldermask
    v = 0.85 + (mott.astype(np.float32) / 255.0) * 0.3
    base *= v[:, :, None]

    # 2. real trace shadows
    mask = ridge > 26
    base[mask] *= np.array([0.72, 0.80, 0.74], np.float32)

    # 3. procedural Manhattan routing + vias
    n_tr = 900 if side == "front" else 500
    for _ in range(n_tr):
        x, y = random.randint(0, w - 1), random.randint(0, h - 1)
        ang = random.choice([0.0, math.pi / 2, math.pi / 4, -math.pi / 4])
        seg = random.randint(40, 200)
        cv2.line(base, (x, y),
                 (int(x + seg * math.cos(ang)), int(y + seg * math.sin(ang))),
                 (29, 78, 23), max(1, int(pxmm * 0.09)))
    for _ in range(900):
        x, y = random.randint(0, w - 1), random.randint(0, h - 1)
        r = max(1, int(pxmm * 0.14))
        cv2.circle(base, (x, y), r + 1, (58, 92, 70), -1)
        cv2.circle(base, (x, y), r, (20, 48, 18), -1)

    # 4. plated rings + slot rim
    def mx(xmm):
        return int((xmm + bw / 2) * pxmm)

    def my(ymm):
        return int((bh / 2 - ymm) * pxmm)

    for hx, hy, hr in holes:
        draw_ring(base, mx(hx), my(hy),
                  int(hr * pxmm) + int(0.8 * pxmm), int(0.7 * pxmm),
                  (170, 178, 175))
    if slot:
        sx, sy, sw_, sh_, srot = slot
        cv2.ellipse(base, (mx(sx), my(sy)),
                    (int(sw_ / 2 * pxmm) + int(0.8 * pxmm),
                     int(sh_ / 2 * pxmm) + int(0.8 * pxmm)),
                    math.degrees(-srot), 0, 360, (170, 178, 175),
                    int(0.7 * pxmm))

    # 5. real silkscreen
    base[silk > 128] = (198, 208, 205)

    # 6. signature printed spiral (A front only) — concentric arcs with a
    # radial stub, matching the photo's white spiral on the daughter zone
    if spiral is not None:
        scx, scy, r_in, r_out = spiral
        px, py = mx(scx), my(scy)
        turns, steps = 4, 200
        prev = None
        for i in range(steps + 1):
            t = i / steps
            ang = 2 * math.pi * turns * t
            rr = (r_in + (r_out - r_in) * t) * pxmm
            pt = (int(px + rr * math.cos(ang)), int(py - rr * math.sin(ang)))
            if prev:
                cv2.line(base, prev, pt, (195, 205, 195),
                         max(1, int(pxmm * 0.18)))
            prev = pt
        cv2.circle(base, (px, py), int(r_in * pxmm), (195, 205, 195),
                   max(1, int(pxmm * 0.18)))

    out = TEX / f"{name}.png"
    cv2.imwrite(str(out), np.clip(base, 0, 255).astype(np.uint8))
    print(f"[bake] {name} {w}x{h}  silk_px={int((silk>128).sum())}")
    return out


def main():
    bake("TEX4_pcb_a_front", board_size("a_front"), A_HOLES, A_SLOT,
         "front", REG / "registered_a_front.png", spiral=A_SPIRAL)
    bake("TEX4_pcb_a_back", board_size("a_back"), A_HOLES, A_SLOT,
         "back", REG / "registered_a_back.png", res=1024)
    bake("TEX4_pcb_b_front", board_size("b_front"), B_HOLES, None,
         "front", REG / "registered_b_front.png")
    bake("TEX4_pcb_b_back", board_size("b_back"), B_HOLES, None,
         "back", REG / "registered_b_back.png", res=1024)


if __name__ == "__main__":
    main()
