# -*- coding: utf-8 -*-
"""بلر الخصوصية — رقم تسلسلي، شاشة، ورقة، لوحة، وجه: يحدّد الهدف مرة، يتتبّعه، ويبلّره قبل طبقات المحرّك.
   python scripts/blur_track.py ref <work> <video> <ref_img> x0,y0,x1,y1 [--from T --to T] [--add | --target ID]
        ← صورة مرجع + منطقة بالكسور (0-1) من الصورة (لشي يتكرر، مثل ملصق بنفس التصميم)
   python scripts/blur_track.py box <work> <video> <t> x,y,w,h [--from T --to T] [--add | --target ID]
        ← مربع بالبكسل على فريم الثانية t، ويتتبّعه قدّام وورا
        --add هدف جديد (رقم جديد) · --target ID تحديد من جديد لنفس الهدف (يشيل مداه المفقود لو غطّاه كامل)
   python scripts/blur_track.py detect <work> <video> --kinds qr,barcode,face [--from T --to T] [--add | --replace]
        ← كشف تلقائي بلا تحديد (_detect.py)؛ غيرها: keyframes <work> <video> ← subagent ← boxes <work> <video> boxes.json
   python scripts/blur_track.py apply <work> <video_in> <video_out> [--accept-band]
   python scripts/blur_track.py qa <work> <video> <out.jpg>        ← ورقة وحدة: الفريمات غير المؤكدة + أطراف كل نافذة
   ref/box يطبعون سطر واحد «نوافذ N · فريمات M · غير مؤكد K · مفقود>1ث R» (للملف كله) ويطلعون بـ3 لو R > 0.
   apply يرفض (3) ما دام فيه مدى مفقود، إلا بـ--accept-band (شريط بعرض الفريم لكل هدف من آخر مضلع معروف له).
   apply/qa يرفضون (3) لو الفيديو مو نفسه اللي انتتبّع (العرض، الطول، fps، عدد الفريمات).
   النتيجة <work>/blur.json = {"fps","n","w","h","frames":[{"i","poly","conf","state","target"}],
                               "flagged":[[t0,t1,target]]}

How (generalises an earlier slab-label tracker): SIFT (4000 features) + BFMatcher ratio 0.75 + RANSAC homography on every frame
of the window, conf = RANSAC inlier ratio; drop centroid outliers; smooth corners over 3 frames; extend each run at
entries/exits by template matching. Fail-safe (spec §10.3): conf < 0.5 → polygon widened 1.5×; no match → nearest
known polygon (interpolated for gaps ≤ 10 frames) held and widened 2× for up to 1 s; lost > 1 s → range flagged,
exit 3, render refused. A frame is never left unblurred silently.
Frame index convention (one for every path): ffmpeg `fps=<probed rate>:start_time=0`, then optional `select`, with
`-fps_mode passthrough`. VFR footage and late-starting video streams get the same indices everywhere (tracking,
template extension, box anchor, render, QA), and the render stays aligned with the copied audio.
Frames are read and written through ffmpeg pipes (Arabic paths with spaces work on Windows) and blurred in YUV,
so pixels outside the polygons keep their exact decoded values (rule 4: no colour change).
Requires opencv: python -m pip install --no-deps opencv-python-headless==4.10.0.84   (NEVER without --no-deps: it
pulls numpy 2 and breaks torch/whisper; numpy must stay 1.26.x). 00_setup.sh --extras installs it.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, replace
from fractions import Fraction
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np  # noqa: E402

try:
    import cv2
except ImportError:  # optional extra; the CLI explains how to install it
    cv2 = None

STATES = ("tracked", "widened", "held", "lost")
RATIO = 0.75
MIN_GOOD = 10
MIN_INLIERS = 8
DETECT_MAX = 960          # detection runs on frames scaled to this long side
OUTLIER_FRAC = 0.15       # centroid jump (fraction of the long side) that marks a detection as an outlier
BRIDGE = 10               # gaps up to this many frames are interpolated, longer ones hold the nearest polygon
EXTEND = 16               # frames followed by template matching beyond each run
TPL_MIN_SCORE = 0.6


class Mismatch(Exception):
    """blur.json was made from a different video."""


@dataclass
class FrameBox:
    i: int
    poly: list | None
    conf: float
    state: str
    target: int = 0


# ---- video io ----------------------------------------------------------------------------------------------------
def _probe(video):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(video)],
                         capture_output=True, text=True, encoding="utf-8")
    if out.returncode != 0:
        raise ValueError(f"ffprobe failed on {video}: {out.stderr.strip()[:200]}")
    streams = json.loads(out.stdout).get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video"), None)
    if v is None:
        raise ValueError(f"no video stream in {video}")
    w, h = int(v["width"]), int(v["height"])
    rot = 0
    for sd in v.get("side_data_list", []) or []:
        if "rotation" in sd:
            rot = int(float(sd["rotation"]))
    rot = rot or int(float((v.get("tags") or {}).get("rotate", 0)))
    if abs(rot) % 180 == 90:  # ffmpeg auto-rotates when decoding
        w, h = h, w
    rate = v.get("r_frame_rate") or "0/0"
    if rate in ("0/0", "0/1"):
        rate = v.get("avg_frame_rate") or "30/1"
    if rate in ("0/0", "0/1"):
        rate = "30/1"
    return {"w": w, "h": h, "rate": rate, "fps": float(Fraction(rate)), "pix": v.get("pix_fmt", ""),
            "audio": any(s.get("codec_type") == "audio" for s in streams),
            "color": {k: v[k] for k in ("color_range", "color_space", "color_transfer", "color_primaries")
                      if v.get(k) and v[k] != "unknown"}}


def probe(video):
    """(width, height, fps, has_audio) as decoded (rotation applied)."""
    p = _probe(video)
    return p["w"], p["h"], p["fps"], p["audio"]


def _ranges(idx):
    idx = sorted(set(idx))
    out = []
    for i in idx:
        if out and i == out[-1][1] + 1:
            out[-1][1] = i
        else:
            out.append([i, i])
    return out


def read_frames(video, w, h, gray=True, select=None, pix=None, rate=None, extra=None):
    """Yield (index, frame) under the one index convention (CFR at the probed rate from t=0).

    pix: 'gray' | 'bgr24' | 'yuv420p' (default from gray). select: frame indices to keep (same indices as a full read).
    extra: filters appended after fps/select (e.g. 'scale=16:16' with matching w, h)."""
    pix = pix or ("gray" if gray else "bgr24")
    rate = rate or _probe(video)["rate"]
    size = {"gray": w * h, "bgr24": w * h * 3, "yuv420p": w * h + 2 * ((w + 1) // 2) * ((h + 1) // 2)}[pix]
    vf = f"fps={rate}:start_time=0"
    order = None
    if select is not None:
        rs = _ranges(select)
        if not rs:
            return
        vf += ",select='" + "+".join(f"between(n,{a},{b})" for a, b in rs) + "'"
        order = [i for a, b in rs for i in range(a, b + 1)]
    if extra:
        vf += "," + extra
    cmd = ["ffmpeg", "-v", "error", "-i", str(video), "-vf", vf, "-fps_mode", "passthrough",
           "-f", "rawvideo", "-pix_fmt", pix, "-"]
    err = tempfile.TemporaryFile()  # drained by the OS, so a chatty ffmpeg can't block
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=err)
    try:
        k = 0
        while order is None or k < len(order):
            b = p.stdout.read(size)
            if len(b) < size:
                p.stdout.close()
                if p.wait() != 0:
                    err.seek(0)
                    msg = err.read().decode("utf-8", "replace").strip()[:300]
                    raise RuntimeError(f"ffmpeg decode failed on {video}: {msg}")
                break
            i = order[k] if order is not None else k
            a = np.frombuffer(b, np.uint8)
            if pix == "gray":
                a = a.reshape(h, w)
            elif pix == "bgr24":
                a = a.reshape(h, w, 3)
            yield i, a
            k += 1
    finally:
        if p.poll() is None:
            p.kill()
        p.stdout.close()
        p.wait()
        err.close()


def count_frames(video, rate=None):
    """Frame count under the index convention (cheap: decoded to 16×16 grey)."""
    return sum(1 for _ in read_frames(video, 16, 16, pix="gray", rate=rate, extra="scale=16:16"))


def video_meta(video):
    info = _probe(video)
    return {"fps": info["fps"], "n": count_frames(video, info["rate"]), "w": info["w"], "h": info["h"]}


def check_video(meta, video):
    """Raise Mismatch when `video` is not the video blur.json was tracked on."""
    have = video_meta(video)
    bad = [k for k in ("w", "h", "n") if meta.get(k) != have[k]]
    if meta.get("fps") is None or abs(float(meta["fps"]) - have["fps"]) > 1e-3:
        bad.append("fps")
    if bad:
        want = ", ".join(f"{k}: {meta.get(k)} ≠ {have[k]}" for k in bad)
        raise Mismatch(f"الفيديو مو نفسه اللي انتتبّع ({want}) — شغّل ref/box على هالفيديو من جديد")
    return have


# ---- geometry ----------------------------------------------------------------------------------------------------
def grow(poly, k):
    q = np.asarray(poly, float)
    c = q.mean(0)
    return (q - c) * k + c


def _plist(q):
    return [(round(float(x), 1), round(float(y), 1)) for x, y in np.asarray(q, float)]


class _Matcher:
    """SIFT + ratio test + RANSAC homography from a template image to a frame."""

    def __init__(self, tpl_gray, tpl_poly):
        self.sift = cv2.SIFT_create(nfeatures=4000)
        self.bf = cv2.BFMatcher(cv2.NORM_L2)
        self.kp, self.des = self.sift.detectAndCompute(tpl_gray, None)
        if self.des is None or len(self.kp) < MIN_GOOD:
            raise ValueError("المرجع ما فيه تفاصيل كافية للتتبّع — كبّر المنطقة أو استخدم صورة أوضح")
        self.poly = np.float32(tpl_poly).reshape(-1, 1, 2)
        q = self.poly.reshape(-1, 2)
        self.aspect = np.linalg.norm(q[1] - q[0]) / max(np.linalg.norm(q[3] - q[0]), 1e-6)

    def locate(self, gray):
        kp, des = self.sift.detectAndCompute(gray, None)
        if des is None or len(kp) < MIN_GOOD:
            return None
        pairs = self.bf.knnMatch(self.des, des, k=2)
        good = [a for a, b in (p for p in pairs if len(p) == 2) if a.distance < RATIO * b.distance]
        if len(good) < MIN_GOOD:
            return None
        src = np.float32([self.kp[g.queryIdx].pt for g in good]).reshape(-1, 1, 2)
        dst = np.float32([kp[g.trainIdx].pt for g in good]).reshape(-1, 1, 2)
        H, inl = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
        if H is None or inl is None or int(inl.sum()) < MIN_INLIERS:
            return None
        q = cv2.perspectiveTransform(self.poly, H).reshape(-1, 2)
        v1, v2 = q[1] - q[0], q[3] - q[0]
        wq, hq = np.linalg.norm(v1), np.linalg.norm(v2)
        a = cv2.contourArea(q.astype(np.float32))
        fh, fw = gray.shape[:2]
        if not cv2.isContourConvex(q.astype(np.float32).reshape(-1, 1, 2)) or not (64 < a < 4 * fw * fh) \
                or not (0.5 < (wq / max(hq, 1e-6)) / self.aspect < 2.0) or abs(np.dot(v1, v2)) / (wq * hq + 1e-6) > 0.5:
            return None
        return q, int(inl.sum()) / len(good)


def extend_runs(video, L, i0, i1, w, h, rate):
    """Extend each run in L ({i: (poly, conf)}) outward by template matching (motion-blurred entries and exits).
    Mutates L."""
    edges = []
    for a, b in _ranges(L):
        edges += [(a, -1), (b, 1)]
    need = set()
    for e, step in edges:
        need.update(e + step * k for k in range(EXTEND + 1) if i0 <= e + step * k < i1)
    G = dict(read_frames(video, w, h, select=sorted(need), rate=rate)) if need else {}
    for e, step in edges:
        if e not in G:
            continue
        poly = L[e][0]
        bw, bh = np.ptp(poly, 0)
        pad = 0.1 * max(bw, bh)
        x0, y0 = np.floor(poly.min(0) - pad).astype(int)
        x1, y1 = np.ceil(poly.max(0) + pad).astype(int)
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, w), min(y1, h)
        if x1 - x0 < 8 or y1 - y0 < 8:
            continue
        tpl = G[e][y0:y1, x0:x1]
        if tpl.std() < 2:
            continue
        px, py, sr = x0, y0, max(24, int(0.5 * max(x1 - x0, y1 - y0)))
        for k in range(1, EXTEND + 1):
            f = e + step * k
            if f < i0 or f >= i1 or f in L or f not in G:
                break
            sx0, sy0 = max(px - sr, 0), max(py - sr, 0)
            win = G[f][sy0:min(py + tpl.shape[0] + sr, h), sx0:min(px + tpl.shape[1] + sr, w)]
            if win.shape[0] < tpl.shape[0] or win.shape[1] < tpl.shape[1] or win.std() < 2:
                break
            _, sc, _, loc = cv2.minMaxLoc(cv2.matchTemplate(win, tpl, cv2.TM_CCOEFF_NORMED))
            if not np.isfinite(sc) or sc < TPL_MIN_SCORE:
                break
            px, py = sx0 + loc[0], sy0 + loc[1]
            L[f] = (grow(poly, 1.12) + np.array([px - x0, py - y0], float), float(sc))


def _track(video, matcher, scale, i0=0, i1=None, anchor=None):
    """Detect on every frame of [i0, i1), clean up, extend runs, and return one FrameBox per frame."""
    info = _probe(video)
    w, h, rate = info["w"], info["h"], info["rate"]
    sw, sh = max(round(w * scale), 1), max(round(h * scale), 1)
    raw, n = {}, 0
    for i, g in read_frames(video, w, h, rate=rate):
        n = i + 1
        if i < i0 or (i1 is not None and i >= i1):
            continue
        r = matcher.locate(cv2.resize(g, (sw, sh), interpolation=cv2.INTER_AREA) if scale != 1 else g)
        if r is not None:
            raw[i] = (r[0] / scale, r[1])
    i1 = n if i1 is None else min(i1, n)
    if i0 >= i1:
        raise ValueError(f"window [{i0}, {i1}) is empty (video has {n} frames)")
    if anchor is not None:
        raw[anchor[0]] = (np.asarray(anchor[1], float), 1.0)
    # drop centroid outliers
    thr = OUTLIER_FRAC * max(w, h)
    keep = {}
    for f, (q, c) in raw.items():
        nb = [raw[g][0].mean(0) for g in range(f - 5, f + 6) if g in raw and g != f]
        if anchor is None or f != anchor[0]:
            if len(nb) >= 2 and np.linalg.norm(q.mean(0) - np.median(nb, 0)) > thr:
                continue
        keep[f] = (q, c)
    # smooth corners over consecutive detections
    L = {}
    for f, (q, c) in keep.items():
        if (anchor is not None and f == anchor[0]) or f - 1 not in keep or f + 1 not in keep:
            L[f] = (q, c)  # symmetric window only: a one-sided mean lags behind a moving target
        else:
            L[f] = (np.mean([keep[g][0] for g in (f - 1, f, f + 1) if g in keep], 0), c)
    # extend each run outward by template matching (motion-blurred entries and exits)
    extend_runs(video, L, i0, i1, w, h, rate)
    return [FrameBox(i, _plist(L[i][0]), round(float(L[i][1]), 3), "tracked") if i in L
            else FrameBox(i, None, 0.0, "lost") for i in range(i0, i1)]


def _detect_scale(video):
    w, h, _, _ = probe(video)
    return min(1.0, DETECT_MAX / max(w, h))


def _window(video, t0, t1):
    fps = probe(video)[2]
    return round((t0 or 0) * fps), (None if t1 is None else round(t1 * fps))


def track_reference(video, ref_img, region, t0=0, t1=None):
    """Mode (a): reference photo + region as fractions (x0, y0, x1, y1) of that photo."""
    if cv2 is None:
        raise ImportError("opencv missing")
    ref = cv2.imdecode(np.fromfile(str(ref_img), np.uint8), cv2.IMREAD_GRAYSCALE)
    if ref is None:
        raise ValueError(f"can't read reference image {ref_img}")
    s = min(1.0, 1000 / max(ref.shape))
    if s < 1:
        ref = cv2.resize(ref, (round(ref.shape[1] * s), round(ref.shape[0] * s)), interpolation=cv2.INTER_AREA)
    rh, rw = ref.shape
    x0, y0, x1, y1 = region
    if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
        raise ValueError("region must be fractions 0 ≤ x0 < x1 ≤ 1, 0 ≤ y0 < y1 ≤ 1")
    poly = [(x0 * rw, y0 * rh), (x1 * rw, y0 * rh), (x1 * rw, y1 * rh), (x0 * rw, y1 * rh)]
    i0, i1 = _window(video, t0, t1)
    return _track(Path(video), _Matcher(ref, poly), _detect_scale(video), i0, i1)


def track_box(video, t, box, t0=0, t1=None):
    """Mode (b): a pixel box (x, y, w, h) on the frame at time t, tracked forward and backward."""
    if cv2 is None:
        raise ImportError("opencv missing")
    video = Path(video)
    w, h, fps, _ = probe(video)
    ai = round(t * fps)
    frame = next((g for _, g in read_frames(video, w, h, select=[ai])), None)
    if frame is None:
        raise ValueError(f"no frame at t={t}")
    x, y, bw, bh = box
    x0, y0, x1, y1 = max(int(x), 0), max(int(y), 0), min(int(x + bw), w), min(int(y + bh), h)
    if x1 - x0 < 8 or y1 - y0 < 8:
        raise ValueError("box is outside the frame or too small")
    s = _detect_scale(video)
    crop = frame[y0:y1, x0:x1]
    if s != 1:
        crop = cv2.resize(crop, (max(round(crop.shape[1] * s), 1), max(round(crop.shape[0] * s), 1)),
                          interpolation=cv2.INTER_AREA)
    ch, cw = crop.shape
    i0, i1 = _window(video, t0, t1)
    if not (i0 <= ai < (i1 if i1 is not None else ai + 1)):
        raise ValueError("t is outside --from/--to")
    anchor = (ai, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)])
    return _track(video, _Matcher(crop, [(0, 0), (cw, 0), (cw, ch), (0, ch)]), s, i0, i1, anchor)


# ---- fail-safe ---------------------------------------------------------------------------------------------------
def apply_failsafe(frames, fps, conf_min=0.5, widen=1.5, lost_widen=2.0, max_lost_s=1.0):
    """One target's frames: widen low confidence, hold+widen short losses, flag losses > max_lost_s (seconds)."""
    fr = sorted(frames, key=lambda f: f.i)
    base = [np.asarray(f.poly, float) if f.poly is not None and f.state != "lost" else None for f in fr]
    out, flagged = [], []
    max_lost = int(round(max_lost_s * fps))
    k = 0
    while k < len(fr):
        f = fr[k]
        if base[k] is not None:
            if f.conf < conf_min and f.state == "tracked":
                out.append(replace(f, poly=_plist(grow(base[k], widen)), state="widened"))
            else:
                out.append(f)
            k += 1
            continue
        e = k
        while e + 1 < len(fr) and base[e + 1] is None and fr[e + 1].i == fr[e].i + 1:
            e += 1
        prev = base[k - 1] if k > 0 and fr[k - 1].i == f.i - 1 else None
        nxt = base[e + 1] if e + 1 < len(fr) and fr[e + 1].i == fr[e].i + 1 else None
        run = e - k + 1
        long_run = run > max_lost or (prev is None and nxt is None)  # nothing to hold → never pass silently
        if long_run:
            flagged.append((round(fr[k].i / fps, 3), round((fr[e].i + 1) / fps, 3)))
        for j in range(k, e + 1):
            a, b = j - k + 1, e + 1 - j  # distance to prev / next known
            if prev is not None and nxt is not None and run <= BRIDGE:
                q = prev + (nxt - prev) * a / (run + 1)
            elif prev is not None and (nxt is None or a <= b):
                q = prev
            else:
                q = nxt
            out.append(FrameBox(fr[j].i, None if q is None else _plist(grow(q, lost_widen)), 0.0,
                                "lost" if long_run else "held", fr[j].target))
        k = e + 1
    return out, flagged


