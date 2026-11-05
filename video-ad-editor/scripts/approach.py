# -*- coding: utf-8 -*-
"""الخطوة 0: السلسلة + الأسلوب من الصوت نفسه، بسطر واحد يصحّحه المستخدم.
   python scripts/approach.py <work> [--series S | --no-series] [--mode reel|podcast|motion|montage|tutorial]
   السلسلة: اللي سمّاها ← اسم مجلد الشغل لو يطابق بطاقة ← وإلا يطبع سطر «أي سلسلة؟» بالقائمة.
   بلا a.wav وفيه <work>/src.* ← يطلّعه أول (نفس سطر reel.md). يقرا <work>/a.json (يشغّل transcribe.py
   لو ناقص) و<work>/beats.json (يشغّل beat.py على bg-audio.mp3 أو a.wav لو ناقص).
   فشل شي؟ يطبع ⚠️ بالعربي، والترجمة «أسأل مرة»، و--mode reel (أو src.* بلا وضع) ← ريل متكلم.
   --pauses ← <work>/pauses.json (وقفات السطور بشكل beats.json) لـ«12_montage.py plan --beats»."""
import argparse
import array
import json
import subprocess
import sys
import wave
from collections import namedtuple
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lessons  # noqa: E402

SCRIPTS = Path(__file__).resolve().parent
APPROACHES = {
    "talking-head": "ريل متكلم",
    "podcast": "مقطع بودكاست",
    "beat-montage": "مونتاج على الإيقاع",
    "voice-montage": "مونتاج على الصوت",
    "tutorial": "شرح بالكلام",
    "motion-explainer": "موشن شرح",
}
CAPTION_LABELS = {"none": "بلا ترجمة", "off": "ترجمة ملف .srt بس", "on": "ترجمة على الفيديو + .srt",
                  "both": "نسختين بترجمة وبلا + .srt", "ask": "الترجمة؟ (أسأل مرة)"}
NO_BURN = {"beat-montage", "voice-montage"}   # محرّك المونتاج ما يرسم كابشن ← .srt بس
MODE_ROUTE = {"podcast": "podcast", "motion": "motion-explainer", "tutorial": "tutorial"}
MIN_SPEECH_S = 3.0
MIN_SPEECH_RATIO = 0.10
MIN_PAUSE_S = 0.25          # أقصر من كذا = نفَس، مو وقفة سطر
SILENT_DBFS = -50.0         # أهدأ من كذا (RMS) = صوت ساكت
Issue = namedtuple("Issue", "kind text")   # kind: audio · transcribe · beat


def speech_seconds(segments) -> float:
    spans = sorted((float(s["start"]), float(s["end"])) for s in segments
                   if s.get("end") is not None and str(s.get("text", "x")).strip())
    total, cur_s, cur_e = 0.0, None, None
    for s, e in spans:
        if cur_e is None or s > cur_e:
            if cur_e is not None:
                total += cur_e - cur_s
            cur_s, cur_e = s, e
        else:
            cur_e = max(cur_e, e)
    if cur_e is not None:
        total += cur_e - cur_s
    return total


def _has_speech(segments, duration) -> bool:
    sp = speech_seconds(segments)
    return sp >= MIN_SPEECH_S and duration > 0 and sp / duration >= MIN_SPEECH_RATIO


def decide_captions(segments: list, duration: float, series_policy, poem: bool = False) -> str:
    if not _has_speech(segments, duration):
        return "none"
    if series_policy:
        return series_policy
    return "ask" if poem else "on"


def pauses(segments, min_gap: float = MIN_PAUSE_S) -> list:
    """وقفات السطور (نص الفراغ بين جملتين) — للمونتاج على الصوت."""
    segs = sorted((float(s["start"]), float(s["end"])) for s in segments if s.get("end") is not None)
    return [round((a_end + b_start) / 2, 3) for (_, a_end), (b_start, _) in zip(segs, segs[1:])
            if b_start - a_end >= min_gap]


def _run(cmd, work):
    """← رمز الخروج (127 لو الأداة مو موجودة)."""
    try:
        return subprocess.run([str(c) for c in cmd], cwd=str(work), capture_output=True, check=False).returncode
    except OSError:
        return 127


