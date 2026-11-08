"""blur_track.py: general privacy blur with a fail-safe (spec §6 Privacy blur, §10 item 3)."""
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

cv2 = pytest.importorskip("cv2")
import numpy as np  # noqa: E402

SCRIPTS = Path(__file__).resolve().parents[1] / "video-ad-editor" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import blur_track as bt  # noqa: E402
from fixtures_blur import PH, PW, make_offset, make_ref, make_vfr, make_video  # noqa: E402

FPS = 30
FULL = (0.0, 0.0, 1.0, 1.0)


def centre(poly):
    return np.asarray(poly, float).mean(0)


def area(poly):
    return cv2.contourArea(np.asarray(poly, np.float32))


def decode(path):
    w, h, _, _ = bt.probe(Path(path))
    return [f for _, f in bt.read_frames(Path(path), w, h, gray=False)]


def run_cli(*args):
    return subprocess.run([sys.executable, str(SCRIPTS / "blur_track.py"), *map(str, args)],
                          capture_output=True, text=True, encoding="utf-8")


@pytest.fixture(scope="module")
def clips(tmp_path_factory):
    d = tmp_path_factory.mktemp("blur")
    ref = make_ref(d / "ref.png")
    out = {"dir": d, "ref": ref}
    out["plain"] = (d / "plain.mp4", make_video(d / "plain.mp4"))
    out["short"] = (d / "short.mp4", make_video(d / "short.mp4", occlude=(30, 45)))
    return out


def test_track_reference_follows_patch(clips):
    video, truth = clips["plain"]
    frames = bt.track_reference(video, clips["ref"], FULL)
    assert len(frames) == len(truth)
    good = sum(1 for fb, t in zip(frames, truth)
               if fb.poly is not None and np.linalg.norm(centre(fb.poly) - t) <= 5)
    assert good >= 0.95 * len(truth)
    assert all(fb.state == "tracked" for fb in frames)


def test_short_occlusion_held_and_widened(clips):
    video, _ = clips["short"]
    frames, flagged = bt.apply_failsafe(bt.track_reference(video, clips["ref"], FULL), FPS)
    assert flagged == []
    normal = np.median([area(fb.poly) for fb in frames if fb.state == "tracked"])
    for fb in frames[30:45]:
        assert fb.state == "held", fb
        assert area(fb.poly) >= 2 * normal


def test_long_occlusion_flagged_exit3(clips):
    d = clips["dir"]
    video = d / "long.mp4"
    make_video(video, occlude=(30, 75))
    frames, flagged = bt.apply_failsafe(bt.track_reference(video, clips["ref"], FULL), FPS)
    assert len(flagged) == 1
    t0, t1 = flagged[0]
    assert abs(t0 - 1.0) < 0.1 and abs(t1 - 2.5) < 0.1
    assert all(fb.poly is not None for fb in frames)  # still blurred (widened), never left bare
    r = run_cli("ref", d / "w_long", video, clips["ref"], "0,0,1,1")
    assert r.returncode == 3, r.stdout + r.stderr
    assert "مفقود>1ث 1" in r.stdout
    data = json.loads((d / "w_long" / "blur.json").read_text(encoding="utf-8"))
    assert len(data["flagged"]) == 1 and data["fps"] == FPS


def _out_and_back(i, n):
    # right and off-frame by frame 22, off until ~45, back from the right, fully inside from frame 62
    return (300 + 16 * i, 120) if i < 25 else (640 - (i - 45) * 12, 120)


def test_reacquire_after_exit_and_return(clips):
    video = clips["dir"] / "back.mp4"
    truth = make_video(video, traj=_out_and_back)
    frames, flagged = bt.apply_failsafe(bt.track_reference(video, clips["ref"], FULL), FPS)
    assert flagged == []  # off-frame 0.8 s ≤ 1 s → held
    for fb in frames[62:]:
        assert fb.state == "tracked", fb
        assert np.linalg.norm(centre(fb.poly) - truth[fb.i]) <= 5  # re-acquired, not stale


