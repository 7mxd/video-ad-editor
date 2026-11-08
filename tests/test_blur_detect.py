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


# ---- faces (Task 3) ----------------------------------------------------------------------------------------------
import os  # noqa: E402

import _detect  # noqa: E402


def run_cli_env(env_extra, *args):
    env = dict(os.environ, **env_extra)
    return subprocess.run([sys.executable, str(SCRIPTS / "blur_track.py"), *map(str, args)],
                          capture_output=True, text=True, encoding="utf-8", env=env)


def test_face_model_missing_warns(vids, tmp_path):
    video, truth = vids["qr"]
    home = tmp_path / "home"
    home.mkdir()
    work = tmp_path / "w"
    r = run_cli_env({"VAE_HOME": str(home)}, "detect", work, video, "--kinds", "face,qr")
    assert r.returncode == 0, r.stderr
    assert "نموذج الوجوه ناقص" in r.stdout + r.stderr
    assert_all_covered(work, truth)
    r = run_cli_env({"VAE_HOME": str(home)}, "detect", tmp_path / "w2", video, "--kinds", "face")
    assert r.returncode == 2


def test_face_model_sha_mismatch(tmp_path, monkeypatch):
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / _detect.YUNET_FILE).write_bytes(b"not a model")
    monkeypatch.setenv("VAE_HOME", str(tmp_path))
    assert _detect.face_model() is None


def test_face_plumbing(tmp_path, monkeypatch):
    """A dark square stands in for a face; the fake detector finds it on the BGR frame it is given."""
    video = tmp_path / "f.mp4"
    tile = np.zeros((120, 120), np.uint8)
    truth = make_code_video(video, [{"tile": tile, "start": (50, 100), "end": (300, 600)}])

    def fake_faces(bgr, model):
        assert bgr.ndim == 3
        ys, xs = np.nonzero(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY) < 60)
        if xs.size == 0:
            return []
        x0, y0, x1, y1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
        return [("face", np.float32([(x0, y0), (x1, y0), (x1, y1), (x0, y1)]))]

    monkeypatch.setattr(_detect, "face_model", lambda: Path("fake.onnx"))
    monkeypatch.setattr(_detect, "find_faces", fake_faces)
    assert bt.main(["detect", str(tmp_path), str(video), "--kinds", "face"]) == 0
    _, frames, _ = bt.load_json(tmp_path)
    assert {f.target for f in frames if f.poly is not None} == {0}
    assert_all_covered(tmp_path, truth)


# ---- route B: keyframes + boxes (Task 4) -------------------------------------------------------------------------
from fixtures_blur import make_cut_video  # noqa: E402


def keyframes(work, video, *extra):
    r = run_cli("keyframes", work, video, *extra)
    assert r.returncode == 0, r.stderr
    return json.loads((Path(work) / "kf" / "keyframes.json").read_text(encoding="utf-8"))


def write_boxes(path, items, not_found=()):
    Path(path).write_text(json.dumps({"items": items, "not_found": list(not_found)}), encoding="utf-8")
    return path


def kf_box(quad, scale, pad=4):
    x0, y0 = quad.min(0) - pad
    x1, y1 = quad.max(0) + pad
    return [float(x0 * scale), float(y0 * scale), float((x1 - x0) * scale), float((y1 - y0) * scale)]


def test_keyframes_cap_and_cut(tmp_path):
    video = tmp_path / "cut.mp4"
    make_cut_video(video)
    kf = keyframes(tmp_path, video)
    idx = sorted(f["i"] for f in kf["frames"])
    assert 1 <= len(idx) <= 12
    assert any(abs(i - 45) <= 2 for i in idx), idx
    assert all(b - a >= 15 for a, b in zip(idx, idx[1:])), idx


def test_keyframes_arabic_path(vids, tmp_path):
    video, _ = vids["qr"]
    work = tmp_path / "عمل تجريبي"
    kf = keyframes(work, video)
    assert kf["frames"]
    for f in kf["frames"]:
        img = cv2.imdecode(np.fromfile(str(work / "kf" / f["file"]), np.uint8), cv2.IMREAD_COLOR)
        assert img is not None and max(img.shape[:2]) <= 720