VIDEO_EXT = (".mov", ".mp4", ".m4v", ".mkv", ".webm", ".avi")


def source_video(work: Path):
    """<work>/src.* (اسم reel.md) ← المسار أو None."""
    for p in sorted(Path(work).glob("src.*")):
        if p.suffix.lower() in VIDEO_EXT and p.is_file():
            return p
    return None


def _ok(rc, out: Path) -> bool:
    return rc in (None, 0) and out.exists() and out.stat().st_size > 0


def _duration(wav: Path, beats: dict, segments) -> float:
    try:
        with wave.open(str(wav), "rb") as w:
            return w.getnframes() / float(w.getframerate())
    except Exception:
        pass
    if beats.get("duration"):
        return float(beats["duration"])
    return max((float(s.get("end") or 0) for s in segments), default=0.0)


def audible(wav: Path) -> bool:
    """RMS حق a.wav (16-bit) فوق SILENT_DBFS؟ ملف ناقص أو غريب ← False."""
    try:
        with wave.open(str(wav), "rb") as w:
            if w.getsampwidth() != 2:
                return False
            a = array.array("h", w.readframes(w.getnframes()))
    except Exception:
        return False
    if sys.byteorder == "big":
        a.byteswap()
    a = a[::8]                  # عيّنة كل 8 تكفي
    if not a:
        return False
    rms = (sum(x * x for x in a) / len(a)) ** 0.5
    return rms > 32768 * 10 ** (SILENT_DBFS / 20)


