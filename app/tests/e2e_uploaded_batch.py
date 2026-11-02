"""BASE_URL SOURCE_FOLDER SCREENSHOT: verify multi-file batch with host features hidden."""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

base, folder, screenshot = sys.argv[1:]
files = [str(p) for p in Path(folder).iterdir() if p.suffix in ('.png', '.mp4')]
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={'width': 1200, 'height': 900})
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto(base)
    expect(page.locator('#folderMode')).to_be_visible()
    assert page.locator('summary').filter(has_text='1.').count() == 0
    page.locator('#folderMode').click()
    page.set_input_files('#batchFiles', files)
    expect(page.locator('#batchSelection li')).to_have_count(len(files), timeout=60000)
    expect(page.locator('#batchBtn')).to_be_enabled()
    page.locator('#batchBtn').click()
    expect(page.locator('#batchStatus')).to_have_text(f'{len(files)} / {len(files)} exported', timeout=60000)
    expect(page.locator('#batchSavedTo')).to_contain_text('Saved to')
    assert page.locator('#batchResults a').count() == 0
    destination = Path(page.locator('#batchSavedTo').inner_text().removeprefix('Saved to '))
    assert len(list(destination.glob('*.png'))) + len(list(destination.glob('*.mp4'))) == len(files)
    page.reload()
    page.locator('#folderMode').click()
    expect(page.locator('#batchSelection li')).to_have_count(len(files))
    page.screenshot(path=screenshot)
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    expect(page.locator('#folderMode')).to_be_visible()
    assert not errors, errors
    browser.close()
print('PASS: multiple uploads, automatic mixed-file save, reload, mobile width')
