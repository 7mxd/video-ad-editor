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
