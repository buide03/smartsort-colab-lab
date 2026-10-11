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
