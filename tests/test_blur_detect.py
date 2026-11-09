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
    bw, bh = 540 - x / s, h / s                                   # the box after clipping to the frame
    assert anchor and np.float32(anchor[0].poly)[:, 0].max() <= 540 + _detect.box_margin(bw, bh) + 1


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


# ---- final-review fixes ------------------------------------------------------------------------------------------
def _rot_square(cx, cy, half, deg):
    a = np.deg2rad(deg)
    R = np.float32([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])
    return (np.float32([(-half, -half), (half, -half), (half, half), (-half, half)]) @ R.T) + (cx, cy)


def test_fill_tilt_through_45_keeps_area(vids):
    """Corner order flips when a code's tilt crosses 45°; the interpolated frame must not shrink."""
    video, _ = vids["none"]
    track = {i: _detect._order(_rot_square(270, 480, 80, 40 + 2 * i)) for i in range(0, 8, 2)}
    frames = {f.i: f for f in _detect.fill(video, track, 0, 60)}
    full = cv2.contourArea(np.float32(_rot_square(270, 480, 80, 45)))
    for i in (1, 3, 5):
        assert frames[i].poly is not None
        assert cv2.contourArea(np.float32(frames[i].poly)) >= 0.95 * full, i


def test_fill_interpolates_long_gap_with_low_conf(vids):
    """Two detections 20 frames apart: the gap follows the motion (widened by the fail-safe), not held."""
    video, _ = vids["none"]
    q = lambda x: np.float32([(x, 400), (x + 100, 400), (x + 100, 500), (x, 500)])  # noqa: E731
    frames = {f.i: f for f in _detect.fill(video, {0: q(50), 20: q(250)}, 0, 60)}
    mid = frames[10]
    assert mid.poly is not None and mid.conf < 0.5
    assert abs(np.float32(mid.poly).mean(0)[0] - 200) < 10


def test_track_anchors_windows_between_neighbours(monkeypatch):
    calls = []

    def fake(video, t, box, t0=0, t1=None):
        calls.append((t, t0, t1))
        return [bt.FrameBox(round(t * 30), [(0, 0), (9, 0), (9, 9), (0, 9)], 1.0, "tracked")]

    monkeypatch.setattr(bt, "track_box", fake)
    _detect.track_anchors(Path("v.mp4"), [(2.5, (0, 0, 9, 9)), (0.5, (0, 0, 9, 9)), (1.5, (0, 0, 9, 9))], size=(540, 960))
    assert sorted(calls) == [(0.5, 0, 1.5), (1.5, 0.5, 2.5), (2.5, 1.5, None)]


def test_face_model_arabic_home(tmp_path, monkeypatch):
    src = Path(os.environ.get("VAE_HOME") or (Path.home() / ".video-ad-editor")) / "models" / _detect.YUNET_FILE
    if not src.is_file():
        pytest.skip("YuNet model not installed")
    home = tmp_path / "مجلد عربي"
    (home / "models").mkdir(parents=True)
    (home / "models" / _detect.YUNET_FILE).write_bytes(src.read_bytes())
    monkeypatch.setenv("VAE_HOME", str(home))
    model = _detect.face_model()
    assert model is not None
    _detect._DET.clear()
    assert _detect.find_faces(np.full((240, 320, 3), 128, np.uint8), model) == []


# ---- v1.1.1: a tight box must still blur past the text ends ------------------------------------------------------
def test_boxes_tight_text_box_gets_margin(tmp_path):
    """The subagent boxes the digits tight to the ink: the blur must still reach past both text ends on every
    frame (real clip: the first digits of a cert number stayed readable at the left edge of the box)."""
    from fixtures_blur import text_ink_quad, text_tile
    tile = text_tile()
    ink = text_ink_quad(tile)
    video = tmp_path / "cert.mp4"
    truth = make_code_video(video, [{"tile": tile, "start": (20, 300), "end": (90, 420)}])
    off = [np.float32(row[0]).min(0) - _ink_quad_of(tile).min(0) for row in truth]   # tile placement per frame
    kf = keyframes(tmp_path, video)
    f0 = kf["frames"][0]
    box = kf_box(ink + off[f0["i"]], kf["scale"], pad=0)                             # tight: no pad at all
    r = run_cli("boxes", tmp_path, video, write_boxes(tmp_path / "b.json", [{"id": "cert", "t": f0["t"], "box": box}]))
    assert r.returncode == 0, r.stderr
    hgt = float(ink[2, 1] - ink[0, 1])
    m = max(4.0, 0.2 * hgt)                                                          # required reach past the ink
    need = [ink + off[i] + np.float32([(-m, -m), (m, -m), (m, m), (-m, m)]) for i in range(len(truth))]
    assert_all_covered(tmp_path, [[q] for q in need])


