"""Real-model bridge verification. Colab training code runs on CPU ONLY for this test."""
import hashlib
import io
import json
import tempfile
import time
import zipfile
from pathlib import Path
import unittest
from unittest.mock import patch

from PIL import Image
from fastapi.testclient import TestClient
from smartsort_app import store
from smartsort_app.server import app
from colab.train_colab import train_package


class ColabBridgeTests(unittest.TestCase):
    def test_real_training_import_validation_lock_and_test(self):
        with tempfile.TemporaryDirectory(prefix='smartsort-colab-test-') as temporary:
            with patch.object(store,'ROOT',Path(temporary)):
                client=TestClient(app)
                s=client.post('/api/sessions',json={'title':'Colab bridge verification'}).json()
                base='/api/sessions/'+s['id']
                zip_path=Path(__file__).resolve().parents[1]/'SmartSort_Lab/SmartSort_Dataset_Original.zip'
                with zipfile.ZipFile(zip_path) as original:
                    reference={}
                    for r in json.loads(original.read('SmartSortPNG/manifest.json')):
                        with Image.open(io.BytesIO(original.read('SmartSortPNG/'+r['file']))) as im:
                            im=im.convert('RGB')
                            sha=hashlib.sha256(str(im.size).encode()+im.tobytes()).hexdigest()
                        reference[sha]=r['label'] if r['label'] in store.CLASSES else 'exclude'
                uploaded=client.post(base+'/images',files={'files':('data.zip',zip_path.read_bytes(),'application/zip')}).json()
                for c in store.CLASSES+['exclude']:
                    ids=[r['id'] for r in uploaded['session']['images'] if reference[r['pixel_hash']]==c]
                    self.assertEqual(client.put(base+'/labels',json={'ids':ids,'label':c}).status_code,200)
                self.assertEqual(client.post(base+'/split',json={}).status_code,200)
                exported=client.post(base+'/colab/export',json={'epochs':12,'views':2,'min_f1':0,'min_recall':0,
                    'candidates':[{'lr':.001,'dropout':.2,'weight_decay':.001},{'lr':.003,'dropout':.2,'weight_decay':.001}]} )
                self.assertEqual(exported.status_code,200,exported.text)
                data=zipfile.ZipFile(io.BytesIO(exported.content))
                metadata=json.loads(data.read('train.json'))
                state=client.get(base).json()
                self.assertEqual(set(r['id'] for r in metadata['images']),set(state['splits']['ids']['train']))
                self.assertFalse(set(state['splits']['ids']['validation']) & set(r['id'] for r in metadata['images']))
                self.assertFalse(any(name.startswith(('test/','validation/')) for name in data.namelist()))
                train_path=Path(temporary)/'train.zip'
                result_path=Path(temporary)/'models.zip'
                train_path.write_bytes(exported.content)
                train_package(train_path,result_path,require_cuda=False)
                imported=client.post(base+'/colab/import',files={'file':('models.zip',result_path.read_bytes(),'application/zip')})
                self.assertEqual(imported.status_code,200,imported.text)
                self.assertEqual(imported.json()['phase'],'imported')
                self.assertIsNone(imported.json()['training'])
                self.assertEqual(client.post(base+'/lock',json={'trial_id':'trial_1'}).status_code,400)
                self.assertEqual(client.post(base+'/test').status_code,400)
                # Wrong-session bundles and path-injection files are rejected.
                other=client.post('/api/sessions',json={}).json()
                self.assertEqual(client.post('/api/sessions/'+other['id']+'/colab/import',files={'file':('models.zip',result_path.read_bytes(),'application/zip')}).status_code,400)
                invalid=io.BytesIO(result_path.read_bytes())
                with zipfile.ZipFile(invalid,'a') as z:z.writestr('../bad.py','print(1)')
                self.assertEqual(client.post(base+'/colab/import',files={'file':('bad.zip',invalid.getvalue(),'application/zip')}).status_code,400)
                from smartsort_app.training import ImageDataset
                seen=[]
                real_init=ImageDataset.__init__
                def observed_init(obj,session,split,transform):
                    seen.append(split)
                    return real_init(obj,session,split,transform)
                with patch.object(ImageDataset,'__init__',observed_init):
                    self.assertEqual(client.post(base+'/validation').status_code,200)
                    deadline=time.monotonic()+90
                    while time.monotonic()<deadline:
                        state=client.get(base).json()
                        if state['job']['status']!='running':break
                        time.sleep(.1)
                self.assertEqual(state['phase'],'trained',state['job'])
                self.assertEqual(seen,['validation'])
                self.assertEqual(state['training']['training_source'],'colab')
                self.assertEqual(len(state['training']['trials'][0]['history']),12)
                chosen=state['training']['recommended']
                self.assertEqual(client.post(base+'/lock',json={'trial_id':chosen}).status_code,200)
                self.assertEqual(client.post(base+'/validation').status_code,400)
                self.assertEqual(client.post(base+'/colab/export',json={}).status_code,400)
                self.assertEqual(client.post(base+'/test').status_code,200)
                deadline=time.monotonic()+60
                while time.monotonic()<deadline:
                    state=client.get(base).json()
                    if state['job']['status']!='running':break
                    time.sleep(.1)
                self.assertEqual(state['phase'],'tested',state['job'])
                self.assertEqual(state['results']['n'],27)
                download=client.get(base+'/download/SmartSort_Results.zip')
                self.assertIsNone(zipfile.ZipFile(io.BytesIO(download.content)).testzip())
                print('PASS: train-only export → real trainer → strict import → validation-only → lock → test/export')


if __name__=='__main__':unittest.main()