def test_failsafe_low_conf_widened_and_nothing_known_flagged():
    sq = [(0, 0), (10, 0), (10, 10), (0, 10)]
    frames = [bt.FrameBox(0, sq, 0.9, "tracked"), bt.FrameBox(1, sq, 0.3, "tracked")]
    out, flagged = bt.apply_failsafe(frames, FPS)
    assert out[0].state == "tracked" and out[1].state == "widened"
    assert area(out[1].poly) == pytest.approx(2.25 * area(sq))
    # a short loss with no known polygon anywhere can't be held: it is flagged, never passed silently
    out, flagged = bt.apply_failsafe([bt.FrameBox(i, None, 0.0, "lost") for i in range(5)], FPS)
    assert flagged == [(0.0, round(5 / FPS, 3))] and all(f.state == "lost" for f in out)


SQ = [(0, 0), (10, 0), (10, 10), (0, 10)]


def test_remark_clears_only_same_target_and_only_full_cover():
    old = [bt.FrameBox(i, SQ, 0.9, "tracked", 0) for i in range(30)] + \
          [bt.FrameBox(i, SQ, 0.0, "lost", 0) for i in range(30, 75)]
    flag = [(1.0, 2.5, 0)]
    new = [bt.FrameBox(i, SQ, 0.9, "tracked", 0) for i in range(30, 75)]
    frames, flagged = bt.merge_targets(old, flag, new, [], 0, True, FPS)
    assert flagged == [] and len(frames) == len(old) + len(new)
    assert bt.merge_targets(old, flag, new[:20], [], 0, True, FPS)[1] == flag  # partial re-mark: still refused
    other = [replace(f, target=1) for f in new]
    assert bt.merge_targets(old, flag, other, [], 1, False, FPS)[1] == flag  # another target never clears it


def test_band_uses_each_targets_own_polygon():
    a = [(0, 60), (200, 60), (200, 180), (0, 180)]        # target 0, known up to frame 20
    b = [(0, 250), (200, 250), (200, 300), (0, 300)]      # target 1, known later (frame 29)
    frames = [bt.FrameBox(i, a, 0.9, "tracked", 0) for i in range(21)] + \
             [bt.FrameBox(i, b, 0.9, "tracked", 1) for i in range(30)]
    bands = bt.band_frames(frames, [(1.0, 2.0, 0), (1.0, 2.0, 2)], FPS, 640, 360)
    ys = lambda t: {(round(f.poly[0][1]), round(f.poly[2][1])) for f in bands if f.target == t}
    assert ys(0) == {(0, 240)}   # rows of target 0 (60-180) widened 2×, not target 1's rows
    assert ys(2) == {(0, 360)}   # target 2 has no known polygon: whole frame
    assert all(f.poly[1][0] == 640 for f in bands) and len(bands) == 60


def test_frame_indices_agree_between_read_paths(clips):
    d = clips["dir"]
    src, _ = clips["plain"]
    for clip, expect in ((make_vfr(src, d / "vfr.mp4"), 93), (make_offset(src, d / "offset.mp4"), 92)):
        w, h, _, _ = bt.probe(clip)
        full = [f for _, f in bt.read_frames(clip, w, h)]
        assert len(full) == expect == bt.count_frames(clip)
        idx = [0, 1, 2, 29, 30, 31, 32, 33, 34, 60, len(full) - 1]
        sel = dict(bt.read_frames(clip, w, h, select=idx))
        assert sorted(sel) == idx
        for i in idx:
            assert np.array_equal(sel[i], full[i]), (clip.name, i)


def test_apply_and_qa_refuse_another_video(clips):
    d = clips["dir"]
    video, truth = clips["plain"]
    work = d / "w_other"
    bt.save_json(work, bt.video_meta(video), [bt.FrameBox(i, SQ, 0.9, "tracked") for i in range(len(truth))], [])
    short = d / "short45.mp4"
    make_video(short, n=45)
    r = run_cli("apply", work, short, d / "other.mp4")
    assert r.returncode == 3 and "مو نفسه" in r.stderr
    assert not (d / "other.mp4").exists()
    r = run_cli("qa", work, short, d / "other.jpg")
    assert r.returncode == 3 and not (d / "other.jpg").exists()


