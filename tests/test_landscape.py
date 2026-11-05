"""references/landscape.md: a wrong crop is fixed by editing `crop` in shots.json and re-running 03.
plan() keeps a hand crop only while the source and the automatic crop are unchanged."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "video-ad-editor" / "scripts"))
import _landscape as L  # noqa: E402

CENTRE = [606, 1080, 657, 0]


def _plan(tmp_path, monkeypatch, src_bytes=b"x" * 100, zooms=(1, 1)):
    src = tmp_path / "src.mov"
    if not src.exists() or src.read_bytes() != src_bytes:
        src.write_bytes(src_bytes)
    monkeypatch.setattr(L, "_facetrack", lambda: None)          # Windows: no face detector -> centre crop
    monkeypatch.setattr(L, "_cuts", lambda s, a, b: [])          # one shot per kept piece
    return L.plan(str(src), str(tmp_path), [(0.0, 4.0), (5.0, 9.0)], 1920, 1080, list(zooms))


def _shots(tmp_path):
    return json.loads((tmp_path / "shots.json").read_text(encoding="utf-8"))


def _edit(tmp_path, i, crop):
    shots = _shots(tmp_path)
    shots[i]["crop"] = crop
    (tmp_path / "shots.json").write_text(json.dumps(shots), encoding="utf-8")


def test_centre_crop_written_with_auto(tmp_path, monkeypatch):
    pieces = _plan(tmp_path, monkeypatch)
    shots = _shots(tmp_path)
    assert [s["crop"] for s in shots] == [CENTRE] * 2
    assert [s["auto"] for s in shots] == [CENTRE] * 2
    assert not any(s.get("manual") for s in shots)
    assert pieces[0] == (0.0, 4.0, "crop=606:1080:657:0")


def test_hand_edit_kept_across_reruns(tmp_path, monkeypatch):
    _plan(tmp_path, monkeypatch)
    _edit(tmp_path, 1, [606, 1080, 946, 0])                      # user moves the second shot onto the speaker
    for _ in range(2):
        pieces = _plan(tmp_path, monkeypatch)
        assert pieces[0][2] == "crop=606:1080:657:0"
        assert pieces[1] == (5.0, 9.0, "crop=606:1080:946:0")
        s = _shots(tmp_path)[1]
        assert s["crop"] == [606, 1080, 946, 0] and s["auto"] == CENTRE and s["manual"] is True


def test_hand_edit_clamped_and_kept_9x16(tmp_path, monkeypatch):
    _plan(tmp_path, monkeypatch)
    _edit(tmp_path, 0, [900, 800, 1500, 500])                    # wrong width, past the right and bottom edges
    pieces = _plan(tmp_path, monkeypatch)
    assert pieces[0][2] == "crop=450:800:1470:280"                # width follows 9:16 of the hand height


def test_source_swap_regenerates(tmp_path, monkeypatch):
    _plan(tmp_path, monkeypatch)
    _edit(tmp_path, 1, [606, 1080, 946, 0])
    pieces = _plan(tmp_path, monkeypatch, src_bytes=b"y" * 250)   # a different src.mov, same cut plan
    assert pieces[1][2] == "crop=606:1080:657:0"
    assert not _shots(tmp_path)[1].get("manual")


def test_auto_change_regenerates(tmp_path, monkeypatch):
    _plan(tmp_path, monkeypatch)
    _edit(tmp_path, 1, [606, 1080, 946, 0])
    pieces = _plan(tmp_path, monkeypatch, zooms=(1, 1.5))        # 03's zoom for that piece changed
    assert pieces[1][2] != "crop=606:1080:946:0"
    assert not _shots(tmp_path)[1].get("manual")


def test_old_file_without_auto_regenerates(tmp_path, monkeypatch):
    _plan(tmp_path, monkeypatch)
    shots = _shots(tmp_path)
    for s in shots:
        s.pop("auto"), s.pop("sig")
    shots[1]["crop"] = [606, 1080, 946, 0]
    (tmp_path / "shots.json").write_text(json.dumps(shots), encoding="utf-8")
    pieces = _plan(tmp_path, monkeypatch)
    assert pieces[1][2] == "crop=606:1080:657:0"


def test_deleted_crop_returns_to_auto(tmp_path, monkeypatch):
    _plan(tmp_path, monkeypatch)
    _edit(tmp_path, 1, [606, 1080, 946, 0])
    _plan(tmp_path, monkeypatch)
    shots = _shots(tmp_path)
    del shots[1]["crop"]
    (tmp_path / "shots.json").write_text(json.dumps(shots), encoding="utf-8")
    pieces = _plan(tmp_path, monkeypatch)
    assert pieces[1][2] == "crop=606:1080:657:0"
