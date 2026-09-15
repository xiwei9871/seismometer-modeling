"""Phase A2.1 — 2D registration of the four real PCB photos.

Pipeline per photo:
  1. segment green soldermask (HSV) -> board mask
  2. largest contour -> outline polygon
  3. minAreaRect -> perspective-rectified top-down image
  4. inside board: dark-blob holes (HoughCircles + dark contours),
     non-green blobs -> component bboxes classified black/white/metal
  5. overlay image with confidence labels
  6. front/back validation: hole sets compared after horizontal flip

Outputs into registration/: registered_*.png, overlay_*.png,
outline_*.svg, board_map.json, registration_report.md
"""
import json
import math
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parents[1]
REF = HERE / "reference"
OUT = HERE / "registration"
OUT.mkdir(exist_ok=True)

# assumed real widths (mm) — flagged ASSUMED, to be confirmed by human
ASSUMED_W = {"a": 104.0, "b": 62.0}

PHOTOS = {
    "a_front": REF / "photo_pcb_a_front.jpg",
    "a_back": REF / "photo_pcb_a_back.jpg",
    "b_front": REF / "photo_pcb_b_front.jpg",
    "b_back": REF / "photo_pcb_b_back.jpg",
}


def board_mask(img):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    m = cv2.inRange(hsv, (30, 35, 20), (95, 255, 255))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cnt = max(cnts, key=cv2.contourArea)
    filled = np.zeros(m.shape, np.uint8)
    cv2.drawContours(filled, [cnt], -1, 255, -1)
    # raw: segmented mask restricted to the board contour — keeps
    # through-holes / component voids open for detection
    raw = m & filled
    return filled, raw, cnt


