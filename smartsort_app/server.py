"""Local-only FastAPI interface for the teaching workflow."""
import csv
import base64
import hmac
import io
import json
import os
import threading
import uuid
import zipfile
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from . import store

app = FastAPI(title='SmartSort Classroom', docs_url='/api/docs', redoc_url=None)
STATIC = Path(__file__).parent / 'static'
WORKER_LOCK = threading.Lock()


@app.middleware('http')
async def classroom_access(request, call_next):
    password=os.environ.get('SMARTSORT_CLASSROOM_PASSWORD','')
    if password and request.url.path!='/healthz':
        authenticated=False
        try:
            scheme,value=request.headers.get('authorization','').split(' ',1)
            username,supplied=base64.b64decode(value,validate=True).decode().split(':',1)
            authenticated=scheme.lower()=='basic' and username=='class' and hmac.compare_digest(supplied.encode(),password.encode())
        except (ValueError,UnicodeError):
            pass
        if not authenticated:
            return Response('Đăng nhập lớp học',status_code=401,headers={'WWW-Authenticate':'Basic realm="SmartSort Classroom", charset="UTF-8"'})
    return await call_next(request)


@app.exception_handler(ValueError)
async def value_error(request, exc):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=400, content={'detail': str(exc)})


class SessionRequest(BaseModel):
    title: str = Field(default='', max_length=100)


class LabelsRequest(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=5000)
    label: str | None


class SplitRequest(BaseModel):
    train: float = Field(default=.70, gt=0, lt=1)
    validation: float = Field(default=.15, gt=0, lt=1)
    test: float = Field(default=.15, gt=0, lt=1)
    seed: int = Field(default=42, ge=0, le=2**31-1)


class Candidate(BaseModel):
    lr: float = Field(gt=0, le=1)
    dropout: float = Field(default=.2, ge=0, lt=1)
    weight_decay: float = Field(default=.001, ge=0, le=1)


class TrainRequest(BaseModel):
    epochs: int = Field(default=60, ge=1, le=200)
    patience: int = Field(default=12, ge=1, le=50)
    views: int = Field(default=4, ge=1, le=8)
    min_f1: float = Field(default=.80, ge=0, le=1)
    min_recall: float = Field(default=.60, ge=0, le=1)
    confidence_threshold: float = Field(default=.70, ge=0, le=1)
    candidates: list[Candidate] = Field(default_factory=lambda: [
        Candidate(lr=.001), Candidate(lr=.003), Candidate(lr=.01, dropout=.4)], min_length=1, max_length=6)


class SelectRequest(BaseModel):
    trial_id: str


def idle(session):
    if session.get('job') and session['job']['status'] == 'running':
        raise ValueError('Phiên này đang chạy. Chờ tác vụ hoàn tất.')


def start_job(session_id, kind, operation):
    if not WORKER_LOCK.acquire(blocking=False):
        raise ValueError('Đang có một tác vụ huấn luyện/kiểm thử khác trên máy. Hãy chờ hoàn tất.')
    try:
        with store.LOCK:
            s = store.load(session_id)
            if kind == 'train':
                s.update({'training': None, 'selected': None, 'phase': 'split'})
            s['job'] = {'kind': kind, 'status': 'running', 'progress': 0, 'message': 'Đang khởi tạo...', 'live': None}
            store.save(s)
    except BaseException:
        WORKER_LOCK.release()
        raise

    def progress(percent, message, live=None):
        with store.LOCK:
            current = store.load(session_id)
            current['job'].update({'progress': round(percent, 1), 'message': message, 'live': live})
            store.save(current)

    def work():
        try:
            result = operation(s, progress)
            with store.LOCK:
                current = store.load(session_id)
                if kind in ['train','validation']:
                    current['training'] = result
                    current['phase'] = 'trained'
                else:
                    current['results'] = result
                    current['phase'] = 'tested'
                current['job'].update({'status': 'completed', 'progress': 100, 'live': None})
                store.save(current)
        except Exception as exc:
            with store.LOCK:
                current = store.load(session_id)
                # A failed test may already have revealed partial outcomes. Do not tune again.
                if kind == 'test':
                    current['phase'] = 'test_failed'
                current['job'].update({'status': 'failed', 'message': str(exc), 'live': None})
                store.save(current)
        finally:
            WORKER_LOCK.release()
    threading.Thread(target=work, daemon=True, name=f'smartsort-{kind}').start()


@app.get('/api/sessions')
def list_sessions():
    return store.sessions()


@app.get('/healthz')
def health():
    return {'status':'ok'}


