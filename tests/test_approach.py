"""approach.py: captions decision + per-video approach detection + the step-0 line."""
import json
import subprocess
import sys
import wave
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "video-ad-editor" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import approach  # noqa: E402
import lessons  # noqa: E402


def seg(s, e, text="كلام"):
    return {"start": s, "end": e, "text": text}


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "vae home"
    monkeypatch.setenv("VAE_HOME", str(h))
    return h


# --- decide_captions -------------------------------------------------------

def test_music_only_gives_none():
    assert approach.decide_captions([], 60.0, None) == "none"
    assert approach.decide_captions([], 60.0, "on") == "none"


def test_speech_gives_series_policy():
    segs = [seg(0, 20), seg(21, 40)]
    assert approach.decide_captions(segs, 60.0, "off") == "off"
    assert approach.decide_captions(segs, 60.0, "both") == "both"
    assert approach.decide_captions(segs, 60.0, None) == "on"


def test_short_speech_under_3s_gives_none():
    assert approach.decide_captions([seg(1.0, 3.5)], 10.0, "on") == "none"


def test_speech_under_10_percent_gives_none():
    assert approach.decide_captions([seg(0, 5.5)], 60.0, None) == "none"


def test_overlapping_segments_not_double_counted():
    # 2.5 s of real speech reported twice must still be under 3 s
    assert approach.decide_captions([seg(0, 2.5), seg(0, 2.5)], 10.0, None) == "none"


def test_poem_without_policy_asks():
    segs = [seg(0, 20)]
    assert approach.decide_captions(segs, 60.0, None, poem=True) == "ask"
    assert approach.decide_captions(segs, 60.0, "off", poem=True) == "off"
    assert approach.decide_captions([], 60.0, None, poem=True) == "none"


# --- detect -----------------------------------------------------------------

def _wav(path: Path, seconds: float):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * int(16000 * seconds))


def _fake_runner(calls, bpm=None):
    def run(cmd, work):
        calls.append(cmd)
        if "transcribe.py" in " ".join(map(str, cmd)):
            (work / "a.json").write_text(json.dumps({"segments": []}), encoding="utf-8")
        else:
            out = Path(cmd[cmd.index("--out") + 1])
            out.write_text(json.dumps({"bpm": bpm, "beats": []}), encoding="utf-8")
    return run


def test_detect_runs_transcribe_only_when_missing(tmp_path):
    work = tmp_path / "my work"
    work.mkdir()
    _wav(work / "a.wav", 30)
    calls = []
    r = approach.detect(work, runner=_fake_runner(calls, bpm=112.4))
    assert any("transcribe.py" in " ".join(map(str, c)) for c in calls)
    assert r["speech_ratio"] == 0.0
    assert r["bpm"] == pytest.approx(112.4)
    assert r["suggested"] == "beat-montage"

    calls.clear()
    approach.detect(work, runner=_fake_runner(calls, bpm=112.4))
    assert not any("transcribe.py" in " ".join(map(str, c)) for c in calls)


def test_detect_speech_suggests_talking_head(tmp_path):
    work = tmp_path / "w"
    work.mkdir()
    _wav(work / "a.wav", 30)
    (work / "a.json").write_text(json.dumps({"segments": [seg(0, 25)]}, ensure_ascii=False), encoding="utf-8")
    r = approach.detect(work, runner=_fake_runner([], bpm=None))
    assert r["speech_ratio"] == pytest.approx(25 / 30, abs=0.01)
    assert r["suggested"] == "talking-head"


def test_detect_mode_and_poem_route(tmp_path):
    work = tmp_path / "w"
    work.mkdir()
    _wav(work / "a.wav", 30)
    (work / "a.json").write_text(json.dumps({"segments": [seg(0, 25)]}), encoding="utf-8")
    run = _fake_runner([], bpm=None)
    assert approach.detect(work, mode="podcast", runner=run)["suggested"] == "podcast"
    assert approach.detect(work, mode="motion", runner=run)["suggested"] == "motion-explainer"
    assert approach.detect(work, poem=True, runner=run)["suggested"] == "voice-montage"


def _loud_wav(path: Path, seconds: float):
    import math
    import struct
    n = int(16000 * seconds)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(i / 5))) for i in range(n)))