def _slab_run(tmp_path, miss=None, **tile_kw):
    """Two-line slab label moving across the frame; the cert line boxed tight on the first keyframe.
    Returns (truth offsets, grade quad, cert quad)."""
    from fixtures_blur import slab_tile
    tile, grade, cert = slab_tile(**tile_kw)
    video = tmp_path / "slab.mp4"
    truth = make_code_video(video, [{"tile": tile, "start": (20, 300), "end": (90, 420)}])
    off = [np.float32(row[0]).min(0) - _ink_quad_of(tile).min(0) for row in truth]
    kf = keyframes(tmp_path, video)
    f0 = kf["frames"][0]
    hgt = float(cert[2, 1] - cert[0, 1])
    box = kf_box(cert + off[f0["i"]], kf["scale"], pad=0)
    if miss:                                     # a subagent box that misses part of the ink: (left, top) x height
        dx, dy = miss[0] * hgt * kf["scale"], miss[1] * hgt * kf["scale"]
        box = [box[0] + dx, box[1] + dy, box[2] - dx, box[3] - dy]
    r = run_cli("boxes", tmp_path, video, write_boxes(tmp_path / "b.json", [{"id": "cert", "t": f0["t"], "box": box}]))
    assert r.returncode == 0, r.stderr
    return off, grade, cert


def _inside_any(polys, pts):
    return [p for p in pts for _, poly in polys
            if cv2.pointPolygonTest(poly.reshape(-1, 1, 2), (float(p[0]), float(p[1])), False) >= 0]


def test_boxes_thin_tight_line_tracked_every_frame(tmp_path):
    """A small cert line boxed tight to its ink is too thin to track on its own (real clip: 126 of 274 frames
    lost). The script tracks a taller patch around it and still blurs the line, both ends, on every frame."""
    off, _, cert = _slab_run(tmp_path, scale=0.4, thick=1)
    hgt = float(cert[2, 1] - cert[0, 1])
    m = max(4.0, 0.2 * hgt)
    need = [cert + off[i] + np.float32([(-m, -m), (m, -m), (m, m), (-m, m)]) for i in range(len(off))]
    assert_all_covered(tmp_path, [[q] for q in need])


def _grade_hits(work, off, grade):
    P = polys_by_frame(work)
    xs = np.linspace(grade[0, 0], grade[1, 0], 25)
    edge = np.float32([(x, grade[2, 1]) for x in xs] + [(x, grade[0, 1]) for x in xs])
    return [i for i in range(len(off)) if _inside_any(P.get(i, []), edge + off[i])]


def test_boxes_snaps_short_box_to_ink(tmp_path):
    """Real clip: the subagent's "tight" box missed the first digit and the digits' tops. The script snaps the box
    to the ink: the whole cert line is blurred on every frame, and the grade line above stays sharp."""
    off, grade, cert = _slab_run(tmp_path, miss=(0.6, 0.3))
    need = [cert + off[i] + np.float32([(-2, -1), (2, -1), (2, 1), (-2, 1)]) for i in range(len(off))]
    assert_all_covered(tmp_path, [[q] for q in need])
    bad = _grade_hits(tmp_path, off, grade)
    assert not bad, f"grade line under the blur on frames {bad[:10]} (of {len(bad)})"


def test_snap_to_ink_finds_the_line():
    from fixtures_blur import slab_tile
    tile, grade, cert = slab_tile()
    img = np.full((400, 600), 150, np.uint8)
    img[100:100 + tile.shape[0], 50:50 + tile.shape[1]] = tile
    ink = cert + np.float32([50, 100])
    hgt = float(ink[2, 1] - ink[0, 1])
    x0, y0 = ink[0]
    x1, y1 = ink[2]
    short = (x0 + 0.6 * hgt, y0 + 0.3 * hgt, x1 - x0 - 0.6 * hgt, y1 - y0 - 0.3 * hgt)   # misses digit 1 and the tops
    x, y, w, h = _detect.snap_to_ink(img, short)
    assert x <= x0 + 1 and y <= y0 + 1 and x + w >= x1 - 1 and y + h >= y1 - 1, (x, y, w, h)
    assert y > grade[2, 1] + 100, "snapped up into the grade line"


def _ink_quad_of(tile):
    from fixtures_blur import _ink_quad
    return _ink_quad(tile)


