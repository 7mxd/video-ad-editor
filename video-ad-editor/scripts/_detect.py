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
BOX_PAD_BARS = 0.6    # a box marked "bars": bars look alike at every height, so a tracked box slides short of their
                      #   ends at no cost (Hook 13.33 s: 0.27 x short); across the bars only, along them as above
TRACK_GROW = 1.0      # route B: track a patch this many short sides taller above and below the box (a tight
                      #   text box alone has too few features), then map the result back onto the box
LINE_RATIO = 3        # snapping and the taller patch apply only to a text line: long side >= 3 x short side
MATCH_MIN = 0.5       # route B: a tracked frame counts only if, warped back, it matches its anchor's patch this well
SEARCH_NEAR = 0.08    # re-detect around a tracked patch: this x its long side (+3 px) in every direction
SEARCH_GAP = 0.3      #   around a predicted patch (frames the tracker lost or got wrong), plus one frame's motion
ECC_SHAPE = 0.08      # ECC may turn and move the patch, but not stretch either side by more than this


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


def box_pads(bw, bh, bars=False):
    """(left, top, right, bottom) pixels added to a route-B box: box_margin() on every side. bars: True, or which
    sides across the bars (the short side's direction) get at least BOX_PAD_BARS x the short side: (top, bottom)
    for a box wider than tall, (left, right) for a taller one (see bar_sides)."""
    m = box_margin(bw, bh)
    if bars is False or bars is None:
        return m, m, m, m
    lo, hi = (True, True) if bars is True else bars
    b = max(m, BOX_PAD_BARS * min(bw, bh))
    lo, hi = (b if lo else m), (b if hi else m)
    return (m, lo, m, hi) if bw >= bh else (lo, m, hi, m)


def bar_sides(box, polys):
    """Which sides across the bars of a "bars" box get BOX_PAD_BARS: (top, bottom), or (left, right) for a box taller
    than wide. A side that another blurred item already covers keeps box_margin(): a polygon (frame pixels, same
    frame) over the box along the bars' row, within the bars pad's reach, that sticks out past that side only (Hook:
    the cert line over the barcode box's top; 0.6 x up went past the cert's blur into the grade line). One that
    sticks out past both sides or neither is the same code (route A) and does not count; both sides taken = both
    get BOX_PAD_BARS (privacy first)."""
    lo, hi = bar_takers(box, polys)
    return (True, True) if lo and hi else (not lo, not hi)


def bar_takers(box, polys):
    """bar_sides' polygons: ([indices of polys that cover the top side], [... the bottom]), or left/right."""
    x, y, bw, bh = box
    ax = 1 if bw >= bh else 0                                            # across the bars: the short side's axis
    lo, hi = (y, y + bh) if ax else (x, x + bw)
    l0, l1 = (x, x + bw) if ax else (y, y + bh)
    reach = BOX_PAD_BARS * min(bw, bh)
    taken = ([], [])
    for k, q in enumerate(polys):
        q = np.asarray(q, np.float32).reshape(-1, 2)
        a0, a1 = float(q[:, ax].min()), float(q[:, ax].max())
        b0, b1 = float(q[:, 1 - ax].min()), float(q[:, 1 - ax].max())
        if b1 <= l0 or b0 >= l1 or a1 <= lo - reach or a0 >= hi + reach:
            continue                                                     # beside the box, or out of reach
        up, down = a0 < lo, a1 > hi
        if up != down:
            taken[0 if up else 1].append(k)
    return taken


