"""Bake TEX42_* board-surface textures — STEP 4 surface pass.

Everything is photo-derived; nothing is procedurally invented:

  1. soldermask green, mottled by the real photo's green luminance
  2. under-mask detail: high-pass luminance of green regions at LOW
     contrast — carries the real trace/ground-pour impressions
  3. real vias: blob-detected dark dots on green → ring + centre
  4. real pads/solder: blob-detected bright-metal dots on green
  5. real silkscreen: thin white features (text, arrows, outlines)
  6. flat stickers/labels baked as light-grey patches
  7. plated rings around registered hole positions

Also bakes close-region textures for the A module top and the coil
daughterboard top (real silkscreen/logo/vias straight from the photo,
with geometry-covered areas neutralised to avoid double-images).

Run: .venv/bin/python scripts/bake_textures_v42.py
"""
import json
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parents[1]
REG = HERE / "registration"
TEX = HERE / "textures"
TEX.mkdir(exist_ok=True)

BMAP = json.loads((REG / "board_map.json").read_text())["detail"]
def board_size(key):
    return BMAP[key]["board_size_px"]            # [w_mm, h_mm]

# hole sets — must match build_pcb_v4.py (board-centred mm)
A_HOLES = [(-41.46, -0.03, 3.07), (40.28, -1.35, 3.34),
           (-32, 43.0, 2.2), (23, 44.0, 2.2),
           (-45.5, 0.5, 2.2), (44, 0.5, 2.2),
           (-24, -42.0, 2.2), (23, -42.5, 2.2),
           (-38, 36, 2.0), (38, 40, 2.0), (-46, -22, 2.0), (46, -30, 2.0)]
A_SLOT = (28, -14, 14, 8, -0.5)
B_HOLES = [(-0.97, -0.16, 2.3),
           (-23, 20, 2.0), (23, 20, 2.0),
           (-23, -20, 2.0), (23, -19, 2.0), (-26.5, 0, 2.0)]

GREEN_LO, GREEN_HI = (30, 30, 15), (95, 255, 255)


def photo(reg_png, tw, th):
    img = cv2.imread(str(reg_png))
    return cv2.resize(img, (tw, th))


