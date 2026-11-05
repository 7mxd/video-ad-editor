"""transcribe.py: faster-whisper when present, openai-whisper otherwise (finding 14)."""
import json
import sys
import types
from collections import namedtuple
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "video-ad-editor" / "scripts"))
import transcribe as T  # noqa: E402

Word = namedtuple("Word", "start end word probability")
Seg = namedtuple("Seg", "id seek start end text tokens avg_logprob compression_ratio no_speech_prob words temperature")


def _fake_seg():
    return Seg(1, 0, 0.0, 1.5, " مرحبا يا", [1, 2], -0.2, 1.1, 0.01,
               [Word(0, 0.7, " مرحبا", 0.9), Word(0.7, 1.5, " يا", 0.8)], 0.0)


def test_to_whisper_json_shape():
    out = T.to_whisper_json([_fake_seg()], "ar")
    assert set(out) >= {"text", "language", "segments"}
    assert out["language"] == "ar"
    s = out["segments"][0]
    assert set(s) >= {"id", "start", "end", "text", "words"}
    assert s["id"] == 0
    assert isinstance(s["start"], float) and isinstance(s["end"], float)
    assert len(s["words"]) == 2
    for w in s["words"]:
        assert set(w) == {"word", "start", "end", "probability"}
        assert isinstance(w["start"], float) and isinstance(w["end"], float)
    assert s["compression_ratio"] == 1.1
    assert out["text"] == " مرحبا يا"


def test_transcribe_falls_back_when_faster_whisper_missing(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "faster_whisper", None)   # import → ImportError
    calls = {}

    class Model:
        def transcribe(self, audio, **kw):
            calls.update(kw, audio=audio)
            return {"text": " hi", "language": "ar",
                    "segments": [{"id": 0, "start": 0.0, "end": 1.0, "text": " hi",
                                  "words": [{"word": " hi", "start": 0.0, "end": 1.0, "probability": 0.9}]}]}

    fake = types.ModuleType("whisper")
    fake.load_model = lambda name: calls.setdefault("model", name) and Model()
    monkeypatch.setitem(sys.modules, "whisper", fake)
    wav, out = tmp_path / "a.wav", tmp_path / "a.json"
    wav.write_bytes(b"")
    assert T.transcribe(wav, out, model="tiny") == "whisper"
    assert calls["model"] == "tiny"
    assert calls["word_timestamps"] is True and calls["language"] == "ar"
    assert json.loads(out.read_text(encoding="utf-8"))["segments"][0]["words"][0]["word"] == " hi"


def test_transcribe_uses_faster_whisper_when_present(monkeypatch, tmp_path):
    seen = {}

    class WhisperModel:
        def __init__(self, name, **kw):
            seen.update(kw, name=name)

        def transcribe(self, audio, **kw):
            seen["kw"] = kw
            return iter([_fake_seg()]), types.SimpleNamespace(language="ar")

    fake = types.ModuleType("faster_whisper")
    fake.WhisperModel = WhisperModel
    monkeypatch.setitem(sys.modules, "faster_whisper", fake)
    out = tmp_path / "a.json"
    assert T.transcribe(tmp_path / "a.wav", out, model="small") == "faster-whisper"
    assert seen["name"] == "small" and seen["device"] == "auto" and seen["compute_type"] == "int8"
    assert seen["kw"]["word_timestamps"] is True and seen["kw"]["vad_filter"] is False
    assert len(json.loads(out.read_text(encoding="utf-8"))["segments"][0]["words"]) == 2


# --- reuse a.json made by approach.py (step 0) -----------------------------

def _work(tmp_path, json_newer=True):
    import os
    wav, aj = tmp_path / "a.wav", tmp_path / "a.json"
    wav.write_bytes(b"RIFF")
    aj.write_text(json.dumps({"segments": []}), encoding="utf-8")
    t = wav.stat().st_mtime
    os.utime(aj, (t + 5, t + 5) if json_newer else (t - 5, t - 5))
    return wav, aj


def _spy(monkeypatch):
    calls = []
    monkeypatch.setattr(T, "transcribe", lambda wav, out, **kw: calls.append((wav, out)) or "whisper")
    return calls


def test_main_reuses_fresh_json(monkeypatch, tmp_path, capsys):
    _work(tmp_path)
    calls = _spy(monkeypatch)
    T.main([str(tmp_path)])
    out = capsys.readouterr().out.strip().splitlines()
    assert calls == []
    assert len(out) == 1 and "a.json" in out[0] and "--force" in out[0]


def test_main_redoes_when_wav_newer(monkeypatch, tmp_path):
    _work(tmp_path, json_newer=False)
    calls = _spy(monkeypatch)
    T.main([str(tmp_path)])
    assert len(calls) == 1


def test_main_force_redoes(monkeypatch, tmp_path, capsys):
    _work(tmp_path)
    calls = _spy(monkeypatch)
    T.main([str(tmp_path), "--force"])
    assert len(calls) == 1 and "whisper" in capsys.readouterr().out


def test_main_runs_when_json_missing(monkeypatch, tmp_path):
    (tmp_path / "a.wav").write_bytes(b"RIFF")
    calls = _spy(monkeypatch)
    T.main([str(tmp_path)])
    assert len(calls) == 1