def test_add_unrelated_target_keeps_flag_then_remark_clears(clips):
    d = clips["dir"]
    video, truth = clips["plain"]
    work = d / "w_targets"
    a = [bt.FrameBox(i, SQ, 0.9, "tracked", 0) for i in range(30)] + \
        [bt.FrameBox(i, SQ, 0.0, "lost", 0) for i in range(30, 60)] + \
        [bt.FrameBox(i, SQ, 0.9, "tracked", 0) for i in range(60, 90)]
    bt.save_json(work, bt.video_meta(video), a, [(1.0, 2.0, 0)])
    cx, cy = truth[45]
    box = f"{int(cx - PW / 2)},{int(cy - PH / 2)},{PW},{PH}"
    r = run_cli("box", work, video, 1.5, box, "--add")      # target B, visible over A's flagged range
    assert r.returncode == 3, r.stdout + r.stderr           # merged file still has A's flag
    meta, frames, flagged = bt.load_json(work)
    assert flagged == [(1.0, 2.0, 0)] and {f.target for f in frames} == {0, 1}
    assert run_cli("apply", work, video, d / "still_refused.mp4").returncode == 3
    r = run_cli("box", work, video, 1.5, box, "--target", 0)  # explicit re-mark of A covering the range
    assert r.returncode == 0, r.stdout + r.stderr
    assert bt.load_json(work)[2] == []


def test_render_blur_only_inside_polygon(clips):
    d = clips["dir"]
    src, truth = d / "audio.mp4", None
    truth = make_video(src, audio=True)
    frames = []
    for i, (cx, cy) in enumerate(truth):
        x0, y0, x1, y1 = cx - PW / 2 - 10, cy - PH / 2 - 10, cx + PW / 2 + 10, cy + PH / 2 + 10
        frames.append(bt.FrameBox(i, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], 1.0, "tracked"))
    out = d / "blurred.mp4"
    bt.render_blur(src, frames, out)
    a, b = decode(src), decode(out)
    assert len(a) == len(b) == len(truth)
    for i in (0, 45, 89):
        mask = np.zeros(a[i].shape[:2], np.uint8)
        cv2.fillPoly(mask, [np.int32(frames[i].poly)], 255)
        outside = cv2.dilate(mask, np.ones((33, 33), np.uint8)) == 0  # 16 px codec margin
        diff = np.abs(a[i].astype(int) - b[i].astype(int))
        assert diff[outside].max() <= 2
        inner = cv2.erode(mask, np.ones((9, 9), np.uint8)) > 0
        lap = lambda f: cv2.Laplacian(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), cv2.CV_64F)[inner].var()
        assert lap(b[i]) < 0.5 * lap(a[i])
    streams = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0",
                              str(out)], capture_output=True, text=True).stdout.split()
    assert "audio" in streams


def test_render_blur_without_audio(clips):
    video, truth = clips["plain"]
    frames = [bt.FrameBox(i, [(10, 10), (100, 10), (100, 80), (10, 80)], 1.0, "tracked") for i in range(len(truth))]
    out = clips["dir"] / "noaudio.mp4"
    bt.render_blur(video, frames, out)
    assert len(decode(out)) == len(truth)


def test_apply_refuses_when_flagged(clips):
    d = clips["dir"]
    video, truth = clips["plain"]
    work = d / "w_flag"
    work.mkdir()
    poly = [[20, 60], [220, 60], [220, 180], [20, 180]]
    data = {"fps": FPS, "n": len(truth), "w": 640, "h": 360,
            "frames": [{"i": i, "poly": poly, "conf": 0.9, "state": "tracked", "target": 0}
                       for i in range(len(truth))],
            "flagged": [[1.0, 2.0, 0]]}
    (work / "blur.json").write_text(json.dumps(data), encoding="utf-8")
    out = d / "refused.mp4"
    r = run_cli("apply", work, video, out)
    assert r.returncode == 3
    assert not out.exists()
    r = run_cli("apply", work, video, out, "--accept-band")
    assert r.returncode == 0, r.stderr
    # frame 45 is inside the flagged range: the patch (x≈222-422) lies outside the stored polygon (x 20-220)
    # but inside the full-width band of its rows, so it must come out blurred
    lap = lambda f: cv2.Laplacian(cv2.cvtColor(f[130:170, 300:400], cv2.COLOR_BGR2GRAY), cv2.CV_64F).var()
    assert lap(decode(out)[45]) < 0.5 * lap(decode(video)[45])

def test_box_mode_tracks_from_mid_clip(clips):
    video, truth = clips["plain"]
    cx, cy = truth[45]
    box = (int(cx - PW / 2), int(cy - PH / 2), PW, PH)
    frames = bt.track_box(video, 45 / FPS, box)
    assert len(frames) == len(truth)
    good = sum(1 for fb, t in zip(frames, truth)
               if fb.poly is not None and np.linalg.norm(centre(fb.poly) - t) <= 5)
    assert good >= 0.95 * len(truth)  # forward and backward from t
    assert frames[0].state == "tracked" and frames[-1].state == "tracked"