def clip_bars(poly, line, side, quad=None, wide=None, depth=None):
    """A bars polygon without its part past the outer edge of a text line that covers its side (0: top, 1: bottom;
    left/right for a box taller than wide), cut along that edge and the line's length only (Hook: the tall bars box reached past
    the cert line's own blur into "MS 66" on 86 of 303 frames). quad: the bars' tracked quad, for its axes, when
    poly was clipped already. wide: the anchor box is wider than tall (default: the quad's own edges, which a pad
    across a near-square box can flip). depth: the deepest cut, as a fraction of the quad across the bars (its pad
    on that side), so a line tracked low in the box cannot uncover the bars. Unchanged when the line's edge is not
    inside the bars polygon; the cut grows back 2 px (privacy first)."""
    p = np.asarray(poly, np.float32).reshape(-1, 2)
    q = np.asarray(p if quad is None else quad, np.float32).reshape(-1, 2)
    e1, e3 = q[1] - q[0], q[3] - q[0]
    if wide is None:
        wide = np.linalg.norm(e1) >= np.linalg.norm(e3)
    along, across = (e1, e3) if wide else (e3, e1)
    u, v = along / np.linalg.norm(along), across / np.linalg.norm(across)
    L = np.asarray(line, np.float32).reshape(-1, 2)
    pa, la = (p - q[0]) @ v, (L - q[0]) @ v
    lo, hi = float(pa.min()), float(pa.max())
    k = np.argsort(la)[:2] if side == 0 else np.argsort(la)[-2:]        # the line's outer edge: its 2 outer corners
    a, b = L[k[0]], L[k[1]]
    if depth is not None:                                                # no deeper than the bars' pad on that side
        qa = (q - q[0]) @ v
        cap = qa.min() + depth * np.ptp(qa) if side == 0 else qa.max() - depth * np.ptp(qa)
        a, b = (c - v * max(0.0, (c - q[0]) @ v - cap) if side == 0 else c + v * max(0.0, cap - (c - q[0]) @ v)
                for c in (a, b))
    e = np.array([(a - q[0]) @ v, (b - q[0]) @ v])
    if not (e.max() > lo + 1 and e.min() < hi if side == 0 else e.min() < hi - 1 and e.max() > lo):
        return p                                                         # the edge is past the bars' side: nothing
    w = v * (hi - lo + 10) * (-1 if side == 0 else 1)                    # out past the bars' side
    notch = np.float32([a, b, b + w, a + w])
    o = np.floor(p.min(0)) - 3
    W, H = (np.ceil(p.max(0)) - o + 4).astype(int)
    m = np.zeros((H, W), np.uint8)
    cv2.fillPoly(m, [np.round(p - o).astype(np.int32)], 255)
    cv2.fillPoly(m, [np.round(notch - o).astype(np.int32)], 0)
    m = cv2.dilate(m, np.ones((5, 5), np.uint8))
    cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if len(cs) != 1:
        return p                                                         # cut in two: keep the whole box
    return (cv2.approxPolyDP(cs[0], 1.5, True).reshape(-1, 2) + o).astype(np.float32)


def _sides(bars, t):
    """track_anchors' bars for the anchor at t: a bool for every anchor, or {t: (lo, hi)} from bar_sides."""
    return bars.get(t, True) if isinstance(bars, dict) else bars


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


def track_anchors(video, anchors, t0=0, t1=None, pad=True, size=None, verify=True, bars=False, sizes=None):
    """One item marked on several keyframes: track_box from each (t, (x, y, w, h)) and keep, per frame, a found
    polygon over a lost one and the higher confidence among found ones. Trimmed to the item's own span.
    pad: grow each polygon by box_pads() of its anchor box (the box is tracked tight, the blur reaches past it).
    bars: the item is barcode bars (boxes.json "kind": "bars"): more pad across the bars (see BOX_PAD_BARS); True for
    both sides, or {t: (lo, hi)} per anchor (see bar_sides).
    size: the video's (w, h), when the caller has it (saves a probe).
    verify: check every tracked frame against its anchor and re-detect the ones that fail (see verify_track).
    sizes: {t: (w, h)} the boxes as marked, before snap_to_ink, for box_pads (Hook: the snap grew the cert boxes
    into the barcode below, and their margin grew up into the grade line); default each anchor's own box."""
    anchors = sorted({t: box for t, box in reversed(anchors)}.items())   # one anchor per time, in order
    cache = {}                                                           # (t, from, to) -> track
    while True:
        try:
            return _track_anchors(video, anchors, t0, t1, pad, cache, size, verify, bars, sizes)
        except bt.WeakTemplate as e:
            # a soft keyframe (motion blur) has too few features: track from the other anchors instead
            bad = getattr(e, "t", None)
            if len(anchors) == 1 or bad is None:
                raise
            print(f"⚠️ لقطة {bad}ث ضبابية وما تنفع مرجع — أتتبّع من اللقطات الثانية")
            anchors = [a for a in anchors if a[0] != bad]


def _size(sizes, t, box):
    """box_pads' (w, h) for the anchor at t: the box as marked when given (see track_anchors' sizes)."""
    return tuple((sizes or {}).get(t, box[2:4]))


