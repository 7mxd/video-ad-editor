"""Repo hygiene checks: removed leftovers stay removed, no dead engine routes."""
import re
import subprocess

import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SELF = "tests/test_repo_hygiene.py"  # holds the patterns themselves


def tracked_text_files() -> list[Path]:
    """All git-tracked files that exist on disk and are not binary."""
    out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True
    ).stdout.decode("utf-8")
    files = []
    for rel in out.split("\0"):
        if not rel:
            continue
        path = ROOT / rel
        if not path.is_file():
            continue
        with path.open("rb") as fh:
            if b"\0" in fh.read(8192):
                continue
        files.append(path)
    return files


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _matches(pattern: str, excluded) -> list[str]:
    rx = re.compile(pattern)
    hits = []
    for path in tracked_text_files():
        rel = _rel(path)
        if rel == SELF or excluded(rel):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for no, line in enumerate(text.splitlines(), 1):
            if rx.search(line):
                hits.append(f"{rel}:{no}")
    return hits


REMOVED_PATHS = [
    "_pkg",
    "video-ad-editor.skill",
    "tools/build-release.sh",
    "video-ad-editor/scripts/04b_remotion.sh",
    "video-ad-editor/scripts/remotion-template.bundle.json",
    "video-ad-editor/references/remotion.md",
]


def test_removed_paths_absent():
    present = [p for p in REMOVED_PATHS if (ROOT / p).exists()]
    assert present == []


def test_no_remotion_runtime_refs():
    keep = {"video-ad-editor/motion/moves/CREDITS.md", "video-ad-editor/motion/moves/catalog.json"}
    hits = _matches(
        r"04b_remotion|remotion-template|references/remotion\.md|ريموشن",
        lambda rel: rel.startswith("docs/") or rel in keep,
    )
    assert hits == []


def test_no_davinci_refs():
    # CHANGELOG.md records the removal itself.
    hits = _matches(r"(?i)davinci|دافنشي", lambda rel: rel.startswith("docs/") or rel == "CHANGELOG.md")
    assert hits == []


MAC_PYTHON3_LINE = "على الماك/لينكس بدون `python` استخدم `python3`"
MAC_PYTHON3_LINE_EN = "on Mac/Linux without `python`, use `python3`"


def test_no_python3_in_docs():
    """Docs say `python` (works on Windows); one mac/linux note may name python3."""
    hits = []
    for path in tracked_text_files():
        rel = _rel(path)
        if rel == SELF or not rel.endswith(".md"):
            continue
        if not (rel.startswith("video-ad-editor/") or rel == "README.md"):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for no, line in enumerate(text.splitlines(), 1):
            if "python3" in line and MAC_PYTHON3_LINE not in line and MAC_PYTHON3_LINE_EN not in line:
                hits.append(f"{rel}:{no}")
    assert hits == []


PYTHON3_CMD = re.compile(r"""(^|[\s;(|&`"'])python3\s""")
PYTHON3_CMD_ALLOWED = {
    # (file, substring of the allowed line): launcher probes that try python3 on purpose
    ("video-ad-editor/scripts/_compat.sh", "for c in python python3 py"),
    ("video-ad-editor/scripts/_find_chrome.js", "['python', 'python3', 'py']"),
}
COMMENT_PREFIXES = ("#", "//", "/*", "*")


def test_no_python3_command_in_scripts():
    """Shell and JS files run python through $PY / pickPython(), never a bare python3."""
    hits = []
    for path in tracked_text_files():
        rel = _rel(path)
        if not rel.startswith("video-ad-editor/") or not rel.endswith((".sh", ".js")):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for no, line in enumerate(text.splitlines(), 1):
            if line.lstrip().startswith(COMMENT_PREFIXES) or not PYTHON3_CMD.search(line):
                continue
            if any(rel == f and frag in line for f, frag in PYTHON3_CMD_ALLOWED):
                continue
            hits.append(f"{rel}:{no}")
    assert hits == []


# ---------- Task 6: one router skill ----------

SKILL_DIR = ROOT / "video-ad-editor"
MODE_REFS = ["reel.md", "motion.md", "podcast.md", "montage.md", "cover.md"]


def _tracked(rel_filter) -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True
    ).stdout.decode("utf-8")
    return [r for r in out.split("\0") if r and (ROOT / r).is_file() and rel_filter(r)]


def test_single_skill():
    skills = _tracked(
        lambda r: r.split("/")[-1] == "SKILL.md"
        and not r.startswith(("docs/", ".superpowers/"))
    )
    assert skills == ["video-ad-editor/SKILL.md"]


def test_router_links_exist():
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    linked = set(re.findall(r"references/([\w./\-]+\.md)", text))
    missing = sorted(n for n in linked if not (SKILL_DIR / "references" / n).is_file())
    assert missing == []
    assert [m for m in MODE_REFS if m not in linked] == []


SCRIPT_REF = re.compile(
    r"scripts/([\w.\-]+\.(?:py|sh|js|swift|html|txt))"
    r"|\b(\d{2}[a-z]?_[\w\-]+\.(?:py|sh|js|swift))"
)


