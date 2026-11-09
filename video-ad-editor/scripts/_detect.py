# -*- coding: utf-8 -*-
"""كشف تلقائي للبلر — اللي سمّاه المستخدم يتلقى بروحه، بلا صورة مرجع ولا مربع.
Route A (built-in OpenCV detectors): qr · barcode · face → scan sampled frames → link into one target per
instance → fill the frames in between → blur_track's fail-safe / apply / qa, unchanged.
Route B (anything named in words) lives in keyframes/boxes (see references/blur.md).
"""
import hashlib
import json
import os
from pathlib import Path

import numpy as np

import blur_track as bt
from blur_track import cv2

ROUTE_A = ("qr", "barcode", "face")
YUNET_FILE = "face_detection_yunet_2023mar.onnx"
YUNET_URL = "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/" + YUNET_FILE
YUNET_SHA256 = "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"
FACE_SCORE = 0.6
FACE_GROW = 1.2       # hair, ears and chin sit outside the detector's box
GROW = 1.1            # detector quads hug the ink; blur a little past it
BAR_SHORT = 1.3       # after refinement: room for the digits printed under the bars
DUP_IOU = 0.5         # same code found at two scales
BOX_PAD_MIN = 6       # route B: a subagent's box hugs the text, so every side grows by the largest of
BOX_PAD_SHORT = 0.35  #   6 px, 0.35 x the box's short side, 0.04 x its long side (in video pixels)
BOX_PAD_LONG = 0.04
TRACK_GROW = 1.0      # route B: track a patch this many short sides taller above and below the box (a tight
                      #   text box alone has too few features), then map the result back onto the box
LINE_RATIO = 3        # snapping and the taller patch apply only to a text line: long side >= 3 x short side


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


def face_model():
    """The YuNet model under VAE_HOME/models, only if its sha256 matches (00_setup.sh --extras fetches it)."""
    home = Path(os.environ.get("VAE_HOME") or (Path.home() / ".video-ad-editor"))
    p = home / "models" / YUNET_FILE
    if not p.is_file():
        return None
    return p if hashlib.sha256(p.read_bytes()).hexdigest() == YUNET_SHA256 else None


def find_faces(bgr, model):
    """-> [("face", quad)] for one BGR frame, each box grown FACE_GROW about its centre."""
    h, w = bgr.shape[:2]
    key = ("face", str(model))
    if key not in _DET:
        # from a buffer: OpenCV's ONNX reader can't open non-ASCII paths on Windows
        _DET[key] = cv2.FaceDetectorYN.create("onnx", np.fromfile(str(model), np.uint8), np.array([], np.uint8),
                                              (w, h), FACE_SCORE)
    det = _DET[key]
    det.setInputSize((w, h))
    _, faces = det.detect(bgr)
    out = []
    for f in [] if faces is None else faces:
        x, y, fw, fh = map(float, f[:4])
        q = np.float32([(x, y), (x + fw, y), (x + fw, y + fh), (x, y + fh)])
        out.append(("face", grow_axes(q, FACE_GROW, FACE_GROW)))
    return out


def align(q, ref):
    """Roll q's corners so each sits nearest the matching corner of ref (start corner flips past a 45° tilt)."""
    q = np.asarray(q, np.float32).reshape(4, 2)
    ref = np.asarray(ref, np.float32).reshape(4, 2)
    k = min(range(4), key=lambda r: float(np.linalg.norm(np.roll(q, -r, axis=0) - ref, axis=1).sum()))
    return np.roll(q, -k, axis=0)