# ---- render ------------------------------------------------------------------------------------------------------
def _by_frame(frames):
    d = {}
    for f in frames:
        if f.poly is not None:
            d.setdefault(f.i, []).append(np.asarray(f.poly, float))
    return d


def _blur_plane(plane, polys, k):
    ph, pw = plane.shape
    pts = np.concatenate(polys)
    x0, y0 = np.floor(pts.min(0)).astype(int) - k
    x1, y1 = np.ceil(pts.max(0)).astype(int) + k
    x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, pw), min(y1, ph)
    if x1 <= x0 or y1 <= y0:
        return
    roi = plane[y0:y1, x0:x1]
    mask = np.zeros(roi.shape, np.uint8)
    cv2.fillPoly(mask, [np.round(p - [x0, y0]).astype(np.int32) for p in polys], 255)
    roi[mask > 0] = cv2.GaussianBlur(roi, (k, k), 0)[mask > 0]


def render_blur(video_in, frames, video_out, strength=31, n_frames=None):
    """Gaussian blur inside each polygon; libx264 crf 16; audio copied when the input has it (trimmed to the video)."""
    video_in, video_out = Path(video_in), Path(video_out)
    info = _probe(video_in)
    w, h, rate = info["w"], info["h"], info["rate"]
    k = max(3, int(strength) | 1)
    kc = max(3, (k // 2) | 1)
    cw, ch = (w + 1) // 2, (h + 1) // 2
    polys = _by_frame(frames)
    color = []
    for key, opt in (("color_range", "-color_range"), ("color_space", "-colorspace"),
                     ("color_transfer", "-color_trc"), ("color_primaries", "-color_primaries")):
        if key in info["color"]:
            color += [opt, info["color"][key]]
    trim = []
    if info["audio"]:  # a longer audio track would outlast the picture; a shorter one is left as is
        n = n_frames if n_frames is not None else count_frames(video_in, rate)
        trim = ["-t", f"{n / float(Fraction(rate)):.6f}"]
    video_out.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "yuv420p", "-s", f"{w}x{h}",
           "-r", rate, "-i", "-", "-i", str(video_in), "-map", "0:v:0", "-map", "1:a?",
           "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", *color, "-c:a", "copy", *trim,
           "-movflags", "+faststart", str(video_out)]
    err = tempfile.TemporaryFile()  # encoder stderr goes to a file: it can never fill a pipe and stall us
    enc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=err)
    count, ok = 0, False
    try:
        for i, buf in read_frames(video_in, w, h, pix="yuv420p", rate=rate):
            ps = polys.get(i)
            if ps:
                a = buf.copy()
                y = a[: w * h].reshape(h, w)
                u = a[w * h: w * h + cw * ch].reshape(ch, cw)
                v = a[w * h + cw * ch:].reshape(ch, cw)
                _blur_plane(y, ps, k)
                half = [p / 2 for p in ps]
                _blur_plane(u, half, kc)
                _blur_plane(v, half, kc)
                buf = a
            enc.stdin.write(buf.tobytes())
            count += 1
        enc.stdin.close()
        rc = enc.wait()
        err.seek(0)
        msg = err.read().decode("utf-8", "replace").strip()[:300]
        if rc != 0:
            raise RuntimeError(f"ffmpeg encode failed: {msg}")
        if polys and max(polys) >= count:
            raise Mismatch(f"فيه مضلعات لفريم {max(polys)} والفيديو {count} فريم بس — مو نفس الفيديو")
        ok = True
    finally:
        if enc.poll() is None:
            enc.kill()
            enc.wait()
        err.close()
        if not ok:
            video_out.unlink(missing_ok=True)  # never leave a half or wrong render behind
    return video_out


