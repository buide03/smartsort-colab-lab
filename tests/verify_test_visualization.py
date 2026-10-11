"""Exercise test-result visualization on a completed, real-model session."""
import json
import os
from pathlib import Path


def verify_gallery(page, state):
    predictions = state['results']['predictions']
    page.wait_for_selector('#testVisualization')
    assert page.locator('.test-image-card').count() == min(12, len(predictions))
    assert page.locator('.test-class-stat').count() == 3
    if len(predictions) > 12:
        first = page.locator('.test-image-button').first.get_attribute('data-test-result')
        page.click('#testNext')
        assert page.locator('.test-image-button').first.get_attribute('data-test-result') != first
        page.click('#testPrev')
    for material in ['metal', 'paper', 'plastic']:
        page.select_option('#testMaterial', material)
        rows = [p for p in predictions if p['true_label'] == material]
        assert page.locator('.test-image-card').count() == min(12, len(rows))
        for label in page.locator('.test-labels').all_text_contents():
            assert {'metal':'Kim loại', 'paper':'Giấy', 'plastic':'Nhựa'}[material] in label
    page.select_option('#testMaterial', 'all')
    for outcome in ['correct', 'wrong']:
        page.select_option('#testOutcome', outcome)
        rows = [p for p in predictions if p['correct'] == (outcome == 'correct')]
        assert page.locator('.test-image-card').count() == min(12, len(rows))
        if not rows:
            assert page.locator('#testVisualization .empty').count() == 1
    page.select_option('#testOutcome', 'all')
    page.select_option('#testSort', 'uncertain')
    expected = min(predictions, key=lambda p:p['confidence'])
    assert page.locator('.test-image-button').first.get_attribute('data-test-result') == expected['id']
    page.locator('.test-image-button').first.click()
    assert page.locator('#imageDialog').is_visible()
    assert page.locator('#largeTestResult meter').count() == 3
    page.wait_for_function('document.querySelector("#largeImage").complete && document.querySelector("#largeImage").naturalWidth > 0')
    page.locator('#imageDialog .dialog-close').click()
    page.fill('#testSearch', expected['filename'])
    expected_matches = [p for p in predictions if expected['filename'].lower() in p['filename'].lower()]
    assert page.locator('.test-image-card').count() == min(12, len(expected_matches))
    page.fill('#testSearch', 'no-such-image-817241')
    assert page.locator('.test-image-card').count() == 0
    page.fill('#testSearch', '')
    # Filters only read stored predictions; they never call the inference endpoint.
    current = page.evaluate('''async id => (await (await BrowserLab.fetch('/api/sessions/'+id)).json()).results''', state['id'])
    assert current == state['results']
    page.set_viewport_size({'width':390, 'height':844})
    assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
    page.set_viewport_size({'width':1440, 'height':1000})


if __name__ == '__main__':
    from playwright.sync_api import sync_playwright
    root = Path(__file__).resolve().parents[1]
    with sync_playwright() as playwright:
        options = {'headless': True}
        if os.name == 'nt':
            options['executable_path'] = r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
        browser = playwright.chromium.launch(**options)
        page = browser.new_page(viewport={'width':1440,'height':1000})
        errors = []
        page.on('pageerror', lambda error:errors.append(str(error)))
        page.goto('http://127.0.0.1:8001', wait_until='networkidle')
        page.wait_for_selector('#uploadInput', state='attached')
        page.set_input_files('#restoreInput', str(root/'tests/runtime/static_backup.zip'))
        page.wait_for_selector('#testVisualization', timeout=60000)
        sid = page.locator('#sessionPicker').input_value()
        state = page.evaluate('''async id => (await (await BrowserLab.fetch('/api/sessions/'+id)).json())''', sid)
        verify_gallery(page, state)
        assert not errors, errors
        page.locator('#testVisualization').screenshot(path=str(root/'tests/runtime/test-visualization.png'))
        print('PASS visualization:', json.dumps({'n':len(state['results']['predictions']), 'js_errors':errors}))
        browser.close()