def find_codes(gray, kinds):
    """-> [(kind, 4x2 float32 quad)] for every QR / barcode found in one grey (or BGR) frame."""
    if gray.ndim == 3:
        gray = cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)
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
    corners interpolated between detections (conf 0.9 up to BRIDGE frames, else 0.4 so the fail-safe widens it),
    runs extended by template matching at both ends."""
    info = bt._probe(Path(video))
    w, h, rate = info["w"], info["h"], info["rate"]
    if i1 is None:
        i1 = bt.count_frames(Path(video), rate)
    L, prev = {}, None
    for i in sorted(track):
        q = np.asarray(bt.grow(track[i], GROW), np.float32)
        if prev is not None:
            q = align(q, prev)     # same physical corner in the same slot, or interpolation folds the quad
        L[i], prev = (q, 1.0), q
    ks = sorted(L)
    for a, b in zip(ks, ks[1:]):
        if b - a > 1:
            # both ends are detections: follow the motion. Past BRIDGE the fail-safe widens it (conf < 0.5)
            c = 0.9 if b - a <= bt.BRIDGE else 0.4
            for j in range(a + 1, b):
                u = (j - a) / (b - a)
                L[j] = ((1 - u) * L[a][0] + u * L[b][0], c)
    bt.extend_runs(Path(video), L, i0, i1, w, h, rate)
    lo, hi = min(L), max(L)
    return [bt.FrameBox(i, bt._plist(L[i][0]), round(float(L[i][1]), 3), "tracked") if i in L
            else bt.FrameBox(i, None, 0.0, "lost") for i in range(lo, hi + 1)]


# ---- route B: keyframes for a subagent, its boxes seed the tracker ---------------------------------------------------
CUT_DIST = 0.4        # Bhattacharyya distance between consecutive grey histograms that marks a scene cut


def pick_keyframes(video, i0, i1, every_s=2.0, max_n=12):
    """Frame indices to show the subagent: every `every_s` seconds plus each scene cut; none closer than 0.5 s
    (cuts win); evenly thinned to max_n."""
    video = Path(video)
    info = bt._probe(video)
    w, h, rate, fps = info["w"], info["h"], info["rate"], bt.probe(video)[2]
    sw, sh = 160, max(round(160 * h / w), 1)
    cuts, prev, last = [], None, i0
    for i, g in bt.read_frames(video, w, h, rate=rate):
        if i < i0 or (i1 is not None and i >= i1):
            continue
        last = i
        hist = cv2.calcHist([cv2.resize(g, (sw, sh), interpolation=cv2.INTER_AREA)], [0], None, [64], [0, 256])
        cv2.normalize(hist, hist)
        if prev is not None and cv2.compareHist(prev, hist, cv2.HISTCMP_BHATTACHARYYA) > CUT_DIST:
            cuts.append(i)
        prev = hist
    step = max(int(round(every_s * fps)), 1)
    gap = int(round(0.5 * fps))
    kept = []
    for c in cuts + list(range(i0, last + 1, step)):
        if all(abs(c - k) >= gap for k in kept):
            kept.append(c)
    kept.sort()
    if len(kept) > max_n:
        kept = [kept[round(j * (len(kept) - 1) / (max_n - 1))] for j in range(max_n)]
    return kept


def write_keyframes(video, work, idx, long_side=720):
    """<work>/kf/kf_NN.jpg (long side <= long_side, never upscaled) + keyframes.json -> the kf folder."""
    video, out = Path(video), Path(work) / "kf"
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("kf_*.jpg"):
        old.unlink()
    w, h, fps, _ = bt.probe(video)
    s = min(1.0, long_side / max(w, h))
    frames = []
    for n, (i, f) in enumerate(bt.read_frames(video, w, h, gray=False, select=sorted(idx))):
        if s != 1:
            f = cv2.resize(f, (max(round(w * s), 1), max(round(h * s), 1)), interpolation=cv2.INTER_AREA)
        ok, enc = cv2.imencode(".jpg", f, [cv2.IMWRITE_JPEG_QUALITY, 90])
        if not ok:
            raise RuntimeError("jpeg encode failed")
        name = f"kf_{n:02d}.jpg"
        enc.tofile(str(out / name))          # np.tofile: Arabic paths on Windows
        frames.append({"t": round(i / fps, 3), "i": i, "file": name})
    data = {"scale": s, "fps": fps, "w": w, "h": h, "n": bt.count_frames(video), "frames": frames}
    (out / "keyframes.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def box_margin(bw, bh):
    """Pixels added on every side of a route-B box (see BOX_PAD_*)."""
    return max(BOX_PAD_MIN, BOX_PAD_SHORT * min(bw, bh), BOX_PAD_LONG * max(bw, bh))


def map_rect(q, bw, bh, r):
    """The rect r = (x0, y0, x1, y1), in the pixels of a (bw x bh) box tracked onto quad q, as a frame quad."""
    q = np.asarray(q, np.float32).reshape(4, 2)
    rect = np.float32([(0, 0), (bw, 0), (bw, bh), (0, bh)])
    H = cv2.getPerspectiveTransform(rect, q)
    x0, y0, x1, y1 = r
    big = np.float32([(x0, y0), (x1, y0), (x1, y1), (x0, y1)]).reshape(-1, 1, 2)
    return cv2.perspectiveTransform(big, H).reshape(-1, 2)


def snap_to_ink(gray, box):
    """A subagent's "tight" box is off by about a character. Grow it to the text line it sits on: the rows around
    its strongest edge row while the edge energy stays high (a lighter gap ends the line), then the columns of
    those rows while the smoothed energy stays high (gaps between digits are bridged). Never smaller than the
    box; a line that does not look like one line (too tall or too short) keeps the box's own rows. A box that is
    not a text line (see LINE_RATIO) is returned as it is."""
    if max(box[2], box[3]) < LINE_RATIO * min(box[2], box[3]):
        return tuple(box)
    if gray.ndim == 3:
        gray = cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)
    H, W = gray.shape
    x, y, bw, bh = box
    s = min(bw, bh)
    vert = bh > bw                                                       # a line printed top to bottom
    if vert:
        gray, (x, y, bw, bh), (H, W) = gray.T, (y, x, bh, bw), (W, H)
    rx0, rx1 = max(int(x - 1.5 * s), 0), min(int(np.ceil(x + bw + 1.5 * s)), W)
    ry0, ry1 = max(int(y - 0.8 * s), 0), min(int(np.ceil(y + bh + 0.8 * s)), H)
    g = cv2.GaussianBlur(gray[ry0:ry1, rx0:rx1].astype(np.float32), (3, 3), 0)
    e = np.abs(cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)) + np.abs(cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3))
    bx0, bx1 = int(x) - rx0, int(np.ceil(x + bw)) - rx0
    by0, by1 = int(y) - ry0, int(np.ceil(y + bh)) - ry0
    rows = cv2.blur(e[:, bx0:bx1].mean(1).reshape(-1, 1), (1, 3)).ravel()
    pk = by0 + int(np.argmax(rows[by0:by1]))
    thr = np.percentile(rows, 15) + 0.5 * (rows[pk] - np.percentile(rows, 15))
    t, b = pk, pk
    while t > 0 and rows[t - 1] > thr:
        t -= 1
    while b < len(rows) - 1 and rows[b + 1] > thr:
        b += 1
    if not 0.6 * s <= b + 1 - t <= 1.6 * s:                              # not one line: keep the box's rows
        t, b = by0, by1 - 1
    k = max(3, int(0.6 * (b + 1 - t)))
    cols = cv2.blur(e[t:b + 1].mean(0).reshape(1, -1), (k, 1)).ravel()
    cthr = np.percentile(cols, 15) + 0.35 * (np.percentile(cols[bx0:bx1], 90) - np.percentile(cols, 15))
    l, r = bx0, bx1 - 1
    while l > 0 and cols[l - 1] > cthr:
        l -= 1
    while r < len(cols) - 1 and cols[r + 1] > cthr:
        r += 1
    x0, y0 = min(x, rx0 + l), min(y, ry0 + t)
    x1, y1 = max(x + bw, rx0 + r + 1), max(y + bh, ry0 + b + 1)
    out = (float(x0), float(y0), float(x1 - x0), float(y1 - y0))
    return (out[1], out[0], out[3], out[2]) if vert else out


def track_patch(box, w, h):
    """The patch tracked for a route-B box: for a text line (see LINE_RATIO), TRACK_GROW short sides more above
    and below (left and right for a vertical line); any other box as it is. Clipped to the w x h frame, in
    whole pixels that contain the box (track_box crops whole pixels)."""
    x, y, bw, bh = box
    g = TRACK_GROW * min(bw, bh) if max(bw, bh) >= LINE_RATIO * min(bw, bh) else 0
    gx, gy = (0, g) if bw >= bh else (g, 0)
    x0, y0 = max(int(np.floor(x - gx)), 0), max(int(np.floor(y - gy)), 0)
    x1, y1 = min(int(np.ceil(x + bw + gx)), w), min(int(np.ceil(y + bh + gy)), h)
    return x0, y0, x1 - x0, y1 - y0


def track_anchors(video, anchors, t0=0, t1=None, pad=True, size=None):
    """One item marked on several keyframes: track_box from each (t, (x, y, w, h)) and keep, per frame, a found
    polygon over a lost one and the higher confidence among found ones. Trimmed to the item's own span.
    pad: grow each polygon by box_margin() of its anchor box (the box is tracked tight, the blur reaches past it).
    size: the video's (w, h), when the caller has it (saves a probe)."""
    anchors = sorted({t: box for t, box in reversed(anchors)}.items())   # one anchor per time, in order
    cache = {}                                                           # (t, from, to) -> track
    while True:
        try:
            return _track_anchors(video, anchors, t0, t1, pad, cache, size)
        except bt.WeakTemplate as e:
            # a soft keyframe (motion blur) has too few features: track from the other anchors instead
            bad = getattr(e, "t", None)
            if len(anchors) == 1 or bad is None:
                raise
            print(f"⚠️ لقطة {bad}ث ضبابية وما تنفع مرجع — أتتبّع من اللقطات الثانية")
            anchors = [a for a in anchors if a[0] != bad]


