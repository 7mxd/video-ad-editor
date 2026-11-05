"""find_chrome(): one Chrome lookup for the Python renderers (finding 10)."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "video-ad-editor" / "scripts"))
from _chrome import find_chrome  # noqa: E402

WIN_ENV = {
    "ProgramFiles": "C:/Program Files",
    "ProgramFiles(x86)": "C:/Program Files (x86)",
    "LOCALAPPDATA": "C:/Users/me/AppData/Local",
}


def _exists_only(*paths):
    allowed = {p.replace("\\", "/") for p in paths}
    return lambda p: p.replace("\\", "/") in allowed


def _no_which(_name):
    return None


def test_env_override_wins():
    env = dict(WIN_ENV, CHROME_PATH="D:/custom/chrome.exe")
    got = find_chrome(env=env, exists=lambda p: True, which=_no_which)
    assert got == "D:/custom/chrome.exe"


def test_localappdata_only():
    target = "C:/Users/me/AppData/Local/Google/Chrome/Application/chrome.exe"
    got = find_chrome(env=WIN_ENV, exists=_exists_only(target), which=_no_which)
    assert got.replace("\\", "/") == target


def test_edge_only():
    target = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
    got = find_chrome(env=WIN_ENV, exists=_exists_only(target), which=_no_which)
    assert got.replace("\\", "/") == target


FIND_CHROME_JS = Path(__file__).resolve().parents[1] / "video-ad-editor" / "scripts" / "_find_chrome.js"


def _node_find(target):
    """findChrome() in node with WIN_ENV injected and only `target` existing."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    code = (
        "const {findChrome}=require(process.argv[1]);"
        "const env=JSON.parse(process.argv[2]), only=process.argv[3];"
        "try{console.log(findChrome(env,p=>p.replace(/\\\\/g,'/')===only,()=>null))}"
        "catch(e){console.log('ERR '+e.message)}"
    )
    r = subprocess.run([node, "-e", code, str(FIND_CHROME_JS), json.dumps(WIN_ENV), target],
                       capture_output=True, text=True, encoding="utf-8", check=True)
    return r.stdout.strip().replace("\\", "/")


def test_js_localappdata_only():
    target = "C:/Users/me/AppData/Local/Google/Chrome/Application/chrome.exe"
    assert _node_find(target) == target


def test_js_edge_only():
    target = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
    assert _node_find(target) == target


def test_js_none_throws_arabic_message():
    assert _node_find("nowhere") == "ERR ما لقيت كروم — حدّد CHROME_PATH"


def test_none_raises_systemexit_with_arabic_message():
    with pytest.raises(SystemExit) as exc:
        find_chrome(env=WIN_ENV, exists=lambda p: False, which=_no_which)
    assert str(exc.value) == "❌ ما لقيت كروم — حدّد CHROME_PATH"
