"""Synthetic videos for the blur tests: a 200x120 noise patch moving over a grey 640x360 frame."""
import subprocess
from pathlib import Path

import cv2
import numpy as np

W, H = 640, 360
PW, PH = 200, 120
GREY = 128


def patch():
    """Deterministic texture: coarse blobs + fine grain (SIFT needs blob-like structure)."""
    rng = np.random.default_rng(7)
    coarse = cv2.resize(rng.integers(0, 256, (24, 40), dtype=np.uint8), (PW, PH), interpolation=cv2.INTER_CUBIC)
    fine = rng.integers(-30, 31, (PH, PW))
    g = np.clip(coarse.astype(int) + fine, 0, 255).astype(np.uint8)
    return cv2.cvtColor(g, cv2.COLOR_GRAY2BGR)


def make_ref(path):
    path = Path(path)
    ok, buf = cv2.imencode(".png", patch())
    assert ok
    buf.tofile(str(path))  # np.tofile: works with Arabic paths on Windows
    return path


def linear(i, n):
    """Top-left of the patch: left-to-right and slightly down, always fully inside the frame."""
    k = i / max(n - 1, 1)
    return round(20 + 400 * k), round(60 + 120 * k)


def make_video(path, n=90, fps=30, occlude=None, traj=None, audio=False):
    """Write the clip; return the true patch centre per frame (None when off-frame).

    occlude=(f0, f1) paints the patch grey for frames f0..f1-1.
    traj(i, n) -> (x, y) top-left, overrides the linear path; the patch is clipped at the frame edge.
    """
    path = Path(path)
    tex = patch()
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
           "-r", str(fps), "-i", "-"]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={n / fps:.3f}", "-c:a", "aac", "-shortest"]
    cmd += ["-c:v", "libx264", "-crf", "10", "-pix_fmt", "yuv420p", "-g", "30", str(path)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    truth = []
    for i in range(n):
        f = np.full((H, W, 3), GREY, np.uint8)
        x, y = (traj or linear)(i, n)
        x0, y0, x1, y1 = max(x, 0), max(y, 0), min(x + PW, W), min(y + PH, H)
        visible = x0 < x1 and y0 < y1
        if visible and not (occlude and occlude[0] <= i < occlude[1]):
            f[y0:y1, x0:x1] = tex[y0 - y:y1 - y, x0 - x:x1 - x]
        truth.append((x + PW / 2, y + PH / 2) if visible else None)
        p.stdin.write(f.tobytes())
    p.stdin.close()
    assert p.wait() == 0
    return truth


def make_vfr(src, dst, at=30, gap=0.1):
    """Variable frame rate: a `gap`-second hole in the timestamps from frame `at` on (phone-style VFR)."""
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src),
                        "-vf", f"setpts='if(gte(N,{at}),PTS+{gap}/TB,PTS)'", "-fps_mode", "passthrough",
                        "-c:v", "libx264", "-crf", "10", "-pix_fmt", "yuv420p", str(dst)])
    assert r.returncode == 0
    return Path(dst)


def make_offset(src, dst, offset=0.067):
    """Video stream that starts `offset` s after the audio (as many phone clips do)."""
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
                        "-itsoffset", str(offset), "-i", str(src), "-map", "1:v", "-map", "0:a",
                        "-c:v", "copy", "-c:a", "aac", str(dst)])
    assert r.returncode == 0
    return Path(dst)


# ---- codes (QR / EAN-13) on a portrait frame, for auto-detect tests -------------------------------------------------
CW, CH = 540, 960
_EAN_L = ["0001101", "0011001", "0010011", "0111101", "0100011", "0110001", "0101111", "0111011", "0110111", "0001011"]
_EAN_G = ["0100111", "0110011", "0011011", "0100001", "0011101", "0111001", "0000101", "0010001", "0001001", "0010111"]
_EAN_R = ["1110010", "1100110", "1101100", "1000010", "1011100", "1001110", "1010000", "1000100", "1001000", "1110100"]
_EAN_P = ["LLLLLL", "LLGLGG", "LLGGLG", "LLGGGL", "LGLLGG", "LGGLLG", "LGGGLL", "LGLGLG", "LGLGGL", "LGGLGL"]