def rectify(img, filled, raw, out_w):
    cnts, _ = cv2.findContours(filled, cv2.RETR_EXTERNAL,
                               cv2.CHAIN_APPROX_SIMPLE)
    cnt = max(cnts, key=cv2.contourArea)
    rect = cv2.minAreaRect(cnt)          # centre, (w,h), angle
    box = cv2.boxPoints(rect)
    (w, h) = rect[1]
    if w < h:
        box = np.roll(box, 1, axis=0)
        w, h = h, w
    out_h = int(out_w * h / w)
    dst = np.array([[0, 0], [out_w, 0], [out_w, out_h], [0, out_h]],
                   np.float32)
    # order box pts TL,TR,BR,BL
    s = box.sum(1)
    d = np.diff(box, 1).ravel()
    src = np.array([box[s.argmin()], box[d.argmin()], box[s.argmax()],
                    box[d.argmax()]], np.float32)
    M = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(img, M, (out_w, out_h))
    wf = cv2.warpPerspective(filled, M, (out_w, out_h))
    wr = cv2.warpPerspective(raw, M, (out_w, out_h))
    wcnt, _ = cv2.findContours(wf, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return warped, wf, wr, max(wcnt, key=cv2.contourArea), M


def detect_holes(warped, wf, wr, wcnt, pxmm):
    """Through-holes = voids inside the filled board mask (the table or
    dark interior shows through). Voids whose interior looks like a
    component (neutral dark IC, white connector) are rejected."""
    inner_voids = wf & ~wr

    holes, notches = [], []
    for c in cv2.findContours(inner_voids, cv2.RETR_EXTERNAL,
                              cv2.CHAIN_APPROX_SIMPLE)[0]:
        area = cv2.contourArea(c)
        r = math.sqrt(area / math.pi) / pxmm
        if not (0.9 < r < 9.0):
            continue
        (cx, cy), rr = cv2.minEnclosingCircle(c)
        circ = area / (math.pi * rr * rr + 1e-6)
        if circ < 0.6:
            continue
        # sample interior colour — through-holes are wood-warm or very dark
        ix, iy = int(cx), int(cy)
        rad = max(2, int(rr * 0.5))
        patch = warped[max(0, iy - rad):iy + rad, max(0, ix - rad):ix + rad]
        if patch.size == 0:
            continue
        b, g, rr_ = patch.reshape(-1, 3).mean(0)
        warm = rr_ > g + 8 and g >= b          # wood shows through
        dark = (b + g + rr_) / 3 < 50          # dark interior shadow
        if not (warm or dark):
            continue
        conf = min(0.95, 0.55 + circ * 0.4)
        holes.append({"x_mm": round(cx / pxmm, 2),
                      "y_mm": round(cy / pxmm, 2),
                      "r_mm": round(r, 2), "confidence": round(conf, 2)})

    # edge notches: convexity-defect-like deep indents of the outline
    hull = cv2.convexHull(wcnt, returnPoints=False)
    defects = cv2.convexityDefects(wcnt, hull) if len(hull) > 3 else None
    if defects is not None:
        for row in defects.reshape(-1, 4):
            s, e, f, depth = int(row[0]), int(row[1]), int(row[2]), int(row[3])
            d_mm = depth / 256.0 / pxmm
            if d_mm < 1.5:
                continue
            pt = wcnt[f][0]
            notches.append({"x_mm": round(pt[0] / pxmm, 2),
                            "y_mm": round(pt[1] / pxmm, 2),
                            "depth_mm": round(d_mm, 2),
                            "confidence": round(min(0.9, 0.4 + d_mm / 8), 2)})
    return holes, notches


def detect_components(warped, wmask, pxmm):
    """Non-soldermask blobs -> component bboxes, classified by tone."""
    hsv = cv2.cvtColor(warped, cv2.COLOR_BGR2HSV)
    inner = cv2.erode(wmask, np.ones((11, 11), np.uint8))
    green = cv2.inRange(hsv, (30, 35, 20), (95, 255, 255))
    notgreen = (~green.astype(bool)).astype(np.uint8) * 255 & inner
    notgreen = cv2.morphologyEx(notgreen, cv2.MORPH_OPEN,
                                np.ones((3, 3), np.uint8))
    comps = []
    for c in cv2.findContours(notgreen, cv2.RETR_EXTERNAL,
                              cv2.CHAIN_APPROX_SIMPLE)[0]:
        x, y, w, h = cv2.boundingRect(c)
        wm, hm = w / pxmm, h / pxmm
        area = cv2.contourArea(c) / (pxmm * pxmm)
        if not (3.0 < area < 1600.0) or wm > 60 or hm > 60:
            continue
        roi = warped[y:y + h, x:x + w]
        hsvr = hsv[y:y + h, x:x + w]
        mask_r = np.zeros((h, w), np.uint8)
        cv2.drawContours(mask_r, [c], -1, 255, -1, offset=(-x, -y))
        v = float(cv2.mean(hsvr[:, :, 2], mask=mask_r)[0])
        s = float(cv2.mean(hsvr[:, :, 1], mask=mask_r)[0])
        cls = ("white" if (v > 130 and s < 80)
               else "metal" if (v > 90 and s < 110)
               else "black")
        level = "A" if area > 90 else ("B" if area > 22 else "C")
        conf = round(min(0.95, 0.4 + area / 300.0 + (0.15 if level == "A" else 0)), 2)
        comps.append({"x_mm": (x + w / 2) / pxmm, "y_mm": (y + h / 2) / pxmm,
                      "w_mm": wm, "h_mm": hm, "class": cls, "level": level,
                      "confidence": conf})
    return comps


def draw_overlay(warped, cnt, holes, notches, comps, pxmm, out):
    vis = warped.copy()
    cv2.drawContours(vis, [cnt], -1, (0, 255, 255), 2)
    for h_ in holes:
        cx, cy = int(h_["x_mm"] * pxmm), int(h_["y_mm"] * pxmm)
        cv2.circle(vis, (cx, cy), int(h_["r_mm"] * pxmm), (0, 0, 255), 2)
        cv2.putText(vis, f'{h_["confidence"]:.2f}', (cx + 4, cy),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)
    for n in notches:
        nx, ny = int(n["x_mm"] * pxmm), int(n["y_mm"] * pxmm)
        cv2.circle(vis, (nx, ny), int(max(2, n["depth_mm"]) * pxmm),
                   (255, 0, 255), 1)
        cv2.putText(vis, "N", (nx - 3, ny), cv2.FONT_HERSHEY_SIMPLEX,
                    0.4, (255, 0, 255), 1)
    col = {"black": (60, 60, 255), "white": (255, 255, 0),
           "metal": (255, 160, 0)}
    for c in comps:
        x = int((c["x_mm"] - c["w_mm"] / 2) * pxmm)
        y = int((c["y_mm"] - c["h_mm"] / 2) * pxmm)
        cv2.rectangle(vis, (x, y),
                      (x + int(c["w_mm"] * pxmm), y + int(c["h_mm"] * pxmm)),
                      col[c["class"]], 2 if c["level"] == "A" else 1)
        if c["level"] == "A":
            cv2.putText(vis, f'{c["class"][:1].upper()}{c["confidence"]:.2f}',
                        (x, y - 3), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                        col[c["class"]], 1)
    cv2.imwrite(str(out), vis)


def contour_svg(cnt, pxmm, path):
    pts = " ".join(f"{p[0][0]/pxmm:.1f},{p[0][1]/pxmm:.1f}" for p in cnt)
    x0, y0, w_, h_ = cv2.boundingRect(cnt)
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" '
           f'viewBox="0 0 {w_/pxmm:.1f} {h_/pxmm:.1f}">'
           f'<polygon points="{pts}" fill="none" stroke="black"/>'
           f'</svg>')
    path.write_text(svg)