def _track_anchors(video, anchors, t0, t1, pad, cache, size, verify=False, bars=False, sizes=None):
    w, h = size or bt.probe(Path(video))[:2]
    best = {}
    for k, (t, box) in enumerate(anchors):
        # each anchor covers up to its neighbours only: SIFT runs ~2x the item's span, not once per anchor
        a = max(t0, anchors[k - 1][0]) if k else t0
        b = anchors[k + 1][0] if k + 1 < len(anchors) else t1
        pl, pt, pr, pb = box_pads(*_size(sizes, t, box), _sides(bars, t)) if pad else (0, 0, 0, 0)
        px, py, pw, ph = track_patch(box, w, h)
        # the padded box in the tracked patch's own pixels
        r = (box[0] - px - pl, box[1] - py - pt, box[0] + box[2] - px + pr, box[1] + box[3] - py + pb)
        if (t, a, b) not in cache:
            try:
                cache[(t, a, b)] = bt.track_box(Path(video), t, (px, py, pw, ph), a, b)
            except bt.WeakTemplate as e:
                e.t = t                                                  # which anchor, for the retry
                raise
        track = cache[(t, a, b)]
        if verify:
            continue
        for f in track:
            if f.poly is not None:
                f = bt.replace(f, poly=bt._plist(map_rect(f.poly, pw, ph, r)))
            cur = best.get(f.i)
            if cur is None or (cur.state == "lost" and f.state != "lost") \
                    or (f.state != "lost" and cur.state != "lost" and f.conf > cur.conf):
                best[f.i] = f
    if verify:
        tracks = [cache[(t, max(t0, anchors[k - 1][0]) if k else t0,
                         anchors[k + 1][0] if k + 1 < len(anchors) else t1)] for k, (t, _) in enumerate(anchors)]
        best = {f.i: f for f in verify_track(video, anchors, tracks, w, h, pad, bars, sizes)}
    out = [best[i] for i in sorted(best)]
    found = [k for k, f in enumerate(out) if f.state != "lost"]
    # the item's own span only: before it first shows / after it last shows is not "lost" (same as route A)
    return out[found[0]:found[-1] + 1] if found else out


# ---- route B: check each tracked frame, re-detect the rest ---------------------------------------------------------
def _xy(dx, dy):
    return np.array([[1, 0, dx], [0, 1, dy], [0, 0, 1]], np.float64)