# ---- QA sheet ----------------------------------------------------------------------------------------------------
def _spread(xs, n):
    if n <= 0 or not xs:
        return []
    if len(xs) <= n:
        return list(xs)
    return [xs[round(j * (len(xs) - 1) / max(n - 1, 1))] for j in range(n)]


def _states(frames):
    state = {}
    for f in frames:  # worst state wins when several targets share a frame
        if STATES.index(f.state) >= STATES.index(state.get(f.i, "tracked")):
            state[f.i] = f.state
    return state


def qa_picks(frames, n, max_tiles=24, outside=6):
    """-> (sorted picks, outside picks). Outside = up to `outside` frames spread over indices with no polygon
    (a missed item shows up there); then first/last frame of each window; then widened/held/lost frames."""
    polys = _by_frame(frames)
    state = _states(frames)
    edges = []
    for a, b in _ranges(polys):
        edges += [a] if a == b else [a, b]
    unsure = [i for i in sorted(state) if state[i] != "tracked" and i not in edges]
    out = _spread([i for i in range(n) if i not in polys], min(outside, max_tiles))
    picks = out + _spread(edges, max_tiles - len(out))
    picks = sorted(set(picks + _spread(unsure, max_tiles - len(picks))))
    return picks, out


def qa_sheet(video, frames, out_jpg, max_tiles=24, outside=6, n=None):
    """One sheet: frames with no blur ("clear") + first and last frame of each window + widened/held/lost
    frames; 240-px tiles labelled with time and state."""
    video, out_jpg = Path(video), Path(out_jpg)
    w, h, fps, _ = probe(video)
    polys = _by_frame(frames)
    state = _states(frames)
    if n is None:
        n = count_frames(video, _probe(video)["rate"]) if outside > 0 else 0
    picks, _ = qa_picks(frames, n, max_tiles, outside)
    if not picks:
        raise ValueError("nothing to show — blur.json has no frames")
    TW, TH, BAR = 240, 240, 22
    tiles = []
    for i, f in read_frames(video, w, h, gray=False, select=picks):
        img = f.copy()
        ps = polys.get(i)
        if ps:
            pts = np.concatenate(ps)
            bw, bh = np.ptp(pts, 0)
            pad = 0.25 * max(bw, bh, 20)
            x0, y0 = np.floor(pts.min(0) - pad).astype(int)
            x1, y1 = np.ceil(pts.max(0) + pad).astype(int)
            x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, w), min(y1, h)
            if x1 - x0 < 2 or y1 - y0 < 2:
                x0, y0, x1, y1 = 0, 0, w, h
            cv2.polylines(img, [np.round(p).astype(np.int32) for p in ps], True, (0, 0, 255), 2)
            img = img[y0:y1, x0:x1]
        s = min(TW / img.shape[1], TH / img.shape[0])
        img = cv2.resize(img, (max(round(img.shape[1] * s), 1), max(round(img.shape[0] * s), 1)),
                         interpolation=cv2.INTER_AREA)
        tile = np.full((TH + BAR, TW, 3), 40, np.uint8)
        oy, ox = BAR + (TH - img.shape[0]) // 2, (TW - img.shape[1]) // 2
        tile[oy:oy + img.shape[0], ox:ox + img.shape[1]] = img
        st = state.get(i, "tracked") if i in polys else "clear"
        cv2.putText(tile, f"{i / fps:.2f}s {st}", (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                    (255, 255, 255) if st == "tracked" else (0, 200, 255), 1, cv2.LINE_AA)
        tiles.append(tile)
    if len(tiles) != len(picks):
        raise Mismatch(f"الورقة تبي {len(picks)} فريم والفيديو عطى {len(tiles)} — مو نفس الفيديو")
    cols = min(6, len(tiles))
    tiles += [np.zeros_like(tiles[0])] * (-len(tiles) % cols)
    sheet = np.vstack([np.hstack(tiles[r:r + cols]) for r in range(0, len(tiles), cols)])
    out_jpg.parent.mkdir(parents=True, exist_ok=True)
    ok, enc = cv2.imencode(".jpg", sheet, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        raise RuntimeError("jpeg encode failed")
    enc.tofile(str(out_jpg))
    return len(picks)


# ---- blur.json + CLI ---------------------------------------------------------------------------------------------
def save_json(work, meta, frames, flagged):
    """meta = {"fps","n","w","h"}; flagged = [(t0, t1, target)]."""
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    data = {"fps": meta["fps"], "n": meta["n"], "w": meta["w"], "h": meta["h"],
            "frames": [{"i": f.i, "poly": None if f.poly is None else [list(p) for p in f.poly],
                        "conf": f.conf, "state": f.state, "target": f.target} for f in frames],
            "flagged": [[r[0], r[1], r[2]] for r in flagged]}
    tmp = work / "blur.json.tmp"
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, work / "blur.json")


def load_json(work):
    """-> (meta, frames, flagged[(t0, t1, target)])."""
    data = json.loads((Path(work) / "blur.json").read_text(encoding="utf-8"))
    meta = {k: data.get(k) for k in ("fps", "n", "w", "h")}
    frames = [FrameBox(int(f["i"]), None if f["poly"] is None else [tuple(p) for p in f["poly"]],
                       float(f["conf"]), f["state"], int(f.get("target", 0))) for f in data["frames"]]
    flagged = [(float(r[0]), float(r[1]), int(r[2]) if len(r) > 2 else 0) for r in data["flagged"]]
    return meta, frames, flagged


def summary(frames, flagged):
    windows = len(_ranges([f.i for f in frames if f.poly is not None and f.state != "lost"]))
    blurred = len({f.i for f in frames if f.poly is not None})
    unsure = sum(1 for f in frames if f.state in ("widened", "held"))
    return f"نوافذ {windows} · فريمات {blurred} · غير مؤكد {unsure} · مفقود>1ث {len(flagged)}"


def merge_targets(old, old_flag, new, new_flag, target, remark, fps):
    """Add `new` (all of one target) to the file. Only an explicit re-mark of the same target (`remark`)
    may clear that target's earlier flagged ranges, and only those the new track covers on every frame."""
    covered = {f.i for f in new if f.poly is not None and f.state != "lost"}
    keep = [r for r in old_flag
            if not (remark and r[2] == target
                    and all(i in covered for i in range(round(r[0] * fps), round(r[1] * fps))))]
    return list(old) + list(new), keep + list(new_flag)


def band_frames(frames, flagged, fps, width, height, lost_widen=2.0):
    """--accept-band: per flagged range, a full-width band over the rows of that target's last known polygon
    (else its first known one after the range); a target with no known polygon at all gets the whole frame."""
    extra = []
    for t0, t1, tid in flagged:
        i0, i1 = round(t0 * fps), round(t1 * fps)
        known = sorted((f for f in frames if f.target == tid and f.poly is not None and f.state != "lost"),
                       key=lambda f: f.i)
        src = [f for f in known if f.i < i0][-1:] or [f for f in known if f.i >= i1][:1]
        if src:
            ys = np.asarray(src[0].poly, float)[:, 1]
            c, half = (ys.min() + ys.max()) / 2, (ys.max() - ys.min()) / 2 * lost_widen
            ya, yb = max(c - half, 0), min(c + half, height)
        else:
            ya, yb = 0, height
        extra += [FrameBox(i, [(0, ya), (width, ya), (width, yb), (0, yb)], 0.0, "lost", tid) for i in range(i0, i1)]
    return extra


def _floats(s, n):
    v = [float(x) for x in s.split(",")]
    if len(v) != n:
        raise ValueError(f"expected {n} comma-separated numbers, got {s!r}")
    return v


def _ranges_text(flagged):
    return "، ".join(f"هدف {r[2]}: {r[0]:.2f}-{r[1]:.2f}ث" for r in flagged)


def _load_existing(args, meta, remark=False):
    """Refuse to overwrite a filled blur.json unless --add/--target/--replace; with --add/--target load it
    (and check it was made from this video). -> (old_frames, old_flagged, existing target ids)."""
    old, old_flag = [], []
    bj = Path(args.work) / "blur.json"
    add = getattr(args, "add", False)
    if not (add or remark or args.replace) and bj.exists() and load_json(args.work)[1]:
        raise ValueError("blur.json فيه أهداف — هدف جديد: --add · تعديل هدف: --target رقمه · "
                         "تبدأ من الصفر: --replace")
    if (add or remark) and bj.exists():
        old_meta, old, old_flag = load_json(args.work)
        if any(old_meta.get(k) != meta[k] for k in ("n", "w", "h")) or old_meta.get("fps") is None                 or abs(float(old_meta["fps"]) - meta["fps"]) > 1e-3:
            raise Mismatch("blur.json من فيديو ثاني — ما أقدر أضيف عليه")
    return old, old_flag, {f.target for f in old}


def _finish(work, meta, all_frames, all_flag):
    save_json(work, meta, all_frames, all_flag)
    print(summary(all_frames, all_flag))
    if all_flag:
        print(f"⛔ الهدف ضاع أكثر من ثانية: {_ranges_text(all_flag)} — حدّده من جديد "
              f"(box … --target رقمه) أو apply --accept-band", file=sys.stderr)
        return 3
    return 0


def _detect_cmd(args, meta):
    import _detect
    kinds = [k.strip().lower() for k in args.kinds.split(",") if k.strip()]
    other = [k for k in kinds if k not in _detect.ROUTE_A]
    if other or not kinds:
        raise ValueError(f"ما أكشف «{'، '.join(other) or '—'}» بروحي (أعرف: {', '.join(_detect.ROUTE_A)}). "
                         "غيرها بالطريق الثاني: keyframes ثم boxes (references/blur.md)")
    finders, bgr = [], False
    if "face" in kinds:
        model = _detect.face_model()
        if model is None:
            print("⚠️ نموذج الوجوه ناقص (00_setup.sh --extras) — الوجوه بالطريق الثاني: keyframes + boxes")
            kinds = [k for k in kinds if k != "face"]
            if not kinds:
                raise ValueError("ما بقى شي أكشفه بروحي — الوجوه: keyframes ثم boxes، أو ثبّت النموذج")
        else:
            finders.append(lambda img, ks: _detect.find_faces(img, model))
            bgr = True
    if any(k in ("qr", "barcode") for k in kinds):
        finders.append(_detect.find_codes)
    old, old_flag, ids = _load_existing(args, meta)
    fps = meta["fps"]
    i0, i1 = _window(Path(args.video), args.t0, args.t1)
    dets = _detect.scan(Path(args.video), set(kinds), i0, i1, bgr=bgr, finders=finders)
    tracks = _detect.link(dets, fps, max(meta["w"], meta["h"]))
    for k in kinds:
        if not any(t["kind"] == k for t in tracks):
            print(f"ما لقيت: {k}")
    if not tracks:
        return 0
    all_frames, all_flag = old, old_flag
    tid = max(ids) + 1 if (args.add and ids) else 0
    for t in tracks:
        frames = _detect.fill(Path(args.video), t["q"], i0, i1)
        frames, flagged = apply_failsafe([replace(f, target=tid) for f in frames], fps)
        all_frames, all_flag = merge_targets(all_frames, all_flag, frames, [(a, b, tid) for a, b in flagged],
                                             tid, False, fps)
        tid += 1
    return _finish(args.work, meta, all_frames, all_flag)


def _boxes_cmd(args, meta):
    """boxes.json = {"items": [{"id", "t", "box": [x, y, w, h]}], "not_found": [names]}, in keyframe pixels."""
    import _detect
    kj = Path(args.work) / "kf" / "keyframes.json"
    if not kj.exists():
        raise ValueError("ما فيه kf/keyframes.json — شغّل keyframes أول")
    scale = float(json.loads(kj.read_text(encoding="utf-8"))["scale"])
    data = json.loads(Path(args.boxes).read_text(encoding="utf-8"))
    fps, n, w, h = meta["fps"], meta["n"], meta["w"], meta["h"]
    groups = {}
    for it in data.get("items", []):
        iid, t = str(it["id"]), float(it["t"])
        x, y, bw, bh = (float(v) / scale for v in it["box"])
        x0, y0, x1, y1 = max(x, 0), max(y, 0), min(x + bw, w), min(y + bh, h)
        if not (0 <= round(t * fps) < n):
            raise ValueError(f"{iid}: الوقت {t}ث برّا الفيديو (طوله {n / fps:.2f}ث)")
        if x1 - x0 < 8 or y1 - y0 < 8:
            raise ValueError(f"{iid}: المربع برّا الفريم أو صغير وايد")
        groups.setdefault(iid, []).append((t, (x0, y0, x1 - x0, y1 - y0)))
    old, old_flag, ids = _load_existing(args, meta)
    for name in data.get("not_found", []):
        print(f"ما لقيت: {name}")
    if not groups:
        return 0
    all_frames, all_flag = old, old_flag
    tid = max(ids) + 1 if (args.add and ids) else 0
    for iid, anchors in groups.items():
        try:
            frames = _detect.track_anchors(Path(args.video), anchors)
        except ValueError as e:
            raise ValueError(f"{iid}: {e}") from e
        frames, flagged = apply_failsafe([replace(f, target=tid) for f in frames], fps)
        all_frames, all_flag = merge_targets(all_frames, all_flag, frames, [(a, b, tid) for a, b in flagged],
                                             tid, False, fps)
        print(f"هدف {tid} = {iid}")
        tid += 1
    return _finish(args.work, meta, all_frames, all_flag)


def main(argv=None):
    ap = argparse.ArgumentParser(description="privacy blur: track → fail-safe → render → QA sheet")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("ref")
    r.add_argument("work"); r.add_argument("video"); r.add_argument("ref_img"); r.add_argument("region")
    b = sub.add_parser("box")
    b.add_argument("work"); b.add_argument("video"); b.add_argument("t", type=float); b.add_argument("box")
    for p in (r, b):
        p.add_argument("--from", dest="t0", type=float, default=0)
        p.add_argument("--to", dest="t1", type=float, default=None)
        g = p.add_mutually_exclusive_group()
        g.add_argument("--add", action="store_true", help="a new target, kept next to the ones in blur.json")
        g.add_argument("--target", type=int, default=None, help="re-mark this existing target")
        g.add_argument("--replace", action="store_true", help="start blur.json over, dropping its targets")
    dt = sub.add_parser("detect", help="find qr / barcode / face by itself")
    dt.add_argument("work"); dt.add_argument("video")
    dt.add_argument("--kinds", required=True, help="comma list: qr,barcode,face")
    dt.add_argument("--from", dest="t0", type=float, default=0)
    dt.add_argument("--to", dest="t1", type=float, default=None)
    g = dt.add_mutually_exclusive_group()
    g.add_argument("--add", action="store_true", help="new targets, kept next to the ones in blur.json")
    g.add_argument("--replace", action="store_true", help="start blur.json over, dropping its targets")
    kf = sub.add_parser("keyframes", help="a few frames for a subagent to box items named in words")
    kf.add_argument("work"); kf.add_argument("video")
    kf.add_argument("--every", type=float, default=2.0)
    kf.add_argument("--max", dest="max_n", type=int, default=12)
    kf.add_argument("--from", dest="t0", type=float, default=0)
    kf.add_argument("--to", dest="t1", type=float, default=None)
    bx = sub.add_parser("boxes", help="the subagent's boxes.json -> one tracked target per id")
    bx.add_argument("work"); bx.add_argument("video"); bx.add_argument("boxes")
    g = bx.add_mutually_exclusive_group()
    g.add_argument("--add", action="store_true", help="new targets, kept next to the ones in blur.json")
    g.add_argument("--replace", action="store_true", help="start blur.json over, dropping its targets")
    a = sub.add_parser("apply")
    a.add_argument("work"); a.add_argument("video_in"); a.add_argument("video_out")
    a.add_argument("--accept-band", action="store_true")
    a.add_argument("--strength", type=int, default=31)
    q = sub.add_parser("qa")
    q.add_argument("work"); q.add_argument("video"); q.add_argument("out")
    q.add_argument("--max-tiles", type=int, default=24)
    q.add_argument("--outside", type=int, default=6, help="frames with no blur, to spot a missed item")
    args = ap.parse_args(argv)
    # blur.md runs from the skill folder with bare names (`box <work> cut.mp4 …`): those mean files in <work>
    for k in ("video", "video_in", "ref_img", "boxes"):
        v = getattr(args, k, None)
        if v and not Path(v).is_absolute() and (Path(args.work) / v).exists():
            setattr(args, k, str(Path(args.work) / v))
    for k in ("video_out", "out"):
        v = getattr(args, k, None)
        if v and not Path(v).is_absolute() and Path(v).parent == Path("."):
            setattr(args, k, str(Path(args.work) / v))

    if cv2 is None:
        print("⛔ ناقص opencv — شغّل: bash scripts/00_setup.sh --extras", file=sys.stderr)
        return 2
    try:
        if args.cmd in ("ref", "box"):
            meta = video_meta(args.video)
            fps = meta["fps"]
            remark = args.target is not None
            old, old_flag, ids = _load_existing(args, meta, remark)
            tid = 0
            if remark:
                if args.target not in ids:
                    raise ValueError(f"ما فيه هدف رقم {args.target} بـblur.json (الموجود: {sorted(ids)})")
                tid = args.target
            elif args.add:
                tid = max(ids) + 1 if ids else 0
            if args.cmd == "ref":
                frames = track_reference(Path(args.video), Path(args.ref_img), tuple(_floats(args.region, 4)),
                                         args.t0, args.t1)
            else:
                frames = track_box(Path(args.video), args.t, tuple(_floats(args.box, 4)), args.t0, args.t1)
            frames, flagged = apply_failsafe([replace(f, target=tid) for f in frames], fps)
            all_frames, all_flag = merge_targets(old, old_flag, frames, [(a_, b_, tid) for a_, b_ in flagged],
                                                 tid, remark, fps)
            return _finish(args.work, meta, all_frames, all_flag)
        if args.cmd == "detect":
            return _detect_cmd(args, video_meta(args.video))
        if args.cmd == "keyframes":
            import _detect
            i0, i1 = _window(Path(args.video), args.t0, args.t1)
            idx = _detect.pick_keyframes(Path(args.video), i0, i1, args.every, args.max_n)
            out = _detect.write_keyframes(Path(args.video), Path(args.work), idx)
            print(f"{len(idx)} لقطة → {out}")
            return 0
        if args.cmd == "boxes":
            return _boxes_cmd(args, video_meta(args.video))
        if args.cmd == "apply":
            meta, frames, flagged = load_json(args.work)
            check_video(meta, args.video_in)
            if flagged and not args.accept_band:
                print(f"⛔ ما أطبّق البلر: فيه مدى ضاع فيه الهدف ({_ranges_text(flagged)}). حدّده من جديد "
                      f"(box … --target رقمه) أو وافق على شريط بعرض الفريم (--accept-band).", file=sys.stderr)
                return 3
            if flagged:
                frames = frames + band_frames(frames, flagged, meta["fps"], meta["w"], meta["h"])
            render_blur(Path(args.video_in), frames, Path(args.video_out), args.strength, meta["n"])
            print(args.video_out)
            return 0
        meta, frames, _ = load_json(args.work)
        check_video(meta, args.video)
        n = qa_sheet(Path(args.video), frames, Path(args.out), args.max_tiles, args.outside, meta.get("n"))
        print(f"{args.out} · {n} لقطة")
        return 0
    except Mismatch as e:
        print(f"⛔ {e}", file=sys.stderr)
        return 3
    except (ValueError, FileNotFoundError, RuntimeError) as e:
        print(f"⛔ {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
