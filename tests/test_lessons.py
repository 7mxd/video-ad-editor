"""lessons.py: global lessons + series cards under VAE_HOME (spec: series profiles and the lessons loop)."""
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "video-ad-editor" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import lessons  # noqa: E402


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "vae home"
    monkeypatch.setenv("VAE_HOME", str(h))
    return h


def test_vae_home_default(monkeypatch):
    monkeypatch.delenv("VAE_HOME", raising=False)
    assert lessons.vae_home() == Path.home() / ".video-ad-editor"


def test_show_missing_files_ok(home):
    out = lessons.show("coffee")
    assert out.splitlines()[0] == "قواعد: 0"
    assert "⚠️" not in out


def test_add_dedupes(home):
    assert lessons.add("Keep captions off the face", "ep1", None) is True
    assert lessons.add("  keep CAPTIONS   off the face ", "ep2", None) is False
    text = (home / "lessons.md").read_text(encoding="utf-8")
    assert text.count("Keep captions off the face") == 1
    assert "· ep1)" in text


def test_add_line_format(home):
    lessons.add("لا فلاش", "ep 3", None)
    line = [l for l in (home / "lessons.md").read_text(encoding="utf-8").splitlines() if l.startswith("- ")][0]
    import re
    assert re.fullmatch(r"- لا فلاش \(\d{4}-\d{2}-\d{2} · ep 3\)", line)


def test_add_series_creates_lessons_section(home):
    assert lessons.add("no zoom punches", "coffee-12", "coffee") is True
    text = (home / "series" / "coffee.md").read_text(encoding="utf-8")
    assert "## Lessons" in text
    after = text.split("## Lessons", 1)[1]
    assert "- no zoom punches (" in after
    assert not (home / "lessons.md").exists()


def test_add_series_appends_under_lessons_not_at_end_of_other_section(home):
    card = lessons.init_series("coffee")
    lessons.add("rule one", "a", "coffee")
    lessons.add("rule two", "b", "coffee")
    text = card.read_text(encoding="utf-8")
    lesson_part = text.split("## Lessons", 1)[1]
    assert "rule one" in lesson_part and "rule two" in lesson_part
    never_part = text.split("## Never", 1)[1].split("## Lessons", 1)[0]
    assert "rule one" not in never_part


def test_init_series_sections(home):
    p = lessons.init_series("coins", approach_defaults="talking-head")
    text = p.read_text(encoding="utf-8")
    for s in ("## Look", "## Story", "## Delivery", "## Never", "## Lessons"):
        assert s in text
    assert text.index("## Look") < text.index("## Lessons")
    assert "talking-head" in text
    assert p == home / "series" / "coins.md"


def test_init_series_does_not_overwrite(home):
    p = lessons.init_series("coffee")
    lessons.add("keep me", "x", "coffee")
    lessons.init_series("coffee")
    assert "keep me" in p.read_text(encoding="utf-8")


def test_show_counts_rules(home):
    lessons.add("g1", "x", None)
    lessons.add("g2", "x", None)
    lessons.init_series("coffee")
    lessons.add("s1", "x", "coffee")
    out = lessons.show("coffee")
    assert out.splitlines()[0] == "قواعد: 3"
    assert "g1" in out and "s1" in out


def test_show_warns_over_budget(home):
    home.mkdir(parents=True)
    body = "# Lessons\n" + "".join(f"- rule {i} (2026-11-05 · v)\n" for i in range(41))
    (home / "lessons.md").write_text(body, encoding="utf-8")
    out = lessons.show(None)
    assert out.splitlines()[0] == "قواعد: 41"
    assert "⚠️" in out and "40" in out


def test_show_warns_when_budget_reached(home):
    home.mkdir(parents=True)
    body = "".join(f"- rule {i} (2026-11-05 · v)\n" for i in range(40))
    (home / "lessons.md").write_text(body, encoding="utf-8")
    assert "⚠️" in lessons.show(None)


def test_show_no_warning_under_budget(home):
    home.mkdir(parents=True)
    body = "".join(f"- rule {i} (2026-11-05 · v)\n" for i in range(39))
    (home / "lessons.md").write_text(body, encoding="utf-8")
    assert "⚠️" not in lessons.show(None)


def test_show_warns_series_lessons_over_budget(home):
    lessons.init_series("coffee")
    for i in range(41):
        lessons.add(f"series rule {i}", "v", "coffee", force=True)
    assert "⚠️" in lessons.show("coffee")


def test_arabic_series_name_and_space_in_vae_home(home):
    name = "عملات قديمة"
    lessons.init_series(name)
    assert lessons.add("الكابشن فوق الكرت", "حلقة 5", name) is True
    card = home / "series" / f"{name}.md"
    assert card.exists()
    out = lessons.show(name)
    assert "الكابشن فوق الكرت" in out
    assert out.splitlines()[0] == "قواعد: 1"


def test_series_name_rejects_path_tricks(home):
    with pytest.raises(ValueError):
        lessons.init_series("../evil")


