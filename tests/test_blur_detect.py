"""Auto-detect blur: route A (qr / barcode / face) and route B (keyframes + boxes)."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

cv2 = pytest.importorskip("cv2")
import numpy as np  # noqa: E402

SCRIPTS = Path(__file__).resolve().parents[1] / "video-ad-editor" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import blur_track as bt  # noqa: E402
from fixtures_blur import ean13_tile, make_code_video, qr_tile  # noqa: E402


def run_cli(*args):
    return subprocess.run([sys.executable, str(SCRIPTS / "blur_track.py"), *map(str, args)],
                          capture_output=True, text=True, encoding="utf-8")


def polys_by_frame(work):
    _, frames, _ = bt.load_json(work)
    out = {}
    for f in frames:
        if f.poly is not None:
            out.setdefault(f.i, []).append((f.target, np.float32(f.poly)))
    return out


def covered(polys, quad, tol=1.5):
    """Every corner of quad lies inside (or within tol px of) one of the polygons."""
    for _, p in polys:
        if all(cv2.pointPolygonTest(p.reshape(-1, 1, 2), (float(x), float(y)), True) >= -tol for x, y in quad):
            return True
    return False


def assert_all_covered(work, truth):
    P = polys_by_frame(work)
    miss = [i for i, row in enumerate(truth) if row for q in row if not covered(P.get(i, []), q)]
    assert not miss, f"frames with an uncovered code: {miss[:10]} (of {len(miss)})"


@pytest.fixture(scope="module")
def vids(tmp_path_factory):
    d = tmp_path_factory.mktemp("detect")
    v = {"dir": d}
    v["qr"] = (d / "qr.mp4", make_code_video(d / "qr.mp4", [{"tile": qr_tile(), "start": (40, 80), "end": (280, 600)}]))
    v["bar"] = (d / "bar.mp4", make_code_video(d / "bar.mp4", [{"tile": ean13_tile(), "start": (20, 700),
                                                                  "end": (60, 200)}]))
    v["three"] = (d / "three.mp4", make_code_video(d / "three.mp4", [
        {"tile": qr_tile("A-1", 150), "start": (10, 100), "end": (10, 500)},
        {"tile": qr_tile("B-2", 150), "start": (195, 100), "end": (195, 500)},
        {"tile": qr_tile("C-3", 150), "start": (380, 100), "end": (380, 500)}]))
    v["warp"] = (d / "warp.mp4", make_code_video(d / "warp.mp4", [{"tile": qr_tile(size=240), "warp": 35,
                                                                    "start": (60, 100), "end": (200, 500)}]))
    v["none"] = (d / "none.mp4", make_code_video(d / "none.mp4", []))
    return v


def test_qr_every_frame_covered(vids, tmp_path):
    video, truth = vids["qr"]
    r = run_cli("detect", tmp_path, video, "--kinds", "qr")
    assert r.returncode == 0, r.stderr
    assert_all_covered(tmp_path, truth)


def test_barcode_found(vids, tmp_path):
    video, truth = vids["bar"]
    r = run_cli("detect", tmp_path, video, "--kinds", "barcode")
    assert r.returncode == 0, r.stderr
    assert_all_covered(tmp_path, truth)


def test_three_qrs_three_targets(vids, tmp_path):
    video, truth = vids["three"]
    assert run_cli("detect", tmp_path, video, "--kinds", "qr").returncode == 0
    _, frames, _ = bt.load_json(tmp_path)
    assert {f.target for f in frames if f.poly is not None} == {0, 1, 2}
    owner = {}
    for f in frames:
        if f.poly is None or not truth[f.i]:
            continue
        c = np.float32(f.poly).mean(0)
        k = int(np.argmin([np.linalg.norm(q.mean(0) - c) for q in truth[f.i]]))
        owner.setdefault(f.target, set()).add(k)
    assert all(len(s) == 1 for s in owner.values()), owner
    assert_all_covered(tmp_path, truth)


def test_short_hide_same_target(tmp_path):
    video = tmp_path / "h.mp4"
    make_code_video(video, [{"tile": qr_tile(), "start": (100, 300), "end": (100, 300)}], n=60, hide=(20, 35))
    assert run_cli("detect", tmp_path, video, "--kinds", "qr").returncode == 0
    _, frames, _ = bt.load_json(tmp_path)
    assert {f.target for f in frames if f.poly is not None} == {0}


def test_long_hide_new_target(tmp_path):
    video = tmp_path / "h.mp4"
    make_code_video(video, [{"tile": qr_tile(), "start": (100, 300), "end": (100, 300)}], n=120, hide=(30, 90))
    assert run_cli("detect", tmp_path, video, "--kinds", "qr").returncode == 0
    _, frames, flagged = bt.load_json(tmp_path)
    assert {f.target for f in frames if f.poly is not None} == {0, 1}
    assert flagged == []


def test_perspective_qr_corners_covered(vids, tmp_path):
    video, truth = vids["warp"]
    assert run_cli("detect", tmp_path, video, "--kinds", "qr").returncode == 0
    assert_all_covered(tmp_path, truth)


def test_not_found_message(vids, tmp_path):
    video, _ = vids["none"]
    r = run_cli("detect", tmp_path, video, "--kinds", "qr")
    assert r.returncode == 0, r.stderr
    assert "ما لقيت: qr" in r.stdout
    assert not (tmp_path / "blur.json").exists() or not polys_by_frame(tmp_path)


def test_detect_refuses_overwrite(vids, tmp_path):
    video, _ = vids["qr"]
    assert run_cli("detect", tmp_path, video, "--kinds", "qr").returncode == 0
    before = (tmp_path / "blur.json").read_bytes()
    r = run_cli("detect", tmp_path, video, "--kinds", "qr")
    assert r.returncode == 2
    assert (tmp_path / "blur.json").read_bytes() == before


def test_unknown_kind_exit2(vids, tmp_path):
    video, _ = vids["qr"]
    r = run_cli("detect", tmp_path, video, "--kinds", "plate")
    assert r.returncode == 2
    assert "keyframes" in r.stderr
