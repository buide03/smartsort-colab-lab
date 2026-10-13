"""Verify Colab-transfer UI with a real trainer on CPU as a development fixture."""
import hashlib
import io
import json
import zipfile
from pathlib import Path
from PIL import Image
from playwright.sync_api import sync_playwright
from tests.privacy_fixture_review import upload_public_fixture
from colab.train_colab import train_package

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'tests/runtime'
OUT.mkdir(exist_ok=True)
dataset=ROOT/'SmartSort_Lab/SmartSort_Dataset_Original.zip'
reference={}
with zipfile.ZipFile(dataset) as z:
    for r in json.loads(z.read('SmartSortPNG/manifest.json')):
        with Image.open(io.BytesIO(z.read('SmartSortPNG/'+r['file']))) as im:
            im=im.convert('RGB')
            sha=hashlib.sha256(str(im.size).encode()+im.tobytes()).hexdigest()
        reference[sha]=r['label'] if r['label'] in ['metal','paper','plastic'] else 'exclude'

with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8000',wait_until='networkidle')
    page.wait_for_selector('#sessionPicker')
    page.click('#newSession')
    page.fill('#newTitle','Luồng Colab — minh họa kiểm thử')
    page.click('#confirmNew')
    page.wait_for_function("!document.querySelector('#newDialog').open")
    upload_public_fixture(page, dataset)
    page.wait_for_function("document.querySelector('#labelFilter')?.value==='unlabeled'",timeout=60000)
    sid=page.locator('#sessionPicker').input_value()
    base='http://127.0.0.1:8000/api/sessions/'+sid
    state=page.request.get(base).json()
    for label in ['metal','paper','plastic','exclude']:
        ids=[r['id'] for r in state['images'] if reference[r['pixel_hash']]==label]
        assert page.request.put(base+'/labels',data={'ids':ids,'label':label}).status==200
    page.reload(wait_until='networkidle')
    page.locator('#steps [data-go="2"]').click()
    page.click('#splitAction')
    page.wait_for_selector('a[href$="dataset.zip"]')
    page.locator('#steps [data-go="3"]').click()
    page.fill('#epochs','12')
    page.fill('#views','2')
    page.fill('#learningRates','0.003, 0.01')
    page.locator('details summary').click()
    page.fill('#minF1','0')
    page.fill('#minRecall','0')
    with page.expect_download() as downloaded:
        page.click('#colabExportAction')
    train_path=OUT/'browser_train.zip'
    downloaded.value.save_as(str(train_path))
    page.wait_for_selector('#chooseColabModels:not([disabled])')
    page.screenshot(path=str(OUT/'colab-export.png'),full_page=True)
    models_path=OUT/'browser_models.zip'
    train_package(train_path,models_path,require_cuda=False)
    page.set_input_files('#colabImportInput',str(models_path))
    page.wait_for_selector('#validationAction:not([disabled])')
    page.click('#validationAction')
    page.wait_for_selector('#content button[data-go="4"]',timeout=90000)
    page.evaluate('window.scrollTo(0,0)')
    page.screenshot(path=str(OUT/'colab-validation.png'),full_page=True)
    page.locator('#steps [data-go="4"]').click()
    page.click('#lockAction')
    page.wait_for_selector('button[data-go="5"]')
    page.locator('#steps [data-go="5"]').click()
    page.click('#testAction')
    page.wait_for_selector('a[href$="SmartSort_Results.zip"]',timeout=90000)
    assert not errors,errors
    state=page.request.get(base).json()
    assert state['training']['training_source']=='colab' and state['phase']=='tested'
    (OUT/'colab-browser.json').write_text(json.dumps({'session_id':sid,'js_errors':errors,'source':'CPU development fixture',
        'test_n':state['results']['n'],'accuracy':state['results']['accuracy']},ensure_ascii=False,indent=2),encoding='utf-8')
    print('PASS: export download → model import → explicit validation → lock → test via browser',flush=True)
    browser.close()