def test_boxes_scale_back(vids, tmp_path):
    video, truth = vids["qr"]
    kf = keyframes(tmp_path, video)
    assert kf["scale"] == pytest.approx(0.75)
    f0 = kf["frames"][0]
    bj = write_boxes(tmp_path / "b.json", [{"id": "code-1", "t": f0["t"], "box": kf_box(truth[f0["i"]][0], kf["scale"])}])
    r = run_cli("boxes", tmp_path, video, bj)
    assert r.returncode == 0, r.stderr
    assert_all_covered(tmp_path, truth)


def test_boxes_two_anchors_one_target(vids, tmp_path):
    video, truth = vids["qr"]
    kf = keyframes(tmp_path, video)
    s = kf["scale"]
    items = [{"id": "code-1", "t": t, "box": kf_box(truth[round(t * 30)][0], s)} for t in (0.5, 1.5)]
    r = run_cli("boxes", tmp_path, video, write_boxes(tmp_path / "b.json", items))
    assert r.returncode == 0, r.stderr
    _, frames, _ = bt.load_json(tmp_path)
    assert {f.target for f in frames if f.poly is not None} == {0}
    assert_all_covered(tmp_path, truth)


def test_boxes_out_of_frame_clipped(vids, tmp_path):
    video, truth = vids["qr"]
    kf = keyframes(tmp_path, video)
    s = kf["scale"]
    x, y, w, h = kf_box(truth[30][0], s)
    items = [{"id": "edge", "t": 1.0, "box": [x, y, 540 * s - x + 80, h]}]   # hangs 80 px past the right edge
    r = run_cli("boxes", tmp_path, video, write_boxes(tmp_path / "b.json", items))
    assert r.returncode in (0, 3), r.stderr
    _, frames, _ = bt.load_json(tmp_path)
    anchor = [f for f in frames if f.i == 30 and f.poly is not None]
    assert anchor and np.float32(anchor[0].poly)[:, 0].max() <= 540 + 1


def test_boxes_bad_time_exit2(vids, tmp_path):
    video, truth = vids["qr"]
    kf = keyframes(tmp_path, video)
    good = [{"id": "code-1", "t": 1.0, "box": kf_box(truth[30][0], kf["scale"])}]
    assert run_cli("boxes", tmp_path, video, write_boxes(tmp_path / "b.json", good)).returncode == 0
    before = (tmp_path / "blur.json").read_bytes()
    bad = [{"id": "late", "t": 99.0, "box": [10, 10, 50, 50]}]
    r = run_cli("boxes", tmp_path, video, write_boxes(tmp_path / "b2.json", bad), "--add")
    assert r.returncode == 2
    assert "late" in r.stderr
    assert (tmp_path / "blur.json").read_bytes() == before


def test_boxes_not_found_message(vids, tmp_path):
    video, truth = vids["qr"]
    kf = keyframes(tmp_path, video)
    items = [{"id": "code-1", "t": 1.0, "box": kf_box(truth[30][0], kf["scale"])}]
    r = run_cli("boxes", tmp_path, video, write_boxes(tmp_path / "b.json", items, ["serial"]))
    assert r.returncode == 0, r.stderr
    assert "ما لقيت: serial" in r.stdout


def test_boxes_item_in_part_of_video_not_flagged(tmp_path):
    """An item that leaves the frame halfway is blurred while visible; the frames after it left are not 'lost'."""
    from fixtures_blur import make_video
    video = tmp_path / "leave.mp4"
    truth = make_video(video, n=90, traj=lambda i, n: (40 + 12 * i, 120))   # off the right edge from ~frame 50
    kf = keyframes(tmp_path, video)
    x, y = 40 + 12 * 15, 120
    items = [{"id": "patch", "t": 0.5, "box": [x * kf["scale"], y * kf["scale"], 200 * kf["scale"], 120 * kf["scale"]]}]
    r = run_cli("boxes", tmp_path, video, write_boxes(tmp_path / "b.json", items))
    assert r.returncode == 0, r.stderr
    _, _, flagged = bt.load_json(tmp_path)
    assert flagged == []
    assert truth[15] is not None
