"""Browser acceptance: BASE_URL SOURCE_FOLDER OUTPUT_FOLDER SCREENSHOT_DIR.

SOURCE_FOLDER must contain at least one image. Chooser UI is stubbed; folder
inspection, uploads, preview rendering and exports use the real server.
Run with: uv run --no-project --with playwright python app/tests/e2e_workflows.py ...
"""
import json
import re
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

base, source, output, screenshots = sys.argv[1:]
source, output, screenshots = Path(source), Path(output), Path(screenshots)
screenshots.mkdir(parents=True, exist_ok=True)
photo = next(p for p in source.iterdir() if p.suffix.lower() in ('.png', '.jpg'))
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto(base)
    expect(page.locator('h1')).to_contain_text('0.2.0')
    expect(page.locator('#singleMedia')).to_be_visible()
    expect(page.locator('#batchBox')).not_to_be_visible()
    page.set_input_files('#file', str(photo))
    expect(page.locator('#status')).to_contain_text('Uploaded', timeout=30000)
    for look in ('web216', 'crt', 'handheld', 'zine', 'ps1'):
        page.locator('[data-path="media_fx.mode"]').select_option(look)
        page.wait_for_timeout(400)
        page.wait_for_function("() => document.querySelector('#busy').hidden && document.querySelector('#preview').naturalWidth === 1080")
    page.screenshot(path=str(screenshots / 'single.png'))
    page.locator('#exportBtn').click()
    expect(page.locator('#status')).to_contain_text('Exported', timeout=30000)
    expect(page.locator('#exports a[download]').first).to_have_attribute('download', re.compile(r'.*\.png'))
    with page.expect_download() as download:
        page.locator('#exports a[download]').first.click()
    download.value.save_as(str(screenshots / 'export.png'))
    page.locator('#folderMode').click()
    expect(page.locator('#batchBox')).to_be_visible()
    expect(page.locator('#singleExport')).not_to_be_visible()
    page.route('**/api/choose-path', lambda route: route.fulfill(json={'path': str(source)}))
    page.locator('#chooseFolder').click()
    expect(page.locator('#folderSummary')).to_contain_text('Preview:', timeout=30000)
    page.unroute('**/api/choose-path')
    page.locator('#batchOutput').fill(str(output))
    page.locator('#captionMode').select_option('random')
    page.locator('#batchBtn').click()
    expect(page.locator('#batchStatus')).to_contain_text('done:', timeout=60000)
    assert list(output.glob('*.png'))
    if any(p.suffix == '.mp4' for p in source.iterdir()):
        assert list(output.glob('*.mp4'))
    page.screenshot(path=str(screenshots / 'batch.png'))
    page.set_viewport_size({'width': 900, 'height': 760})
    page.screenshot(path=str(screenshots / 'laptop.png'))
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    assert not errors, errors
    browser.close()
print('PASS: workflow modes, five looks, PNG download, folder selection, mixed batch, laptop width; no JavaScript errors')
