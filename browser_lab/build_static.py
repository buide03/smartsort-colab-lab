"""Build self-contained Render static assets; dependencies are vendored and pinned."""
import base64
import hashlib
import io
import json
from pathlib import Path
import shutil
import tarfile
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'static_site'
OUT.mkdir(exist_ok=True)

def vendor(package,version,files):
    destination=OUT/'vendor'
    destination.mkdir(exist_ok=True)
    if all((destination/target).is_file() for target in files.values()):return
    with urllib.request.urlopen(f'https://registry.npmjs.org/{package}/{version}',timeout=60) as r:metadata=json.load(r)
    with urllib.request.urlopen(metadata['dist']['tarball'],timeout=120) as r:data=r.read()
    expected='sha512-'+base64.b64encode(hashlib.sha512(data).digest()).decode()
    assert metadata['dist']['integrity']==expected,'Dependency integrity mismatch'
    with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as archive:
        for name,target in files.items():
            (destination/target).write_bytes(archive.extractfile('package/'+name).read())

vendor('fflate','0.8.2',{'umd/index.js':'fflate.js','LICENSE':'fflate.LICENSE'})
vendor('onnxruntime-web','1.23.2',{'dist/ort.wasm.min.js':'ort.wasm.min.js',
    'dist/ort-wasm-simd-threaded.mjs':'ort-wasm-simd-threaded.mjs',
    'dist/ort-wasm-simd-threaded.wasm':'ort-wasm-simd-threaded.wasm'})
license_path=OUT/'vendor/onnxruntime.LICENSE'
if not license_path.exists():
    with urllib.request.urlopen('https://raw.githubusercontent.com/microsoft/onnxruntime/v1.23.2/LICENSE',timeout=30) as r:
        license_path.write_bytes(r.read())
source=ROOT/'smartsort_app/static'
shutil.copyfile(source/'style.css',OUT/'style.css')
shutil.copyfile(source/'privacy-review.js',OUT/'privacy-review.js')
with (OUT/'style.css').open('a',encoding='utf-8',newline='\n') as f:
    f.write('\n.session-tools{flex-wrap:wrap;justify-content:flex-end}.topbar{flex-wrap:wrap;gap:12px;padding:16px 0}@media(max-width:650px){.session-tools{justify-content:flex-start}.session-tools select{max-width:100%;width:100%}.session-tools .button{font-size:11px;padding:8px 10px}}\n')
index=(source/'index.html').read_text(encoding='utf-8').replace('>+</head>','></head>')
index=index.replace('Phiên học được lưu trên server.','Lưu trên trình duyệt này · Xuất ZIP để sao lưu.')
index=index.replace('CLASSROOM LAB','BROWSER LAB')
index=index.replace('<button class="button ghost" id="newSession">',
    '<button class="button ghost" id="backupSession">↓ Sao lưu phiên</button><button class="button ghost" id="restoreSession">↑ Mở bản sao lưu</button><input id="restoreInput" type="file" accept=".zip" hidden><button class="button ghost" id="newSession">')
index=index.replace('<script src="/app.js"></script>',
    '<script src="/vendor/ort.wasm.min.js"></script><script src="/browser-engine.js"></script><script src="/app.js"></script>')
index=index.replace('<div id="content"></div>','<div class="notice" style="margin:20px 0">Ảnh và model lưu trên trình duyệt này. Dùng cùng máy/trình duyệt để quay lại phiên; sao lưu ZIP trước khi đổi máy hoặc xóa dữ liệu trình duyệt. Validation/test dùng CPU máy học sinh; train dùng Colab GPU.</div><div id="content"></div>')
(OUT/'index.html').write_text(index,encoding='utf-8',newline='\n')
app=(source/'app.js').read_text(encoding='utf-8')
app=app.replace('function url(path) { return `/api/sessions/${session.id}/${path}`; }',
    'function url(path) { return path.startsWith("images/") ? BrowserLab.imageURL(session.id,path.slice(7)) : `/api/sessions/${session.id}/${path}`; }')
app=app.replace('await fetch(', 'await BrowserLab.fetch(')
app=app.replace('act(async()=>{appConfig=await api', 'act(async()=>{await BrowserLab.ready;appConfig=await api')
app=app.replace('Chạy validation trên web','Chạy validation trong trình duyệt')
app=app.replace('model.pt','SmartSort_Locked_Model.zip').replace("'PT'","'ZIP'")
app=app.replace('SmartSort_Colab_Models.zip','SmartSort_Browser_Models.zip')
app=app.replace('backend. Kiểm tra cửa sổ chạy python run_local.py.','bộ nhớ trình duyệt. Tải lại trang hoặc kiểm tra quyền lưu dữ liệu.')
app=app.replace('Lần đầu cần Internet để tải trọng số pretrained.','Trọng số pretrained được tải trên Colab.')
app=app.replace('Patience (chỉ train local)','Patience (không dùng trên Colab)')
app=app.replace('${disabled(!canTrain)}></label><label>Phiên bản / ảnh train', ' disabled></label><label>Phiên bản / ảnh train')
app+='''
document.addEventListener('click',event=>{const a=event.target.closest('a[href^="/api/"]');if(!a)return;event.preventDefault();act(()=>BrowserLab.download(a.getAttribute('href')));});
$('#backupSession').addEventListener('click',()=>act(()=>BrowserLab.backup(session.id)));
$('#restoreSession').addEventListener('click',()=>$('#restoreInput').click());
$('#restoreInput').addEventListener('change',event=>act(async()=>{const file=event.target.files[0];if(!file)return;const id=await BrowserLab.restore(file);await loadSessions(id);toast('Đã mở phiên từ bản sao lưu.');}));
'''
(OUT/'app.js').write_text(app,encoding='utf-8',newline='\n')
shutil.copyfile(ROOT/'browser_lab/browser-engine.js',OUT/'browser-engine.js')
print('Built static_site: Render Static Site, no Python backend required')
