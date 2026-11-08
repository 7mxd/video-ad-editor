# -*- coding: utf-8 -*-
"""كشف تلقائي للبلر — اللي سمّاه المستخدم يتلقى بروحه، بلا صورة مرجع ولا مربع.
Route A (built-in OpenCV detectors): qr · barcode · face → scan sampled frames → link into one target per
instance → fill the frames in between → blur_track's fail-safe / apply / qa, unchanged.
Route B (anything named in words) lives in keyframes/boxes (see references/blur.md).
"""
from pathlib import Path

import numpy as np

import blur_track as bt
from blur_track import cv2

ROUTE_A = ("qr", "barcode")
GROW = 1.1            # detector quads hug the ink; blur a little past it
BAR_SHORT = 1.3       # after refinement: room for the digits printed under the bars
DUP_IOU = 0.5         # same code found at two scales


_DET = {}


def _detector(kind):
    if kind not in _DET:
        _DET[kind] = cv2.QRCodeDetectorAruco() if kind == "qr" else cv2.barcode.BarcodeDetector()
    return _DET[kind]


def _order(q):
    """Corners clockwise from top-left, so quads from different frames interpolate corner to corner."""
    q = np.asarray(q, np.float32).reshape(4, 2)
    c = q.mean(0)
    q = q[np.argsort(np.arctan2(q[:, 1] - c[1], q[:, 0] - c[0]))]   # clockwise in image coords, from the left-up side
    k = int(np.argmin(q.sum(1)))
    return np.roll(q, -k, axis=0)


def find_codes(gray, kinds):
    """-> [(kind, 4x2 float32 quad)] for every QR / barcode found in one grey frame."""
    out = []
    for kind in ("qr", "barcode"):
        if kind not in kinds:
            continue
        try:
            r = _detector(kind).detectMulti(gray)
        except cv2.error:
            continue
        ok, pts = r[0], r[1]
        if ok and pts is not None:
            for p in np.asarray(pts, np.float32).reshape(-1, 4, 2):
                if cv2.contourArea(p.reshape(-1, 1, 2)) > 16:
                    q = _order(p)
                    if kind == "barcode":
                        q = grow_axes(refine_barcode(gray, q), 1.0, BAR_SHORT)
                    out.append((kind, q))
    return out


def grow_axes(q, k_long, k_short):
    """Scale a quad about its centre: k_long along its longer side, k_short along the shorter one."""
    q = np.asarray(q, np.float32).reshape(4, 2)
    c = q.mean(0)
    u, v = (q[1] - q[0]) / 2, (q[3] - q[0]) / 2          # half side vectors (top edge, left edge)
    if np.linalg.norm(u) < np.linalg.norm(v):
        ku, kv = k_short, k_long
    else:
        ku, kv = k_long, k_short
    d = q - c
    # decompose each corner offset on (u, v) and scale each component
    M = np.stack([u, v], 1)
    coef = np.linalg.lstsq(M, d.T, rcond=None)[0]
    return (M @ (coef * np.array([[ku], [kv]]))).T + c


def _extent(e, lo, hi, thr, gap):
    """Grow [lo, hi] outward over a 1-D profile while it stays above thr, bridging dips of up to `gap`."""
    n = len(e)
    for direction in (-1, 1):
        k, miss = (lo if direction < 0 else hi), 0
        while 0 < k < n - 1 and miss <= gap:
            k += direction
            miss = 0 if e[k] > thr else miss + 1
            if miss == 0:
                if direction < 0:
                    lo = k
                else:
                    hi = k
    return lo, hi


def refine_barcode(gray, q):
    """The barcode detector's box is rough (its width jitters by a third). Measure the bars around it: in an
    upright crop along the box axes, follow the strong edges across the bars (long axis) and along them
    (short axis). Never shrinks the detector's box."""
    q = np.asarray(q, np.float32).reshape(4, 2)
    c = q.mean(0)
    u, v = q[1] - q[0], q[3] - q[0]
    L, S = (u, v) if np.linalg.norm(u) >= np.linalg.norm(v) else (v, u)
    hl, hs = np.linalg.norm(L) / 2, np.linalg.norm(S) / 2
    if hl < 4 or hs < 2:
        return q
    el, es = L / (2 * hl), S / (2 * hs)
    cw, ch = int(2 * hl * 2.4), int(2 * hs * 2.0)
    # crop pixel (x, y) -> image point c + (x - cw/2) el + (y - ch/2) es
    M = np.float32([[el[0], es[0], c[0] - cw / 2 * el[0] - ch / 2 * es[0]],
                    [el[1], es[1], c[1] - cw / 2 * el[1] - ch / 2 * es[1]]])
    crop = cv2.warpAffine(gray, M, (cw, ch), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                          borderMode=cv2.BORDER_REPLICATE).astype(np.float32)
    gx = np.abs(cv2.Sobel(crop, cv2.CV_32F, 1, 0, ksize=3))
    x0, x1 = int(cw / 2 - hl), int(cw / 2 + hl) - 1
    y0, y1 = int(ch / 2 - hs), int(ch / 2 + hs) - 1
    col = cv2.blur(gx[y0:y1 + 1].mean(0).reshape(1, -1), (3, 1)).ravel()
    inside = col[x0:x1 + 1]
    if inside.size == 0 or inside.max() <= 0:
        return q
    xl, xr = _extent(col, x0, x1, 0.25 * np.percentile(inside, 95), max(6, int(0.06 * 2 * hl)))
    row = gx[:, xl:xr + 1].mean(1)
    yt, yb = _extent(row, y0, y1, 0.25 * row[y0:y1 + 1].max(), 2)
    box = np.float32([(xl, yt), (xr + 1, yt), (xr + 1, yb + 1), (xl, yb + 1)])
    return _order(box @ M[:, :2].T + M[:, 2])


