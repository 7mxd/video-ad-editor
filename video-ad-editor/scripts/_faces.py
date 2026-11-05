# -*- coding: utf-8 -*-
"""راصد الوجه: Vision بالماك (facetrack.swift) أول، وإلا OpenCV (بديل أقل دقة) — نفس صيغة JSON.
   python _faces.py <inDir> <out.json>     ← نفس واجهة برنامج facetrack (البديل بدون ماك)
   لكل صورة jpg: {"f", "face":{x,y,w,h} نِسَب 0..1 الأصل أعلى يسار, "n", "mouth"}
   «mouth» بالبديل = تباين منطقة الفم (تقريب لحركته، مو قياس فتحة) — يكفي لـ«من يتكلم» لأنه نسبي.
   على الماك (swiftc موجود) المسار ما تغيّر: Vision دائماً."""
import json, os, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))


def have_swiftc():
    return bool(shutil.which("swiftc"))


def have_cv2():
    try:
        import cv2  # noqa: F401
        return True
    except Exception:
        return False


def pick_tracker(has_swiftc, has_cv2):
    """"vision" (ماك) · "opencv" (بديل) · "" (ولا واحد → بلا تتبّع)"""
    return "vision" if has_swiftc else ("opencv" if has_cv2 else "")


def tracker_cmd(ft, has_swiftc=None, has_cv2=None):
    """(النوع, أمر يُلحق به <inDir> <out.json>) — أو ("", None). ft = مسار برنامج Vision المبني (كاش)."""
    sw = have_swiftc() if has_swiftc is None else has_swiftc
    cv = have_cv2() if has_cv2 is None else has_cv2
    kind = pick_tracker(sw, cv)
    if kind == "vision":
        if os.path.exists(ft): return "vision", [ft]
        os.makedirs(os.path.dirname(ft) or ".", exist_ok=True)
        r = subprocess.run(["swiftc", "-O", "-o", ft, os.path.join(HERE, "facetrack.swift")], capture_output=True)
        if r.returncode == 0 and os.path.exists(ft): return "vision", [ft]
        kind = pick_tracker(False, cv)
    if kind == "opencv": return "opencv", [sys.executable, os.path.abspath(__file__)]
    return "", None


def _jpgs(in_dir):
    return sorted(f for f in os.listdir(in_dir) if f.endswith(".jpg"))


def write_empty(in_dir, out):
    """بلا راصد: صف لكل صورة بدون وجه — الباقي يرجع لقصّ من النص."""
    json.dump([{"f": f} for f in _jpgs(in_dir)], open(out, "w", encoding="utf-8"))


def _haar():
    import cv2
    c = cv2.CascadeClassifier(os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml"))
    def det(gray, name):
        m = max(24, int(0.06 * min(gray.shape[:2])))
        return [tuple(int(v) for v in b) for b in c.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(m, m))]
    return det


def detect(in_dir, out, detector=None):
    """نفس مخرج facetrack.swift. detector(gray, name) → [(x,y,w,h) بكسل] (للاختبار)."""
    import cv2
    import numpy as np
    det = detector or _haar()
    rows = []
    for f in _jpgs(in_dir):
        # np.fromfile + imdecode: يقرا مسارات عربية على ويندوز (cv2.imread ما يقدر)، وبلا Pillow
        g = cv2.imdecode(np.fromfile(os.path.join(in_dir, f), np.uint8), cv2.IMREAD_GRAYSCALE)
        H, W = g.shape; row = {"f": f}
        bs = list(det(g, f))
        if bs:
            x, y, w, h = max(bs, key=lambda b: b[2] * b[3])
            row["face"] = {"x": x / W, "y": y / H, "w": w / W, "h": h / H}
            roi = g[y + int(0.65 * h):y + int(0.95 * h), x + int(0.25 * w):x + int(0.75 * w)]
            row["mouth"] = float(roi.std() / 255.0) if roi.size else 0.0
            row["n"] = len(bs)
        rows.append(row)
    json.dump(rows, open(out, "w", encoding="utf-8"))
    print(f"faces: {len(rows)} (OpenCV)")


if __name__ == "__main__":
    if len(sys.argv) < 3: print(__doc__); sys.exit(2)
    detect(sys.argv[1], sys.argv[2])
