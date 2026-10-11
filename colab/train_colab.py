"""Train only on a SmartSort train package. Validation and test stay on the web server."""
import io
import json
import random
import time
import zipfile
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.utils.data import Dataset, DataLoader, TensorDataset
from torchvision.models import efficientnet_b0, EfficientNet_B0_Weights
from torchvision import transforms as T
from PIL import Image, ImageOps


def npz_state(state):
    buffer = io.BytesIO()
    np.savez_compressed(buffer, **{k: v.detach().cpu().numpy() for k, v in state.items()})
    return buffer.getvalue()


def train_package(package_path, result_path='SmartSort_Colab_Models.zip', require_cuda=True):
    dev = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    if require_cuda and dev.type != 'cuda':
        raise RuntimeError('Chọn Runtime → Change runtime type → T4 GPU, rồi chạy lại. Notebook không tự chuyển train sang CPU.')
    if dev.type == 'cpu':
        torch.set_num_threads(4)
    with zipfile.ZipFile(package_path) as package:
        metadata = json.loads(package.read('train.json'))
        assert metadata['kind'] == 'smartsort_train' and metadata['version'] == 1
        assert metadata['classes'] == ['metal', 'paper', 'plastic']
        assert not any(p.startswith(('validation/', 'test/')) for p in package.namelist())
        settings = metadata['settings']
        seed = metadata['seed']
        random.seed(seed)
        np.random.seed(seed)
        torch.manual_seed(seed)
        if dev.type == 'cuda':
            torch.cuda.manual_seed_all(seed)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
        weights = EfficientNet_B0_Weights.DEFAULT
        norm = weights.transforms()
        def letterbox(image):
            return ImageOps.pad(image.convert('RGB'), (224,224), method=Image.Resampling.BICUBIC, color='white')
        evaluation = T.Compose([T.Lambda(letterbox), T.ToTensor(), T.Normalize(norm.mean,norm.std)])
        augmentation = T.Compose([T.Lambda(letterbox), T.RandomHorizontalFlip(), T.RandomRotation(15,fill=255),
                                  T.ColorJitter(brightness=.15,contrast=.15,saturation=.1),T.ToTensor(),T.Normalize(norm.mean,norm.std)])
        class TrainImages(Dataset):
            def __init__(self, transform):
                self.transform = transform
            def __len__(self):
                return len(metadata['images'])
            def __getitem__(self,i):
                row = metadata['images'][i]
                with Image.open(io.BytesIO(package.read('train/'+row['id']+'.png'))) as image:
                    x = self.transform(image)
                return x, metadata['classes'].index(row['label'])
        model = efficientnet_b0(weights=weights).to(dev).eval()
        for p in model.features.parameters():
            p.requires_grad = False
        start = time.perf_counter()
        xs, ys = [], []
        with torch.inference_mode():
            for view in range(settings['views']):
                for x,y in DataLoader(TrainImages(evaluation if view == 0 else augmentation),batch_size=16,num_workers=0):
                    xs.append(model.avgpool(model.features(x.to(dev))).flatten(1).cpu())
                    ys.append(y)
                print(f'Train views {view+1}/{settings["views"]}; validation/test không có trong gói.',flush=True)
        features, labels = torch.cat(xs), torch.cat(ys)
        criterion = nn.CrossEntropyLoss()
        candidates = []
        with zipfile.ZipFile(result_path,'w',zipfile.ZIP_DEFLATED) as output:
            output.writestr('backbone.npz',npz_state(model.features.state_dict()))
            for index,config in enumerate(settings['candidates']):
                torch.manual_seed(seed)
                head = nn.Sequential(nn.Dropout(config['dropout']),nn.Linear(1280,3)).to(dev)
                optimizer = torch.optim.AdamW(head.parameters(),lr=config['lr'],weight_decay=config['weight_decay'])
                trial_id = f'trial_{index+1}'
                history = []
                dl = DataLoader(TensorDataset(features,labels),batch_size=16,shuffle=True)
                for epoch in range(1,settings['epochs']+1):
                    head.train()
                    loss_sum = correct = count = 0
                    for x,y in dl:
                        x,y = x.to(dev),y.to(dev)
                        optimizer.zero_grad(set_to_none=True)
                        logits = head(x)
                        loss = criterion(logits,y)
                        loss.backward()
                        optimizer.step()
                        loss_sum += loss.item()*len(y)
                        correct += int((logits.argmax(1)==y).sum())
                        count += len(y)
                    filename = f'heads/{trial_id}/epoch_{epoch:03d}.npz'
                    output.writestr(filename,npz_state(head.state_dict()))
                    history.append({'epoch':epoch,'file':filename,'train_loss':loss_sum/count,'train_accuracy':correct/count})
                    if epoch == 1 or epoch % 10 == 0:
                        print(f'{trial_id} epoch {epoch}: train loss {loss_sum/count:.4f}',flush=True)
                candidates.append({'id':trial_id,'config':config,'checkpoints':history})
            bundle = {'kind':'smartsort_colab_models','version':1,'model':'efficientnet_b0',
                      'classes':metadata['classes'],'request_id':metadata['request_id'],
                      'session_id':metadata['session_id'],'split_sha256':metadata['split_sha256'],
                      'settings':settings,'candidates':candidates,'training_seconds':time.perf_counter()-start,
                      'device':str(dev),'torch_version':str(torch.__version__),'torchvision_weights':str(weights),
                      'preprocessing':{'size':224,'fill':'white','mean':list(norm.mean),'std':list(norm.std)}}
            output.writestr('bundle.json',json.dumps(bundle,ensure_ascii=False,indent=2))
    print('Đã xuất',result_path,'— chưa chạy validation, chưa đọc test.',flush=True)
    return str(Path(result_path).resolve())


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package')
    parser.add_argument('--output',default='SmartSort_Colab_Models.zip')
    parser.add_argument('--allow-cpu',action='store_true',help='For development verification only')
    args = parser.parse_args()
    train_package(args.package,args.output,require_cuda=not args.allow_cpu)