def _iou(a, b):
    ax0, ay0 = a.min(0); ax1, ay1 = a.max(0)
    bx0, by0 = b.min(0); bx1, by1 = b.max(0)
    iw, ih = max(0, min(ax1, bx1) - max(ax0, bx0)), max(0, min(ay1, by1) - max(ay0, by0))
    inter = iw * ih
    return inter / max((ax1 - ax0) * (ay1 - ay0) + (bx1 - bx0) * (by1 - by0) - inter, 1e-6)


def scan(video, kinds, i0, i1, step=2, scales=(1.0, 0.5), bgr=False, finders=None):
    """-> {frame index: [(kind, quad in full-resolution pixels)]} over sampled frames of [i0, i1)."""
    info = bt._probe(Path(video))
    w, h, rate = info["w"], info["h"], info["rate"]
    finders = finders or [find_codes]
    dets = {}
    for i, f in bt.read_frames(Path(video), w, h, gray=not bgr, rate=rate):
        if i < i0 or (i1 is not None and i >= i1) or (i - i0) % step:
            continue
        found = []
        for s in scales:
            img = f if s == 1 else cv2.resize(f, (max(round(w * s), 1), max(round(h * s), 1)),
                                              interpolation=cv2.INTER_AREA)
            for fn in finders:
                for kind, q in fn(img, kinds):
                    q = q / s
                    if not any(k == kind and _iou(q, p) > DUP_IOU for k, p in found):
                        found.append((kind, q))
        if found:
            dets[i] = found
    return dets


def link(dets, fps, long_side, max_gap_s=1.0):
    """Link detections into tracks, one per instance -> [{"kind", "q": {i: quad}}].
    Same kind + nearest centroid within OUTLIER_FRAC x long side, one-to-one per frame; a gap > max_gap_s
    closes the track (the instance comes back as a new target)."""
    max_gap = int(round(max_gap_s * fps))
    thr = bt.OUTLIER_FRAC * long_side
    tracks = []
    for i in sorted(dets):
        live = [t for t in tracks if i - t["last"] <= max_gap]
        pairs = sorted((np.linalg.norm(t["q"][t["last"]].mean(0) - q.mean(0)), ti, di)
                       for ti, t in enumerate(live) for di, (k, q) in enumerate(dets[i]) if k == t["kind"])
        used_t, used_d = set(), set()
        for d, ti, di in pairs:
            if d > thr or ti in used_t or di in used_d:
                continue
            used_t.add(ti); used_d.add(di)
            live[ti]["q"][i] = dets[i][di][1]
            live[ti]["last"] = i
        for di, (k, q) in enumerate(dets[i]):
            if di not in used_d:
                tracks.append({"kind": k, "q": {i: q}, "last": i})
    return [{"kind": t["kind"], "q": t["q"]} for t in tracks]


def fill(video, track, i0, i1):
    """One track's sampled quads -> FrameBoxes over the track's own span: detected frames (conf 1.0),
    corners interpolated across gaps <= BRIDGE (conf 0.9), runs extended by template matching; other frames
    in the span are `lost` so apply_failsafe holds or flags them."""
    info = bt._probe(Path(video))
    w, h, rate = info["w"], info["h"], info["rate"]
    if i1 is None:
        i1 = bt.count_frames(Path(video), rate)
    L = {i: (bt.grow(q, GROW), 1.0) for i, q in track.items()}
    ks = sorted(L)
    for a, b in zip(ks, ks[1:]):
        if 1 < b - a <= bt.BRIDGE:
            for j in range(a + 1, b):
                u = (j - a) / (b - a)
                L[j] = ((1 - u) * L[a][0] + u * L[b][0], 0.9)
    bt.extend_runs(Path(video), L, i0, i1, w, h, rate)
    lo, hi = min(L), max(L)
    return [bt.FrameBox(i, bt._plist(L[i][0]), round(float(L[i][1]), 3), "tracked") if i in L
            else bt.FrameBox(i, None, 0.0, "lost") for i in range(lo, hi + 1)]
