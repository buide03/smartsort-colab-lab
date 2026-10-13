"""Browser privacy regression. Start run_browser_lab.py --port 8017 first."""
import io
import os
import zipfile
from PIL import Image, PngImagePlugin
from playwright.sync_api import sync_playwright


def fixture():
    buffer = io.BytesIO()
    image = Image.new('RGB', (200, 100), 'white')
    image.paste('red', (20, 20, 80, 60))
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text('Description', 'PRIVATE_NAME_PHONE_0901234567')
    image.save(buffer, 'PNG', pnginfo=metadata)
    return buffer.getvalue()


with sync_playwright() as playwright:
    options = {'headless': True}
    if os.name == 'nt':
        options['executable_path'] = r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
    browser = playwright.chromium.launch(**options)
    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(os.environ.get('SMARTSORT_PRIVACY_URL', 'http://127.0.0.1:8017'))
    page.wait_for_selector('#uploadInput', state='attached')
    page.evaluate('''() => {
      window.imageWrites = 0;
      const original = BrowserLab.fetch;
      BrowserLab.fetch = (...args) => {
        if (args[0].endsWith('/images') && args[1]?.method === 'POST') {
          imageWrites++;
          window.safeUpload = args[1].body.get('files');
        }
        return original(...args);
      };
    }''')
    payload = {'name': 'Nguyen_Van_A_phone_0901234567.png', 'mimeType': 'image/png', 'buffer': fixture()}
    page.set_input_files('#uploadInput', payload)
    page.wait_for_selector('.privacy-dialog[open]')
    assert page.locator('[data-accept]').is_disabled()
    assert page.evaluate('imageWrites') == 0
    assert page.evaluate('session.images.length') == 0
    canvas = page.locator('.privacy-dialog canvas').bounding_box()
    page.mouse.move(canvas['x'] + canvas['width'] * .09, canvas['y'] + canvas['height'] * .19)
    page.mouse.down()
    page.mouse.move(canvas['x'] + canvas['width'] * .41, canvas['y'] + canvas['height'] * .61)
    page.mouse.up()
    page.locator('[data-review]').check()
    # A mask edit invalidates the prior confirmation.
    page.locator('[data-undo]').click()
    assert page.locator('[data-accept]').is_disabled()
    page.mouse.move(canvas['x'] + canvas['width'] * .09, canvas['y'] + canvas['height'] * .19)
    page.mouse.down()
    page.mouse.move(canvas['x'] + canvas['width'] * .41, canvas['y'] + canvas['height'] * .61)
    page.mouse.up()
    page.locator('[data-review]').check()
    assert page.locator('[data-accept]').is_disabled()
    page.locator('[data-review-label]').select_option('metal')
    page.locator('[data-accept]').click()
    page.wait_for_function('session.images.length === 1')
    assert page.evaluate('imageWrites') == 1
    assert not page.evaluate('async () => (await safeUpload.text()).includes("PRIVATE_NAME_PHONE")')
    record = page.evaluate('session.images[0]')
    assert record['label'] == 'metal'
    assert page.evaluate('session.unlabeled') == 0
    page.wait_for_selector('#splitAction')
    assert page.evaluate('page') == 2
    assert page.locator('.privacy-dialog').count() == 0
    page.evaluate('go(1)')
    assert not page.locator('details.card').evaluate('(node) => node.open')
    assert record['filename'].startswith('image_') and 'Nguyen' not in record['filename']
    pixels = page.evaluate('''async () => {
      const blob = await (await fetch(BrowserLab.imageURL(session.id, session.images[0].id))).blob();
      const image = await createImageBitmap(blob), c = document.createElement('canvas');
      c.width=image.width;c.height=image.height;const ctx=c.getContext('2d');ctx.drawImage(image,0,0);
      return [Array.from(ctx.getImageData(40,40,1,1).data),Array.from(ctx.getImageData(150,80,1,1).data)];
    }''')
    assert pixels == [[0, 0, 0, 255], [255, 255, 255, 255]], pixels
    # Cancelling an entire batch must discard previously approved images, too.
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr('private/a.png', fixture())
        archive.writestr('private/b.png', fixture())
    page.set_input_files('#uploadInput', {'name':'private.zip','mimeType':'application/zip','buffer':buffer.getvalue()})
    page.wait_for_selector('.privacy-dialog[open]')
    page.locator('[data-review]').check()
    page.locator('[data-review-label]').select_option('paper')
    page.locator('[data-accept]').click()
    page.wait_for_function('document.querySelector(".privacy-dialog")?.textContent.includes("Ảnh 2 / 2")')
    page.locator('[data-cancel]').click()
    page.wait_for_selector('.privacy-dialog', state='detached')
    assert page.evaluate('imageWrites') == 1
    assert page.evaluate('session.images.length') == 1
    page.reload()
    page.wait_for_selector('#splitAction')
    assert page.evaluate('session.images[0].label') == 'metal'
    page.evaluate('go(1)')
    page.locator('#labelReview summary').click()
    page.locator('[data-select]').first.check()
    assert page.locator('#labelReview').evaluate('(node) => node.open')
    page.locator('#batchLabel').select_option('metal')
    page.locator('#applyBatch').click()
    page.wait_for_function('selected.size === 0')
    assert page.locator('#labelReview').evaluate('(node) => node.open')
    # Save enough labeled images in the initial review, then split without relabeling.
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        for i in range(30):
            image = Image.new('RGB', (40, 40), (i + 1, 100, 200))
            encoded = io.BytesIO()
            image.save(encoded, 'PNG')
            archive.writestr(f'{i}.png', encoded.getvalue())
    page.set_input_files('#uploadInput', {'name':'batch.zip','mimeType':'application/zip','buffer':buffer.getvalue()})
    for i in range(30):
        page.wait_for_function(f'document.querySelector(".privacy-dialog")?.textContent.includes("Ảnh {i + 1} / 30.")')
        page.locator('[data-review-label]').select_option(['metal', 'paper', 'plastic'][i // 10])
        page.locator('[data-review]').check()
        page.locator('[data-accept]').click()
    page.wait_for_selector('#splitAction')
    assert page.evaluate('session.unlabeled') == 0
    labels_before = page.evaluate('session.images.map(row => [row.id, row.label])')
    page.locator('#splitAction').click()
    page.wait_for_function('session.splits !== null')
    assert page.evaluate('session.images.map(row => [row.id, row.label])') == labels_before
    partitions = page.evaluate('session.splits.ids')
    assert set(partitions) == {'train', 'validation', 'test'}
    assigned = [image_id for ids in partitions.values() for image_id in ids]
    assert len(assigned) == len(set(assigned)) == 31
    assert page.locator('.privacy-dialog').count() == 0
    # Test the existing prediction handler without loading/training a model.
    page.evaluate('''() => {
      document.querySelector('#content').innerHTML = '<input id="predictInput" type="file"><button id="choosePredict">Chọn</button><div id="predictResult"></div>';
      bindPage(); window.predictCalls = 0;
      const original = BrowserLab.fetch;
      BrowserLab.fetch = async (...args) => {
        if (args[0].endsWith('/predict')) {
          predictCalls++; window.predictionFilename=args[1].body.get('file').name;
          return new Response(JSON.stringify({decision:'Giấy',name:'Giấy',confidence:.9,probabilities:{paper:.9,metal:.05,plastic:.05}}));
        }
        return original(...args);
      };
    }''')
    page.set_input_files('#predictInput', payload)
    page.wait_for_selector('.privacy-dialog[open]')
    assert page.locator('[data-review-label]').count() == 0
    assert page.evaluate('predictCalls') == 0
    page.locator('[data-cancel]').click()
    page.wait_for_selector('.privacy-dialog', state='detached')
    assert page.evaluate('predictCalls') == 0
    page.set_input_files('#predictInput', payload)
    page.wait_for_selector('.privacy-dialog[open]')
    page.locator('[data-review]').check()
    page.locator('[data-accept]').click()
    page.wait_for_selector('.predict-preview')
    assert page.evaluate('predictCalls') == 1
    assert page.evaluate('predictionFilename').startswith('image_')
    assert not errors, errors
    browser.close()
print('PASS: masks, saved labels, direct split navigation, reload, three disjoint splits, ZIP cancellation, prediction gates')
