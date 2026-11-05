# -*- coding: utf-8 -*-
"""تفريغ الصوت (الخطوة 4): faster-whisper لو موجود (أسرع بكثير على المعالج)، وإلا openai-whisper.
   python scripts/transcribe.py <work>     ← يقرا <work>/a.wav ويكتب <work>/a.json ويطبع المحرّك المستخدم
   a.json أحدث من a.wav (الخطوة 0 سوّته) ← يستخدمه ويطبع سطر واحد · --force يعيد التفريغ
   الناتج بنفس شكل JSON حق «python -m whisper … --word_timestamps True --output_format json»
   WHISPER_MODEL يغيّر الموديل (الافتراضي medium) · WHISPER_BACKEND=whisper يجبر openai-whisper."""
import json
import os
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# نفس افتراضيات سطر أوامر openai-whisper (beam 5 · best_of 5) — دالة transcribe() بالبايثون افتراضيها غير
_WHISPER_CLI = dict(beam_size=5, best_of=5, fp16=False, verbose=None)
_SEG_EXTRA = ("seek", "tokens", "temperature", "avg_logprob", "compression_ratio", "no_speech_prob")


def _f(x):
    return float(x) if x is not None else None


def to_whisper_json(segments: list, language: str) -> dict:
    """مقاطع faster-whisper ← قاموس بشكل JSON حق openai-whisper (أرقام float · id من 0)."""
    out = []
    for i, s in enumerate(segments):
        seg = {"id": i, "start": _f(s.start), "end": _f(s.end), "text": s.text}
        for k in _SEG_EXTRA:
            v = getattr(s, k, None)
            if v is not None:
                seg[k] = list(v) if k == "tokens" else (int(v) if k == "seek" else float(v))
        seg["words"] = [{"word": w.word, "start": _f(w.start), "end": _f(w.end), "probability": _f(w.probability)}
                        for w in (getattr(s, "words", None) or [])]
        out.append(seg)
    return {"text": "".join(s["text"] for s in out), "segments": out, "language": language}


def load(model: str = None, backend: str = None):
    """يرجّع (اسم المحرّك, الموديل). backend=None ← faster-whisper لو انثبّت، وإلا whisper."""
    model = model or os.environ.get("WHISPER_MODEL", "medium")
    backend = backend or os.environ.get("WHISPER_BACKEND") or None
    if backend in (None, "faster-whisper"):
        try:
            from faster_whisper import WhisperModel
            return "faster-whisper", WhisperModel(model, device="auto", compute_type="int8")
        except ImportError:
            if backend == "faster-whisper":
                raise
    import whisper
    return "whisper", whisper.load_model(model)


def run(engine, audio, language: str = "ar", condition_on_previous_text: bool = True) -> dict:
    """يفرّغ ملف (مسار) أو مصفوفة float32 بـ16 kHz بالمحرّك من load() — يرجّع قاموس بشكل whisper."""
    name, m = engine
    src = str(audio) if isinstance(audio, Path) else audio
    if name == "faster-whisper":
        segs, info = m.transcribe(src, language=language, word_timestamps=True, vad_filter=False,
                                  condition_on_previous_text=condition_on_previous_text)
        return to_whisper_json(list(segs), getattr(info, "language", None) or language)
    return m.transcribe(src, language=language, word_timestamps=True,
                        condition_on_previous_text=condition_on_previous_text, **_WHISPER_CLI)


def transcribe(wav: Path, out_json: Path, language="ar", model=os.environ.get("WHISPER_MODEL", "medium"),
               backend=None) -> str:
    """يفرّغ wav ويكتب out_json — يرجّع 'faster-whisper' أو 'whisper'."""
    engine = load(model, backend)
    result = run(engine, Path(wav), language)
    Path(out_json).write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return engine[0]


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    force = "--force" in args
    args = [a for a in args if a != "--force"]
    if not args:
        sys.exit("python scripts/transcribe.py <work> [--force]")
    W = Path(args[0])
    wav, aj = W / "a.wav", W / "a.json"
    if not force and aj.exists() and aj.stat().st_size > 0 and (
            not wav.exists() or aj.stat().st_mtime >= wav.stat().st_mtime):
        print("♻️ استخدمت a.json الموجود (أحدث من a.wav، من الخطوة 0) — --force يعيد التفريغ")
        return
    print(transcribe(wav, aj))


if __name__ == "__main__":
    main()
