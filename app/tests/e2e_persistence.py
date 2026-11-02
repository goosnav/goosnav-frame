"""Real restart + fresh browser context verifies app-backed settings continuity.

uv run --no-project --with playwright python app/tests/e2e_persistence.py
"""
import json
import os
import subprocess
import tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

app_root = Path(__file__).resolve().parents[1]
python = app_root / ('.venv/Scripts/python.exe' if os.name == 'nt' else '.venv/bin/python')
code = """
import sys
from pathlib import Path
from goosnav_frame.server import Server
from goosnav_frame.services import App
base=Path(sys.argv[1])
server=Server(('127.0.0.1',0),App(base/'data',base/'config',[]),'test',False)
print(server.server_address[1],flush=True)
server.serve_forever()
"""

def start(folder):
    env = dict(os.environ, PYTHONPATH=str(app_root / 'src'))
    proc = subprocess.Popen([str(python), '-u', '-c', code, folder], env=env, stdout=subprocess.PIPE, text=True)
    return proc, 'http://127.0.0.1:' + proc.stdout.readline().strip()

with tempfile.TemporaryDirectory(prefix='frame-settings-') as folder, sync_playwright() as p:
    proc, base = start(folder)
    browser = p.chromium.launch()
    try:
        context = browser.new_context()
        page = context.new_page()
        legacy = {'settings': {'title': {'text': 'My saved title'}, 'media_fx': {'mode': 'zine'}}, 'imageDefaults': True}
        page.add_init_script('localStorage.setItem("goosnav-frame/v2", ' + json.dumps(json.dumps(legacy)) + ')')
        page.goto(base)
        expect(page.locator('[data-path="title.text"]')).to_have_value('My saved title')
        expect(page.locator('[data-path="media_fx.mode"]')).to_have_value('zine')
        page.locator('[data-path="media_fx.mode"]').select_option('web216')
        page.locator('[data-path="media_fx.strength"][type="number"]').fill('49')
        page.locator('[data-path="media.border_random"]').check()
        page.locator('#folderMode').click()
        page.locator('#batchOutput').fill(folder + '/my ads')
        page.locator('#captionMode').select_option('random')
        import time, urllib.request
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            state = json.load(urllib.request.urlopen(base + '/api/state')).get('workspace') or {}
            if (state.get('settings', {}).get('media_fx', {}).get('strength') == 49
                    and state.get('batch', {}).get('batchOutput') == folder + '/my ads'):
                break
            page.wait_for_timeout(100)
        else:
            raise AssertionError('Settings were not saved: ' + str(state) + '; UI: ' + page.locator('#status').inner_text())
        context.close()
        proc.terminate(); proc.wait(timeout=10)
        proc, new_base = start(folder)

        # No cookies or browser storage survive into this new context or new server port.
        fresh = browser.new_context()
        page = fresh.new_page()
        page.goto(new_base)
        expect(page.locator('[data-path="title.text"]')).to_have_value('My saved title')
        expect(page.locator('[data-path="media_fx.mode"]')).to_have_value('web216')
        expect(page.locator('[data-path="media_fx.strength"][type="number"]')).to_have_value('49')
        expect(page.locator('[data-path="media.border_random"]')).to_be_checked()
        expect(page.locator('#folderMode')).to_have_attribute('aria-pressed', 'true')
        expect(page.locator('#batchOutput')).to_have_value(folder + '/my ads')
        expect(page.locator('#captionMode')).to_have_value('random')
        fresh.close()
    finally:
        browser.close()
        proc.terminate(); proc.wait(timeout=10)
print('PASS: legacy migration, app restart, new port, fresh browser; settings and output folder preserved')