# ---- v1.1.1 minors -----------------------------------------------------------------------------------------------
@pytest.mark.parametrize("item, field", [({"id": "x", "t": 1.0}, "box"),
                                         ({"id": "x", "t": 1.0, "box": [1, 2, 3]}, "box"),
                                         ({"id": "x", "t": "late", "box": [10, 10, 50, 50]}, "t"),
                                         ({"t": 1.0, "box": [10, 10, 50, 50]}, "id"),
                                         ({"id": "x", "t": 1e400, "box": [10, 10, 50, 50]}, "t"),
                                         ({"id": "x", "t": 1.0, "box": "1234"}, "box"),
                                         ({"id": "x", "t": 1.0, "box": [10, float("nan"), 50, 50]}, "box")])
def test_boxes_malformed_exit2_names_field(vids, tmp_path, item, field):
    video, _ = vids["qr"]
    keyframes(tmp_path, video)
    r = run_cli("boxes", tmp_path, video, write_boxes(tmp_path / "b.json", [item]))
    assert r.returncode == 2, r.stderr
    lines = [ln for ln in r.stderr.splitlines() if ln.strip()]
    assert len(lines) == 1 and "Traceback" not in r.stderr, r.stderr
    assert f"«{field}»" in lines[0] and "⛔" in lines[0], lines[0]


def test_boxes_not_json_exit2(vids, tmp_path):
    video, _ = vids["qr"]
    keyframes(tmp_path, video)
    bj = tmp_path / "b.json"
    bj.write_text('{"items": [', encoding="utf-8")
    r = run_cli("boxes", tmp_path, video, bj)
    assert r.returncode == 2 and "Traceback" not in r.stderr, r.stderr
    assert len([ln for ln in r.stderr.splitlines() if ln.strip()]) == 1


def test_replace_with_nothing_found_refuses(vids, tmp_path):
    """--replace that finds nothing must not silently leave the old targets in blur.json."""
    video, truth = vids["qr"]
    kf = keyframes(tmp_path, video)
    good = [{"id": "code-1", "t": 1.0, "box": kf_box(truth[30][0], kf["scale"])}]
    assert run_cli("boxes", tmp_path, video, write_boxes(tmp_path / "b.json", good)).returncode == 0
    before = (tmp_path / "blur.json").read_bytes()
    r = run_cli("boxes", tmp_path, video, write_boxes(tmp_path / "e.json", [], ["serial"]), "--replace")
    assert r.returncode == 2, (r.returncode, r.stdout, r.stderr)
    assert "--replace" in r.stderr and "blur.json" in r.stderr
    assert (tmp_path / "blur.json").read_bytes() == before
    r = run_cli("detect", tmp_path, video, "--kinds", "barcode", "--replace")
    assert r.returncode == 2, (r.returncode, r.stdout, r.stderr)
    assert (tmp_path / "blur.json").read_bytes() == before


def test_boxes_refuses_keyframes_of_other_video(vids, tmp_path):
    video, truth = vids["qr"]
    other, _ = vids["none"]
    kf = keyframes(tmp_path, video)
    assert {k: kf[k] for k in ("w", "h", "n")} == {"w": 540, "h": 960, "n": 60} and kf["fps"] == pytest.approx(30)
    items = [{"id": "code-1", "t": 1.0, "box": kf_box(truth[30][0], kf["scale"])}]
    data = json.loads((tmp_path / "kf" / "keyframes.json").read_text(encoding="utf-8"))
    data["n"] = 59                                           # keyframes taken from a different cut
    (tmp_path / "kf" / "keyframes.json").write_text(json.dumps(data), encoding="utf-8")
    r = run_cli("boxes", tmp_path, video, write_boxes(tmp_path / "b.json", items))
    assert r.returncode == 3, (r.returncode, r.stderr)
    assert "keyframes" in r.stderr
    assert not (tmp_path / "blur.json").exists()


def test_blur_md_keyframes_path():
    md = (SCRIPTS.parent / "references" / "blur.md").read_text(encoding="utf-8")
    import re
    bare = [m.start() for m in re.finditer(r"keyframes\.json", md) if not md[:m.start()].endswith("<work>/kf/")]
    assert md.count("<work>/kf/keyframes.json") >= 1 and not bare, bare


def test_track_anchors_skips_weak_anchor(monkeypatch, capsys):
    """One keyframe is motion-blurred (too few features): the item is tracked from the other anchors, with a note."""
    calls = []

    def fake(video, t, box, t0=0, t1=None):
        if t == 1.5:
            raise bt.WeakTemplate("المرجع ما فيه تفاصيل كافية للتتبّع")
        calls.append((t, t0, t1))
        return [bt.FrameBox(round(t * 30), [(0, 0), (9, 0), (9, 9), (0, 9)], 1.0, "tracked")]

    monkeypatch.setattr(bt, "track_box", fake)
    out = _detect.track_anchors(Path("v.mp4"), [(0.5, (0, 0, 9, 9)), (1.5, (0, 0, 9, 9)), (2.5, (0, 0, 9, 9))], size=(540, 960))
    assert sorted(calls[-2:]) == [(0.5, 0, 2.5), (2.5, 0.5, None)]  # retry: windows rebuilt without the weak one
    assert [f.i for f in out] == [15, 75]
    assert "1.5" in capsys.readouterr().out


