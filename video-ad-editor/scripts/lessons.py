# -*- coding: utf-8 -*-
"""القواعد المتعلّمة + بطاقات السلاسل — كلها تحت VAE_HOME (نفس 00_onboard.py)، وتحديث السكل ما يلمسها.
   python scripts/lessons.py show [--series S]                  ← «قواعد: N» + الملف العام + بطاقة السلسلة
   python scripts/lessons.py add --video V [--series S] "rule"  ← يضيف سطر (بلا تكرار)؛ الملف وصل حدّه ← يرفض (خروج 4) إلا --force بعد الدمج
   python scripts/lessons.py init-series NAME                   ← بطاقة جديدة من القالب
   البطاقة: series/<name>.md بأقسام Look · Story · Delivery · Never · Lessons.
   بـDelivery: «- captions: on|off|both» و«- poem: true» (فاضي = افتراضي الأسلوب)."""
import argparse
import datetime
import os
import re
import sys
import tempfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

GLOBAL_MAX = 40
SERIES_PROFILE_MAX = 30
SERIES_LESSONS_MAX = 40
CAPTION_POLICIES = ("on", "off", "both")

TEMPLATE = """# {name}

## Look
<!-- الألوان · الخطوط · التدرّج -->

## Story
<!-- أعراف القصة، مثل ترتيب الخطوات -->

## Delivery
{approach}- captions:   (on | off | both — فاضي = افتراضي الأسلوب)
- poem:       (true = قصائد ملقاة — فاضي = لا)
<!-- المقاس · الترميز · LUFS · حجم الملف -->

## Never

## Lessons
"""

_RULE = re.compile(r"^- (.*?) \(\d{4}-\d{2}-\d{2} · .*\)\s*$")


def vae_home() -> Path:
    return Path(os.environ.get("VAE_HOME") or (Path.home() / ".video-ad-editor"))


def _global() -> Path:
    return vae_home() / "lessons.md"


def series_dir() -> Path:
    return vae_home() / "series"


def card_path(name: str) -> Path:
    name = (name or "").strip()
    if not name or name.startswith(".") or any(c in name for c in '/\\:*?"<>|'):
        raise ValueError(f"اسم سلسلة غير صالح: {name!r}")
    return series_dir() / f"{name}.md"


def list_series() -> list:
    d = series_dir()
    return sorted(p.stem for p in d.glob("*.md") if not p.name.startswith(".")) if d.is_dir() else []


def _write(p: Path, text: str) -> None:
    """كتابة ذرّية: ملف مؤقت بنفس المجلد ثم os.replace — البطاقة ما تنمسح لو انقطع شي بالنص."""
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".tmp-", suffix=".md")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(tmp, p)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _sections(text: str) -> dict:
    """{heading: [lines]} — الأسطر قبل أول ## تحت «»."""
    out, cur = {"": []}, ""
    for line in text.splitlines():
        if line.startswith("## "):
            cur = line[3:].strip()
            out.setdefault(cur, [])
        else:
            out[cur].append(line)
    return out


def _bullets(lines) -> list:
    return [l for l in lines if l.startswith("- ")]


def _norm(rule: str) -> str:
    return " ".join(rule.split()).casefold()


def _rule_text(bullet: str) -> str:
    m = _RULE.match(bullet)
    return m.group(1) if m else bullet[2:]


def _content(lines) -> list:
    return [l for l in lines if l.strip() and not l.strip().startswith("<!--")]


def card_settings(series) -> dict:
    out = {"captions": None, "poem": False}
    if not series:
        return out
    for line in _sections(_read(card_path(series))).get("Delivery", []):
        m = re.match(r"^- (captions|poem):\s*(\S*)", line)
        if not m:
            continue
        val = m.group(2).casefold()
        if m.group(1) == "captions" and val in CAPTION_POLICIES:
            out["captions"] = val
        elif m.group(1) == "poem":
            out["poem"] = val == "true"
    return out


def rule_count(series) -> int:
    n = len(_bullets(_read(_global()).splitlines()))
    if series:
        sec = _sections(_read(card_path(series)))
        n += len(_bullets(sec.get("Never", []))) + len(_bullets(sec.get("Lessons", [])))
    return n


class Full(Exception):
    """الملف وصل حدّه — add يرفض إلا بـforce (بعد الدمج)."""


def _global_full(n: int) -> str:
    return f"⚠️ lessons.md: {n}/{GLOBAL_MAX} — ادمج القواعد قبل أي إضافة"


