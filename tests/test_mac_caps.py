"""Finding 8: say up front which features need macOS; OpenCV face-tracking fallback for podcast."""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "video-ad-editor" / "scripts"))
import _caps as C  # noqa: E402
import _faces as F  # noqa: E402


# ── tracker selection ──
def test_pick_prefers_vision_when_swiftc():
    assert F.pick_tracker(has_swiftc=True, has_cv2=True) == "vision"
    assert F.pick_tracker(has_swiftc=True, has_cv2=False) == "vision"


def test_pick_opencv_without_swiftc():
    assert F.pick_tracker(has_swiftc=False, has_cv2=True) == "opencv"


def test_pick_none_without_either():
    assert F.pick_tracker(has_swiftc=False, has_cv2=False) == ""


def test_tracker_cmd_opencv_is_this_script(tmp_path):
    kind, cmd = F.tracker_cmd(str(tmp_path / "facetrack"), has_swiftc=False, has_cv2=True)
    assert kind == "opencv"
    assert cmd[0] == sys.executable and cmd[1].endswith("_faces.py")


def test_tracker_cmd_none(tmp_path):
    assert F.tracker_cmd(str(tmp_path / "facetrack"), has_swiftc=False, has_cv2=False) == ("", None)


def test_tracker_cmd_vision_uses_existing_binary(tmp_path):
    b = tmp_path / "facetrack"
    b.write_text("x")
    assert F.tracker_cmd(str(b), has_swiftc=True, has_cv2=True) == ("vision", [str(b)])


# ── OpenCV detector: same JSON as facetrack.swift ──
def _jpgs(d, n=2, w=270, h=480):
    from PIL import Image
    for i in range(1, n + 1):
        Image.fromarray(np.full((h, w, 3), 128, np.uint8)).save(d / f"{i:05d}.jpg")


def test_detect_rows_format_with_fake_detector(tmp_path):
    _jpgs(tmp_path)
    boxes = {"00001.jpg": [(27, 48, 54, 96), (10, 10, 20, 20)], "00002.jpg": []}
    det = lambda gray, name: boxes[name]
    out = tmp_path / "f.json"
    F.detect(str(tmp_path), str(out), detector=det)
    rows = json.loads(out.read_text())
    assert [r["f"] for r in rows] == ["00001.jpg", "00002.jpg"]
    f = rows[0]["face"]   # largest box, normalised, top-left origin
    assert f == pytest.approx({"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2})
    assert rows[0]["n"] == 2 and isinstance(rows[0]["mouth"], float)
    assert "face" not in rows[1] and "mouth" not in rows[1]


def test_detect_real_cascade_on_blank_frames(tmp_path):
    pytest.importorskip("cv2")
    _jpgs(tmp_path)
    out = tmp_path / "f.json"
    F.detect(str(tmp_path), str(out))
    rows = json.loads(out.read_text())
    assert len(rows) == 2 and all("face" not in r for r in rows)


def test_write_empty(tmp_path):
    _jpgs(tmp_path, n=3)
    out = tmp_path / "f.json"
    F.write_empty(str(tmp_path), str(out))
    assert json.loads(out.read_text()) == [{"f": f"{i:05d}.jpg"} for i in (1, 2, 3)]


# ── capability block (00_setup.sh step 0) ──
def test_caps_all_present_is_one_line():
    lines = C.lines(has_swiftc=True, has_cv2=True, has_mlx=True)
    assert len(lines) == 1 and "✅" in lines[0]


def test_caps_windows_like_lists_mac_only_features():
    txt = "\n".join(C.lines(has_swiftc=False, has_cv2=False, has_mlx=False))
    for k in ("الكلام ورا الشخص", "HDR", "تتبّع الوجه", "mlx", "قصّ الشخص", "--extras", "faceAnchor"):
        assert k in txt
    assert "قل للمستخدم" in txt


def test_caps_cv2_turns_face_tracking_into_fallback():
    txt = "\n".join(C.lines(has_swiftc=False, has_cv2=True, has_mlx=False))
    assert "OpenCV" in txt and "--extras" not in txt


def test_detect_does_not_need_pillow_and_reads_arabic_paths(tmp_path, monkeypatch):
    cv2 = pytest.importorskip("cv2")
    d = tmp_path / "فريمات"
    d.mkdir()
    ok, buf = cv2.imencode(".jpg", np.full((480, 270, 3), 128, np.uint8))
    buf.tofile(str(d / "00001.jpg"))
    monkeypatch.setitem(sys.modules, "PIL", None)          # import PIL → ImportError
    out = tmp_path / "f.json"
    F.detect(str(d), str(out), detector=lambda g, n: [(27, 48, 54, 96)])
    rows = json.loads(out.read_text())
    assert rows[0]["face"] == pytest.approx({"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2})
