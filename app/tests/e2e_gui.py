"""Real-browser workflow check (not part of the unit suite).

    uv run --no-project --with playwright python tests/e2e_gui.py BASE_URL LAN_URL MEDIA OUTDIR
"""
import sys
import time
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

base, lan, media, out = sys.argv[1], sys.argv[2], sys.argv[3], Path(sys.argv[4])
out.mkdir(parents=True, exist_ok=True)
errors = []


def wait_preview(page, timeout=20000):
    page.wait_for_function("() => { const i = document.getElementById('preview'); return i.complete && i.naturalWidth > 0; }",
                           timeout=timeout)
    page.wait_for_function("() => document.getElementById('busy').hidden", timeout=timeout)


with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page(viewport={"width": 1440, "height": 900})
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(base)
    wait_preview(page)
    assert page.evaluate("document.getElementById('preview').naturalWidth") == 1080
    expect(page.locator("#quit")).to_be_visible()
    page.screenshot(path=out / "1_start.png")

    # upload
    page.set_input_files("#file", media)
    expect(page.locator("#status")).to_contain_text("Uploaded", timeout=60000)
    expect(page.locator(".tile.on")).to_have_count(1)
    wait_preview(page)

    # edit title
    page.locator('textarea[data-path="title.text"]').fill("Your problem...\nbundled")
    time.sleep(0.4)
    wait_preview(page)
    page.screenshot(path=out / "2_uploaded_title.png")

    # retro text
    page.locator("summary", has_text="Retro text").click()
    page.locator('input[type=checkbox][data-path="retro.enabled"]').check()
    page.locator('input[type=number][data-path="retro.rgb_split"]').fill("3")
    page.locator('input[type=number][data-path="retro.rgb_split"]').dispatch_event("change")
    page.locator('input[type=checkbox][data-path="retro.shadow"]').check()
    page.locator('input[type=checkbox][data-path="retro.typewriter"]').check()
    page.locator('#time').fill("1.2")
    page.locator('#time').dispatch_event("input")
    time.sleep(0.4)
    wait_preview(page)
    page.screenshot(path=out / "3_retro.png")

    # quick preview video
    page.click("#quick")
    page.wait_for_function("() => { const v = document.getElementById('pvideo'); return !v.hidden && v.readyState >= 2; }",
                           timeout=120000)
    page.screenshot(path=out / "4_preview_video.png")
    page.click("#backToFrame")

    # export
    n0 = page.locator("#exports li a", has_text="Download").count()
    page.click("#exportBtn")
    expect(page.locator("#status")).to_contain_text("Exported", timeout=300000)
    assert page.locator("#exports li a", has_text="Download").count() == n0 + 1
    href = page.locator("#exports li a", has_text="Download").first.get_attribute("href")
    r = page.request.get(base + href)
    assert r.status == 200 and r.headers["content-type"] == "video/mp4", r.status
    (out / "export.mp4").write_bytes(r.body())
    r = page.request.get(base + href + "?inline=1", headers={"Range": "bytes=0-99"})
    assert r.status == 206 and len(r.body()) == 100

    # settings survive a reload
    page.reload()
    wait_preview(page)
    assert "Your problem" in page.locator('textarea[data-path="title.text"]').input_value()

    # phone over the LAN address
    phone = b.new_page(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    phone.on("pageerror", lambda e: errors.append(str(e)))
    phone.goto(lan)
    wait_preview(phone)
    expect(phone.locator("#quit")).to_be_hidden()
    expect(phone.locator("#libraryBox")).to_be_hidden()
    phone.screenshot(path=out / "5_phone.png", full_page=False)
    # host-only action refused from the LAN
    tok = phone.evaluate("document.querySelector('meta[name=frame-token]').content")
    r = phone.request.post(lan + "/api/quit", headers={"X-Frame-Token": tok}, data="{}")
    assert r.status == 403, r.status
    b.close()

print("console errors:", errors)
assert not errors
print("E2E OK")
