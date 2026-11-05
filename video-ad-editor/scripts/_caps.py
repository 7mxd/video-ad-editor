# -*- coding: utf-8 -*-
"""قدرات الجهاز للميزات اللي تحتاج ماك — يطبعها 00_setup.sh بالخطوة 0 (فحص فعلي، مو اسم النظام بس).
   python _caps.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from _faces import have_swiftc, have_cv2


def have_mlx():
    try:
        import mlx_whisper  # noqa: F401
        return True
    except Exception:
        return False


def lines(has_swiftc, has_cv2, has_mlx):
    if has_swiftc and has_mlx:
        return ["✅ ميزات الماك كلها متاحة هنا (Vision · swiftc · mlx_whisper)."]
    out = ["ميزات تحتاج ماك — قل للمستخدم من البداية لو طلب وحدة منها:"]
    if not has_swiftc:
        out.append("  ⛔ ما تشتغل هنا (تحتاج ماك + swiftc): «الكلام ورا الشخص» (11) · قصّ الشخص"
                   " (أنماط القصّ الثلاثة · الكولاج · الخلفية 14 · «الراس برّا الكرت» بالبودكاست · صورة الكفر من الفيديو)"
                   " · تتبّع الكف (29) · تتبّع الوجه للحركات 85/86 (36) · قصّ الفيديو العريض حول الوجه (يقص من النص)"
                   " · القصّ من فوق الراس للكرت (23 — يبقى على faceAnchor، تحقق بعينك)")
        out.append("  ⚠️ فيديو آيفون HDR: محوّل أبل ما يشتغل هنا — نكمل بالأصل والألوان قد تختلف")
        if has_cv2:
            out.append("  ⚠️ تتبّع الوجه بالبودكاست (15 · 24) ومركز الهوك (22b): OpenCV بديل (أقل دقة من Vision)")
        else:
            out.append("  ⛔ تتبّع الوجه بالبودكاست (15 · 24) ومركز الهوك (22b): بلا تتبّع (قصّ من النص)"
                       " — للبديل OpenCV: 00_setup.sh --extras")
    if not has_mlx:
        out.append("  ℹ️ التفريغ الطويل (18): mlx_whisper (ماك M1+) مو موجود ← openai-whisper (أبطأ، يشتغل عادي)")
    return out


if __name__ == "__main__":
    print("\n".join(lines(have_swiftc(), have_cv2(), have_mlx())))