def test_detect_audible_no_beat_little_speech_is_voice_montage(tmp_path):
    work = tmp_path / "w"
    work.mkdir()
    _loud_wav(work / "a.wav", 30)
    (work / "a.json").write_text(json.dumps({"segments": [seg(0, 2)]}), encoding="utf-8")
    assert approach.detect(work, runner=_fake_runner([], bpm=None))["suggested"] == "voice-montage"


def test_detect_silent_no_speech_no_beat_is_beat_montage(tmp_path):
    work = tmp_path / "w"
    work.mkdir()
    _wav(work / "a.wav", 30)
    (work / "a.json").write_text(json.dumps({"segments": []}), encoding="utf-8")
    assert approach.detect(work, runner=_fake_runner([], bpm=None))["suggested"] == "beat-montage"


def test_detect_audible_but_no_speech_no_beat_is_beat_montage(tmp_path):
    work = tmp_path / "w"
    work.mkdir()
    _loud_wav(work / "a.wav", 30)
    (work / "a.json").write_text(json.dumps({"segments": []}), encoding="utf-8")
    assert approach.detect(work, runner=_fake_runner([], bpm=None))["suggested"] == "beat-montage"


def test_audible(tmp_path):
    _wav(tmp_path / "quiet.wav", 2)
    _loud_wav(tmp_path / "loud.wav", 2)
    assert approach.audible(tmp_path / "quiet.wav") is False
    assert approach.audible(tmp_path / "loud.wav") is True
    assert approach.audible(tmp_path / "missing.wav") is False


def test_cli_src_with_silent_audio_is_beat_montage(home, tmp_path, monkeypatch, capsys):
    work = tmp_path / "clip"
    work.mkdir()
    _src_mov(work / "src.mov", 3.0, audio="anullsrc=r=48000:cl=mono")
    _patched_run(monkeypatch, segments=[], bpm=None)
    approach.main([str(work), "--no-series"])
    out = capsys.readouterr().out
    assert "مونتاج على الإيقاع" in out and "مونتاج على الصوت" not in out


def test_suggested_is_one_of_six():
    assert set(approach.APPROACHES) == {"talking-head", "podcast", "beat-montage",
                                        "voice-montage", "tutorial", "motion-explainer"}


# --- series pick + step-0 line ----------------------------------------------

def test_pick_series_named_wins(home, tmp_path):
    lessons.init_series("coffee")
    lessons.init_series("coins")
    assert approach.pick_series(tmp_path / "coffee", "coins") == ("coins", [])


def test_pick_series_from_folder_name(home, tmp_path):
    lessons.init_series("coffee")
    lessons.init_series("coins")
    name, ask = approach.pick_series(tmp_path / "Coffee", None)
    assert name == "coffee" and ask == []


def test_pick_series_ignores_parent_folders(home, tmp_path):
    lessons.init_series("coffee")
    name, ask = approach.pick_series(tmp_path / "coffee" / "ep12", None)
    assert name is None and ask == ["coffee"]


def test_pick_series_ask_when_no_match(home, tmp_path):
    lessons.init_series("coffee")
    lessons.init_series("coins")
    name, ask = approach.pick_series(tmp_path / "random", None)
    assert name is None and sorted(ask) == ["coffee", "coins"]


def test_step0_line_format():
    line = approach.step0_line("coffee", {"suggested": "beat-montage", "bpm": 112.4, "speech_ratio": 0.0}, "none", 9)
    assert line == "السلسلة: coffee · الأسلوب: مونتاج على الإيقاع (112 BPM) · بلا ترجمة · 9 قواعد"


