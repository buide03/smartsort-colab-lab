"""Manual privacy review, no image/text uploads, and sanitized Colab ZIP."""
import io
import os
from urllib.parse import urlparse

from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright


def text_fixture():
    image = Image.new('RGB', (900, 300), 'white')
    font_path = r'C:\Windows\Fonts\arial.ttf' if os.name == 'nt' else '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(font_path, 38)
    draw.text((30, 30), 'Ho ten: Nguyen Van A', font=font, fill='black')
    draw.text((30, 100), 'Dien thoai: 0901234567', font=font, fill='black')
    draw.text((30, 170), 'Dia chi: 12 Duong A', font=font, fill='black')
    buffer = io.BytesIO()
    image.save(buffer, 'PNG')
    return buffer.getvalue()


with sync_playwright() as playwright:
    options = {'headless': True}
    if os.name == 'nt':
        options['executable_path'] = r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
    browser = playwright.chromium.launch(**options)
    context = browser.new_context(viewport={'width':1440, 'height':1000})
    page = context.new_page()
    origin = os.environ.get('SMARTSORT_PRIVACY_URL', 'http://127.0.0.1:8017')
    requests, forbidden, errors = [], [], []

    def guard(route):
        request = route.request
        requests.append((request.method, request.url, request.post_data_buffer))
        if urlparse(request.url).netloc != urlparse(origin).netloc or request.method != 'GET' or request.post_data_buffer:
            forbidden.append(request.url)
            route.abort()
        else:
            route.continue_()

    context.route('**/*', guard)
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(origin)
    page.wait_for_selector('#uploadInput', state='attached')
    page.set_input_files('#uploadInput', {'name':'sensitive_name.png','mimeType':'image/png','buffer':text_fixture()})
    page.wait_for_selector('.privacy-dialog[open]')
    assert page.locator('[data-review]').is_enabled()
    assert page.locator('[data-accept]').is_disabled()
    assert page.locator('[data-scan-status]').count() == 0
    assert page.evaluate('typeof PrivacyScanner') == 'undefined'
    assert page.evaluate('session.images.length') == 0
    canvas = page.locator('.privacy-dialog canvas').bounding_box()

    def mask_text():
        page.mouse.move(canvas['x'] + canvas['width'] * 20/900, canvas['y'] + canvas['height'] * 20/300)
        page.mouse.down()
        page.mouse.move(canvas['x'] + canvas['width'] * 700/900, canvas['y'] + canvas['height'] * 240/300)
        page.mouse.up()

    mask_text()
    page.locator('[data-review]').check()
    page.locator('[data-undo]').click()
    assert page.locator('[data-accept]').is_disabled()
    mask_text()
    page.locator('[data-review]').check()
    # Bypass BrowserLab upload only to inspect the actual human-approved sanitized File.
    page.evaluate('''() => {
      const original = BrowserLab.fetch;
      window.actualLabFetch = original;
      BrowserLab.fetch = async (...args) => {
        if (args[0].endsWith('/images') && args[1]?.method === 'POST') {
          window.reviewedFile = args[1].body.get('files');
          return new Response(JSON.stringify({session,added:0,duplicates:0,rejected:[]}));
        }
        return original(...args);
      };
    }''')
    page.locator('[data-accept]').click()
    page.wait_for_function('window.reviewedFile !== undefined')
    covered = page.evaluate('''async () => {
      const bitmap=await createImageBitmap(reviewedFile),c=document.createElement('canvas');
      c.width=bitmap.width;c.height=bitmap.height;const ctx=c.getContext('2d');ctx.drawImage(bitmap,0,0);
      return [Array.from(ctx.getImageData(45,115,1,1).data),Array.from(ctx.getImageData(850,280,1,1).data)];
    }''')
    assert covered == [[0,0,0,255],[255,255,255,255]], covered
    assert not forbidden, forbidden
    assert not errors, errors
    assert not any('sensitive_name' in url or '0901234567' in url for _,url,_ in requests)
    # Build the existing train-only Colab package from sanitized pixel fixtures.
    # Different corner pixels make independent storage fixtures, not a training dataset.
    exported = page.evaluate('''async () => {
      BrowserLab.fetch = actualLabFetch;
      const created=await (await BrowserLab.fetch('/api/sessions',{method:'POST',body:JSON.stringify({title:'Privacy export fixture'})})).json();
      const base='/api/sessions/'+created.id, form=new FormData();
      const bitmap=await createImageBitmap(reviewedFile),canvas=document.createElement('canvas');
      canvas.width=bitmap.width;canvas.height=bitmap.height;const ctx=canvas.getContext('2d');
      for(let i=0;i<30;i++){
        ctx.drawImage(bitmap,0,0);ctx.fillStyle=`rgb(${i},0,0)`;ctx.fillRect(890,290,1,1);
        form.append('files',new File([await new Promise(done=>canvas.toBlob(done,'image/png'))],`image_fixture_${i}.png`,{type:'image/png'}));
      }
      const added=await (await BrowserLab.fetch(base+'/images',{method:'POST',body:form})).json();
      if(added.added!==30)throw new Error(JSON.stringify(added));
      for(const [index,label] of ['metal','paper','plastic'].entries())await BrowserLab.fetch(base+'/labels',{
        method:'PUT',body:JSON.stringify({ids:added.session.images.slice(index*10,index*10+10).map(r=>r.id),label})});
      await BrowserLab.fetch(base+'/split',{method:'POST',body:JSON.stringify({train:.7,validation:.15,test:.15,seed:42})});
      const response=await BrowserLab.fetch(base+'/colab/export',{method:'POST',body:JSON.stringify({epochs:1,patience:1,views:1,
        min_f1:.8,min_recall:.6,confidence_threshold:.7,candidates:[{lr:.003,dropout:.2,weight_decay:.001}]})});
      if(!response.ok)throw new Error(await response.text());
      const entries=fflate.unzipSync(new Uint8Array(await response.arrayBuffer()));
      let masked=true,count=0;
      for(const [name,data] of Object.entries(entries)){
        if(!name.endsWith('.png'))continue;
        count++;const image=await createImageBitmap(new Blob([data])),c=document.createElement('canvas');
        c.width=image.width;c.height=image.height;const x=c.getContext('2d');x.drawImage(image,0,0);
        masked=masked&&Array.from(x.getImageData(45,115,1,1).data).join(',')==='0,0,0,255';image.close();
      }
      bitmap.close();
      return {count,masked,paths:Object.keys(entries),metadata:JSON.parse(new TextDecoder().decode(entries['train.json']))};
    }''')
    assert exported['count'] == 18, exported['count']  # 10/class: 2 validation, 2 test, 6 train.
    assert exported['masked']
    assert all(name == 'train.json' or name.startswith('train/') for name in exported['paths'])
    assert '0901234567' not in str(exported['metadata']) and 'Nguyen' not in str(exported['metadata'])
    assert not forbidden, forbidden
    browser.close()
print('PASS: manual confirmation, redaction, no outbound image/text requests, masked train-only Colab ZIP')