def test_arabic_work_path(clips):
    d = clips["dir"] / "مجلد عربي"
    d.mkdir()
    video = d / "فيديو قصير.mp4"
    make_video(video, n=45)
    ref = make_ref(d / "صورة مرجع.png")
    work = d / "شغل البلر"
    r = run_cli("ref", work, video, ref, "0,0,1,1")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "نوافذ 1" in r.stdout and "مفقود>1ث 0" in r.stdout
    out = d / "ناتج.mp4"
    assert run_cli("apply", work, video, out).returncode == 0
    sheet = d / "ورقة.jpg"
    r = run_cli("qa", work, out, sheet)
    assert r.returncode == 0, r.stderr
    assert cv2.imdecode(np.fromfile(str(sheet), np.uint8), cv2.IMREAD_COLOR) is not None


def test_bare_names_resolve_inside_work(clips, tmp_path):
    """blur.md writes `box <work> cut.mp4 …` / `apply <work> cut.mp4 cut_blur.mp4` / `qa <work> cut_blur.mp4 qa.jpg`
    from the skill folder: bare file names mean files in <work>, not in the current directory."""
    import shutil
    work = tmp_path / "w"
    work.mkdir()
    video, truth = clips["plain"]
    shutil.copy(video, work / "cut.mp4")
    cx, cy = truth[45]
    r = run_cli("box", work, "cut.mp4", 45 / FPS, f"{int(cx - PW / 2)},{int(cy - PH / 2)},{PW},{PH}")
    assert r.returncode == 0, r.stdout + r.stderr
    assert run_cli("apply", work, "cut.mp4", "cut_blur.mp4").returncode == 0
    assert (work / "cut_blur.mp4").exists()
    r = run_cli("qa", work, "cut_blur.mp4", "qa.jpg")
    assert r.returncode == 0, r.stderr
    assert (work / "qa.jpg").exists()


def test_box_without_add_refuses_to_overwrite_targets(clips):
    d = clips["dir"]
    video, truth = clips["plain"]
    work = d / "w_overwrite"
    a = [bt.FrameBox(i, SQ, 0.9, "tracked", 0) for i in range(90)]
    bt.save_json(work, bt.video_meta(video), a, [])
    before = (work / "blur.json").read_bytes()
    cx, cy = truth[45]
    box = f"{int(cx - PW / 2)},{int(cy - PH / 2)},{PW},{PH}"
    r = run_cli("box", work, video, 1.5, box)
    assert r.returncode == 2, r.stdout + r.stderr
    assert "--add" in r.stderr and "--replace" in r.stderr and "Traceback" not in r.stderr
    assert len(r.stderr.strip().splitlines()) == 1
    assert (work / "blur.json").read_bytes() == before         # target 0 still there
    r = run_cli("box", work, video, 1.5, box, "--replace")
    assert r.returncode == 0, r.stdout + r.stderr
    assert {f.target for f in bt.load_json(work)[1]} == {0}


# ---- QA sheet: frames with no blur (Task 5) ----------------------------------------------------------------------
def _first_half(n=90, upto=45):
    poly = [(10, 10), (100, 10), (100, 60), (10, 60)]
    return [bt.FrameBox(i, poly, 1.0, "tracked") for i in range(upto)]


def test_qa_includes_outside_frames():
    picks, outside = bt.qa_picks(_first_half(), 90, max_tiles=24, outside=6)
    assert len(outside) == 6
    assert all(45 <= i < 90 for i in outside)
    assert set(outside) <= set(picks)


def test_qa_outside_zero_matches_old(clips, tmp_path):
    video, _ = clips["plain"]
    frames = _first_half()
    n_old = bt.qa_sheet(video, frames, tmp_path / "a.jpg", outside=0)
    picks, outside = bt.qa_picks(frames, 90, max_tiles=24, outside=0)
    assert outside == [] and n_old == len(picks) == 2


def test_qa_sheet_draws_outside_tiles(clips, tmp_path):
    video, _ = clips["plain"]
    assert bt.qa_sheet(video, _first_half(), tmp_path / "q.jpg", outside=6) == 8