@app.get('/api/config')
def app_config():
    return {'allow_local_train':os.environ.get('SMARTSORT_ALLOW_LOCAL_TRAIN','true').lower()=='true',
            'upload_limit_mb':int(os.environ.get('SMARTSORT_UPLOAD_LIMIT_MB','64')),
            'colab_notebook':'https://colab.research.google.com/github/buide03/smartsort-colab-lab/blob/main/colab/SmartSort_Train_Colab.ipynb'}


@app.post('/api/sessions')
def create_session(body: SessionRequest):
    return store.public(store.create(body.title))


@app.get('/api/sessions/{session_id}')
def get_session(session_id: str):
    with store.LOCK:
        return store.public(store.load(session_id))


@app.post('/api/sessions/{session_id}/images')
async def upload_images(session_id: str, files: list[UploadFile] = File(...)):
    uploads = []
    total = 0
    limit_mb=int(os.environ.get('SMARTSORT_UPLOAD_LIMIT_MB','64'))
    limit_bytes=limit_mb*1024*1024
    for file in files:
        data = await file.read(limit_bytes-total+1)
        await file.close()
        total += len(data)
        if total > limit_bytes:
            raise ValueError(f'Mỗi lần tải tối đa {limit_mb} MB; có thể tải nhiều lượt.')
        uploads.append((file.filename or 'image', data))
    with store.LOCK:
        s = store.load(session_id)
        idle(s)
        if s['phase'] != 'labeling':
            raise ValueError('Dữ liệu đã khóa. Quay lại gán nhãn hoặc tạo phiên mới.')
        added = duplicates = 0
        rejected = []
        def ingest(name, content):
            nonlocal added, duplicates
            try:
                if store.add_image(s, name, content):
                    added += 1
                else:
                    duplicates += 1
            except ValueError as exc:
                rejected.append({'filename': name, 'reason': str(exc)})
        for name, data in uploads:
            if name.lower().endswith('.zip'):
                try:
                    with zipfile.ZipFile(io.BytesIO(data)) as z:
                        members = [i for i in z.infolist() if not i.is_dir() and Path(i.filename).suffix.lower() in ['.jpg','.jpeg','.png','.webp','.bmp']]
                        if len(members) > 5000 or sum(i.file_size for i in members) > 512*1024*1024:
                            raise ValueError('ZIP tối đa 5.000 ảnh và 512 MB sau giải nén.')
                        for member in members:
                            if member.file_size > store.MAX_IMAGE_BYTES:
                                rejected.append({'filename': member.filename, 'reason': 'Ảnh lớn hơn 25 MB.'})
                                continue
                            ingest(member.filename, z.read(member))
                except (zipfile.BadZipFile, RuntimeError, ValueError) as exc:
                    rejected.append({'filename': name, 'reason': str(exc) if isinstance(exc, ValueError) else 'ZIP hỏng hoặc có mật khẩu.'})
            else:
                ingest(name, data)
        store.save(s)
        return {'added': added, 'duplicates': duplicates, 'rejected': rejected, 'session': store.public(s)}


@app.get('/api/sessions/{session_id}/images/{image_id}')
def get_image(session_id: str, image_id: str):
    with store.LOCK:
        s = store.load(session_id)
        if s['splits'] and image_id in s['splits']['ids']['test'] and s['phase'] != 'tested':
            raise ValueError('Ảnh test được giữ kín cho đến khi đánh giá cuối hoàn tất.')
        return FileResponse(store.image_path(session_id, image_id), media_type='image/png')


@app.put('/api/sessions/{session_id}/labels')
def label_images(session_id: str, body: LabelsRequest):
    if body.label not in store.CLASSES + ['exclude', None]:
        raise ValueError('Nhãn phải là nhựa, giấy, kim loại, bỏ qua hoặc chưa gán.')
    with store.LOCK:
        s = store.load(session_id)
        idle(s)
        if s['phase'] != 'labeling':
            raise ValueError('Không sửa nhãn sau khi chia dữ liệu.')
        ids = set(body.ids)
        if not ids.issubset({r['id'] for r in s['images']}):
            raise ValueError('Có ảnh không thuộc phiên này.')
        for r in s['images']:
            if r['id'] in ids:
                r['label'] = body.label
        store.save(s)
        return store.public(s)


@app.get('/api/sessions/{session_id}/labels.csv')
def download_labels(session_id: str):
    with store.LOCK:
        s = store.load(session_id)
    f = io.StringIO(newline='')
    writer = csv.DictWriter(f, fieldnames=['id','filename','label','pixel_hash'])
    writer.writeheader()
    writer.writerows({k: r[k] for k in writer.fieldnames} for r in s['images'])
    return Response(f.getvalue().encode('utf-8-sig'), media_type='text/csv', headers={'Content-Disposition':'attachment; filename="labels.csv"'})


