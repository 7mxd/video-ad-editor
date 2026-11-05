from pathlib import Path

import measure_tokens as mt


def write_skill(folder: Path, name: str, desc: str, body: str = "Body text.\n") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    p = folder / "SKILL.md"
    p.write_text(f"---\nname: {name}\ndescription: {desc}\n---\n{body}", encoding="utf-8")
    return p


def test_listing_text_reads_frontmatter(tmp_path):
    p = write_skill(tmp_path / "x", "x", "وصف")
    assert mt.listing_text(p, "p") == "- p:x: وصف"


def test_report_sums_reel_path(tmp_path):
    skill = write_skill(tmp_path / "video-ad-editor", "video-ad-editor", "desc", "Main body.\n")
    refs = tmp_path / "video-ad-editor" / "references"
    refs.mkdir()
    (refs / "a.md").write_text("alpha file", encoding="utf-8")
    (refs / "b.md").write_text("بيتا", encoding="utf-8")
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "reel_path.txt").write_text(
        "video-ad-editor/references/a.md\nvideo-ad-editor/references/b.md\n", encoding="utf-8"
    )
    body = skill.read_text(encoding="utf-8")
    files = ["alpha file", "بيتا"]

    rep = mt.report(tmp_path, "p", counter=len)

    assert rep["body"] == len(body)
    assert rep["reel_path"] == len(body) + sum(len(f) for f in files)
    assert set(rep) >= {"listing", "body", "reel_path", "files"}


def test_report_listing_sums_all_skills(tmp_path):
    write_skill(tmp_path / "video-ad-editor", "video-ad-editor", "one")
    write_skill(tmp_path / "motion-video", "motion-video", "two")
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "reel_path.txt").write_text("", encoding="utf-8")

    rep = mt.report(tmp_path, "p", counter=len)

    expected = len("- p:video-ad-editor: one") + len("- p:motion-video: two")
    assert rep["listing"] == expected


def test_check_flags_each_budget():
    assert len(mt.check({"listing": 301, "body": 3001, "reel_path": 15001})) == 3
    assert mt.check({"listing": 300, "body": 3000, "reel_path": 15000}) == []


def test_arabic_path_with_space(tmp_path):
    p = write_skill(tmp_path / "tmp" / "فيديو 1", "x", "وصف")
    assert mt.listing_text(p, "p") == "- p:x: وصف"


def test_count_tokens_uses_injected_counter():
    assert mt.count_tokens("abcd", counter=len) == 4


def test_baseline_cache_ignores_entry_without_cwd_schema(tmp_path, monkeypatch):
    """A baseline cached before claude -p ran from a neutral cwd must be re-measured."""
    import json
    cache = tmp_path / "baseline.json"
    cache.write_text(json.dumps({"version": "v1", "baseline": 999}), encoding="utf-8")
    monkeypatch.setattr(mt, "CACHE_FILE", cache)
    monkeypatch.setattr(mt, "_claude_version", lambda: "v1")
    monkeypatch.setattr(mt, "_claude_input_tokens", lambda text: 123)
    assert mt._baseline() == 123
    assert mt._baseline() == 123  # now cached under the new key
    assert json.loads(cache.read_text(encoding="utf-8"))["schema"] == mt.CACHE_SCHEMA
