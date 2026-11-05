"""Bundled fonts are served locally, Google only for unbundled families (finding 11)."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "video-ad-editor" / "scripts"))
import _fonts  # noqa: E402
from _fonts import BUNDLED, font_css  # noqa: E402

FONTS_DIR = ROOT / "video-ad-editor" / "motion" / "fonts"
BASE = "file:///fonts/"


def test_font_css_bundled_uses_local_file():
    css = font_css("Cairo", [700, 900], BASE)
    assert "src:url(" + BASE + "Cairo-VF.ttf" in css.replace("'", "").replace('"', "")
    assert "googleapis" not in css
    assert css.count("@font-face") == 2


def test_font_css_unknown_uses_google():
    css = font_css("Almarai", [400, 800], BASE)
    assert "@import" in css and "fonts.googleapis.com" in css
    assert "family=Almarai:wght@400;800" in css


def test_static_family_picks_weight_file_and_nearest():
    css = font_css("Tajawal", [700, 800, 900], BASE)
    rules = re.findall(r"font-weight:(\d+);src:url\('([^']+)'\)", css)
    got = dict(rules)
    assert got["700"].endswith("Tajawal-Bold.ttf")
    assert got["900"].endswith("Tajawal-Black.ttf")
    assert got["800"].endswith("Tajawal-ExtraBold.ttf")  # Google served ExtraBold for 800
    # IBM Plex has 400/700 only: 600 → 700, 500 → 400? (tie at 500/600 handled by nearest)
    plex = dict(re.findall(r"font-weight:(\d+);src:url\('([^']+)'\)", font_css("IBM Plex Sans Arabic", [400, 600], BASE)))
    assert plex["600"].endswith("IBMPlexSansArabic-SemiBold.ttf")  # Google served SemiBold for 600
    assert plex["400"].endswith("IBMPlexSansArabic-Regular.ttf")


def test_bundled_covers_all_families_and_files_exist():
    want = {"Cairo", "Tajawal", "IBM Plex Sans Arabic", "Readex Pro", "Noto Kufi Arabic",
            "Lalezar", "Aref Ruqaa", "Amiri Quran", "Inter"}
    assert want <= set(BUNDLED)
    for fam, f in BUNDLED.items():
        assert (FONTS_DIR / f).is_file(), (fam, f)
    for fam, weights in _fonts._WEIGHTS.items():
        for f in weights.values():
            assert (FONTS_DIR / f).is_file(), (fam, f)


def test_fonts_css_matches_bundle():
    css = (FONTS_DIR / "fonts.css").read_text(encoding="utf-8")
    assert "googleapis" not in css
    assert css == _fonts.fonts_css_text()
    for fam in BUNDLED:
        assert f"font-family:'{fam}'" in css


def test_js_mirror_has_same_families():
    js = (ROOT / "video-ad-editor" / "scripts" / "_fonts.js").read_text(encoding="utf-8")
    for fam, weights in _fonts._WEIGHTS.items():
        assert f"'{fam}'" in js
        for f in weights.values():
            assert f in js


def test_nearest_weight_tie_goes_heavier():
    # Aref Ruqaa has 400/700 only (Google too): 600 → 700, 500 → 400 (nearer)
    got = dict(re.findall(r"font-weight:(\d+);src:url\('([^']+)'\)", font_css("Aref Ruqaa", [500, 600], BASE)))
    assert got["600"].endswith("ArefRuqaa-Bold.ttf")
    assert got["500"].endswith("ArefRuqaa-Regular.ttf")