def masks(img):
    """green / thin-white-silk / flat-label / via / pad masks."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    green = cv2.inRange(hsv, GREEN_LO, GREEN_HI)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    white = ((hsv[:, :, 2] > 150) & (hsv[:, :, 1] < 80)).astype(np.uint8) * 255
    white = cv2.morphologyEx(white, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))

    silk = np.zeros_like(white)
    label = np.zeros_like(white)
    n, lab, st, _ = cv2.connectedComponentsWithStats(white)
    for i in range(1, n):
        x, y, w_, h_, a = st[i]
        thin = min(w_, h_) <= 26 and a < 1400          # strokes / text / marks
        flat = a < 14000 and a / max(1, w_ * h_) > 0.6  # solid light patches
        if thin:
            silk[lab == i] = 255
        elif flat:
            label[lab == i] = 255

    # vias: small dark blobs sitting on green
    green_d = cv2.dilate(green, np.ones((7, 7), np.uint8))
    dark = ((gray < 118) & (green_d > 0)).astype(np.uint8) * 255
    via = np.zeros_like(white)
    n, lab, st, _ = cv2.connectedComponentsWithStats(dark)
    for i in range(1, n):
        x, y, w_, h_, a = st[i]
        if 2 <= a <= 46 and max(w_, h_) <= 9 and a / max(1, w_ * h_) > 0.45:
            via[lab == i] = 255

    # exposed metal pads / solder dots: small bright blobs on green
    brt = ((gray > 150) & (hsv[:, :, 1] < 110) &
           (green_d > 0)).astype(np.uint8) * 255
    pad = np.zeros_like(white)
    n, lab, st, _ = cv2.connectedComponentsWithStats(brt)
    for i in range(1, n):
        x, y, w_, h_, a = st[i]
        if 3 <= a <= 260 and max(w_, h_) <= 26:
            pad[lab == i] = 255
    pad[white > 0] = 0                               # not already-classified white
    return green, silk, label, via, pad, gray


def bake(name, size_mm, holes, slot, reg_png, res=2048):
    bw, bh = size_mm
    w, h = res, int(res * bh / bw)
    pxmm = w / bw
    img = photo(reg_png, w, h)
    green, silk, label, via, pad, gray = masks(img)

    # 1. mottled soldermask — photo green luminance, highlights clipped
    gm = cv2.bitwise_and(gray, gray, mask=green)
    gvals = gm[green > 0]
    clip = np.percentile(gvals, 85)
    gm = np.clip(gm, 0, clip)
    mott = cv2.GaussianBlur(gm, (0, 0), 6)

    base = np.zeros((h, w, 3), np.float32)
    base[:, :] = (52, 138, 64)[::-1]
    v = 0.82 + (mott.astype(np.float32) / 255.0) * 0.36
    base *= v[:, :, None]

    # 2. real under-mask detail — high-pass photo detail on green, subtle
    blur = cv2.GaussianBlur(gray.astype(np.float32), (0, 0), 9)
    hp = (gray.astype(np.float32) - blur) / 255.0
    detail = 1.0 + np.clip(hp * 0.55, -0.28, 0.22)
    detail[green == 0] = 1.0
    base *= detail[:, :, None]

    # 3. real vias — dark ring + shadowed hole centre
    vy, vx = np.nonzero(via)
    n, lab, st, cent = cv2.connectedComponentsWithStats(via)
    for i in range(1, n):
        cx, cy = cent[i]
        r = max(1, int(0.14 * pxmm))
        cv2.circle(base, (int(cx), int(cy)), r + 1, (30, 70, 28), -1)
        cv2.circle(base, (int(cx), int(cy)), r, (16, 40, 15), -1)

    # 4. exposed pads / solder — cool metal
    n, lab, st, cent = cv2.connectedComponentsWithStats(pad)
    for i in range(1, n):
        cv2.ellipse(base, (int(cent[i][0]), int(cent[i][1])),
                    (max(1, int(st[i][2] / 2)), max(1, int(st[i][3] / 2))),
                    0, 0, 360, (152, 160, 154), -1)

    # 5. flat labels/stickers
    base[label > 0] = (188, 193, 186)

    # 6. plated rings + slot rim
    def mx(xmm):
        return int((xmm + bw / 2) * pxmm)

    def my(ymm):
        return int((bh / 2 - ymm) * pxmm)

    for hx, hy, hr in holes:
        cv2.circle(base, (mx(hx), my(hy)),
                   int(hr * pxmm) + int(0.8 * pxmm), (170, 178, 175),
                   int(0.7 * pxmm))
    if slot:
        sx, sy, sw_, sh_, srot = slot
        cv2.ellipse(base, (mx(sx), my(sy)),
                    (int(sw_ / 2 * pxmm) + int(0.8 * pxmm),
                     int(sh_ / 2 * pxmm) + int(0.8 * pxmm)),
                    np.degrees(-srot), 0, 360, (170, 178, 175),
                    int(0.7 * pxmm))

    # 7. real silkscreen on top
    base[silk > 0] = (196, 205, 200)

    out = TEX / f"{name}.png"
    cv2.imwrite(str(out), np.clip(base, 0, 255).astype(np.uint8))
    print(f"[bake42] {name} {w}x{h} silk={int((silk>0).sum())} "
          f"via={int((via>0).sum())} pad={int((pad>0).sum())}")
    return out


def mm_rect_mask(img, bw, bh, rects):
    """mask photo-px rects given in board-centred mm."""
    pxmm = img.shape[1] / bw
    m = np.zeros(img.shape[:2], np.uint8)
    for cx, cy, w_, h_ in rects:
        x0 = int((cx - w_ / 2 + bw / 2) * pxmm)
        y0 = int((bh / 2 - cy - h_ / 2) * pxmm)
        cv2.rectangle(m, (x0, y0), (x0 + int(w_ * pxmm), y0 + int(h_ * pxmm)),
                      255, -1)
    return m


def smt_field(name, reg_png, bw, bh, cell=1.0):
    """photo-guided SMT density grid (JSON, board-centred mm cells).

    component mask = on-board pixels that are neither soldermask-green
    nor white silk/label nor background wood.  Blurred -> per-cell
    density.  Cells ~fully covered (>0.82) are component *bodies*, not
    field — the builder skips them; mid-density fringes are where the
    real passive clusters live."""
    img = photo(reg_png, int(bw * 20), int(bh * 20))
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    green = cv2.inRange(hsv, GREEN_LO, GREEN_HI) > 0
    white = (hsv[:, :, 2] > 150) & (hsv[:, :, 1] < 80)
    wood = cv2.inRange(hsv, (5, 40, 60), (28, 255, 255)) > 0
    notwood = (~wood).astype(np.uint8) * 255
    cnts, _ = cv2.findContours(notwood, cv2.RETR_EXTERNAL,
                               cv2.CHAIN_APPROX_SIMPLE)
    board = np.zeros(notwood.shape, np.uint8)
    cv2.drawContours(board, [max(cnts, key=cv2.contourArea)], -1, 255, -1)
    board = cv2.erode(board, np.ones((25, 25), np.uint8))  # 1.2mm margin
    comp = (board > 0) & (~green) & (~white) & (hsv[:, :, 2] > 25)
    dens = cv2.GaussianBlur(comp.astype(np.float32), (0, 0), 14)

    w, h = img.shape[1], img.shape[0]
    pxmm = w / bw
    cs = max(4, int(cell * pxmm))
    cells = []
    for j in range(0, h - cs, cs):
        for i in range(0, w - cs, cs):
            d = float(dens[j:j + cs, i:i + cs].mean())
            if d > 0.10:
                cells.append([round((i + cs / 2 - w / 2) / pxmm, 2),
                              round((h / 2 - j - cs / 2) / pxmm, 2),
                              round(d, 3)])
    out = TEX / f"smt_field_{name}.json"
    out.write_text(json.dumps({"cell_mm": cell, "cells": cells}))
    print(f"[field] {name}: {len(cells)} dense cells")
    return out


def bake_region(name, reg_png, board_mm, rect_mm, res, tone,
                neutral_mm=None, neutral_tone=None):
    """crop a board-mm rect out of the registered photo → flat texture.
    neutral_mm rects are painted over with the local base tone so geometry
    sitting there doesn't ghost."""
    img = cv2.imread(str(reg_png))
    bw, bh = board_mm
    pxmm = img.shape[1] / bw
    cx, cy, w_, h_ = rect_mm
    x0 = int((cx - w_ / 2 + bw / 2) * pxmm)
    y0 = int((bh / 2 - cy - h_ / 2) * pxmm)
    crop = img[y0:y0 + int(h_ * pxmm), x0:x0 + int(w_ * pxmm)].copy()
    cw, ch = res, int(res * h_ / w_)
    crop = cv2.resize(crop, (cw, ch))
    if neutral_mm:
        m = np.zeros(crop.shape[:2], np.uint8)
        for ncx, ncy, nw, nh in neutral_mm:
            nx = int((ncx - (cx - w_ / 2)) / w_ * cw)
            ny = int(((cy + h_ / 2) - ncy) / h_ * ch)
            cv2.rectangle(m, (int(nx - nw / w_ * cw / 2), int(ny - nh / h_ * ch / 2)),
                          (int(nx + nw / w_ * cw / 2), int(ny + nh / h_ * ch / 2)),
                          255, -1)
        crop[m > 0] = neutral_tone or tone
    out = TEX / f"{name}.png"
    cv2.imwrite(str(out), crop)
    print(f"[bake42] {name} {cw}x{ch}")
    return out


