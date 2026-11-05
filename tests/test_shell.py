"""Python scripts that call .sh files must reach Git Bash on Windows, not the WSL bash.exe in System32."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "video-ad-editor" / "scripts"))
import _shell as S  # noqa: E402


def test_non_windows_uses_plain_bash():
    assert S.find_bash(platform="darwin") == "bash"
    assert S.find_bash(platform="linux") == "bash"


def test_windows_skips_system32_wsl_bash():
    env = {"PATH": r"C:\Windows\System32;C:\Program Files\Git\usr\bin"}
    have = {r"C:\Windows\System32\bash.exe", r"C:\Program Files\Git\usr\bin\bash.exe"}
    got = S.find_bash(platform="win32", which=lambda n: None, exists=lambda p: p in have, env=env)
    assert got == r"C:\Program Files\Git\usr\bin\bash.exe"


def test_windows_finds_bash_next_to_git():
    env = {"PATH": r"C:\Windows\System32"}
    have = {r"C:\Windows\System32\bash.exe", r"D:\Tools\Git\bin\bash.exe"}
    got = S.find_bash(platform="win32", which=lambda n: r"D:\Tools\Git\cmd\git.exe",
                      exists=lambda p: p in have, env=env)
    assert got == r"D:\Tools\Git\bin\bash.exe"


def test_windows_program_files_fallback():
    env = {"PATH": "", "ProgramFiles": r"C:\Program Files"}
    have = {r"C:\Program Files\Git\bin\bash.exe"}
    got = S.find_bash(platform="win32", which=lambda n: None, exists=lambda p: p in have, env=env)
    assert got == r"C:\Program Files\Git\bin\bash.exe"


def test_windows_fallback_warns(capsys):
    got = S.find_bash(platform="win32", which=lambda n: None, exists=lambda p: False, env={"PATH": ""})
    assert got == "bash"
    assert "Git Bash" in capsys.readouterr().err


def test_no_script_calls_bare_bash():
    hits = []
    base = ROOT / "video-ad-editor"
    for p in [*base.joinpath("scripts").glob("*.py"), *base.joinpath("studio").glob("*.py"),
              *base.joinpath("motion").glob("*.py")]:
        if p.name != "_shell.py" and re.search(r"""\[\s*['"]bash['"]\s*,""", p.read_text(encoding="utf-8")):
            hits.append(p.name)
    assert hits == []
