"""Measure the token cost of the plugin's skill files and check it against budgets.

Method (same as docs/AUDIT.md section 1): each text is sent to the model with
`claude -p --tools ""`, wrapped in a fixed "Reply OK" prompt, and the input-token
count is compared with an empty-payload baseline. The baseline is cached in
tools/.cache/ (git-ignored), keyed by the claude CLI version and CACHE_SCHEMA.

Usage: python tools/measure_tokens.py [--plugin NAME] [--check] [--json OUT]
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

DEFAULT_BUDGETS = {"listing": 300, "body": 3000, "reel_path": 15000}
MAIN_SKILL = "video-ad-editor/SKILL.md"
CACHE_FILE = Path(__file__).resolve().parent / ".cache" / "baseline.json"
# bump when the measuring conditions change; "tempcwd-1" = claude -p runs from the temp dir
CACHE_SCHEMA = "tempcwd-1"
SKIP_DIRS = {".git", "node_modules", "_pkg", "dist", ".superpowers", "tests", "tools"}


# ---------- frontmatter / listing ----------

def _frontmatter(text: str) -> str:
    text = text.replace("\r\n", "\n")
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if not m:
        raise ValueError("SKILL.md has no frontmatter")
    return m.group(1)


def _field(fm: str, key: str) -> str:
    m = re.search(rf"^{key}:\s*(.*)$", fm, re.M)
    if not m:
        raise ValueError(f"frontmatter has no '{key}'")
    return m.group(1).strip()


def listing_text(skill_md: Path, plugin: str) -> str:
    """The line Claude Code shows for this skill at session start."""
    fm = _frontmatter(Path(skill_md).read_text(encoding="utf-8"))
    return f"- {plugin}:{_field(fm, 'name')}: {_field(fm, 'description')}"


# ---------- counting ----------

def _wrap(text: str) -> str:
    return "Reply OK. Ignore the data below.\n<data>\n" + text + "\n</data>"


def _claude_input_tokens(text: str) -> int:
    cl = shutil.which("claude")
    if not cl:
        raise RuntimeError("claude CLI not found on PATH")
    out = subprocess.run(
        [cl, "-p", "--output-format", "json", "--tools", "", "--strict-mcp-config",
         "--disable-slash-commands", "--no-session-persistence"],
        input=_wrap(text).encode("utf-8"), capture_output=True,
        # neutral cwd: claude -p puts the cwd's git status in its prompt, which would
        # make counts drift against the cached baseline as the repo changes
        cwd=tempfile.gettempdir(),
    )
    if out.returncode != 0:
        raise RuntimeError(f"claude -p failed: {out.stderr.decode('utf-8', 'replace')[:500]}")
    u = json.loads(out.stdout)["usage"]
    return (u["input_tokens"] + u.get("cache_creation_input_tokens", 0)
            + u.get("cache_read_input_tokens", 0))


def _claude_version() -> str:
    cl = shutil.which("claude")
    out = subprocess.run([cl, "--version"], capture_output=True) if cl else None
    return out.stdout.decode("utf-8", "replace").strip() if out else "unknown"


def _baseline() -> int:
    version = _claude_version()
    try:
        cached = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        if cached.get("version") == version and cached.get("schema") == CACHE_SCHEMA:
            return int(cached["baseline"])
    except (OSError, ValueError, KeyError):
        pass
    base = _claude_input_tokens("")
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps({"version": version, "schema": CACHE_SCHEMA, "baseline": base}), encoding="utf-8")
    return base


def count_tokens(text: str, counter=None) -> int:
    """Tokens `text` adds to a prompt. `counter` overrides the claude call (tests)."""
    if counter is not None:
        return counter(text)
    return _claude_input_tokens(text) - _baseline()


# ---------- report / check ----------

def _skill_files(repo: Path) -> list[Path]:
    found = []
    for p in sorted(repo.rglob("SKILL.md")):
        rel = p.relative_to(repo).parts
        if any(part in SKIP_DIRS for part in rel[:-1]):
            continue
        found.append(p)
    return found


def _main_skill(repo: Path, skills: list[Path]) -> Path:
    main = repo / MAIN_SKILL
    if main.is_file():
        return main
    if len(skills) == 1:
        return skills[0]
    raise FileNotFoundError(f"cannot pick the main skill: no {MAIN_SKILL} and {len(skills)} skills found")


def _reel_path(repo: Path) -> list[str]:
    f = repo / "tools" / "reel_path.txt"
    if not f.is_file():
        return []
    lines = f.read_text(encoding="utf-8").splitlines()
    return [ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("#")]


def report(repo: Path, plugin: str, counter=None) -> dict:
    """listing: sum over all skills; body: main SKILL.md (whole file, as Claude reads it);
    reel_path: body + every file in tools/reel_path.txt; files: per-file counts."""
    repo = Path(repo)
    skills = _skill_files(repo)
    files: dict[str, int] = {}
    listing = 0
    for s in skills:
        rel = s.relative_to(repo).as_posix()
        n = count_tokens(listing_text(s, plugin), counter)
        files[f"listing:{rel}"] = n
        listing += n
    main = _main_skill(repo, skills)
    body = count_tokens(main.read_text(encoding="utf-8"), counter)
    files[main.relative_to(repo).as_posix()] = body
    reel = body
    for rel in _reel_path(repo):
        n = count_tokens((repo / rel).read_text(encoding="utf-8"), counter)
        files[rel] = n
        reel += n
    return {"listing": listing, "body": body, "reel_path": reel, "files": files}


def check(rep: dict, budgets=None) -> list[str]:
    budgets = DEFAULT_BUDGETS if budgets is None else budgets
    return [f"{key}: {rep[key]} > budget {limit}"
            for key, limit in budgets.items() if rep.get(key, 0) > limit]


# ---------- CLI ----------

def _plugin_name(repo: Path) -> str:
    try:
        return json.loads((repo / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["name"]
    except (OSError, ValueError, KeyError):
        return repo.name


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--plugin", help="plugin name (default: .claude-plugin/plugin.json)")
    ap.add_argument("--repo", default=str(Path(__file__).resolve().parents[1]),
                    help="repo root to measure (default: this repo)")
    ap.add_argument("--check", action="store_true", help="exit 1 if a budget is exceeded")
    ap.add_argument("--json", metavar="OUT", help="write the report as JSON")
    args = ap.parse_args(argv)

    repo = Path(args.repo)
    rep = report(repo, args.plugin or _plugin_name(repo))
    for name, n in rep["files"].items():
        print(f"  {n:>7,}  {name}")
    for key in ("listing", "body", "reel_path"):
        print(f"{key:>10}: {rep[key]:,} (budget {DEFAULT_BUDGETS[key]:,})")
    if args.json:
        Path(args.json).write_text(json.dumps(rep, indent=1, ensure_ascii=False), encoding="utf-8")
    if args.check:
        bad = check(rep)
        for v in bad:
            print("OVER BUDGET", v)
        return 1 if bad else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
