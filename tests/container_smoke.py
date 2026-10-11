"""Standard-library HTTP smoke check for a Docker CPU deployment and volume restart."""
import base64
import io
import json
import os
from pathlib import Path
import struct
import sys
import urllib.error
import urllib.request
import zipfile
import zlib

URL=os.environ.get('SMARTSORT_SMOKE_URL','http://127.0.0.1:18000')
PASSWORD=os.environ.get('SMARTSORT_SMOKE_PASSWORD','ci-password')
STATE=Path(__file__).parent/'runtime'/'container-state.json'

def request(path, data=None, content_type='application/json', authenticated=True, expected=200, method=None):
    if isinstance(data,dict):
        data=json.dumps(data).encode()
    headers={'Content-Type':content_type}
    if authenticated:
        headers['Authorization']='Basic '+base64.b64encode(('class:'+PASSWORD).encode()).decode()
    req=urllib.request.Request(URL+path,data=data,headers=headers,method=method)
    try:
        with urllib.request.urlopen(req,timeout=60) as response:
            status,body=response.status,response.read()
    except urllib.error.HTTPError as exc:
        status,body=exc.code,exc.read()
    assert status==expected,(path,status,body[:300])
    return body

def get_json(path, **kwargs):
    return json.loads(request(path,**kwargs))

def png(index):
    def chunk(kind,data):
        return struct.pack('!I',len(data))+kind+data+struct.pack('!I',zlib.crc32(kind+data)&0xffffffff)
    pixels=bytes((index*7%256,index*11%256,index*13%256))*24
    return (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!2I5B',24,24,8,2,0,0,0))
            +chunk(b'IDAT',zlib.compress((b'\x00'+pixels)*24))+chunk(b'IEND',b''))

def main():
    assert get_json('/healthz',authenticated=False)['status']=='ok'
    request('/api/sessions',authenticated=False,expected=401)
    assert get_json('/api/config')['allow_local_train'] is False
    request('/')
    if sys.argv[1]=='check':
        saved=json.loads(STATE.read_text())
        current=get_json('/api/sessions/'+saved['id'])
        assert current['phase']=='split'
        assert current['splits']==saved['splits']
        assert len(current['images'])==30
        print('Volume restart: images, labels and split persisted')
        return
    session=get_json('/api/sessions',data={'title':'Docker smoke check'})
    path='/api/sessions/'+session['id']
    boundary='SmartSortSmokeBoundary'
    parts=[]
    for i in range(30):
        parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="files"; filename="image-{i}.png"\r\nContent-Type: image/png\r\n\r\n').encode()+png(i)+b'\r\n')
    parts.append(f'--{boundary}--\r\n'.encode())
    uploaded=get_json(path+'/images',data=b''.join(parts),content_type='multipart/form-data; boundary='+boundary)
    assert uploaded['added']==30
    rows=uploaded['session']['images']
    assert all(r['label'] is None for r in rows)
    for i,label in enumerate(['metal','paper','plastic']):
        request(path+'/labels',data={'ids':[r['id'] for r in rows[i*10:(i+1)*10]],'label':label},method='PUT')
    request(path+'/split',data={'train':.7,'validation':.15,'test':.15,'seed':42})
    current=get_json(path)
    ids=current['splits']['ids']
    sets=[set(value) for value in ids.values()]
    assert len(set.union(*sets))==30 and sum(map(len,sets))==30
    request(path+'/images/'+ids['test'][0],expected=400)
    request(path+'/train',data={},expected=400)
    request(path+'/test',data={},expected=400)
    request(path+'/validation',data={},expected=400)
    with zipfile.ZipFile(io.BytesIO(request(path+'/colab/export',data={}))) as archive:
        metadata=json.loads(archive.read('train.json'))
        assert set(r['id'] for r in metadata['images'])==set(ids['train'])
        assert all(name=='train.json' or name.startswith('train/') for name in archive.namelist())
        assert archive.testzip() is None
    STATE.parent.mkdir(parents=True,exist_ok=True)
    STATE.write_text(json.dumps(get_json(path)),encoding='utf-8')
    print('Container workflow: auth, upload, labels, split, sealed test, train-only Colab export OK')

if __name__=='__main__':
    main()
