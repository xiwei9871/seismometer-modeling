"""Photo-match region overlays for the A-board STEP 2/3 features.

Crops a feature rectangle out of the registered A-front photo and the
v41 top-down render (both aligned by their green board masks), writes a
reference crop, a matched render crop and a 50/50 overlay per region,
plus a contact sheet for the module review set.

Outputs into validation_v41/:
  A_<region>_reference_crop.png / A_<region>_render_match.png /
  A_<region>_overlay.png        for region in module, antenna, coil
  A_module_contact_sheet.png    six-image STEP2 review sheet

Run: .venv/bin/python scripts/compare_module_v41.py
"""
import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parents[1]
REG = HERE / "registration"
REN = HERE / "renders_v41"
OUT = HERE / "validation_v41"

# board-local mm rects (x_min, x_max, y_min, y_max) — measured on
# registered_a_front; each includes the feature + a small margin
REGIONS = {
    "module":   (-23.5, 20.5, 14.5, 45.5),
    "antenna":  (-35.5, -9.0, -43.5, -17.0),
    "coil":     (-12.0, 18.5, -50.5, -8.0),
}


def green_mask(img):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    m = cv2.inRange(hsv, (30, 30, 15), (95, 255, 255))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return m, max(cnts, key=cv2.contourArea)


def crop_mm(img, board_w_mm, board_h_mm, rect_mm):
    """crop a board-local mm rect from an image whose board fills bbox."""
    _, cnt = green_mask(img)
    bx, by, bw, bh = cv2.boundingRect(cnt)
    pxmm_x, pxmm_y = bw / board_w_mm, bh / board_h_mm
    x0, x1, y0, y1 = rect_mm
    px0 = int(bx + (x0 + board_w_mm / 2) * pxmm_x)
    px1 = int(bx + (x1 + board_w_mm / 2) * pxmm_x)
    py0 = int(by + (board_h_mm / 2 - y1) * pxmm_y)
    py1 = int(by + (board_h_mm / 2 - y0) * pxmm_y)
    return img[max(0, py0):py1, max(0, px0):px1]


def contact_sheet(paths, out):
    imgs = [cv2.imread(str(p)) for p in paths]
    h = 560
    imgs = [cv2.resize(i, (int(i.shape[1] * h / i.shape[0]), h))
            for i in imgs]
    gap = np.full((h, 12, 3), 24, np.uint8)
    rows = []
    for row in (imgs[:3], imgs[3:]):
        joined = row[0]
        for im in row[1:]:
            joined = np.hstack([joined, gap, im])
        rows.append(joined)
    w = max(r.shape[1] for r in rows)
    rows = [np.hstack([r, np.full((h, w - r.shape[1], 3), 24, np.uint8)])
            for r in rows]
    sheet = np.vstack([rows[0], np.full((12, w, 3), 24, np.uint8), rows[1]])
    cv2.imwrite(str(out), sheet)


def main():
    OUT.mkdir(exist_ok=True)
    photo = cv2.imread(str(REG / "registered_a_front.png"))
    render = cv2.imread(str(REN / "v41_topdown_a_front.png"))
    if render is None:
        sys.exit("missing renders_v41/v41_topdown_a_front.png")

    for tag, rect in REGIONS.items():
        pc = crop_mm(photo, 104.0, 101.1, rect)
        rc = crop_mm(render, 104.0, 101.1, rect)
        if rc.size == 0 or pc.size == 0:
            print(f"[{tag}] empty crop — skipped")
            continue
        rc = cv2.resize(rc, (pc.shape[1], pc.shape[0]))
        overlay = cv2.addWeighted(pc, 0.5, rc, 0.5, 0)
        cv2.rectangle(overlay, (2, 2), (overlay.shape[1] - 3,
                      overlay.shape[0] - 3), (0, 255, 255), 2)
        cv2.imwrite(str(OUT / f"A_{tag}_reference_crop.png"), pc)
        cv2.imwrite(str(OUT / f"A_{tag}_render_match.png"), rc)
        cv2.imwrite(str(OUT / f"A_{tag}_overlay.png"), overlay)
        print(f"[{tag}] wrote reference/render/overlay crops")

    sheet_imgs = [OUT / "A_module_reference_crop.png",
                  OUT / "A_module_render_match.png",
                  OUT / "A_module_overlay.png",
                  REN / "01_A_module_topdown.png",
                  REN / "02_A_module_3quarter.png",
                  REN / "03_A_module_closeup.png"]
    contact_sheet(sheet_imgs, OUT / "A_module_contact_sheet.png")
    print("[module] wrote A_module_contact_sheet.png")


if __name__ == "__main__":
    main()