def _track_anchors(video, anchors, t0, t1, pad, cache, size):
    w, h = size or bt.probe(Path(video))[:2]
    best = {}
    for k, (t, box) in enumerate(anchors):
        # each anchor covers up to its neighbours only: SIFT runs ~2x the item's span, not once per anchor
        a = max(t0, anchors[k - 1][0]) if k else t0
        b = anchors[k + 1][0] if k + 1 < len(anchors) else t1
        m = box_margin(box[2], box[3]) if pad else 0
        px, py, pw, ph = track_patch(box, w, h)
        # the padded box in the tracked patch's own pixels
        r = (box[0] - px - m, box[1] - py - m, box[0] + box[2] - px + m, box[1] + box[3] - py + m)
        if (t, a, b) not in cache:
            try:
                cache[(t, a, b)] = bt.track_box(Path(video), t, (px, py, pw, ph), a, b)
            except bt.WeakTemplate as e:
                e.t = t                                                  # which anchor, for the retry
                raise
        track = cache[(t, a, b)]
        for f in track:
            if f.poly is not None:
                f = bt.replace(f, poly=bt._plist(map_rect(f.poly, pw, ph, r)))
            cur = best.get(f.i)
            if cur is None or (cur.state == "lost" and f.state != "lost") \
                    or (f.state != "lost" and cur.state != "lost" and f.conf > cur.conf):
                best[f.i] = f
    out = [best[i] for i in sorted(best)]
    found = [k for k, f in enumerate(out) if f.state != "lost"]
    # the item's own span only: before it first shows / after it last shows is not "lost" (same as route A)
    return out[found[0]:found[-1] + 1] if found else out