def test_no_dead_script_refs():
    """Every `scripts/<name>` (and bare `NN_name.ext`) named in a doc exists."""
    hits = []
    for rel in _tracked(lambda r: r.endswith(".md") and not r.startswith("docs/")):
        text = (ROOT / rel).read_text(encoding="utf-8", errors="ignore")
        for no, line in enumerate(text.splitlines(), 1):
            for m in SCRIPT_REF.finditer(line):
                name = m.group(1) or m.group(2)
                if not (SKILL_DIR / "scripts" / name).is_file():
                    hits.append(f"{rel}:{no}:{name}")
    assert hits == []


# Promo token: MAJED alone or with a suffix (MAJED15…); credits to "Majed Alzaabi" stay.
PROMO = r"\bMAJED[0-9A-Z]*\b|majed-plugins"


def test_no_upstream_promo():
    hits = _matches(PROMO, lambda rel: rel.startswith("docs/") or rel == "README.md")
    assert hits == []


def test_no_upstream_promo_readme():
    hits = _matches(PROMO, lambda rel: rel != "README.md")
    assert hits == []


CREDIT = (
    "> Based on [majedphotos/video-ad-editor](https://github.com/majedphotos/video-ad-editor)"
    " by Majed Alzaabi (MIT)."
)


def test_attribution():
    import json

    lic = (ROOT / "LICENSE").read_text(encoding="utf-8").splitlines()
    assert "Copyright (c) 2026 Majed Alzaabi" in lic
    assert "Copyright (c) 2026 7mxd" in lic
    readme = (ROOT / "README.md").read_text(encoding="utf-8-sig")
    assert readme.splitlines()[0] == CREDIT
    plugin = json.loads((ROOT / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    assert plugin["upstream"] == "https://github.com/majedphotos/video-ad-editor"
    assert plugin["description"].endswith("Based on video-ad-editor by Majed Alzaabi")
    version = (ROOT / "video-ad-editor/VERSION").read_text(encoding="utf-8").strip()
    latest = re.search(r"^## (\d+\.\d+\.\d+)", (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), re.M).group(1)
    assert plugin["version"] == version == latest


def test_setup_installs_from_lockfile():
    """`00_setup.sh --install` must not rewrite the tracked package.json/lock (npm i bumps them)."""
    setup = (ROOT / "video-ad-editor/scripts/00_setup.sh").read_text(encoding="utf-8")
    assert re.search(r"npm ci\b", setup)
    assert not re.search(r"npm (i|install)\b", setup)


def _bare_text_opens(tree) -> list[int]:
    """Lines of builtin open(...) calls in text mode without an explicit encoding."""
    import ast
    hits = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open"):
            continue
        if any(k.arg == "encoding" for k in node.keywords):
            continue
        mode = node.args[1] if len(node.args) > 1 else next(
            (k.value for k in node.keywords if k.arg == "mode"), None)
        if isinstance(mode, ast.Constant) and isinstance(mode.value, str) and "b" in mode.value:
            continue
        hits.append(node.lineno)
    return hits


def test_scripts_are_utf8_on_windows():
    """Docs run `python scripts/X.py` directly; on Windows stdout and open() default to cp1252 and
    crash on Arabic. Each entry script must switch stdout to UTF-8, and no text open() may rely on
    the locale unless the file installs the UTF-8 open shim (builtins.open patched)."""
    import ast
    bad = []
    base = ROOT / "video-ad-editor"
    for path in sorted([*base.joinpath("scripts").glob("*.py"), *base.joinpath("studio").glob("*.py"),
                        *base.joinpath("motion").glob("*.py")]):
        src = path.read_text(encoding="utf-8")
        if not path.name.startswith("_") and "reconfigure(" not in src:
            bad.append(f"{path.name}: stdout not reconfigured to utf-8")
        if re.search(r"_bi\.open\s*=", src):
            if "len(a) < 2" not in src:   # open(f, "w", -1, "cp1256") passes encoding positionally
                bad.append(f"{path.name}: open shim overrides a positional encoding")
        else:
            bad += [f"{path.name}:{n}: open() without encoding" for n in _bare_text_opens(ast.parse(src))]
    assert bad == []


def test_readme_local_links_exist():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "_pkg/" not in readme and "releases/latest/download" not in readme
    targets = re.findall(r'(?:\]\(|src=")((?!https?:|#|mailto:)[^)"\s]+)', readme)
    missing = [t for t in targets if not (ROOT / t).exists()]
    assert missing == []


def test_python_launcher_order_matches():
    """_compat.sh (shell) and _find_chrome.js (node) must try the same launchers in the same order."""
    sh = (ROOT / "video-ad-editor/scripts/_compat.sh").read_text(encoding="utf-8")
    js = (ROOT / "video-ad-editor/scripts/_find_chrome.js").read_text(encoding="utf-8")
    sh_order = re.search(r"for c in ([\w ]+); do", sh).group(1).split()
    js_order = re.findall(r"'(\w+)'", re.search(r"for \(const c of \[([^\]]+)\]\)", js).group(1))
    assert sh_order == js_order == ["python", "python3", "py"]
    assert "version_info" in sh and "version_info" in js        # skip a Python 2 `python` on old Macs
