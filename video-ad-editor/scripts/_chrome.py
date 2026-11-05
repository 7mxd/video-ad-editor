# -*- coding: utf-8 -*-
"""كروم: نفس البحث على ويندوز وماك ولينكس (نفس الترتيب في _find_chrome.js).
   from _chrome import find_chrome   ← 28_cover.py و33_thumb.py"""
import os
import shutil

NOT_FOUND = "❌ ما لقيت كروم — حدّد CHROME_PATH"
MAC_CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
LINUX = ["/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser"]
WHICH = ["google-chrome", "chromium", "chromium-browser"]


def _candidates(env):
    pf, p86, la = env.get("ProgramFiles"), env.get("ProgramFiles(x86)"), env.get("LOCALAPPDATA")
    chrome = "/Google/Chrome/Application/chrome.exe"
    edge = "/Microsoft/Edge/Application/msedge.exe"
    out = [base + chrome for base in (pf, p86, la) if base]
    out += [base + edge for base in (p86, pf) if base]
    return out + [MAC_CHROME] + LINUX


def find_chrome(env=os.environ, exists=os.path.exists, which=shutil.which) -> str:
    for key in ("CHROME_PATH", "CHROME"):
        if env.get(key):
            return env[key]
    for path in _candidates(env):
        if exists(path):
            return path
    for name in WHICH:
        found = which(name)
        if found:
            return found
    raise SystemExit(NOT_FOUND)


if __name__ == "__main__":   # 00_setup.sh: python _chrome.py ← يطبع المسار أو يخرج بخطأ
    print(find_chrome())