@app.post('/api/sessions/{session_id}/split')
def split_session(session_id: str, body: SplitRequest):
    with store.LOCK:
        s = store.load(session_id)
        idle(s)
        store.split_data(s, body.train, body.validation, body.test, body.seed)
        return store.public(s)


@app.post('/api/sessions/{session_id}/return-to-labeling')
def return_to_labeling(session_id: str):
    with store.LOCK:
        s = store.load(session_id)
        idle(s)
        if s['phase'] in ['tested','test_failed']:
            raise ValueError('Đã mở test. Để cải tiến và đánh giá cuối, tạo phiên với test mới độc lập.')
        s.update({'phase':'labeling','splits':None,'training':None,'selected':None,'results':None,'job':None,
                  'colab_request':None,'imported':None})
        store.save(s)
        return store.public(s)


@app.post('/api/sessions/{session_id}/train')
def train_session(session_id: str, body: TrainRequest):
    if os.environ.get('SMARTSORT_ALLOW_LOCAL_TRAIN','true').lower()!='true':
        raise ValueError('Server này chỉ huấn luyện trên Colab. Xuất gói train và nhập checkpoint để chạy validation.')
    with store.LOCK:
        s = store.load(session_id)
        idle(s)
        if s['phase'] not in ['split','trained']:
            raise ValueError('Chia dữ liệu trước. Không huấn luyện lại khi đã chốt hoặc mở test.')
        settings = body.model_dump()
        settings['run_id'] = uuid.uuid4().hex
        def operation(snapshot, progress):
            from .training import train_trials
            return train_trials(snapshot, settings, progress)
        start_job(session_id, 'train', operation)
        return store.public(store.load(session_id))


@app.post('/api/sessions/{session_id}/colab/export')
def export_colab(session_id: str, body: TrainRequest):
    with store.LOCK:
        s=store.load(session_id)
        idle(s)
        if s['phase'] not in ['split','imported','trained']:
            raise ValueError('Cần chia dữ liệu; không xuất kế hoạch train mới khi đã chốt/mở test.')
        from .colab_bridge import export_train
        p=export_train(s,body.model_dump())
        return FileResponse(p,filename='SmartSort_Colab_Train.zip')


@app.post('/api/sessions/{session_id}/colab/import')
async def import_colab(session_id: str, file: UploadFile = File(...)):
    data=await file.read(128*1024*1024+1)
    await file.close()
    if len(data)>128*1024*1024:
        raise ValueError('Gói mô hình tối đa 128 MB.')
    with store.LOCK:
        s=store.load(session_id)
        idle(s)
        if s['phase'] not in ['split','imported','trained']:
            raise ValueError('Không nhập mô hình khi đã chốt/mở test.')
        from .colab_bridge import inspect_bundle
        metadata=inspect_bundle(s,data)
        import_id=uuid.uuid4().hex
        directory=store.session_dir(session_id)/'imports'
        directory.mkdir(exist_ok=True)
        (directory/f'{import_id}.zip').write_bytes(data)
        s.update({'imported':{'id':import_id,'metadata':metadata},'phase':'imported',
                  'training':None,'selected':None,'job':None})
        store.save(s)
        return store.public(s)


@app.post('/api/sessions/{session_id}/validation')
def run_validation(session_id: str):
    with store.LOCK:
        s=store.load(session_id)
        idle(s)
        if s['phase'] not in ['imported','trained'] or not s.get('imported'):
            raise ValueError('Nhập gói mô hình Colab trước khi chạy validation; không chạy lại sau khi chốt.')
        def operation(snapshot,progress):
            from .colab_bridge import validate_bundle
            return validate_bundle(snapshot,progress)
        start_job(session_id,'validation',operation)
        return store.public(store.load(session_id))


@app.post('/api/sessions/{session_id}/lock')
def lock_model(session_id: str, body: SelectRequest):
    with store.LOCK:
        s = store.load(session_id)
        idle(s)
        if s['phase'] != 'trained' or not s['training']:
            raise ValueError('Cần huấn luyện xong và so sánh validation trước khi chốt.')
        candidate = next((t for t in s['training']['trials'] if t['id'] == body.trial_id), None)
        if not candidate:
            raise ValueError('Không tìm thấy cấu hình này.')
        if not candidate['eligible']:
            raise ValueError('Cấu hình chưa đạt tiêu chí validation đã đặt trước; chưa được mở test.')
        s['selected'] = {'trial_id': candidate['id'], 'model': s['training']['model'],
                         'config': candidate['config'], 'best_epoch': candidate['best_epoch'],
                         'validation': candidate['validation'], 'split_sha256': s['splits']['sha256'],
                         'criteria': {k: s['training']['settings'][k] for k in ['min_f1','min_recall','confidence_threshold']},
                         'locked_at': store.now()}
        s['phase'] = 'locked'
        store.save(s)
        (store.session_dir(session_id) / 'locked_config.json').write_text(json.dumps(s['selected'], ensure_ascii=False, indent=2), encoding='utf-8')
        return store.public(s)


