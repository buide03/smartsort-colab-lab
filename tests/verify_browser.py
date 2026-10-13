"""Manual verification tool: real images, real training, real browser.

This tool uses the supplied dataset's known reference labels as a test fixture.
The application itself never reads or infers these labels from the ZIP.
Run with the local server at port 8000. Screenshots/logs are ignored by Git.
"""
import hashlib
import io
import json
import time
import zipfile
from pathlib import Path
from PIL import Image
from playwright.sync_api import sync_playwright
from tests.privacy_fixture_review import upload_public_fixture

HERE=Path(__file__).resolve().parents[1]
OUT=HERE/'tests/runtime'
OUT.mkdir(exist_ok=True)
ZIP=HERE/'SmartSort_Lab/SmartSort_Dataset_Original.zip'
with zipfile.ZipFile(ZIP) as z:
    manifest=json.loads(z.read('SmartSortPNG/manifest.json'))
    reference={}
    for row in manifest:
        with Image.open(io.BytesIO(z.read('SmartSortPNG/'+row['file']))) as im:
            im=im.convert('RGB')
            sha=hashlib.sha256(str(im.size).encode()+im.tobytes()).hexdigest()
        reference[sha]=row['label'] if row['label'] in ['metal','paper','plastic'] else 'exclude'

with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000},device_scale_factor=1)
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8000',wait_until='networkidle')
    page.wait_for_selector('#chooseFiles')
    page.click('#newSession')
    page.fill('#newTitle','Kiểm thử đầy đủ — dữ liệu mẫu')
    page.click('#confirmNew')
    page.wait_for_function("!document.querySelector('#newDialog').open")
    page.wait_for_function("document.querySelector('#sessionPicker')?.selectedOptions[0]?.textContent==='Kiểm thử đầy đủ — dữ liệu mẫu'")
    page.wait_for_selector('#uploadInput',state='attached')
    upload_public_fixture(page, ZIP)
    page.wait_for_function("document.querySelector('#labelFilter')?.value==='all'",timeout=60000)
    session_id=page.locator('#sessionPicker').input_value()
    base=f'http://127.0.0.1:8000/api/sessions/{session_id}'
    request=page.request
    state=request.get(base).json()
    assert len(state['images'])==195 and state['excluded']==195
    assert request.post(base+'/test').status==400
    # Exercise the visible bulk-label UI before applying the reference fixture.
    page.locator('[data-select]').first.check()
    page.select_option('#batchLabel','metal')
    page.click('#applyBatch')
    page.wait_for_function("document.querySelector('#selectionCount')?.textContent==='0 ảnh đã chọn'")
    for label in ['metal','paper','plastic','exclude']:
        ids=[r['id'] for r in state['images'] if reference[r['pixel_hash']]==label]
        response=request.put(base+'/labels',data={'ids':ids,'label':label})
        assert response.status==200,response.text()
    page.reload(wait_until='networkidle')
    page.wait_for_selector('#splitAction')
    page.evaluate('go(1)')
    page.locator('details.card summary').click()
    page.select_option('#labelFilter','all')
    page.screenshot(path=str(OUT/'01-labels.png'),full_page=True)
    page.locator('#steps [data-go="2"]').click()
    page.click('#splitAction')
    page.wait_for_selector('a[href$="dataset.zip"]')
    state=request.get(base).json()
    assert state['split_counts']=={'train':{'metal':42,'paper':42,'plastic':42},'validation':{'metal':9,'paper':9,'plastic':9},'test':{'metal':9,'paper':9,'plastic':9}}
    assert request.get(base+'/images/'+state['splits']['ids']['test'][0]).status==400
    assert request.post(base+'/test').status==400
    page.screenshot(path=str(OUT/'02-split.png'),full_page=True)
    page.locator('#steps [data-go="3"]').click()
    page.click('#trainAction')
    deadline=time.monotonic()+240
    while time.monotonic()<deadline:
        state=request.get(base).json()
        print(state['job']['status'],state['job']['message'],flush=True)
        if state['job']['status']!='running':break
        page.wait_for_timeout(2000)
    assert state['phase']=='trained',state['job']
    assert len(state['training']['trials'])==3
    page.wait_for_selector('button[data-go="4"]')
    page.screenshot(path=str(OUT/'03-train.png'),full_page=True)
    page.locator('#steps [data-go="4"]').click()
    page.screenshot(path=str(OUT/'04-choose.png'),full_page=True)
    assert page.locator('#lockAction').is_enabled(),'Validation gate not met by the predefined trial configs.'
    page.click('#lockAction')
    page.wait_for_selector('button[data-go="5"]')
    assert request.post(base+'/train',data={}).status==400
    page.locator('#steps [data-go="5"]').click()
    page.click('#testAction')
    deadline=time.monotonic()+120
    while time.monotonic()<deadline:
        state=request.get(base).json()
        if state['job']['status']!='running':break
        page.wait_for_timeout(1000)
    assert state['phase']=='tested',state['job']
    page.wait_for_selector('a[href$="SmartSort_Results.zip"]')
    page.screenshot(path=str(OUT/'05-results.png'),full_page=True)
    assert request.post(base+'/train',data={}).status==400
    assert request.post(base+'/return-to-labeling').status==400
    for name in ['SmartSort_Results.zip','REPORT.md','test_predictions.csv','model.pt']:
        response=request.get(base+'/download/'+name)
        assert response.status==200,name
        if name.endswith('.zip'):
            assert zipfile.ZipFile(io.BytesIO(response.body())).testzip() is None
    sample=next(r for r in manifest if r['label']=='plastic')
    with zipfile.ZipFile(ZIP) as z:
        content=z.read('SmartSortPNG/'+sample['file'])
    response=request.post(base+'/predict',multipart={'file':{'name':'new.png','mimeType':'image/png','buffer':content}})
    assert response.status==200,response.text()
    assert response.json()['label'] in ['metal','paper','plastic']
    page.reload(wait_until='networkidle')
    page.wait_for_selector('a[href$="SmartSort_Results.zip"]')
    page.set_viewport_size({'width':390,'height':844})
    page.screenshot(path=str(OUT/'06-mobile.png'),full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'),'Mobile horizontal overflow'
    assert not errors,errors
    (OUT/'browser-verification.json').write_text(json.dumps({'session_id':session_id,'js_errors':errors,
        'split_counts':state['split_counts'],'trials':[{'id':t['id'],'eligible':t['eligible'],'macro_f1':t['validation']['macro_f1']} for t in state['training']['trials']],
        'test':{k:state['results'][k] for k in ['n','accuracy','macro_f1','high_confidence_errors']}},ensure_ascii=False,indent=2),encoding='utf-8')
    print('PASS: full real-model browser workflow, exports, persistence, mobile and test gates.',flush=True)
    browser.close()
