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
def test_overlay_remains_available_and_media_fills_frame():
    s = S.normalize({"canvas": {"layout": "overlay"}, "media": {"fit": "cover", "border": 0}})
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


def wait_job(job):
    import time
    deadline = time.monotonic() + 60
    while job.state not in ("done", "failed", "cancelled") and time.monotonic() < deadline:
        time.sleep(0.05)
    assert job.state in ("done", "failed", "cancelled"), job.public()
    return job


def test_photo_defaults_center_between_text_and_wrap():
    s = S.normalize({"title": {"text": "ALL OF THIS CAN BE YOURS"}})
    lay = R.layout(s)
    assert len(lay["title"]["rows"]) > 1
    x, y, w, h = R.media_rect(s, lay, 1000, 1000)
    assert w == h and abs(x - (1080-w)/2) <= 0.5
    assert lay["title"]["bottom"] < y < y+h < lay["link"]["top"]
    assert x > 0
    for row in lay["title"]["rows"]:
        assert row["width"] <= 1080 - 2 * lay["side"]


def test_single_photo_auto_exports_png_http(server, still):
    base, app = server
    code, body, _ = _req(base + "/api/upload?name=photo.png", "PUT", still.read_bytes(), {"X-Frame-Token": "tok"})
    mid = json.loads(body)["id"]
    code, body, _ = _req(base + "/api/export", "POST", json.dumps({"media_id": mid,
        "settings": {"title": {"text": "Hello / world!"}}}).encode(), {"X-Frame-Token": "tok"})
    job = wait_job(app.job(json.loads(body)["id"]))
    assert job.state == "done", job.error
    assert job.output.startswith("Hello-world_") and job.output.endswith(".png")
    code, body, headers = _req(base + "/api/exports/" + job.output)
    assert code == 200 and headers["Content-Type"] == "image/png"
    assert Image.open(io.BytesIO(body)).size == (1080, 1350)


def test_mixed_batch_random_and_custom_destination(server, still, clip, tmp_path):
    import shutil
    base, app = server
    source = tmp_path / "source"
    source.mkdir()
    shutil.copy(still, source / "one.png")
    shutil.copy(still, source / "two.png")
    shutil.copy(clip, source / "clip.mp4")
    captions = tmp_path / "captions.txt"
    captions.write_text("\ufeffHello world\n\nAnother caption\n", encoding="utf-8")
    dest = tmp_path / "output"
    job = wait_job(app.start_batch({"media": {"trim_duration": 0.2}}, str(source), str(dest), "random", str(captions)))
    assert job.state == "done", job.public()
    assert len(job.results) == 3
    outputs = [Path(r["output"]) for r in job.results]
    assert len(set(outputs)) == 3 and all(p.is_file() and p.parent == dest for p in outputs)
    assert sorted(p.suffix for p in outputs) == [".mp4", ".png", ".png"]
    assert all(r["caption"] in ("Hello world", "Another caption") for r in job.results)
    assert M.probe(next(p for p in outputs if p.suffix == ".mp4")).has_audio


def test_batch_default_folder_failures_and_repeat(server, still, tmp_path):
    import shutil
    _, app = server
    source = tmp_path / "source"
    source.mkdir()
    shutil.copy(still, source / "one.png")
    (source / "bad.png").write_text("invalid image")
    for _ in range(2):
        job = wait_job(app.start_batch({"title": {"text": "Same caption"}}, str(source)))
        assert job.state == "failed" and job.total == 2
        assert sum(bool(r["output"]) for r in job.results) == 1
        assert all(r["caption"] == "Same caption" for r in job.results)
    assert len(list((source / "Goosnav Exports").glob("*.png"))) == 2


def test_batch_validates_captions_and_can_cancel(server, still, tmp_path):
    import shutil
    from goosnav_frame.services import ServiceError
    _, app = server
    source = tmp_path / "source"
    source.mkdir()
    shutil.copy(still, source / "one.png")
    empty = tmp_path / "empty.txt"
    empty.write_text(" \n")
    with pytest.raises(ServiceError):
        app.start_batch({}, str(source), caption_mode="random", caption_file=str(empty))
    with app.queue_lock:
        job = app.start_batch({}, str(source))
        job.cancel.set()
    assert wait_job(job).state == "cancelled"
    assert not list((source / "Goosnav Exports").glob("*.png"))


