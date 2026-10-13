"""Real-model static-browser E2E. CPU training is a development fixture, not hosted Colab."""
import base64
import hashlib
import io
import json
import os
import time
from pathlib import Path
import zipfile
import numpy as np
from PIL import Image,ImageOps
from playwright.sync_api import sync_playwright
from tests.privacy_fixture_review import upload_public_fixture
from colab.train_browser_colab import train_browser_package
from tests.verify_test_visualization import verify_gallery

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'tests/runtime'
OUT.mkdir(exist_ok=True)
dataset=ROOT/'SmartSort_Lab/SmartSort_Dataset_Original.zip'
reference={}
with zipfile.ZipFile(dataset) as archive:
    for row in json.loads(archive.read('SmartSortPNG/manifest.json')):
        with Image.open(io.BytesIO(archive.read('SmartSortPNG/'+row['file']))) as image:
            image=image.convert('RGB');sha=hashlib.sha256(str(image.size).encode()+image.tobytes()).hexdigest()
        reference[sha]=row['label'] if row['label'] in ['metal','paper','plastic'] else 'exclude'

def call(page,path,body=None,method=None):
    return page.evaluate('''async ({path,body,method})=>{
      const response=await BrowserLab.fetch(path,{method:method||(body===null?'GET':'POST'),body:body===null?undefined:JSON.stringify(body)});
      return {status:response.status,data:await response.json()};
    }''',{'path':path,'body':body,'method':method})

def wait_job(page,base,kind):
    deadline=time.monotonic()+180
    while time.monotonic()<deadline:
        state=call(page,base)['data']
        job=state.get('job') or {}
        if job.get('kind')==kind and job.get('status') in ['completed','failed']:
            assert job['status']=='completed',job
            return state
        page.wait_for_timeout(250)
    raise AssertionError(state.get('job'))