def _series_full(series: str, n: int) -> str:
    return f"⚠️ {series}: Lessons {n}/{SERIES_LESSONS_MAX} — ادمج القواعد قبل أي إضافة"


def show(series) -> str:
    g = _read(_global())
    parts, warn = [f"قواعد: {rule_count(series)}"], []
    if g.strip():
        parts.append(g.strip())
    n = len(_bullets(g.splitlines()))
    if n >= GLOBAL_MAX:
        warn.append(_global_full(n))
    if series:
        card = _read(card_path(series))
        if card.strip():
            parts.append(card.strip())
        sec = _sections(card)
        prof = sum(len(_content(v)) for k, v in sec.items() if k not in ("Lessons",))
        prof -= 1 if card.startswith("# ") else 0   # سطر العنوان
        les = len(_bullets(sec.get("Lessons", [])))
        if prof >= SERIES_PROFILE_MAX:
            warn.append(f"⚠️ {series}: البطاقة {prof}/{SERIES_PROFILE_MAX} سطر — اختصرها")
        if les >= SERIES_LESSONS_MAX:
            warn.append(_series_full(series, les))
    return "\n\n".join(parts + warn) + "\n"


def init_series(name: str, approach_defaults: str = "") -> Path:
    p = card_path(name)
    if p.exists():
        return p
    appr = f"- approach: {' '.join(approach_defaults.split())}\n" if approach_defaults else ""
    _write(p, TEMPLATE.format(name=name.strip(), approach=appr))
    return p


def _exists(rule: str, text: str) -> bool:
    key = _norm(rule)
    return any(_norm(_rule_text(b)) == key for b in _bullets(text.splitlines()))


def add(rule: str, video: str, series, force: bool = False) -> bool:
    """يرفع Full لو الملف المقصود وصل حدّه (إلا force=True، بعد الدمج)."""
    rule = " ".join(rule.split())
    video = " ".join(str(video).split())
    g = _global()
    if _exists(rule, _read(g)):
        return False
    line = f"- {rule} ({datetime.date.today().isoformat()} · {video})"
    if series is None:
        n = len(_bullets(_read(g).splitlines()))
        if n >= GLOBAL_MAX and not force:
            raise Full(_global_full(n))
        text = _read(g) or "# Lessons — كل الفيديوهات\n\n"
        _write(g, text.rstrip("\n") + "\n" + line + "\n")
        return True
    p = init_series(series)
    text = _read(p)
    if _exists(rule, text):
        return False
    n = len(_bullets(_sections(text).get("Lessons", [])))
    if n >= SERIES_LESSONS_MAX and not force:
        raise Full(_series_full(series, n))
    lines = text.rstrip("\n").splitlines()
    start = next((i for i, l in enumerate(lines) if l.rstrip() == "## Lessons"), None)
    if start is None:
        lines += ["", "## Lessons"]
        start = len(lines) - 1
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    while end - 1 > start and not lines[end - 1].strip():
        end -= 1
    lines.insert(end, line)
    _write(p, "\n".join(lines) + "\n")
    return True


def main(argv=None):
    ap = argparse.ArgumentParser(prog="lessons.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("show")
    s.add_argument("--series")
    a = sub.add_parser("add")
    a.add_argument("--video", required=True)
    a.add_argument("--series")
    a.add_argument("--force", action="store_true", help="بعد الدمج بس: يضيف ولو الملف وصل حدّه")
    a.add_argument("rule")
    i = sub.add_parser("init-series")
    i.add_argument("name")
    i.add_argument("--approach", default="")
    ns = ap.parse_args(argv)
    try:
        card_path(ns.name if ns.cmd == "init-series" else ns.series or "x")
    except ValueError as e:
        print(f"❌ {e} — بلا / أو \\ أو : أو نقطة بالبداية")
        sys.exit(2)
    if ns.cmd == "show":
        print(show(ns.series), end="")
    elif ns.cmd == "add":
        try:
            ok = add(ns.rule, ns.video, ns.series, ns.force)
        except Full as e:
            print(f"{e} — ما انضافت (بعد الدمج: --force)")
            sys.exit(4)
        print("✅ انضافت" if ok else "= موجودة من قبل — ما انضافت")
    else:
        print(f"✅ {init_series(ns.name, ns.approach)}")


if __name__ == "__main__":
    main()
