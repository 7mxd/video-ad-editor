# -*- coding: utf-8 -*-
"""الخطوط المحلية: كل عائلة موجودة بـmotion/fonts تنقرا من الملف — بلا شبكة وقت الرسم.
   from _fonts import font_css, BUNDLED        ← 28_cover.py و33_thumb.py و22_hook.py
   نفس الجدول بـ_fonts.js (للراسمات بـnode) — وmotion/fonts/fonts.css للقوالب (python _fonts.py يعيد كتابته)."""
import os
import shutil
from pathlib import Path

FONTS_DIR = Path(__file__).resolve().parent.parent / "motion" / "fonts"

# عائلة ← {وزن: ملف}. الخط المتغيّر (VF) = ملف واحد لكل الأوزان (نطاقه بـ_VF).
_WEIGHTS: dict[str, dict[int, str]] = {
    "Cairo": {400: "Cairo-VF.ttf"},
    "Tajawal": {400: "Tajawal-Regular.ttf", 700: "Tajawal-Bold.ttf", 800: "Tajawal-ExtraBold.ttf",
                900: "Tajawal-Black.ttf"},
    "IBM Plex Sans Arabic": {400: "IBMPlexSansArabic-Regular.ttf", 600: "IBMPlexSansArabic-SemiBold.ttf",
                             700: "IBMPlexSansArabic-Bold.ttf"},
    "Readex Pro": {400: "ReadexPro-VF.ttf"},
    "Noto Kufi Arabic": {400: "NotoKufiArabic-VF.ttf"},
    "Lalezar": {400: "Lalezar-Regular.ttf"},
    "Aref Ruqaa": {400: "ArefRuqaa-Regular.ttf", 700: "ArefRuqaa-Bold.ttf"},
    "Amiri Quran": {400: "AmiriQuran-Regular.ttf"},
    "Inter": {400: "Inter-VF.ttf"},
}
_VF: dict[str, tuple[int, int]] = {"Cairo": (200, 1000), "Readex Pro": (160, 700),
                                   "Noto Kufi Arabic": (100, 900), "Inter": (100, 900)}

# عائلة ← الملف الأساسي (العادي)
BUNDLED: dict[str, str] = {fam: w.get(400) or next(iter(w.values())) for fam, w in _WEIGHTS.items()}


def _nearest(fam: str, weight: int) -> str:
    """ملف الوزن المطلوب، أو أقرب وزن موجود (التعادل: الأثقل للعريض ≥500 والأخف تحته — نفس ترتيب CSS)."""
    have = _WEIGHTS[fam]
    if fam in _VF or weight in have:
        return have.get(weight) or BUNDLED[fam]
    return have[min(have, key=lambda w: (abs(w - weight), -w if weight >= 500 else w))]


def _face(fam: str, weight, file: str, base_url: str) -> str:
    return f"@font-face{{font-family:'{fam}';font-style:normal;font-weight:{weight};src:url('{base_url}{file}')}}"


def font_css(family: str, weights: list[int], base_url: str) -> str:
    """قواعد @font-face من الملفات المحلية لو العائلة موجودة، وإلا @import من قوقل (عائلة مو بالحزمة)."""
    if family in _WEIGHTS:
        return "\n".join(_face(family, w, _nearest(family, int(w)), base_url) for w in sorted(set(weights)))
    ws = ";".join(str(w) for w in sorted(set(weights)))
    return ("@import url('https://fonts.googleapis.com/css2?family=" + family.replace(" ", "+")
            + (":wght@" + ws if ws else "") + "&display=swap');")


def base_url() -> str:
    """رابط file:/// لمجلد الخطوط (بالشرطة الأخيرة)."""
    return FONTS_DIR.as_uri() + "/"


def fonts_css_text() -> str:
    """محتوى motion/fonts/fonts.css: كل العائلات بروابط نسبية (الملفات جنب الـcss)."""
    rules = []
    for fam, weights in _WEIGHTS.items():
        if fam in _VF:
            lo, hi = _VF[fam]
            rules.append(_face(fam, f"{lo} {hi}", BUNDLED[fam], ""))
        else:
            rules += [_face(fam, w, f, "") for w, f in sorted(weights.items())]
    return "/* مولّد من scripts/_fonts.py — لا تعدّله يدوي (python scripts/_fonts.py) */\n" + "\n".join(rules) + "\n"


def copy_to(work) -> None:
    """ينسخ fonts.css والخطوط لمجلد الشغل (compose.html يطلب fonts.css جنبه)."""
    for f in [p for p in FONTS_DIR.iterdir() if p.suffix in (".ttf", ".css")]:
        dst = os.path.join(work, f.name)
        if not os.path.exists(dst) or os.path.getsize(dst) != f.stat().st_size:
            shutil.copyfile(f, dst)


if __name__ == "__main__":
    (FONTS_DIR / "fonts.css").write_text(fonts_css_text(), encoding="utf-8", newline="\n")
    print(FONTS_DIR / "fonts.css")