def _load(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def analyse(work: Path, runner=None, issues=None, beats=True):
    """← (segments, duration, bpm|None). اللي فشل ينضاف لـissues (Issue(kind, نص عربي)) بدل ما ينبلع.
       بلا a.wav وفيه src.* ← يطلّعه بنفس سطر reel.md (الخطوة 4 تستخدمه بعدين)."""
    run = runner or _run
    issues = [] if issues is None else issues
    work = Path(work)
    wav, aj, bj = work / "a.wav", work / "a.json", work / "beats.json"
    src = source_video(work)
    if not wav.exists() and src is not None:
        rc = run(["ffmpeg", "-v", "error", "-i", src, "-vn", "-ac", "1", "-ar", "16000", "-y", wav], work)
        if not _ok(rc, wav):
            wav.unlink(missing_ok=True)
            issues.append(Issue("audio", f"ما قدرت أطلّع الصوت من {src.name} (ما فيه صوت، أو ffmpeg ناقص)"))
    if not aj.exists() and wav.exists():
        rc = run([sys.executable, SCRIPTS / "transcribe.py", work], work)
        if not _ok(rc, aj):
            issues.append(Issue("transcribe", "التفريغ فشل (transcribe.py) — ما أقدر أعرف فيه كلام ولا لا"))
    segments = _load(aj).get("segments") or []
    if beats and not bj.exists():
        music = work / "bg-audio.mp3"
        bsrc = music if music.exists() else wav
        if bsrc.exists():
            rc = run([sys.executable, SCRIPTS / "beat.py", bsrc, "--out", bj], work)
            if not _ok(rc, bj):
                issues.append(Issue("beat", "beat.py ما طلّع إيقاع (ما فيه نبضة واضحة، أو فشل)"))
    bdata = _load(bj)
    bpm = bdata.get("bpm") or None
    return segments, _duration(wav, bdata, segments), (float(bpm) if bpm else None)


def suggest(speech, bpm, mode=None, poem=False, audio=True) -> str:
    """speech=None = ما قدرنا نحلّل الصوت. audio = صوت مسموع بلا إيقاع وفيه شوية كلام.
       بلا صوت مسموع (مجلد مقاطع، أو src.* ساكت) ← beat-montage = افتراضي upstream (الموسيقى تنضاف بعدين)."""
    if mode in MODE_ROUTE:
        return MODE_ROUTE[mode]
    if speech is None:
        return "talking-head"
    if speech:
        return "voice-montage" if poem or mode == "montage" else "talking-head"
    return "beat-montage" if bpm or not audio else "voice-montage"


def _analysis(work: Path, mode=None, poem=False, runner=None):
    """← (det, segments, duration, issues)."""
    issues = []
    segments, duration, bpm = analyse(work, runner, issues)
    deaf = any(i.kind != "beat" for i in issues)          # الصوت أو التفريغ فشل، مو الإيقاع بس
    unknown = deaf and (mode == "reel" or (mode is None and source_video(work) is not None))
    speech = None if unknown else _has_speech(segments, duration)
    ratio = round(speech_seconds(segments) / duration, 3) if duration else 0.0
    audio = ratio > 0 and audible(Path(work) / "a.wav")  # ساكت أو بلا كلام أبداً ← مو مونتاج على الصوت
    det = {"speech_ratio": ratio, "bpm": bpm, "suggested": suggest(speech, bpm, mode, poem, audio)}
    return det, segments, duration, issues


def detect(work: Path, mode=None, poem=False, runner=None) -> dict:
    return _analysis(work, mode, poem, runner)[0]


def pick_series(work: Path, named):
    """← (name, []) أو (None, [قائمة البطاقات للسؤال]). ما يخمّن أبداً."""
    if named:
        return named.strip(), []
    cards = lessons.list_series()
    by_key = {c.casefold(): c for c in cards}
    key = Path(work).resolve().name.casefold()
    if key in by_key:
        return by_key[key], []
    return None, cards


def rules_ar(n: int) -> str:
    if n == 0:
        return "بلا قواعد"
    if n == 1:
        return "قاعدة واحدة"
    if n == 2:
        return "قاعدتين"
    return f"{n} قواعد" if n <= 10 else f"{n} قاعدة"


def step0_line(series, det: dict, captions: str, rules: int) -> str:
    appr = APPROACHES[det["suggested"]]
    if det["suggested"] == "beat-montage" and det.get("bpm"):
        appr += f" ({round(det['bpm'])} BPM)"
    if captions in ("on", "both") and det["suggested"] in NO_BURN:
        captions = "off"
    return (f"السلسلة: {series or 'بلا'} · الأسلوب: {appr} · "
            f"{CAPTION_LABELS[captions]} · {rules_ar(rules)}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="approach.py")
    ap.add_argument("work")
    ap.add_argument("--series")
    ap.add_argument("--no-series", action="store_true")
    ap.add_argument("--pauses", action="store_true", help="يكتب <work>/pauses.json لـ12_montage.py plan --beats")
    ap.add_argument("--mode", choices=["reel", "podcast", "motion", "montage", "tutorial"])
    ns = ap.parse_args(argv)
    work = Path(ns.work)
    if ns.pauses:                       # خطوة مستقلة بالمونتاج على الصوت — بلا سطر الخطوة 0
        out = work / "pauses.json"
        issues = []
        segs = analyse(work, issues=issues, beats=False)[0]
        for i in issues:
            print(f"⚠️ {i.text}")
        out.write_text(json.dumps({"bpm": 0, "beats": pauses(segs)}), encoding="utf-8")
        print(f"✅ {out}")
        return
    if ns.series:
        try:
            lessons.card_path(ns.series)
        except ValueError as e:
            print(f"❌ {e} — بلا / أو \\ أو : أو نقطة بالبداية")
            sys.exit(2)
    series = None
    if not ns.no_series:
        series, ask = pick_series(work, ns.series)
        if series is None and ask:
            print("أي سلسلة؟ " + " · ".join(ask) + " — أو «بلا سلسلة» (--no-series)")
            return
    card = lessons.card_settings(series)
    det, segments, duration, issues = _analysis(work, ns.mode, card["poem"])
    caps = decide_captions(segments, duration, card["captions"], card["poem"])
    if any(i.kind != "beat" for i in issues) or (issues and caps == "none"):
        caps = "ask"                    # ما نقدر نجزم «بلا ترجمة» والتحليل ناقص
    talk = _has_speech(segments, duration)
    for i in issues:
        if not (i.kind == "beat" and talk):   # ريل فيه كلام ما يحتاج إيقاع ← لا تحذّر
            print(f"⚠️ {i.text}")
    print(step0_line(series, det, caps, lessons.rule_count(series)))
    if series and not lessons.card_path(series).exists():
        print(f"🆕 ما فيه بطاقة لـ«{series}» — أسوّيها من هالفيديو؟ (lessons.py init-series)")


if __name__ == "__main__":
    main()
