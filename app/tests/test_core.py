import io
import json
import subprocess
import threading
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from goosnav_frame.core import export as X
from goosnav_frame.core import media as M
from goosnav_frame.core import render as R
from goosnav_frame.core import settings as S


@pytest.fixture(scope="session")
def clip(tmp_path_factory) -> Path:
    """A 2 s 320x400 test video with a sine tone."""
    out = tmp_path_factory.mktemp("media") / "clip.mp4"
    subprocess.run([M.ffmpeg(), "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=320x400:rate=12:duration=2",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest", str(out)], check=True)
    return out


@pytest.fixture
def still(tmp_path) -> Path:
    p = tmp_path / "still.png"
    Image.new("RGB", (400, 300), (200, 30, 30)).save(p)
    return p


# ------------------------------------------------------------------ settings
def test_normalize_fills_and_clamps():
    s = S.normalize({"title": {"size": 99999, "color": "red", "text": "a\x00b"}, "canvas": {"preset": "1:1"},
                     "bogus": 1, "retro": {"enabled": "true", "pixel": -5}})
    assert s["title"]["size"] == 600
    assert s["title"]["color"] == "#000000"
    assert s["title"]["text"] == "ab"
    assert (s["canvas"]["width"], s["canvas"]["height"]) == (1080, 1080)
    assert "bogus" not in s and s["retro"]["enabled"] is True and s["retro"]["pixel"] == 1


def test_custom_canvas_is_even():
    s = S.normalize({"canvas": {"preset": "custom", "width": 701, "height": 901}})
    assert (s["canvas"]["width"], s["canvas"]["height"]) == (700, 900)


# ------------------------------------------------------------------ layout / render
def test_overlay_is_default_and_media_fills_frame():
    s = S.normalize({})
    lay = R.layout(s)
    assert s["canvas"]["layout"] == "overlay" and lay["box"] == (0, 0, 1080, 1350)
    green = np.zeros((500, 400, 3), np.uint8)
    green[..., 1] = 255
    out = R.compose(s, lay, green)
    assert tuple(out[5, 5]) == (0, 255, 0) and tuple(out[-5, -5]) == (0, 255, 0)  # full bleed, no margins
    title = lay["title"]["rows"][0]
    ink = out[int(title["baseline"]) - 20, int(title["x"]):int(title["x"] + title["width"])]
    assert (ink.sum(axis=1) < 60).any()  # black title drawn over the media


def test_outline_adds_ink_around_text():
    plain = S.normalize({})
    outl = S.normalize({"title": {"outline": 6}, "link": {"outline": 6}})
    a = (R.text_layer(plain, R.layout(plain))[..., 3] > 0).sum()
    b = (R.text_layer(outl, R.layout(outl))[..., 3] > 0).sum()
    assert b > a * 1.3


def test_layout_stacks_title_media_link():
    s = S.normalize({"canvas": {"layout": "stacked"}})
    lay = R.layout(s)
    x0, y0, x1, y1 = lay["box"]
    assert lay["title"]["bottom"] < y0 < y1 < lay["link"]["top"] <= lay["H"]
    for row in lay["title"]["rows"]:
        assert 0 <= row["x"] and row["x"] + row["width"] <= lay["W"]


def test_autofit_shrinks_long_titles():
    s = S.normalize({"title": {"text": "A VERY LONG HEADLINE THAT CANNOT FIT", "size": 300}})
    lay = R.layout(s)
    assert lay["title"]["size"] < 300
    assert max(r["width"] for r in lay["title"]["rows"]) <= lay["W"] - 2 * lay["side"] + 1


def test_text_layer_has_ink_and_link_is_blue():
    s = S.normalize({})
    lay = R.layout(s)
    layer = R.text_layer(s, lay)
    assert layer.shape == (1350, 1080, 4)
    lk = lay["link"]
    band = layer[int(lk["top"]):int(lk["baseline"]) + 10]
    ink = band[band[..., 3] > 200][:, :3]
    assert len(ink) > 100 and np.all(ink[:, 2] > 200) and np.all(ink[:, 0] < 40)


def test_typewriter_reveals_over_time():
    s = S.normalize({"retro": {"enabled": True, "typewriter": True, "cursor": False, "type_delay": 0, "type_speed": 10}})
    lay = R.layout(s)
    ink = [int((R.text_layer(s, lay, t)[..., 3] > 0).sum()) for t in (0.0, 0.5, 1.5, 10.0)]
    assert ink[0] == 0 and ink[0] < ink[1] < ink[2] < ink[3]


def test_retro_pixels_are_blocky():
    s = S.normalize({"retro": {"enabled": True, "pixel": 4}})
    a = R.text_layer(s, R.layout(s))[..., 3][:1348, :1080].reshape(337, 4, 270, 4)
    assert (a > 0).any() and (a == a[:, :1, :, :1]).all()


def test_compose_background_and_media_box():
    s = S.normalize({"canvas": {"background": "#102030", "layout": "stacked"}, "media": {"fit": "contain"},
                     "title": {"visible": False}, "link": {"visible": False}})
    lay = R.layout(s)
    red = np.zeros((100, 100, 3), np.uint8)
    red[..., 0] = 255
    out = R.compose(s, lay, red)
    assert tuple(out[2, 2]) == (16, 32, 48)
    x, y, w, h = R.media_rect(s, lay, 100, 100)
    assert tuple(out[y + h // 2, x + w // 2]) == (255, 0, 0)


def test_ps1_media_fx_quantizes():
    s = S.normalize({"media_fx": {"mode": "ps1", "pixel": 2}})
    grad = np.tile(np.linspace(0, 255, 64, dtype=np.uint8)[None, :, None], (64, 1, 3))
    out = R.media_fx(grad, s)
    assert len(np.unique(out)) <= 32


# ------------------------------------------------------------------ media / export
def test_probe_video_and_image(clip, still):
    v = M.probe(clip)
    assert (v.kind, v.width, v.height, v.has_audio) == ("video", 320, 400, True)
    assert 1.9 < v.duration < 2.2 and v.fps == 12
    i = M.probe(still)
    assert (i.kind, i.width, i.height) == ("image", 400, 300)


def test_frame_at_and_unsupported(clip, tmp_path):
    assert M.frame_at(clip, 1.0).shape == (400, 320, 3)
    bad = tmp_path / "x.txt"
    bad.write_text("nope")
    with pytest.raises(M.MediaError):
        M.probe(bad)


def test_export_mp4_with_audio_and_trim(clip, tmp_path):
    s = S.normalize({"media": {"trim_start": 0.5, "trim_duration": 1.0}, "export": {"quality": "small"},
                     "retro": {"enabled": True, "jitter": True}})
    out = X.export_mp4(s, str(clip), tmp_path / "o.mp4")
    info = M.probe(out)
    assert (info.width, info.height, info.has_audio) == (1080, 1350, True)
    assert 0.9 < info.duration < 1.2


def test_export_image_to_video_and_png(still, tmp_path):
    s = S.normalize({"media": {"image_duration": 1.0}, "export": {"fps": 10, "quality": "small"}})
    info = M.probe(X.export_mp4(s, str(still), tmp_path / "i.mp4"))
    assert info.kind == "video" and abs(info.duration - 1.0) < 0.15
    png = X.export_png(s, str(still), tmp_path / "i.png")
    assert Image.open(png).size == (1080, 1350)


def test_export_cancel(clip, tmp_path):
    ev = threading.Event()
    ev.set()
    with pytest.raises(X.Cancelled):
        X.export_mp4(S.normalize({}), str(clip), tmp_path / "c.mp4", cancel=ev)
    assert not list(tmp_path.glob("c*"))


# ------------------------------------------------------------------ services + http
@pytest.fixture
def server(tmp_path):
    from goosnav_frame.server import Server
    from goosnav_frame.services import App
    app = App(tmp_path / "data", tmp_path / "config", [])
    srv = Server(("127.0.0.1", 0), app, "tok", lan=False)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", app
    srv.shutdown()
    srv.server_close()


def _req(url, method="GET", data=None, headers=None):
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)


def test_http_requires_token_and_same_origin(server):
    base, _ = server
    assert _req(base + "/health/ready")[0] == 200
    assert _req(base + "/api/preview", "POST", b"{}")[0] == 403
    code, _, _ = _req(base + "/api/preview", "POST", b"{}", {"X-Frame-Token": "tok", "Origin": "http://evil.example"})
    assert code == 403
    code, body, hdr = _req(base + "/api/preview", "POST", b"{}", {"X-Frame-Token": "tok"})
    assert code == 200 and hdr["Content-Type"] == "image/png"
    assert Image.open(io.BytesIO(body)).size == (1080, 1350)


def test_http_upload_preview_export_flow(server, clip):
    base, app = server
    H = {"X-Frame-Token": "tok"}
    code, body, _ = _req(base + "/api/upload?name=my%20clip.mp4", "PUT", clip.read_bytes(),
                         dict(H, **{"Content-Type": "application/octet-stream"}))
    assert code == 200
    item = json.loads(body)
    assert item["name"] == "my clip.mp4" and item["info"]["kind"] == "video"
    code, body, _ = _req(base + "/api/preview", "POST",
                         json.dumps({"media_id": item["id"], "t": 1.0}).encode(), H)
    assert code == 200
    code, body, _ = _req(base + "/api/export", "POST",
                         json.dumps({"media_id": item["id"], "settings": {"export": {"quality": "small"}}}).encode(), H)
    job = json.loads(body)
    import time
    for _ in range(200):
        st = json.loads(_req(base + "/api/jobs/" + job["id"])[1])
        if st["state"] in ("done", "failed"):
            break
        time.sleep(0.1)
    assert st["state"] == "done", st
    code, body, hdr = _req(base + "/api/exports/" + st["output"], headers={"Range": "bytes=0-9"})
    assert code == 206 and len(body) == 10


def test_http_rejects_bad_ids_and_traversal(server):
    base, _ = server
    assert _req(base + "/api/media/../../etc/thumb")[0] in (400, 404)
    assert _req(base + "/static/../src/goosnav_frame/start.py")[0] == 404
    assert _req(base + "/api/exports/..%2Fconfig.json")[0] in (400, 404)
    assert _req(base + "/api/exports/config.json")[0] == 400
    code, _, _ = _req(base + "/api/upload?name=evil.sh", "PUT", b"#!/bin/sh", {"X-Frame-Token": "tok"})
    assert code == 415
