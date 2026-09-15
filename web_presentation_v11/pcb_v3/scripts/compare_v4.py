"""Photo-vs-render overlay validation for A2.2.

Scales the top-down V4 render so its board matches the registered photo
width, aligns centres, alpha-blends, and draws both contours.

Run: .venv/bin/python scripts/compare_v4.py
"""
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parents[1]
REG = HERE / "registration"
REN = HERE / "renders_v4"
OUT = HERE / "validation"
OUT.mkdir(exist_ok=True)

PAIRS = [
    ("a_front", REG / "registered_a_front.png",
     REN / "v4_topdown_a_front.png"),
    ("b_front", REG / "registered_b_front.png",
     REN / "v4_topdown_b_front.png"),
]


def green_mask(img):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    m = cv2.inRange(hsv, (30, 30, 15), (95, 255, 255))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return m, max(cnts, key=cv2.contourArea)


def compare(tag, photo_path, render_path):
    photo = cv2.imread(str(photo_path))
    render = cv2.imread(str(render_path))
    pm, pcnt = green_mask(photo)
    rm, rcnt = green_mask(render)
    px, py, pw, ph = cv2.boundingRect(pcnt)
    rx, ry, rw, rh = cv2.boundingRect(rcnt)

    # scale render so board width matches photo board width
    s = pw / rw
    render_s = cv2.resize(render, None, fx=s, fy=s)
    rx, ry, rw, rh = [int(v * s) for v in (rx, ry, rw, rh)]

    # paste render centred over photo board centre
    canvas = np.zeros_like(photo)
    pcx, pcy = px + pw // 2, py + ph // 2
    rcx, rcy = rx + rw // 2, ry + rh // 2
    ox, oy = pcx - rcx, pcy - rcy
    H, W = photo.shape[:2]
    x0, y0 = max(0, ox), max(0, oy)
    x1 = min(W, ox + render_s.shape[1])
    y1 = min(H, oy + render_s.shape[0])
    canvas[y0:y1, x0:x1] = render_s[y0 - oy:y1 - oy, x0 - ox:x1 - ox]

    blend = cv2.addWeighted(photo, 0.55, canvas, 0.45, 0)
    cv2.drawContours(blend, [pcnt], -1, (0, 255, 255), 2)   # photo = yellow
    rcnt_s = (rcnt * s).astype(np.int32) + np.array([[[ox, oy]]])
    cv2.drawContours(blend, [rcnt_s], -1, (0, 0, 255), 2)   # render = red

    # alignment metric: IoU of the two board masks
    rmask_s = cv2.resize(rm, None, fx=s, fy=s)
    aligned = np.zeros(pm.shape, np.uint8)
    aligned[y0:y1, x0:x1] = rmask_s[y0 - oy:y1 - oy, x0 - ox:x1 - ox]
    inter = np.logical_and(pm > 0, aligned > 0).sum()
    union = np.logical_or(pm > 0, aligned > 0).sum()
    iou = inter / union if union else 0

    cv2.putText(blend, f"{tag}  IoU={iou:.2f}  scale={s:.3f}",
                (16, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
    out = OUT / f"compare_{tag}.png"
    cv2.imwrite(str(out), blend)
    print(f"[compare] {tag}: IoU={iou:.3f} -> {out.name}")
    return iou


def main():
    ious = [compare(t, p, r) for t, p, r in PAIRS]
    print(f"[compare] mean IoU={sum(ious)/len(ious):.3f}")


if __name__ == "__main__":
    main()