def test_track_anchors_all_weak_raises(monkeypatch):
    def fake(video, t, box, t0=0, t1=None):
        raise bt.WeakTemplate("المرجع ما فيه تفاصيل كافية للتتبّع")

    monkeypatch.setattr(bt, "track_box", fake)
    with pytest.raises(ValueError):
        _detect.track_anchors(Path("v.mp4"), [(0.5, (0, 0, 9, 9)), (1.5, (0, 0, 9, 9))], size=(540, 960))


def test_track_anchors_single_weak_clean_message(monkeypatch):
    def fake(video, t, box, t0=0, t1=None):
        raise bt.WeakTemplate("المرجع ما فيه تفاصيل كافية للتتبّع")

    monkeypatch.setattr(bt, "track_box", fake)
    with pytest.raises(bt.WeakTemplate) as e:
        _detect.track_anchors(Path("v.mp4"), [(0.5, (0, 0, 9, 9))], size=(540, 960))
    assert str(e.value) == "المرجع ما فيه تفاصيل كافية للتتبّع"


def test_track_anchors_retry_reuses_good_tracks(monkeypatch):
    calls = []

    def fake(video, t, box, t0=0, t1=None):
        calls.append((t, t0, t1))
        if t == 3.5:
            raise bt.WeakTemplate("weak")
        return [bt.FrameBox(round(t * 30), [(0, 0), (9, 0), (9, 9), (0, 9)], 1.0, "tracked")]

    monkeypatch.setattr(bt, "track_box", fake)
    _detect.track_anchors(Path("v.mp4"), [(t, (0, 0, 9, 9)) for t in (0.5, 1.5, 2.5, 3.5)], size=(540, 960))
    assert calls.count((0.5, 0, 1.5)) == 1 and calls.count((1.5, 0.5, 2.5)) == 1, calls


def test_boxes_old_keyframes_format_message(vids, tmp_path):
    video, truth = vids["qr"]
    kf = keyframes(tmp_path, video)
    data = json.loads((tmp_path / "kf" / "keyframes.json").read_text(encoding="utf-8"))
    for k in ("w", "h", "n"):
        del data[k]                                          # written by 1.1.0
    (tmp_path / "kf" / "keyframes.json").write_text(json.dumps(data), encoding="utf-8")
    items = [{"id": "code-1", "t": 1.0, "box": kf_box(truth[30][0], kf["scale"])}]
    r = run_cli("boxes", tmp_path, video, write_boxes(tmp_path / "b.json", items))
    assert r.returncode == 3 and "None" not in r.stderr and "keyframes" in r.stderr, r.stderr


def test_map_rect_follows_perspective():
    """A box seen in strong perspective: the padded quad is the padded box through the same homography."""
    bw, bh, m = 200.0, 40.0, 12.0
    rect = np.float32([(0, 0), (bw, 0), (bw, bh), (0, bh)])
    quad = np.float32([(100, 100), (300, 140), (300, 170), (100, 160)])
    H = cv2.getPerspectiveTransform(rect, quad)
    want = cv2.perspectiveTransform(np.float32([(-m, -m), (bw + m, -m), (bw + m, bh + m), (-m, bh + m)])
                                    .reshape(-1, 1, 2), H).reshape(-1, 2)
    assert np.allclose(_detect.map_rect(quad, bw, bh, (-m, -m, bw + m, bh + m)), want, atol=0.5)



def test_snap_and_patch_only_for_text_lines():
    """Snapping and the taller tracking patch are for a thin text line. A screen-like box (not 3x longer than
    tall), or a flat one, is tracked and blurred as the subagent drew it."""
    rng = np.random.default_rng(1)
    img = rng.integers(0, 255, (600, 800)).astype(np.uint8)          # texture everywhere
    box = (300.0, 200.0, 200.0, 150.0)
    assert _detect.snap_to_ink(img, box) == box
    assert _detect.track_patch(box, 800, 600) == (300, 200, 200, 150)
    small = (300.0, 200.0, 20.0, 26.0)                                 # a two-digit box, taller than wide
    assert _detect.track_patch(small, 800, 600) == (300, 200, 20, 26)


def test_track_patch_contains_the_box():
    x, y, w, h = _detect.track_patch((10.4, 100.6, 200.3, 20.6), 800, 600)
    assert x <= 10.4 and y <= 100.6 and x + w >= 210.7 and y + h >= 121.2