def test_card_settings(home):
    p = lessons.init_series("coffee")
    text = p.read_text(encoding="utf-8").replace("- captions:", "- captions: off  #").replace("- poem:", "- poem: true  #")
    p.write_text(text, encoding="utf-8")
    s = lessons.card_settings("coffee")
    assert s["captions"] == "off" and s["poem"] is True


def test_card_settings_defaults_when_blank_or_missing(home):
    assert lessons.card_settings("nope") == {"captions": None, "poem": False}
    lessons.init_series("coffee")
    assert lessons.card_settings("coffee") == {"captions": None, "poem": False}


def test_cli_roundtrip_utf8(home):
    env_run = dict(capture_output=True, text=True, encoding="utf-8")
    r = subprocess.run([sys.executable, str(SCRIPTS / "lessons.py"), "init-series", "قهوة"], **env_run)
    assert r.returncode == 0, r.stderr
    r = subprocess.run([sys.executable, str(SCRIPTS / "lessons.py"), "add", "--video", "v 1",
                        "--series", "قهوة", "بلا فلاش"], **env_run)
    assert r.returncode == 0, r.stderr
    r = subprocess.run([sys.executable, str(SCRIPTS / "lessons.py"), "show", "--series", "قهوة"], **env_run)
    assert r.returncode == 0, r.stderr
    assert r.stdout.splitlines()[0] == "قواعد: 1"
    assert "بلا فلاش" in r.stdout


def test_add_keeps_one_rule_on_one_line(home):
    lessons.add("no\nflash  here", "ep\n 7", None)
    bullets = [l for l in (home / "lessons.md").read_text(encoding="utf-8").splitlines() if l.startswith("- ")]
    assert len(bullets) == 1 and bullets[0].startswith("- no flash here (") and bullets[0].endswith("· ep 7)")


def test_add_tolerates_trailing_space_on_lessons_heading(home):
    p = lessons.init_series("coffee")
    p.write_text(p.read_text(encoding="utf-8").replace("## Lessons", "## Lessons   "), encoding="utf-8")
    lessons.add("rule", "v", "coffee")
    assert p.read_text(encoding="utf-8").count("## Lessons") == 1


def test_writes_are_atomic(home, monkeypatch):
    p = lessons.init_series("coffee")
    lessons.add("keep", "v", "coffee")
    before = p.read_text(encoding="utf-8")
    real = lessons.os.replace

    def boom(src, dst):
        raise OSError("disk full")
    monkeypatch.setattr(lessons.os, "replace", boom)
    with pytest.raises(OSError):
        lessons.add("new rule", "v", "coffee")
    monkeypatch.setattr(lessons.os, "replace", real)
    assert p.read_text(encoding="utf-8") == before
    assert [f.name for f in p.parent.iterdir()] == ["coffee.md"]


def test_cli_invalid_series_name(home):
    r = subprocess.run([sys.executable, str(SCRIPTS / "lessons.py"), "show", "--series", "../x"],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 2 and "Traceback" not in r.stderr + r.stdout
    assert len((r.stdout + r.stderr).strip().splitlines()) == 1


def test_add_refuses_when_global_full(home):
    home.mkdir(parents=True)
    body = "".join(f"- rule {i} (2026-11-05 · v)\n" for i in range(lessons.GLOBAL_MAX))
    (home / "lessons.md").write_text(body, encoding="utf-8")
    with pytest.raises(lessons.Full) as e:
        lessons.add("one more", "v", None)
    assert "⚠️" in str(e.value) and "40" in str(e.value)
    assert (home / "lessons.md").read_text(encoding="utf-8") == body
    assert lessons.add("one more", "v", None, force=True) is True


def test_add_refuses_when_series_lessons_full(home):
    lessons.init_series("coffee")
    for i in range(lessons.SERIES_LESSONS_MAX):
        lessons.add(f"series rule {i}", "v", "coffee")
    with pytest.raises(lessons.Full):
        lessons.add("one more", "v", "coffee")
    assert lessons.add("one more", "v", "coffee", force=True) is True


def test_cli_add_full_exits_4(home):
    home.mkdir(parents=True)
    body = "".join(f"- rule {i} (2026-11-05 · v)\n" for i in range(lessons.GLOBAL_MAX))
    (home / "lessons.md").write_text(body, encoding="utf-8")
    run = lambda *a: subprocess.run([sys.executable, str(SCRIPTS / "lessons.py"), "add", "--video", "v", *a],
                                    capture_output=True, text=True, encoding="utf-8")
    r = run("one more")
    assert r.returncode == 4 and "⚠️" in r.stdout and "Traceback" not in r.stderr
    r = run("--force", "one more")
    assert r.returncode == 0 and "✅" in r.stdout


def test_list_series_ignores_dot_files(home):
    lessons.init_series("coffee")
    (lessons.series_dir() / ".tmp-abc.md").write_text("x", encoding="utf-8")
    assert lessons.list_series() == ["coffee"]