def _streak(tpl, v):
    """The template smeared along v (pixels per frame), like a frame shot while the camera moved by v."""
    n = float(np.hypot(*v))
    if n < 2:
        return tpl
    k = int(np.ceil(n)) | 1
    ker = np.zeros((k, k), np.float32)
    d = np.asarray(v, float) / n
    for u in np.linspace(-n / 2, n / 2, 4 * k):
        ker[int(round(k // 2 + d[1] * u)), int(round(k // 2 + d[0] * u))] = 1
    return cv2.filter2D(tpl, -1, ker / ker.sum())


def refine(gray, tpl, H, S, v=(0, 0)):
    """H maps the template's pixels into the frame. Search +-S template pixels around it (normalised correlation),
    then let ECC fix scale and rotation. Returns (H, score): score is the match of the warped-back frame against the
    template, smeared along v (template pixels per frame) when the frame is motion-blurred."""
    th, tw = tpl.shape
    tb = _streak(tpl, v)
    win = cv2.warpPerspective(gray, H @ _xy(-S, -S), (tw + 2 * S, th + 2 * S),
                              flags=cv2.WARP_INVERSE_MAP | cv2.INTER_LINEAR).astype(np.float32)
    _, sc, _, loc = cv2.minMaxLoc(cv2.matchTemplate(win, tb, cv2.TM_CCOEFF_NORMED))
    H = H @ _xy(loc[0] - S, loc[1] - S)
    try:
        img = cv2.warpPerspective(gray, H, (tw, th), flags=cv2.WARP_INVERSE_MAP | cv2.INTER_LINEAR).astype(np.float32)
        _, A = cv2.findTransformECC(tb, img, np.eye(2, 3, dtype=np.float32), cv2.MOTION_AFFINE,
                                    (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 50, 1e-4), None, 5)
        H2 = H @ np.vstack([A, [0, 0, 1]]).astype(np.float64)
        if np.abs(np.linalg.norm(A[:, :2], axis=0) - 1).max() > ECC_SHAPE:         # a stretch, not a move (bars, glare)
            return H, float(sc)
        img = cv2.warpPerspective(gray, H2, (tw, th), flags=cv2.WARP_INVERSE_MAP | cv2.INTER_LINEAR).astype(np.float32)
        s2 = float(cv2.matchTemplate(img, tb, cv2.TM_CCOEFF_NORMED)[0, 0])
        if s2 >= sc:
            return H2, s2
    except cv2.error:                                                    # ECC did not converge: keep the shift
        pass
    return H, float(sc)


def _rigid(B, q):
    """The anchor's box B moved, scaled and turned to fit q best (least squares): the tracker gives where the box is,
    how big and how turned; its shape stays the anchor's. On motion-blurred frames SIFT and ECC return boxes that are
    stretched or sheared and still match (bars look the same at every height), so their shape is not trusted."""
    b, z = B[:, 0] + 1j * B[:, 1], q[:, 0] + 1j * q[:, 1]
    bc, zc = b - b.mean(), z - z.mean()
    r = z.mean() + (np.vdot(bc, zc) / max(np.vdot(bc, bc).real, 1e-9)) * bc
    return np.float32(np.stack([r.real, r.imag], 1))


def verify_track(video, anchors, tracks, w, h, pad=True, bars=False, sizes=None):
    """SIFT drifts on fast, motion-blurred moves while still reporting high confidence, and the template-matched run
    ends follow a shift only. So every tracked frame is checked again: warp it back onto its anchor's patch (search a
    little around it, ECC for scale and rotation) and keep it only if the match reaches MATCH_MIN. Frames left
    without a match are re-detected from the motion of their verified neighbours, from both sides, against a
    template smeared by that motion: between two verified frames every frame is tried; past the first and the last
    only up to bt.EXTEND frames, until the first miss. conf = the match score. Returns FrameBoxes over the tracks'
    span. anchors: [(t, box)] in video pixels; tracks: track_box's output for each, in the same order."""
    video = Path(video)
    s = bt._detect_scale(video)
    sw, sh = max(round(w * s), 1), max(round(h * s), 1)

    def small(g):
        return cv2.resize(g, (sw, sh), interpolation=cv2.INTER_AREA) if s != 1 else g

    fps = bt.probe(video)[2]
    idx = [round(t * fps) for t, _ in anchors]
    grab = dict(bt.read_frames(video, w, h, select=sorted(set(idx))))
    A = []
    for (t, box), ai, tr in zip(anchors, idx, tracks):
        px, py, pw, ph = track_patch(box, w, h)
        tw, th = max(round(pw * s), 1), max(round(ph * s), 1)
        tpl = cv2.resize(grab[ai][py:py + ph, px:px + pw], (tw, th), interpolation=cv2.INTER_AREA).astype(np.float32)
        B = (np.float32([(box[0], box[1]), (box[0] + box[2], box[1]), (box[0] + box[2], box[1] + box[3]),
                         (box[0], box[1] + box[3])]) - np.float32([px, py])) * np.float32([tw / pw, th / ph])
        A.append(dict(i=ai, box=box, tpl=tpl, B=B, P=np.float32([(0, 0), (tw, 0), (tw, th), (0, th)]),
                      tr={f.i: np.float32(f.poly) * s for f in tr if f.poly is not None and f.state != "lost"},
                      S=np.array([[pw * s / tw, 0, px * s], [0, ph * s / th, py * s], [0, 0, 1]]),
                      ax=0 if box[2] >= box[3] else 1, sides=_sides(bars, t), size=_size(sizes, t, box)))
    for a in A:                                                          # the line's extent along its long side
        a["ext"] = [float(a["B"][:, a["ax"]].min()), float(a["B"][:, a["ax"]].max())]
    _carry_extent(A, {i: small(g) for i, g in grab.items()})
    del grab
    span = [f.i for tr in tracks for f in tr]
    lo, hi = min(span), max(span) + 1

    def quad(a, H):                                                      # the box, in (scaled) frame pixels
        return cv2.perspectiveTransform(a["B"].reshape(-1, 1, 2), H).reshape(-1, 2)

    res = {}                                                             # i -> (box quad, score, anchor)
    for i, g in bt.read_frames(video, w, h, select=sorted({i for a in A for i in a["tr"]})):
        g = small(g)
        for a in A:
            if i in a["tr"]:
                th, tw = a["tpl"].shape
                H0 = cv2.getPerspectiveTransform(a["P"], a["tr"][i]).astype(np.float64)
                H, sc = refine(g, a["tpl"], H0, int(SEARCH_NEAR * max(th, tw)) + 3)
                if sc >= MATCH_MIN and (i not in res or sc > res[i][1]):
                    res[i] = (_rigid(a["B"], quad(a, H)), sc, a)
    if not res:
        return [bt.FrameBox(i, None, 0.0, "lost") for i in range(lo, hi)]
    known = sorted(res)
    gaps = {i for i in range(known[0], known[-1]) if i not in res}
    gaps |= set(range(max(lo, known[0] - bt.EXTEND), known[0]))
    gaps |= set(range(known[-1] + 1, min(hi, known[-1] + 1 + bt.EXTEND)))
    G = {i: small(g) for i, g in bt.read_frames(video, w, h, select=sorted(gaps))} if gaps else {}

    def chain(start, step):
        """Follow the box from a verified frame into the frames after it (step 1) or before it (step -1)."""
        out = {}
        q, _, a = res[start]                                             # one anchor per chain: q is its box
        th, tw = a["tpl"].shape
        v = q - res[start - step][0] if start - step in res and res[start - step][2] is a else np.zeros_like(q)
        j = start + step
        while j in G and j not in res:
            Hp = cv2.getPerspectiveTransform(a["B"], np.float32(q + v)).astype(np.float64)
            vp = v.mean(0) / max(np.sqrt(abs(np.linalg.det(Hp[:2, :2]))), 1e-6)   # the motion in template pixels
            H, sc = refine(G[j], a["tpl"], Hp, int(SEARCH_GAP * max(th, tw) + np.hypot(*vp)) + 3, vp)
            if sc >= MATCH_MIN:
                nq = _rigid(a["B"], quad(a, H))
                v, q = nq - q, nq
                out[j] = (q, sc, a)
            elif known[0] < j < known[-1]:
                q = q + v                                                # keep moving: a later frame may match
            else:
                break
            j += step
        return out

    found = {}
    for k in known:
        for step in (1, -1):
            if k + step not in res:
                for j, r in chain(k, step).items():
                    if j not in found or r[1] > found[j][1]:
                        found[j] = r
    res.update(found)
    out = []
    for i in range(lo, hi):
        if i not in res:
            out.append(bt.FrameBox(i, None, 0.0, "lost"))
            continue
        q, sc, a = res[i]
        H = cv2.getPerspectiveTransform(a["B"], np.float32(q))
        pl, pt, pr, pb = box_pads(*a["size"], a["sides"]) if pad else (0, 0, 0, 0)
        kx, ky = s / a["S"][0, 0], s / a["S"][1, 1]                       # video pixels -> template pixels
        pl, pr, pt, pb = pl * kx, pr * kx, pt * ky, pb * ky
        (x0, y0), (x1, y1) = a["B"].min(0), a["B"].max(0)
        if a["ax"] == 0:
            x0, x1 = a["ext"]
        else:
            y0, y1 = a["ext"]
        r = np.float32([(x0 - pl, y0 - pt), (x1 + pr, y0 - pt), (x1 + pr, y1 + pb), (x0 - pl, y1 + pb)])
        poly = cv2.perspectiveTransform(r.reshape(-1, 1, 2), H).reshape(-1, 2) / s
        out.append(bt.FrameBox(i, bt._plist(poly), round(sc, 3), "tracked"))
    return out


def _carry_extent(A, frames):
    """An anchor box can hold only part of the line (it ran off the frame edge, or glare hid its end) while its
    neighbours saw all of it. Warp each anchor's patch onto its neighbour's keyframe (from the neighbour's track),
    and if it matches, widen both boxes along the line to the union of their extents; a sweep each way carries an
    extent along the whole chain. Never across the line, so a nearby line stays sharp. Mutates each anchor's "ext"."""
    longest = max(a["ext"][1] - a["ext"][0] for a in A)
    pairs = []
    for a, b in zip(A, A[1:]):                                           # b's track starts at a's keyframe
        if a["i"] not in b["tr"] or a["i"] not in frames:
            continue
        th, tw = b["tpl"].shape
        H0 = cv2.getPerspectiveTransform(b["P"], b["tr"][a["i"]]).astype(np.float64)
        H, sc = refine(frames[a["i"]], b["tpl"], H0, int(SEARCH_NEAR * max(th, tw)) + 3)
        if sc >= MATCH_MIN:
            M = np.linalg.inv(a["S"]) @ H                                # b's template -> a's template
            pairs.append((a, b, M))

    def take(dst, src, M):                                               # src's extent, seen in dst's template
        (x0, y0), (x1, y1) = src["B"].min(0), src["B"].max(0)
        if src["ax"] == 0:
            x0, x1 = src["ext"]
        else:
            y0, y1 = src["ext"]
        q = cv2.perspectiveTransform(np.float32([(x0, y0), (x1, y0), (x1, y1), (x0, y1)]).reshape(-1, 1, 2),
                                     M).reshape(-1, 2)[:, dst["ax"]]
        lo, hi = min(dst["ext"][0], float(q.min())), max(dst["ext"][1], float(q.max()))
        if hi - lo <= 2 * longest:                                       # a wild warp is ignored, not trusted
            dst["ext"] = [lo, hi]

    for a, b, M in pairs:
        take(b, a, np.linalg.inv(M))
    for a, b, M in reversed(pairs):
        take(a, b, M)