with sync_playwright() as playwright:
    launch={'headless':True}
    if os.name=='nt':launch['executable_path']=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
    browser=playwright.chromium.launch(**launch)
    context=browser.new_context(viewport={'width':1440,'height':1000})
    page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto('http://127.0.0.1:8001',wait_until='networkidle')
    page.wait_for_selector('#uploadInput',state='attached',timeout=30000)
    # Resampling and normalization match Pillow for non-square RGB images.
    preprocess_error=0
    for width,height in [(41,67),(319,91),(224,224)]:
        array=np.random.default_rng(42).integers(0,256,(height,width,3),dtype=np.uint8)
        image=Image.fromarray(array);buffer=io.BytesIO();image.save(buffer,format='PNG')
        actual=page.evaluate('''async encoded=>{const data=Uint8Array.from(atob(encoded),c=>c.charCodeAt(0));return Array.from(BrowserLab.tensorPixels(await BrowserLab.pixels(new Blob([data]))));}''',base64.b64encode(buffer.getvalue()).decode())
        expected=np.asarray(ImageOps.pad(image,(224,224),method=Image.Resampling.BICUBIC,color='white'),dtype=np.float32)/255
        expected=((expected-np.array([.485,.456,.406]))/np.array([.229,.224,.225])).transpose(2,0,1).flatten()
        error=float(np.max(np.abs(np.array(actual)-expected)));preprocess_error=max(preprocess_error,error)
        assert error<1e-5,(width,height,error)
    upload_public_fixture(page, dataset)
    page.wait_for_function("document.querySelector('#labelFilter')?.value==='all'",timeout=90000)
    sid=page.locator('#sessionPicker').input_value();base='/api/sessions/'+sid
    state=call(page,base)['data'];assert len(state['images'])==195 and all(r['label']=='exclude' for r in state['images'])
    for label in ['metal','paper','plastic','exclude']:
        ids=[r['id'] for r in state['images'] if reference[r['pixel_hash']]==label]
        assert call(page,base+'/labels',{'ids':ids,'label':label},'PUT')['status']==200
    page.reload(wait_until='networkidle');page.wait_for_selector('#splitAction')
    page.locator('#steps [data-go="2"]').click();page.click('#splitAction')
    page.wait_for_selector('a[href$="dataset.zip"]');state=call(page,base)['data']
    parts=[set(ids) for ids in state['splits']['ids'].values()];assert sum(map(len,parts))==len(set.union(*parts))==180
    assert call(page,base+'/test',{},'POST')['status']==400
    page.locator('#steps [data-go="3"]').click();page.fill('#epochs','8');page.fill('#views','1');page.fill('#learningRates','0.003, 0.01')
    page.locator('details summary').click();page.fill('#minF1','0');page.fill('#minRecall','0')
    with page.expect_download() as downloaded:page.click('#colabExportAction')
    train=OUT/'static_train.zip';downloaded.value.save_as(str(train))
    with zipfile.ZipFile(train) as archive:
        metadata=json.loads(archive.read('train.json'))
        assert set(r['id'] for r in metadata['images'])==parts[0]
        assert not any(name.startswith(('test/','validation/')) for name in archive.namelist())
    models=OUT/'static_models.zip';train_browser_package(train,models,require_cuda=False)
    wrong=OUT/'static_wrong_models.zip'
    with zipfile.ZipFile(models) as source,zipfile.ZipFile(wrong,'w',zipfile.ZIP_DEFLATED) as target:
        for name in source.namelist():
            data=source.read(name)
            if name=='bundle.json':
                data=json.loads(data);data['request_id']='0'*32;data=json.dumps(data).encode()
            target.writestr(name,data)
    page.set_input_files('#colabImportInput',str(wrong))
    page.wait_for_function('document.querySelector("#toast").textContent.includes("khớp")')
    assert call(page,base)['data']['phase']=='split'
    page.set_input_files('#colabImportInput',str(models));page.wait_for_selector('#validationAction:not([disabled])',timeout=60000)
    # Count actual decoded inputs, not API/state reads, during validation.
    page.evaluate('()=>{window.decodedImages=0;window.realBitmap=createImageBitmap;window.createImageBitmap=(...args)=>{window.decodedImages++;return window.realBitmap(...args);};}')
    page.click('#validationAction')
    completed=wait_job(page,base,'validation');assert completed['phase']=='trained',completed.get('job')
    page.wait_for_selector('#content button[data-go="4"]',timeout=15000)
    assert page.evaluate('window.decodedImages')==len(parts[1])
    state=call(page,base)['data'];assert state['phase']=='trained'
    page.locator('#steps [data-go="4"]').click();page.click('#lockAction');page.wait_for_selector('#content button[data-go="5"]')
    assert call(page,base+'/validation',{},'POST')['status']==400
    page.locator('#steps [data-go="5"]').click()
    assert page.locator('#testVisualization').count()==0, 'Test images must remain sealed before evaluation'
    page.evaluate('window.decodedImages=0');page.click('#testAction')
    completed=wait_job(page,base,'test');assert completed['phase']=='tested',completed.get('job')
    page.wait_for_selector('a[href$="SmartSort_Results.zip"]',timeout=15000)
    assert page.evaluate('window.decodedImages')==len(parts[2])
    state=call(page,base)['data'];assert state['phase']=='tested'
    verify_gallery(page,state)
    assert call(page,base+'/colab/export',metadata['settings'],'POST')['status']==400
    assert call(page,base+'/return-to-labeling',{},'POST')['status']==400
    with page.expect_download() as downloaded:page.locator('a[href$="SmartSort_Results.zip"]').click()
    results=OUT/'static_results.zip';downloaded.value.save_as(str(results))
    with zipfile.ZipFile(results) as archive:
        assert archive.testzip() is None
        assert json.loads(archive.read('test_results.json'))==state['results']
        assert 'SmartSort_Locked_Model.zip' in archive.namelist()
    with page.expect_download() as downloaded:page.click('#backupSession')
    backup=OUT/'static_backup.zip';downloaded.value.save_as(str(backup))
    old_result=state['results'];page.reload(wait_until='networkidle');page.wait_for_selector('a[href$="SmartSort_Results.zip"]')
    assert call(page,base)['data']['results']==old_result
    page.set_input_files('#restoreInput',str(backup));page.wait_for_function('(old)=>document.querySelector("#sessionPicker").value!==old',arg=sid,timeout=60000)
    restored=page.locator('#sessionPicker').input_value();restored_state=call(page,'/api/sessions/'+restored)['data']
    assert restored_state['results']==old_result and restored_state['splits']==state['splits']
    page.evaluate('window.scrollTo(0,0)');page.screenshot(path=str(OUT/'static-results.png'),full_page=True)
    page.set_viewport_size({'width':390,'height':844});page.wait_for_timeout(300)
    assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth'), 'Mobile horizontal overflow'
    assert not errors,errors
    report={'preprocessing_max_error':preprocess_error,'accuracy':state['results']['accuracy'],'n':state['results']['n'],'js_errors':errors,'fixture':'CPU development trainer, zero validation gates only for workflow testing'}
    (OUT/'static-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('PASS static browser:',json.dumps(report),flush=True)
    browser.close()