def test_cli_prints_step0_line(home, tmp_path):
    lessons.init_series("coffee")
    lessons.add("never flashes", "ep1", "coffee")
    work = tmp_path / "coffee"
    work.mkdir()
    _wav(work / "a.wav", 30)
    (work / "a.json").write_text(json.dumps({"segments": [seg(0, 25)]}), encoding="utf-8")
    (work / "beats.json").write_text(json.dumps({"bpm": None, "beats": []}), encoding="utf-8")
    r = subprocess.run([sys.executable, str(SCRIPTS / "approach.py"), str(work)],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "السلسلة: coffee · الأسلوب: ريل متكلم · ترجمة على الفيديو + .srt · قاعدة واحدة"


def test_cli_asks_with_list(home, tmp_path):
    lessons.init_series("coffee")
    lessons.init_series("قهوة")
    work = tmp_path / "other"
    work.mkdir()
    r = subprocess.run([sys.executable, str(SCRIPTS / "approach.py"), str(work)],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    assert "coffee" in r.stdout and "قهوة" in r.stdout and "؟" in r.stdout


# --- line pauses for voice-led montage ---------------------------------------

def test_pauses_mid_gap_between_lines():
    segs = [seg(0.0, 2.0), seg(2.1, 4.0), seg(5.0, 7.0)]
    # 0.1 s gap is a breath, not a line pause; 4.0-5.0 is a pause -> cut in the middle
    assert approach.pauses(segs) == [4.5]


def test_cli_pauses_writes_beats_shape(home, tmp_path):
    work = tmp_path / "w"
    work.mkdir()
    _wav(work / "a.wav", 10)
    (work / "a.json").write_text(json.dumps({"segments": [seg(0, 2), seg(3, 5)]}), encoding="utf-8")
    (work / "beats.json").write_text(json.dumps({"bpm": None}), encoding="utf-8")
    r = subprocess.run([sys.executable, str(SCRIPTS / "approach.py"), str(work), "--no-series", "--pauses"],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    data = json.loads((work / "pauses.json").read_text(encoding="utf-8"))
    assert data["beats"] == [2.5] and data["bpm"] == 0


def test_detect_no_audio_folder_keeps_upstream_beat_montage(tmp_path):
    work = tmp_path / "clips"
    work.mkdir()
    calls = []
    r = approach.detect(work, runner=_fake_runner(calls))
    assert calls == []
    assert r == {"speech_ratio": 0.0, "bpm": None, "suggested": "beat-montage"}


def test_rules_wording():
    det = {"suggested": "talking-head", "bpm": None}
    tail = lambda n: approach.step0_line(None, det, "on", n).rsplit(" · ", 1)[1]
    assert [tail(n) for n in (0, 1, 2, 9, 11)] == ["بلا قواعد", "قاعدة واحدة", "قاعدتين", "9 قواعد", "11 قاعدة"]


def test_caption_labels_say_what_happens():
    th = {"suggested": "talking-head", "bpm": None}
    vm = {"suggested": "voice-montage", "bpm": None}
    off = approach.step0_line(None, th, "off", 2)
    assert ".srt" in off and "بلا ترجمة" not in off
    assert "على الفيديو" in approach.step0_line(None, th, "on", 2)
    assert "على الفيديو" not in approach.step0_line(None, vm, "on", 2)
    assert ".srt" in approach.step0_line(None, vm, "on", 2)


def test_cli_invalid_series_name(home, tmp_path):
    r = subprocess.run([sys.executable, str(SCRIPTS / "approach.py"), str(tmp_path), "--series", "a/b"],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 2 and "Traceback" not in r.stderr + r.stdout
    assert len((r.stdout + r.stderr).strip().splitlines()) == 1


# --- step 0 on a fresh reel folder (only src.mov) ----------------------------

def _src_mov(path: Path, seconds: float = 2.0, audio: str = "sine=frequency=440"):
    cmd = ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", f"color=c=black:s=64x64:d={seconds}"]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"{audio}:d={seconds}", "-c:a", "aac", "-shortest"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-y", str(path)]
    subprocess.run(cmd, check=True, capture_output=True)


def _patched_run(monkeypatch, segments=None, transcribe_ok=True, bpm=None):
    """ffmpeg is real; transcribe.py / beat.py are faked (no whisper in tests)."""
    real = approach._run
    calls = []

    def run(cmd, work):
        calls.append(cmd)
        line = " ".join(map(str, cmd))
        if "transcribe.py" in line:
            if not transcribe_ok:
                return 1
            (Path(work) / "a.json").write_text(json.dumps({"segments": segments or []}), encoding="utf-8")
            return 0
        if "beat.py" in line:
            Path(cmd[cmd.index("--out") + 1]).write_text(json.dumps({"bpm": bpm, "beats": []}), encoding="utf-8")
            return 0
        return real(cmd, work)
    monkeypatch.setattr(approach, "_run", run)
    return calls


def test_cli_fresh_reel_extracts_audio_and_finds_speech(home, tmp_path, monkeypatch, capsys):
    work = tmp_path / "reel 1"
    work.mkdir()
    _src_mov(work / "src.mov", 6.0)
    _patched_run(monkeypatch, segments=[seg(0, 5)])
    approach.main([str(work), "--no-series", "--mode", "reel"])
    out = capsys.readouterr().out
    assert (work / "a.wav").exists()          # same file reel.md step 4 makes, reused there
    assert "مونتاج على الإيقاع" not in out and "بلا ترجمة" not in out
    assert "ريل متكلم" in out and "على الفيديو" in out


def test_cli_fresh_reel_transcribe_failure_warns_and_asks(home, tmp_path, monkeypatch, capsys):
    work = tmp_path / "reel 1"
    work.mkdir()
    _src_mov(work / "src.mov", 2.0)
    _patched_run(monkeypatch, transcribe_ok=False)
    approach.main([str(work), "--no-series", "--mode", "reel"])
    out = capsys.readouterr().out
    assert "⚠️" in out and "التفريغ" in out
    assert "ريل متكلم" in out and "أسأل مرة" in out and "بلا ترجمة" not in out


def test_cli_reel_mode_without_audio_track_is_talking_head(home, tmp_path, monkeypatch, capsys):
    work = tmp_path / "reel 1"
    work.mkdir()
    _src_mov(work / "src.mov", 2.0, audio=None)   # no audio stream → a.wav can't be made
    _patched_run(monkeypatch)
    approach.main([str(work), "--no-series", "--mode", "reel"])
    out = capsys.readouterr().out
    assert "ريل متكلم" in out and "أسأل مرة" in out
    assert "مونتاج على الإيقاع" not in out


def test_analyse_reports_failed_transcribe(tmp_path):
    work = tmp_path / "w"
    work.mkdir()
    _wav(work / "a.wav", 5)
    issues = []
    approach.analyse(work, runner=lambda cmd, w: 1, issues=issues)
    assert any(i.kind == "transcribe" and "التفريغ" in i.text for i in issues)


def test_pauses_does_not_run_beat(tmp_path):
    work = tmp_path / "w"
    work.mkdir()
    _wav(work / "a.wav", 5)
    calls = []
    approach.analyse(work, runner=_fake_runner(calls), beats=False)
    assert not any("beat.py" in " ".join(map(str, c)) for c in calls)


def test_cli_subprocess_src_only_no_audio_stream(home, tmp_path):
    work = tmp_path / "reel 1"
    work.mkdir()
    _src_mov(work / "src.mov", 2.0, audio=None)
    r = subprocess.run([sys.executable, str(SCRIPTS / "approach.py"), str(work), "--no-series", "--mode", "reel"],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    assert "مونتاج على الإيقاع" not in r.stdout and "بلا ترجمة" not in r.stdout
    assert "ريل متكلم" in r.stdout


def test_beat_failure_alone_does_not_force_talking_head(tmp_path):
    work = tmp_path / "w"
    work.mkdir()
    _wav(work / "a.wav", 30)
    (work / "a.json").write_text(json.dumps({"segments": []}), encoding="utf-8")
    (work / "src.mov").write_bytes(b"x")
    det, _, _, issues = approach._analysis(work, runner=lambda cmd, w: 1)
    assert [i.kind for i in issues] == ["beat"]
    assert det["suggested"] == "beat-montage"            # silent track: upstream default, not talking-head


def test_beat_failure_keeps_speech_captions_but_asks_when_silent(home, tmp_path, monkeypatch, capsys):
    def run_with(segments):
        work = tmp_path / f"w{len(segments)}"
        work.mkdir()
        _wav(work / "a.wav", 30)
        (work / "a.json").write_text(json.dumps({"segments": segments}), encoding="utf-8")
        monkeypatch.setattr(approach, "_run", lambda cmd, w: 2)        # beat.py: no clear beats (exit 2)
        approach.main([str(work), "--no-series"])
        return capsys.readouterr().out
    out = run_with([seg(0, 25)])
    assert "⚠️" not in out and "beat.py" not in out      # speech reel: no beat warning to relay
    assert "ترجمة على الفيديو" in out
    out = run_with([])
    assert "⚠️" in out and "beat.py" in out
    assert "أسأل مرة" in out and "بلا ترجمة" not in out