def main():
    a_mm = tuple(board_size("a_front"))
    b_mm = tuple(board_size("b_front"))
    bake("TEX42_pcb_a_front", a_mm, A_HOLES, A_SLOT,
         REG / "registered_a_front.png")
    bake("TEX42_pcb_a_back", a_mm, A_HOLES, A_SLOT,
         REG / "registered_a_back.png", res=2048)
    bake("TEX42_pcb_b_front", b_mm, B_HOLES, None,
         REG / "registered_b_front.png")
    bake("TEX42_pcb_b_back", b_mm, B_HOLES, None,
         REG / "registered_b_back.png", res=2048)

    for tag, mm_ in (("a_front", a_mm), ("a_back", a_mm),
                     ("b_front", b_mm), ("b_back", b_mm)):
        smt_field(tag, REG / f"registered_{tag}.png", *mm_)

    # A module top surface — real photo crop; geometry-covered rects
    # (ICs, labels, icons, screws, cable, glue) painted to module tone.
    bake_region("TEX42_mod_top", REG / "registered_a_front.png", a_mm,
                (-2.1, 29.8, 42.6, 30.1), 1024, (30, 30, 32),
                neutral_mm=[
                    (-17.4, 31.75, 7.6, 10.4), (-10.25, 31.75, 7.6, 10.4),
                    (-13.5, 20.75, 13.8, 11.3), (0.5, 31.6, 15.8, 19.8),
                    (13.2, 38, 4.6, 5.6), (13.2, 30, 4.6, 5.6),
                    (13.2, 22.5, 4.6, 5.6), (10.2, 18.2, 5.6, 3.8),
                    (16.8, 26.5, 3.6, 4.6),
                    (1.6, 18.6, 12.5, 4.0), (1.75, 21.4, 12.0, 3.2),
                    (-13.5, 41.5, 5.0, 5.0), (-7.9, 39.7, 6.5, 6.5),
                    (-1.9, 39.4, 4.2, 4.2), (8.9, 27.5, 5.5, 5.5),
                    (-21.8, 44.2, 5, 5), (18.3, 44.2, 5, 5),
                    (-21.8, 15.5, 5, 5), (16.5, 15.5, 5, 5),
                    (7.5, 42, 3.0, 12.0), (10.5, 33, 3.0, 10.0)])

    # daughterboard top surface — real logo/pads/SN/marks straight from
    # the photo; coil disc painted flat so the geometric coil sits clean.
    bake_region("TEX42_db_top", REG / "registered_a_front.png", a_mm,
                (3.0, -29.0, 27.0, 41.0), 512, (18, 60, 26),
                neutral_mm=[(0.1, -36.4, 15.5, 15.5)])


if __name__ == "__main__":
    main()