def ean13_tile(code="4006381333931", module=3, height=140, quiet=10):
    par = _EAN_P[int(code[0])]
    bits = "101" + "".join((_EAN_L if par[i] == "L" else _EAN_G)[int(c)] for i, c in enumerate(code[1:7]))
    bits += "01010" + "".join(_EAN_R[int(c)] for c in code[7:]) + "101"
    t = np.full((height + 20, (len(bits) + 2 * quiet) * module), 255, np.uint8)
    for i, b in enumerate(bits):
        if b == "1":
            t[10:10 + height, (quiet + i) * module:(quiet + i + 1) * module] = 0
    return t


def qr_tile(text="TEST-123", size=200):
    q = cv2.QRCodeEncoder.create().encode(text)
    return cv2.resize(q, (size, size), interpolation=cv2.INTER_NEAREST)


def _ink_quad(tile):
    ys, xs = np.nonzero(tile < 128)
    x0, y0, x1, y1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
    return np.float32([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


def make_code_video(path, codes, n=60, fps=30, hide=None):
    """codes: [{"tile": uint8 gray, "start": (x, y), "end": (x, y), "warp": degrees around the vertical axis}].
    hide=(f0, f1) leaves every code out of frames f0..f1-1.
    Returns truth[i] = list (one per code) of the 4 true ink corners in frame pixels, or None when hidden."""
    path = Path(path)
    rng = np.random.default_rng(3)
    bg = np.clip(150 + rng.integers(-12, 13, (CH, CW)), 0, 255).astype(np.uint8)
    prepared = []
    for c in codes:
        t = c["tile"]
        h, w = t.shape
        src = np.float32([(0, 0), (w, 0), (w, h), (0, h)])
        a = np.deg2rad(c.get("warp", 0))
        dw, shrink = w * np.cos(a), 0.5 * h * (1 - np.cos(a))
        dst = np.float32([(0, 0), (dw, shrink), (dw, h - shrink), (0, h)])
        Hm = cv2.getPerspectiveTransform(src, dst)
        size = (int(np.ceil(dw)), h)
        tile = cv2.warpPerspective(t, Hm, size, flags=cv2.INTER_LINEAR, borderValue=255)
        mask = cv2.warpPerspective(np.full_like(t, 255), Hm, size, flags=cv2.INTER_NEAREST)
        ink = cv2.perspectiveTransform(_ink_quad(t).reshape(-1, 1, 2), Hm).reshape(-1, 2)
        prepared.append((tile, mask > 0, ink, c))
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{CW}x{CH}",
           "-r", str(fps), "-i", "-", "-c:v", "libx264", "-crf", "12", "-pix_fmt", "yuv420p", "-g", "30", str(path)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    truth = []
    for i in range(n):
        f = bg.copy()
        k = i / max(n - 1, 1)
        if hide and hide[0] <= i < hide[1]:
            truth.append(None)
        else:
            row = []
            for tile, m, ink, c in prepared:
                x = round(c["start"][0] + (c["end"][0] - c["start"][0]) * k)
                y = round(c["start"][1] + (c["end"][1] - c["start"][1]) * k)
                region = f[y:y + tile.shape[0], x:x + tile.shape[1]]
                region[m] = tile[m]
                row.append(ink + np.float32([x, y]))
            truth.append(row)
        p.stdin.write(f.tobytes())
    p.stdin.close()
    assert p.wait() == 0
    return truth


def make_cut_video(path, n=90, fps=30, cut=45):
    """Two different shots joined at frame `cut`: grey with the noise patch, then a bright striped scene."""
    path = Path(path)
    tex = patch()
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
           "-r", str(fps), "-i", "-", "-c:v", "libx264", "-crf", "12", "-pix_fmt", "yuv420p", "-g", "30", str(path)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    stripes = np.zeros((H, W, 3), np.uint8)
    stripes[:, ::40] = 230
    stripes = cv2.blur(stripes, (15, 1)) + 20
    for i in range(n):
        if i < cut:
            f = np.full((H, W, 3), GREY, np.uint8)
            x, y = linear(i, n)
            f[y:y + PH, x:x + PW] = tex
        else:
            f = np.roll(stripes, 2 * i, axis=1)
        p.stdin.write(f.tobytes())
    p.stdin.close()
    assert p.wait() == 0