def test_optional_random_border_matches_preview_and_export(server, still):
    from goosnav_frame.services import PRIMARY_COLORS
    _, app = server
    item = app.save_upload('test.png', io.BytesIO(still.read_bytes()), still.stat().st_size)
    settings = {"media": {"border_enabled": True, "border_random": True, "border": 20}}
    preview = np.asarray(Image.open(io.BytesIO(app.preview_png(settings, item['id'], 0))))
    job = wait_job(app.start_export(settings, item['id']))
    exported = np.asarray(Image.open(app.export_path(job.output)))
    assert np.array_equal(preview, exported)
    s = app._border_settings(S.normalize(settings), item['id'])
    assert s['media']['border_color'] in PRIMARY_COLORS
    x, y, w, h = R.media_rect(s, R.layout(s), 400, 300)
    assert tuple(exported[y-10, x+w//2]) == S.hex_rgb(s['media']['border_color'])
    without = S.normalize({})
    assert not without['media']['border_enabled']


def test_batch_random_border_uses_primary_palette(server, still, tmp_path):
    import shutil
    from goosnav_frame.services import PRIMARY_COLORS
    _, app = server
    source = tmp_path / 'source'
    source.mkdir()
    for i in range(3):
        shutil.copy(still, source / f'{i}.png')
    job = wait_job(app.start_batch({'media': {'border_enabled': True, 'border_random': True}}, str(source)))
    assert job.state == 'done'
    assert all(r['border_color'] in PRIMARY_COLORS for r in job.results)


@pytest.mark.parametrize('color', ['red', 'blue', 'yellow', '#009b24', '#ae31bd'])
@pytest.mark.parametrize('padding', [0, 40, 90])
def test_detects_colored_frames_with_white_padding(color, padding):
    from PIL import ImageDraw
    from goosnav_frame.core.borders import has_colored_frame
    image = Image.new('RGB', (500, 500), 'white')
    draw = ImageDraw.Draw(image)
    draw.rectangle((padding, padding, 499-padding, 499-padding), outline=color, width=12)
    draw.ellipse((180, 180, 320, 320), fill='black')
    assert has_colored_frame(np.asarray(image))


def test_border_detector_rejects_corners_and_solid_images():
    from PIL import ImageDraw
    from goosnav_frame.core.borders import has_colored_frame
    assert not has_colored_frame(np.full((400, 400, 3), (255, 0, 0), dtype=np.uint8))
    image = Image.new('RGB', (400, 400), 'white')
    draw = ImageDraw.Draw(image)
    for x, y in [(0,0), (350,0), (0,350), (350,350)]:
        draw.rectangle((x,y,x+49,y+49), fill='blue')
    assert not has_colored_frame(np.asarray(image))


def test_auto_skip_can_be_overridden(tmp_path):
    from PIL import ImageDraw
    image = Image.new('RGB', (400,400), 'white')
    ImageDraw.Draw(image).rectangle((30,30,370,370), outline='green', width=12)
    path = tmp_path / 'framed.png'
    image.save(path)
    plain = X.render_still(S.normalize({}), str(path), 0)
    skip = X.render_still(S.normalize({'media': {'border_enabled': True}}), str(path), 0)
    forced = X.render_still(S.normalize({'media': {'border_enabled': True, 'border_auto_skip': False}}), str(path), 0)
    assert np.array_equal(plain, skip)
    assert not np.array_equal(skip, forced)


@pytest.mark.parametrize('mode', ['ps1', 'web216', 'crt', 'handheld', 'zine', 'pixelate', 'posterize'])
def test_retro_looks_are_deterministic_and_preserve_dimensions(mode):
    rng = np.random.default_rng(18)
    photo = rng.integers(0, 256, (123, 157, 3), dtype=np.uint8)
    settings = S.normalize({'media_fx': {'mode': mode, 'pixel': 3}})
    result = R.media_fx(photo, settings)
    assert result.shape == photo.shape and result.dtype == np.uint8
    assert np.array_equal(result, R.media_fx(photo, settings))
    assert not np.array_equal(photo, result)
    settings['media_fx']['strength'] = 0
    assert np.array_equal(photo, R.media_fx(photo, settings))
    if mode in ('handheld', 'zine'):
        assert len(np.unique(result.reshape(-1, 3), axis=0)) <= 4
    if mode == 'web216':
        assert len(np.unique(result.reshape(-1, 3), axis=0)) <= 216


def test_folder_inspection_registers_preview_and_ignores_exports(server, still, tmp_path):
    import shutil
    base, app = server
    folder = tmp_path / 'folder'
    folder.mkdir()
    shutil.copy(still, folder / 'first.png')
    exports = folder / 'Goosnav Exports'
    exports.mkdir()
    shutil.copy(still, exports / 'prior.png')
    code, body, _ = _req(base + '/api/folder', 'POST', json.dumps({'folder': str(folder)}).encode(), {'X-Frame-Token': 'tok'})
    data = json.loads(body)
    assert code == 200 and data['count'] == data['images'] == 1
    assert data['sample']['name'] == 'first.png'
    assert app.resolve(data['sample']['id']) == folder / 'first.png'
    assert any(i['id'] == data['sample']['id'] for i in app.list_media())


def test_launcher_only_reuses_current_build(server, monkeypatch):
    from goosnav_frame.start import _already_running
    from goosnav_frame import BUILD_ID, APP_ID
    base, app = server
    assert _already_running(int(base.rsplit(':', 1)[1]))
    def old(*args, **kwargs):
        return io.BytesIO(json.dumps({'ok': True, 'version': '0.1.0'}).encode())
    monkeypatch.setattr('urllib.request.urlopen', old)
    assert not _already_running(8787)


def test_manual_title_breaks_do_not_create_orphan_words():
    settings = S.normalize({})
    rows = R.layout(settings)['title']['rows']
    assert [r['text'] for r in rows] == ['TWEAKING OFF THE', 'GOOSNAV PACK']