def main():
    result = {"assumed_widths_mm": ASSUMED_W, "boards": {}}
    data = {}
    for key, path in PHOTOS.items():
        board, side = key.split("_")
        img = cv2.imread(str(path))
        filled, raw, _cnt = board_mask(img)
        out_w = int(ASSUMED_W[board] * 20)        # 20 px/mm
        warped, wf, wr, wcnt, M = rectify(img, filled, raw, out_w)
        pxmm = 20.0
        cv2.imwrite(str(OUT / f"registered_{key}.png"), warped)

        holes, notches = detect_holes(warped, wf, wr, wcnt, pxmm)
        comps = detect_components(warped, wf, pxmm)
        draw_overlay(warped, wcnt, holes, notches, comps, pxmm,
                     OUT / f"overlay_{key}.png")
        if side == "front":
            contour_svg(wcnt, pxmm, OUT / f"outline_pcb_{board}.svg")

        bx, by, bw_, bh_ = cv2.boundingRect(wcnt)
        entry = {
            "board_size_px": [round(bw_ / pxmm, 1), round(bh_ / pxmm, 1)],
            "mm_per_px_assumed": round(ASSUMED_W[board] * pxmm / bw_, 3),
            "outline_points_mm": [
                [round(p[0][0] / pxmm, 1), round(p[0][1] / pxmm, 1)]
                for p in cv2.approxPolyDP(wcnt, 3.0, True)],
            "holes": holes,
            "edge_notches": notches,
            "components": comps,
        }
        data[key] = entry
        result["boards"].setdefault(board, {})[side] = {
            "size_mm": entry["board_size_px"],
            "hole_count": len(holes),
            "notch_count": len(notches),
            "component_count": len(comps),
            "components_A": sum(1 for c in comps if c["level"] == "A"),
        }

    # front/back hole registration: flip back x, compare hole sets
    for board in ("a", "b"):
        f = data.get(f"{board}_front", {})
        b = data.get(f"{board}_back", {})
        if not f or not b or not f["holes"] or not b["holes"]:
            continue
        w_mm = f["board_size_px"][0]
        fb = [(h_["x_mm"], h_["y_mm"]) for h_ in f["holes"]]
        bb = [(w_mm - h_["x_mm"], h_["y_mm"]) for h_ in b["holes"]]
        pairs, used = [], set()
        for fx, fy in fb:
            best, bd = None, 1e9
            for j, (bx, by) in enumerate(bb):
                if j in used:
                    continue
                d = math.hypot(fx - bx, fy - by)
                if d < bd:
                    bd, best = d, j
            if best is not None and bd < 6.0:
                used.add(best)
                pairs.append(round(bd, 2))
        result["boards"][board]["front_back_registration"] = {
            "matched_holes": len(pairs),
            "front_holes": len(fb),
            "back_holes": len(bb),
            "mean_offset_mm": round(sum(pairs) / len(pairs), 2) if pairs else None,
            "verdict": "PASS" if len(pairs) >= max(2, len(fb) - 1) else "REVIEW",
        }

    (OUT / "board_map.json").write_text(json.dumps(
        {"meta": result, "detail": data}, indent=1, ensure_ascii=False))
    print(json.dumps(result, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
