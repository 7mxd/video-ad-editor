"""authorized(): studio is local by default, LAN mode needs a token (finding 5)."""
import importlib.util
from pathlib import Path

STUDIO = Path(__file__).resolve().parents[1] / "video-ad-editor" / "studio" / "studio.py"
_spec = importlib.util.spec_from_file_location("studio", STUDIO)
studio = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(studio)  # must not start a server
authorized = studio.authorized

TOKEN = "s3cret-token"


def test_local_mode_allows_api():
    assert authorized("/api/state", {}, {}, None) is True
    assert authorized("/api/render", {}, {}, None) is True


def test_lan_requires_token():
    assert authorized("/api/state", {}, {}, TOKEN) is False
    assert authorized("/api/state", {}, {"t": "wrong"}, TOKEN) is False
    assert authorized("/api/state", {"X-Studio-Token": "wrong"}, {}, TOKEN) is False
    assert authorized("/api/state", {}, {"t": TOKEN}, TOKEN) is True
    assert authorized("/api/save", {"X-Studio-Token": TOKEN}, {}, TOKEN) is True


def test_local_mode_static_paths_open():
    for p in ("/m", "/", "/share", "/cutz.mp4", "/vfr/00001.jpg"):
        assert authorized(p, {}, {}, None) is True


def test_lan_requires_token_on_every_path():
    for p in ("/m", "/", "/share", "/cutz.mp4", "/vfr/00001.jpg", "/a.json"):
        assert authorized(p, {}, {}, TOKEN) is False
        assert authorized(p, {}, {"t": TOKEN}, TOKEN) is True


def test_lan_cookie_counts_as_token():
    assert authorized("/cutz.mp4", {"Cookie": f"studio_t={TOKEN}"}, {}, TOKEN) is True
    assert authorized("/cutz.mp4", {"Cookie": "studio_t=nope; x=1"}, {}, TOKEN) is False
    assert authorized("/cutz.mp4", {"Cookie": "garbage;;=="}, {}, TOKEN) is False


def test_local_origin_allow_list():
    ok = studio.local_origin_ok
    assert ok({"Host": "127.0.0.1:8792"}, 8792)
    assert ok({"Host": "localhost:8792", "Origin": "http://localhost:8792"}, 8792)
    assert ok({"Host": "127.0.0.1:8792", "Origin": "http://127.0.0.1:8792"}, 8792)
    assert not ok({"Host": "evil.example:8792"}, 8792)                       # DNS rebinding
    assert not ok({"Host": "127.0.0.1:8792", "Origin": "https://evil.example"}, 8792)
    assert not ok({"Host": "127.0.0.1:8792", "Origin": "null"}, 8792)
    assert not ok({}, 8792)


# --- live server: LAN mode -----------------------------------------------------

import http.client  # noqa: E402
import threading  # noqa: E402

import pytest  # noqa: E402


@pytest.fixture
def lan_server(tmp_path, monkeypatch):
    (tmp_path / "cutz.mp4").write_bytes(b"0123456789")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "x.txt").write_text("x", encoding="utf-8")
    monkeypatch.setattr(studio, "W", str(tmp_path))
    monkeypatch.setattr(studio, "TOKEN", TOKEN)
    srv = studio.http.server.ThreadingHTTPServer(("127.0.0.1", 0), studio.H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()
    srv.server_close()


def _get(port, path, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    c.request("GET", path, headers=headers or {})
    r = c.getresponse()
    body = r.read()
    c.close()
    return r, body


def test_lan_static_file_needs_token_then_cookie(lan_server):
    r, _ = _get(lan_server, "/cutz.mp4")
    assert r.status == 403
    r, body = _get(lan_server, f"/cutz.mp4?t={TOKEN}")
    assert r.status == 200 and body == b"0123456789"
    cookie = r.getheader("Set-Cookie") or ""
    assert f"studio_t={TOKEN}" in cookie and "HttpOnly" in cookie and "SameSite=Strict" in cookie
    r, body = _get(lan_server, "/cutz.mp4", {"Cookie": cookie.split(";")[0]})
    assert r.status == 200 and body == b"0123456789"


def test_lan_no_directory_listing(lan_server):
    r, body = _get(lan_server, f"/sub/?t={TOKEN}")
    assert r.status == 404 and b"x.txt" not in body


def test_local_post_rejects_foreign_origin(tmp_path, monkeypatch):
    monkeypatch.setattr(studio, "W", str(tmp_path))
    monkeypatch.setattr(studio, "TOKEN", None)
    srv = studio.http.server.ThreadingHTTPServer(("127.0.0.1", 0), studio.H)
    port = srv.server_address[1]
    monkeypatch.setattr(studio, "PORT", port)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        def post(headers):
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            c.request("POST", "/api/nope", body=b"{}", headers=headers)
            r = c.getresponse(); r.read(); c.close()
            return r.status
        assert post({"Origin": "https://evil.example"}) == 403
        assert post({"Host": f"evil.example:{port}"}) == 403
        assert post({"Origin": f"http://127.0.0.1:{port}"}) == 404     # allowed through to routing
    finally:
        srv.shutdown(); srv.server_close()
