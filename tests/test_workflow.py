"""Tests for dataset integrity and the train/validation/lock/test boundaries."""
import io
import os
import tempfile
import time
import types
import unittest
from unittest.mock import patch

from PIL import Image
from fastapi.testclient import TestClient

TEMP = tempfile.TemporaryDirectory(prefix='smartsort-tests-')
os.environ['SMARTSORT_APP_DATA'] = TEMP.name
from smartsort_app.server import app
from smartsort_app import store


def image_bytes(i):
    f = io.BytesIO()
    Image.new('RGB', (24, 24), (i*7 % 256, i*11 % 256, i*13 % 256)).save(f, format='PNG')
    return f.getvalue()


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.session = self.client.post('/api/sessions', json={'title':'Test lab'}).json()
        self.base = '/api/sessions/' + self.session['id']

    def state(self):
        return self.client.get(self.base).json()

    def prepare(self):
        files = [('files', (f'image-{i}.png', image_bytes(i), 'image/png')) for i in range(30)]
        response = self.client.post(self.base+'/images', files=files)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['added'], 30)
        rows = response.json()['session']['images']
        self.assertTrue(all(r['label'] is None for r in rows))
        for index,c in enumerate(store.CLASSES):
            response = self.client.put(self.base+'/labels', json={'ids':[r['id'] for r in rows[index*10:(index+1)*10]],'label':c})
            self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.post(self.base+'/split',json={'train':.7,'validation':.15,'test':.15,'seed':42}).status_code,200)

    def test_unknown_labels_and_duplicates(self):
        response=self.client.post(self.base+'/images',files=[('files',('plastic.png',image_bytes(1),'image/png'))])
        self.assertIsNone(response.json()['session']['images'][0]['label'])
        response=self.client.post(self.base+'/images',files=[('files',('renamed.png',image_bytes(1),'image/png'))])
        self.assertEqual(response.json()['duplicates'],1)
        self.assertEqual(len(self.state()['images']),1)
        self.assertEqual(self.client.post(self.base+'/split',json={}).status_code,400)
        self.assertEqual(self.client.post(self.base+'/images',files=[('files',('bad.png',b'not an image','image/png'))]).json()['rejected'][0]['filename'],'bad.png')

    def test_partitions_and_sealed_test(self):
        self.prepare()
        state=self.state()
        parts=[set(ids) for ids in state['splits']['ids'].values()]
        self.assertEqual(len(set.union(*parts)),30)
        self.assertTrue(all(not parts[i]&parts[j] for i in range(3) for j in range(i+1,3)))
        for counts in state['split_counts'].values():
            self.assertTrue(all(n>=1 for n in counts.values()))
        self.assertEqual(self.client.get(self.base+'/images/'+state['splits']['ids']['test'][0]).status_code,400)
        self.assertEqual(self.client.post(self.base+'/test').status_code,400)
        self.assertEqual(self.client.put(self.base+'/labels',json={'ids':[state['images'][0]['id']],'label':'paper'}).status_code,400)
        self.assertEqual(self.client.post(self.base+'/lock',json={'trial_id':'trial_1'}).status_code,400)

    def test_hosting_quotas_and_worker_recovery(self):
        with patch.dict(os.environ, {'SMARTSORT_MAX_IMAGES':'1'}):
            first=self.client.post(self.base+'/images',files={'files':('one.png',image_bytes(1),'image/png')})
            self.assertEqual(first.json()['added'],1)
            duplicate=self.client.post(self.base+'/images',files={'files':('copy.png',image_bytes(1),'image/png')})
            self.assertEqual(duplicate.json()['duplicates'],1)
            extra=self.client.post(self.base+'/images',files={'files':('two.png',image_bytes(2),'image/png')})
            self.assertEqual(extra.json()['added'],0)
            self.assertEqual(len(extra.json()['rejected']),1)
            self.assertEqual(len(self.state()['images']),1)
        with patch.dict(os.environ, {'SMARTSORT_UPLOAD_LIMIT_MB':'1'}):
            response=self.client.post(self.base+'/images',files={'files':('large.png',b'x'*(1024*1024+1),'image/png')})
            self.assertEqual(response.status_code,400)
        with patch.dict(os.environ, {'SMARTSORT_MAX_SESSIONS':'0'}):
            self.assertEqual(self.client.post('/api/sessions',json={}).status_code,400)
        from smartsort_app.server import start_job,WORKER_LOCK
        with patch.object(store,'load',side_effect=ValueError('missing')):
            with self.assertRaises(ValueError):
                start_job(self.session['id'],'validation',lambda *_:None)
        self.assertFalse(WORKER_LOCK.locked())

    def test_hosting_access_and_train_only_export(self):
        self.prepare()
        with patch.dict(os.environ,{'SMARTSORT_ALLOW_LOCAL_TRAIN':'false'}):
            self.assertFalse(self.client.get('/api/config').json()['allow_local_train'])
            self.assertEqual(self.client.post(self.base+'/train',json={}).status_code,400)
        response=self.client.post(self.base+'/colab/export',json={})
        self.assertEqual(response.status_code,200)
        import zipfile,json
        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            metadata=json.loads(z.read('train.json'))
            self.assertEqual(set(r['id'] for r in metadata['images']),set(self.state()['splits']['ids']['train']))
            self.assertTrue(all(p=='train.json' or p.startswith('train/') for p in z.namelist()))
        self.assertEqual(self.client.post(self.base+'/validation').status_code,400)
        with patch.dict(os.environ,{'SMARTSORT_CLASSROOM_PASSWORD':'test-class-password'}):
            self.assertEqual(self.client.get('/healthz').status_code,200)
            self.assertEqual(self.client.get('/api/sessions').status_code,401)
            self.assertEqual(self.client.get('/api/sessions',auth=('class','wrong')).status_code,401)
            self.assertEqual(self.client.get('/api/sessions',auth=('class','test-class-password')).status_code,200)

    def test_validation_gate_and_no_training_after_lock_or_test(self):
        self.prepare()
        def fake_train(session, settings, progress):
            return {'run_id':settings['run_id'],'model':'efficientnet_b0','recommended':'trial_2','settings':settings,
                    'trials':[{'id':'trial_1','eligible':False,'config':{'lr':.001},'best_epoch':2,'validation':{'macro_f1':.5}},
                              {'id':'trial_2','eligible':True,'config':{'lr':.003},'best_epoch':3,'validation':{'macro_f1':.9}}]}
        def fake_test(session, progress):
            return {'accuracy':.8}
        fake=types.SimpleNamespace(train_trials=fake_train,test_model=fake_test)
        with patch.dict('sys.modules',{'smartsort_app.training':fake}):
            self.assertEqual(self.client.post(self.base+'/train',json={}).status_code,200)
            for _ in range(100):
                if self.state()['job']['status']!='running':break
                time.sleep(.01)
            self.assertEqual(self.state()['phase'],'trained')
            self.assertEqual(self.client.post(self.base+'/lock',json={'trial_id':'trial_1'}).status_code,400)
            self.assertEqual(self.client.post(self.base+'/lock',json={'trial_id':'trial_2'}).status_code,200)
            self.assertEqual(self.client.post(self.base+'/train',json={}).status_code,400)
            self.assertEqual(self.client.post(self.base+'/test').status_code,200)
            for _ in range(100):
                if self.state()['job']['status']!='running':break
                time.sleep(.01)
            self.assertEqual(self.state()['phase'],'tested')
            self.assertEqual(self.client.post(self.base+'/train',json={}).status_code,400)
            self.assertEqual(self.client.post(self.base+'/return-to-labeling').status_code,400)
            self.assertEqual(self.client.post(self.base+'/test').json()['results']['accuracy'],.8)


if __name__=='__main__':
    unittest.main()
