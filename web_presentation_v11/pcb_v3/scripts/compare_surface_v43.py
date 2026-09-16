"""STEP 5 surface validation — 4-face photo/render/overlay + sheet.

Whole-board alignment per face: the registered photo and the matched
top-down render are each cropped to their green board mask, resized to
the same size, and blended 50/50.  Backs are page-flip matched already
(the render flips the board about world Y, same as the photo).

Outputs validation_v43/:
  {A,B}_{front,back}_{reference,render,overlay}.png
  12_surface_contact_sheet.png

Run: .venv/bin/python scripts/compare_surface_v42.py
"""
import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parents[1]
REG = HERE / "registration"
REN = HERE / "renders_v43"
OUT = HERE / "validation_v43"

FACES = [("A_front", "registered_a_front.png", "04_A_front_final.png"),
         ("A_back", "registered_a_back.png", "05_A_back_final.png"),
         ("B_front", "registered_b_front.png", "06_B_front_final.png"),
         ("B_back", "registered_b_back.png", "07_B_back_final.png")]


def board_crop(img):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    m = cv2.inRange(hsv, (30, 30, 15), (95, 255, 255))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    x, y, w, h = cv2.boundingRect(max(cnts, key=cv2.contourArea))
    return img[y:y + h, x:x + w]


def main():
    OUT.mkdir(exist_ok=True)
    tiles = []
    for tag, ref_png, ren_png in FACES:
        photo = cv2.imread(str(REG / ref_png))
        render = cv2.imread(str(REN / ren_png))
        if photo is None or render is None:
            sys.exit(f"missing input for {tag}")
        pc, rc = board_crop(photo), board_crop(render)
        rc = cv2.resize(rc, (pc.shape[1], pc.shape[0]))
        overlay = cv2.addWeighted(pc, 0.5, rc, 0.5, 0)
        cv2.rectangle(overlay, (2, 2), (overlay.shape[1] - 3,
                      overlay.shape[0] - 3), (0, 255, 255), 2)
        cv2.imwrite(str(OUT / f"{tag}_reference.png"), pc)
        cv2.imwrite(str(OUT / f"{tag}_render.png"), rc)
        cv2.imwrite(str(OUT / f"{tag}_overlay.png"), overlay)
        tiles += [pc, rc, overlay]
        print(f"[{tag}] wrote reference/render/overlay")

    h = 420
    tiles = [cv2.resize(t, (int(t.shape[1] * h / t.shape[0]), h))
             for t in tiles]
    gap = np.full((h, 10, 3), 24, np.uint8)
    rows = []
    for r in range(4):
        row = tiles[r * 3]
        for t in tiles[r * 3 + 1:r * 3 + 3]:
            row = np.hstack([row, gap, t])
        rows.append(row)
    w = max(r.shape[1] for r in rows)
    rows = [np.hstack([r, np.full((h, w - r.shape[1], 3), 24, np.uint8)])
            for r in rows]
    sheet = rows[0]
    for r in rows[1:]:
        sheet = np.vstack([sheet, np.full((10, w, 3), 24, np.uint8), r])
    cv2.imwrite(str(OUT / "12_surface_contact_sheet.png"), sheet)
    print("[sheet] wrote 12_surface_contact_sheet.png")


if __name__ == "__main__":
    main()
