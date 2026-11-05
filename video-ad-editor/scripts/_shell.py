# -*- coding: utf-8 -*-
"""bash للسكربتات اللي تنادي ملفات .sh من بايثون.
   ويندوز: subprocess.run(["bash", …]) يدوّر بـSystem32 قبل PATH فيلقى bash حق WSL (بلا توزيعة = يفشل:
   «execvpe(/bin/bash) failed»). هني نلقى Git Bash: من PATH بدون System32/WindowsApps، أو جنب git.exe، أو مجلد Git المعتاد."""
import os
import shutil
import sys


def _bad(p):
    q = p.replace("/", "\\").lower()
    return "\\windows\\system32\\" in q or "\\windowsapps\\" in q


def find_bash(platform=None, which=None, exists=None, env=None):
    platform = platform or sys.platform
    if not platform.startswith("win"):
        return "bash"
    which = which or shutil.which
    exists = exists or os.path.isfile
    env = os.environ if env is None else env
    cands = []
    for d in (env.get("PATH") or "").split(os.pathsep):
        if d:
            cands.append(os.path.join(d, "bash.exe"))
    git = which("git")
    if git:
        root = os.path.dirname(os.path.dirname(git))          # …/Git/cmd/git.exe → …/Git
        cands += [os.path.join(root, "bin", "bash.exe"), os.path.join(root, "usr", "bin", "bash.exe")]
    for k in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)", "LOCALAPPDATA"):
        base = env.get(k)
        if base:
            sub = ("Programs", "Git") if k == "LOCALAPPDATA" else ("Git",)
            cands.append(os.path.join(base, *sub, "bin", "bash.exe"))
    for c in cands:
        if not _bad(c) and exists(c):
            return c
    print("⚠️ ما لقيت Git Bash — نزّل Git for Windows (git-scm.com)، وإلا أوامر .sh ممكن تفشل", file=sys.stderr)
    return "bash"

