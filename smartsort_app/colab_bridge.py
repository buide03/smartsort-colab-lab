"""Train-only export, strict model import and local validation of all epochs."""
import io
import json
import math
import uuid
import zipfile
from pathlib import Path

from . import store


def export_train(session, settings):
    request_id = uuid.uuid4().hex
    settings = dict(settings,run_id=request_id)
    records = {r['id']:r for r in session['images']}
    images = [{k:records[i][k] for k in ['id','label','pixel_hash']} for i in session['splits']['ids']['train']]
    metadata = {'kind':'smartsort_train','version':1,'classes':store.CLASSES,
                'session_id':session['id'],'request_id':request_id,
                'split_sha256':session['splits']['sha256'],'seed':session['splits']['seed'],
                'settings':settings,'images':images}
    p = store.session_dir(session['id']) / 'colab_train.zip'
    with zipfile.ZipFile(p,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('train.json',json.dumps(metadata,ensure_ascii=False,indent=2))
        for row in images:
            z.write(store.session_dir(session['id'])/'images'/f'{row["id"]}.png',f'train/{row["id"]}.png')
    session.update({'colab_request':metadata,'imported':None,'training':None,'selected':None,'phase':'split','job':None})
    store.save(session)
    return p


def inspect_bundle(session, data):
    request = session.get('colab_request')
    if not request:
        raise ValueError('Xuất gói train cho Colab từ phiên này trước khi nhập mô hình.')
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        infos = z.infolist()
        if len(infos)>1300 or len({i.filename for i in infos})!=len(infos) or sum(i.file_size for i in infos)>150*1024*1024:
            raise ValueError('Gói mô hình quá lớn hoặc có tên file trùng.')
        if z.getinfo('bundle.json').file_size>4*1024*1024:
            raise ValueError('Metadata quá lớn.')
        bundle = json.loads(z.read('bundle.json'))
        if bundle.get('kind')!='smartsort_colab_models' or bundle.get('version')!=1 or bundle.get('model')!='efficientnet_b0':
            raise ValueError('Không đúng định dạng mô hình SmartSort Colab.')
        for key in ['session_id','request_id','split_sha256','classes','settings']:
            if bundle.get(key)!=request[key]:
                raise ValueError('Gói mô hình không thuộc yêu cầu Colab/bản chia hiện tại của phiên này.')
        expected_pre = {'size':224,'fill':'white','mean':[.485,.456,.406],'std':[.229,.224,.225]}
        if bundle.get('preprocessing')!=expected_pre:
            raise ValueError('Tiền xử lý không khớp với ứng dụng.')
        if not isinstance(bundle.get('training_seconds'),(int,float)) or not math.isfinite(bundle['training_seconds']) or bundle['training_seconds']<0:
            raise ValueError('Thời gian huấn luyện không hợp lệ.')
        candidates = bundle['candidates']
        if len(candidates)!=len(request['settings']['candidates']):
            raise ValueError('Số cấu hình không khớp.')
        allowed = {'bundle.json','backbone.npz'}
        for index,candidate in enumerate(candidates):
            if candidate['id']!=f'trial_{index+1}' or candidate['config']!=request['settings']['candidates'][index]:
                raise ValueError('Cấu hình không khớp kế hoạch train.')
            if len(candidate['checkpoints'])!=request['settings']['epochs']:
                raise ValueError('Thiếu checkpoint epoch; Colab cần chạy đủ kế hoạch.')
            for epoch,row in enumerate(candidate['checkpoints'],1):
                name=f'heads/trial_{index+1}/epoch_{epoch:03d}.npz'
                if row['epoch']!=epoch or row['file']!=name:
                    raise ValueError('Danh sách epoch không hợp lệ.')
                if not all(isinstance(row.get(k),(int,float)) and math.isfinite(row[k]) for k in ['train_loss','train_accuracy']):
                    raise ValueError('Lịch sử train không hợp lệ.')
                if row['train_loss']<0 or not 0<=row['train_accuracy']<=1:
                    raise ValueError('Lịch sử train ngoài khoảng hợp lệ.')
                allowed.add(name)
        if set(z.namelist())!=allowed or z.testzip() is not None:
            raise ValueError('Gói thiếu file, có file ngoài định dạng hoặc lỗi CRC.')
        if any(i.file_size>30*1024*1024 for i in infos):
            raise ValueError('File mô hình quá lớn.')
        return bundle
    except (KeyError,TypeError,zipfile.BadZipFile,json.JSONDecodeError,RuntimeError) as exc:
        raise ValueError('Không đọc được gói checkpoint SmartSort hợp lệ.') from exc


def numpy_state(data, expected):
    import numpy as np
    import torch
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as inner:
            if sum(i.file_size for i in inner.infolist())>40*1024*1024:
                raise ValueError('Tensor quá lớn.')
        with np.load(io.BytesIO(data),allow_pickle=False) as archive:
            if set(archive.files)!=set(expected):
                raise ValueError('Tên tensor không khớp kiến trúc.')
            result = {}
            for key,reference in expected.items():
                value = archive[key]
                if value.shape!=tuple(reference.shape) or value.dtype!=reference.numpy().dtype or not np.isfinite(value).all():
                    raise ValueError('Shape/dtype/giá trị tensor không hợp lệ.')
                result[key]=torch.from_numpy(value.copy())
        return result
    except (OSError,zipfile.BadZipFile,TypeError) as exc:
        raise ValueError('Checkpoint NPZ không hợp lệ.') from exc


def validate_bundle(session, progress):
    import numpy as np
    import torch
    from torch import nn
    from torch.utils.data import DataLoader
    from .training import make_model, device, transforms, ImageDataset, metrics
    imported = session['imported']
    bundle = imported['metadata']
    dev=device()
    model=make_model(pretrained=False).to(dev).eval()
    _,eval_tf=transforms()
    path=store.session_dir(session['id'])/'imports'/f'{imported["id"]}.zip'
    output_dir=store.session_dir(session['id'])/'runs'/bundle['settings']['run_id']
    output_dir.mkdir(parents=True,exist_ok=True)
    progress(1,'Nạp backbone đã train trên Colab; không tải lại trọng số qua mạng.')
    with zipfile.ZipFile(path) as z:
        expected={k:v.cpu() for k,v in model.features.state_dict().items()}
        model.features.load_state_dict(numpy_state(z.read('backbone.npz'),expected))
        torch.save({k:v.cpu() for k,v in model.features.state_dict().items()},output_dir/'backbone.pt')
        xs,ys=[],[]
        with torch.inference_mode():
            for x,y in DataLoader(ImageDataset(session,'validation',eval_tf),batch_size=16,num_workers=0):
                xs.append(model.avgpool(model.features(x.to(dev))).flatten(1).cpu())
                ys.append(y)
        features,targets=torch.cat(xs),torch.cat(ys).numpy()
        trials=[]
        for index,candidate in enumerate(bundle['candidates']):
            head=nn.Sequential(nn.Dropout(candidate['config']['dropout']),nn.Linear(1280,3)).eval()
            best=None
            history=[]
            for checkpoint in candidate['checkpoints']:
                state=numpy_state(z.read(checkpoint['file']),head.state_dict())
                head.load_state_dict(state)
                with torch.inference_mode():
                    probabilities=head(features).softmax(1).numpy()
                score=metrics(targets,probabilities)
                history.append({k:checkpoint[k] for k in ['epoch','train_loss','train_accuracy']} |
                               {'val_loss':score['loss'],'val_accuracy':score['accuracy'],'val_macro_f1':score['macro_f1']})
                if best is None or (score['macro_f1'],-score['loss'])>(best['validation']['macro_f1'],-best['validation']['loss']):
                    best={'epoch':checkpoint['epoch'],'validation':score,'state':state}
                fraction=(index+checkpoint['epoch']/len(candidate['checkpoints']))/len(bundle['candidates'])
                progress(15+fraction*80,f'Validation {candidate["id"]} · epoch {checkpoint["epoch"]} · F1 {score["macro_f1"]:.3f}',
                         {'trial':index+1,'history':history})
            settings=bundle['settings']
            eligible=best['validation']['macro_f1']>=settings['min_f1'] and min(r['recall'] for r in best['validation']['per_class'])>=settings['min_recall']
            torch.save({'classifier_state':best['state'],'config':candidate['config'],'classes':store.CLASSES,
                        'epoch':best['epoch'],'validation':best['validation'],'split_sha256':session['splits']['sha256']},
                       output_dir/f'{candidate["id"]}.pt')
            trials.append({'id':candidate['id'],'config':candidate['config'],'best_epoch':best['epoch'],
                           'validation':best['validation'],'history':history,'eligible':eligible})
    ranked=sorted(trials,key=lambda t:(t['eligible'],t['validation']['macro_f1'],-t['validation']['loss']),reverse=True)
    result={'run_id':bundle['settings']['run_id'],'settings':bundle['settings'],'model':'efficientnet_b0','classes':store.CLASSES,
            'trials':trials,'recommended':ranked[0]['id'],'device':str(dev),'training_device':bundle['device'],
            'training_source':'colab','training_seconds':bundle['training_seconds'],'finished_at':store.now()}
    (output_dir/'training.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    progress(100,'Validation hoàn tất trên web. Chọn và chốt cấu hình; test vẫn chưa được đọc.')
    return result