@app.post('/api/sessions/{session_id}/test')
def run_test(session_id: str):
    with store.LOCK:
        s = store.load(session_id)
        idle(s)
        if s['phase'] == 'tested':
            return store.public(s)  # cached result; never silently retrain or resplit
        if s['phase'] not in ['locked','test_failed']:
            raise ValueError('Phải chốt cấu hình trước khi mở test.')
        def operation(snapshot, progress):
            from .training import test_model
            return test_model(snapshot, progress)
        start_job(session_id, 'test', operation)
        return store.public(store.load(session_id))


@app.get('/api/sessions/{session_id}/dataset.zip')
def download_dataset(session_id: str):
    with store.LOCK:
        s = store.load(session_id)
        if not s['splits']:
            raise ValueError('Cần chia dữ liệu trước.')
        p = store.session_dir(session_id) / 'dataset_splits.zip'
        records = {r['id']: r for r in s['images']}
        with zipfile.ZipFile(p, 'w', zipfile.ZIP_DEFLATED) as z:
            for split, ids in s['splits']['ids'].items():
                for image_id in ids:
                    z.write(store.session_dir(session_id) / 'images' / (image_id+'.png'),
                            f'{split}/{records[image_id]["label"]}/{image_id}.png')
            z.writestr('manifest.json', json.dumps({'images': s['images'], 'splits': s['splits']}, ensure_ascii=False, indent=2))
        return FileResponse(p, filename='SmartSort_Dataset_Splits.zip')


@app.get('/api/sessions/{session_id}/download/{filename}')
def download_result(session_id: str, filename: str):
    allowed = ['SmartSort_Results.zip','REPORT.md','test_predictions.csv','model.pt',
               'per_class_metrics.csv','test_results.json','training.json','locked_config.json','labels_and_splits.csv']
    if filename not in allowed:
        raise HTTPException(404)
    p = store.session_dir(session_id) / 'results' / filename
    if not p.is_file():
        raise ValueError('Chưa có kết quả này; hãy chạy test trước.')
    return FileResponse(p, filename=filename)


@app.post('/api/sessions/{session_id}/predict')
async def predict_image(session_id: str, file: UploadFile = File(...)):
    with store.LOCK:
        s = store.load(session_id)
        idle(s)
        if s['phase'] != 'tested':
            raise ValueError('Hoàn thành test trước khi thử ảnh mới.')
    data = await file.read(store.MAX_IMAGE_BYTES+1)
    await file.close()
    image = store.rgb_image(data)
    if not WORKER_LOCK.acquire(blocking=False):
        raise ValueError('Server đang validation/test hoặc nhận diện ảnh khác. Chờ tác vụ đó hoàn tất.')
    def inference():
        from .training import selected_model, transforms, device
        import torch
        model = selected_model(s).to(device()).eval()
        _, transform = transforms()
        with torch.inference_mode():
            p = model(transform(image).unsqueeze(0).to(next(model.parameters()).device)).softmax(1)[0].cpu().numpy()
        i = int(p.argmax())
        return {'label': store.CLASSES[i], 'name':store.CLASS_NAMES[store.CLASSES[i]], 'confidence':float(p[i]),
                'decision':store.CLASS_NAMES[store.CLASSES[i]] if p[i]>=s['selected']['criteria']['confidence_threshold'] else 'Cần kiểm tra',
                'probabilities':{c:float(p[j]) for j,c in enumerate(store.CLASSES)}}
    try:
        return await run_in_threadpool(inference)
    finally:
        WORKER_LOCK.release()


# An interrupted job is not reported as still running after a process restart.
for summary in store.sessions():
    with store.LOCK:
        session = store.load(summary['id'])
        if session.get('job') and session['job']['status'] == 'running':
            if session['job']['kind'] == 'test':
                session['phase'] = 'test_failed'
            session['job'].update({'status':'failed','message':'Phiên chạy bị ngắt khi server dừng. Có thể chạy lại tác vụ với dữ liệu/cấu hình đã giữ.', 'live':None})
            store.save(session)

app.mount('/', StaticFiles(directory=STATIC, html=True), name='frontend')
