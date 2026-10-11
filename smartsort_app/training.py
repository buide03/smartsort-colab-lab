"""Train on train, choose with validation, freeze, then evaluate a sealed test."""
import csv
import json
import random
import time
import zipfile
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageOps
from torch import nn
from torch.utils.data import Dataset, DataLoader, TensorDataset
from torchvision import transforms as T
from torchvision.models import efficientnet_b0, EfficientNet_B0_Weights
from sklearn.metrics import (accuracy_score, f1_score, precision_recall_fscore_support,
                             confusion_matrix, log_loss)

from .store import CLASSES, CLASS_NAMES, session_dir, now


class Letterbox:
    def __call__(self, image):
        return ImageOps.pad(image.convert('RGB'), (224, 224), method=Image.Resampling.BICUBIC, color='white')


def transforms():
    norm = EfficientNet_B0_Weights.DEFAULT.transforms()
    evaluation = T.Compose([Letterbox(), T.ToTensor(), T.Normalize(norm.mean, norm.std)])
    train = T.Compose([Letterbox(), T.RandomHorizontalFlip(), T.RandomRotation(15, fill=255),
                       T.ColorJitter(brightness=.15, contrast=.15, saturation=.1),
                       T.ToTensor(), T.Normalize(norm.mean, norm.std)])
    return train, evaluation


class ImageDataset(Dataset):
    def __init__(self, session, split, transform):
        records = {r['id']: r for r in session['images']}
        self.records = [records[i] for i in session['splits']['ids'][split]]
        self.directory = session_dir(session['id']) / 'images'
        self.transform = transform

    def __len__(self):
        return len(self.records)

    def __getitem__(self, i):
        row = self.records[i]
        with Image.open(self.directory / (row['id'] + '.png')) as image:
            x = self.transform(image)
        return x, CLASSES.index(row['label'])


def make_model(dropout=.2, pretrained=True):
    model = efficientnet_b0(weights=EfficientNet_B0_Weights.DEFAULT if pretrained else None)
    model.classifier = nn.Sequential(nn.Dropout(dropout), nn.Linear(model.classifier[1].in_features, 3))
    for p in model.features.parameters():
        p.requires_grad = False
    return model


def device():
    result = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    if result.type == 'cpu':
        torch.set_num_threads(4)
    return result


def metrics(y, probabilities):
    prediction = probabilities.argmax(1)
    precision, recall, f1, support = precision_recall_fscore_support(y, prediction, labels=range(3), zero_division=0)
    return {'n': len(y), 'accuracy': float(accuracy_score(y, prediction)),
            'macro_f1': float(f1.mean()), 'loss': float(log_loss(y, probabilities, labels=range(3))),
            'per_class': [{'label': c, 'name': CLASS_NAMES[c], 'precision': float(precision[i]),
                           'recall': float(recall[i]), 'f1': float(f1[i]), 'support': int(support[i])}
                          for i, c in enumerate(CLASSES)],
            'confusion_matrix': confusion_matrix(y, prediction, labels=range(3)).tolist()}


def train_trials(session, settings, progress):
    seed = session['splits']['seed']
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    dev = device()
    train_tf, eval_tf = transforms()
    progress(1, 'Đang tải EfficientNet-B0 pretrained ImageNet; lần đầu cần Internet.')
    model = make_model().to(dev)
    model.eval()
    start = time.perf_counter()

    @torch.inference_mode()
    def features(split, transform):
        dl = DataLoader(ImageDataset(session, split, transform), batch_size=16, num_workers=0)
        xs, ys = [], []
        for x, y in dl:
            xs.append(model.avgpool(model.features(x.to(dev))).flatten(1).cpu())
            ys.append(y)
        return torch.cat(xs), torch.cat(ys)

    train_x, train_y = [], []
    for view in range(settings['views']):
        x, y = features('train', eval_tf if view == 0 else train_tf)
        train_x.append(x)
        train_y.append(y)
        progress(5 + (view+1)*15/settings['views'], f'Trích đặc trưng train {view+1}/{settings["views"]}. Không đọc test.')
    train_x, train_y = torch.cat(train_x), torch.cat(train_y)
    val_x, val_y = features('validation', eval_tf)
    output_dir = session_dir(session['id']) / 'runs' / settings['run_id']
    output_dir.mkdir(parents=True, exist_ok=True)
    criterion = nn.CrossEntropyLoss()
    trials = []
    for trial_index, config in enumerate(settings['candidates']):
        torch.manual_seed(seed)  # same initialization/order seed for a fairer comparison
        model.classifier = nn.Sequential(nn.Dropout(config['dropout']), nn.Linear(1280, 3)).to(dev)
        optimizer = torch.optim.AdamW(model.classifier.parameters(), lr=config['lr'], weight_decay=config['weight_decay'])
        dl = DataLoader(TensorDataset(train_x, train_y), batch_size=16, shuffle=True)
        best_score, best_loss, stale = -1., float('inf'), 0
        history, best_state, best_metrics, best_epoch = [], None, None, None
        for epoch in range(1, settings['epochs']+1):
            model.eval()
            model.classifier.train()
            total_loss = correct = count = 0
            for x, y in dl:
                x, y = x.to(dev), y.to(dev)
                optimizer.zero_grad(set_to_none=True)
                logits = model.classifier(x)
                loss = criterion(logits, y)
                loss.backward()
                optimizer.step()
                total_loss += float(loss.item()) * len(y)
                correct += int((logits.argmax(1) == y).sum())
                count += len(y)
            model.eval()
            with torch.inference_mode():
                probabilities = model.classifier(val_x.to(dev)).softmax(1).cpu().numpy()
            current = metrics(val_y.numpy(), probabilities)
            history.append({'epoch': epoch, 'train_loss': total_loss/count,
                            'train_accuracy': correct/count, 'val_loss': current['loss'],
                            'val_accuracy': current['accuracy'], 'val_macro_f1': current['macro_f1']})
            improved = current['macro_f1'] > best_score + 1e-8 or (
                abs(current['macro_f1'] - best_score) < 1e-8 and current['loss'] < best_loss - 1e-5)
            if improved:
                best_score, best_loss, stale = current['macro_f1'], current['loss'], 0
                best_state = {k: v.detach().cpu().clone() for k, v in model.classifier.state_dict().items()}
                best_metrics, best_epoch = current, epoch
            else:
                stale += 1
            completed = (trial_index + epoch/settings['epochs']) / len(settings['candidates'])
            progress(25 + completed*70,
                     f'Cấu hình {trial_index+1}/{len(settings["candidates"])} · epoch {epoch}/{settings["epochs"]} · validation F1 {current["macro_f1"]:.3f}',
                     {'trial': trial_index+1, 'history': history})
            if stale >= settings['patience']:
                break
        trial_id = f'trial_{trial_index+1}'
        checkpoint_path = output_dir / f'{trial_id}.pt'
        torch.save({'classifier_state': best_state, 'config': config, 'classes': CLASSES,
                    'epoch': best_epoch, 'validation': best_metrics,
                    'split_sha256': session['splits']['sha256']}, checkpoint_path)
        eligible = best_metrics['macro_f1'] >= settings['min_f1'] and min(r['recall'] for r in best_metrics['per_class']) >= settings['min_recall']
        trials.append({'id': trial_id, 'config': config, 'best_epoch': best_epoch,
                       'validation': best_metrics, 'history': history, 'eligible': eligible})
    # Store the actual backbone, so the final model never requires a second network download.
    torch.save({k: v.detach().cpu() for k, v in model.features.state_dict().items()}, output_dir / 'backbone.pt')
    ranked = sorted(trials, key=lambda t: (t['eligible'], t['validation']['macro_f1'], -t['validation']['loss']), reverse=True)
    result = {'run_id': settings['run_id'], 'settings': settings, 'trials': trials,
              'recommended': ranked[0]['id'], 'device': str(dev), 'training_seconds': time.perf_counter()-start,
              'model': 'efficientnet_b0', 'classes': CLASSES, 'finished_at': now()}
    (output_dir / 'training.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    progress(100, 'Huấn luyện xong. So sánh validation rồi chốt cấu hình; test vẫn chưa được đọc.')
    return result


def selected_model(session):
    selected = session['selected']
    run_dir = session_dir(session['id']) / 'runs' / session['training']['run_id']
    checkpoint = torch.load(run_dir / f'{selected["trial_id"]}.pt', map_location='cpu', weights_only=True)
    model = make_model(checkpoint['config']['dropout'], pretrained=False)
    model.features.load_state_dict(torch.load(run_dir / 'backbone.pt', map_location='cpu', weights_only=True))
    model.classifier.load_state_dict(checkpoint['classifier_state'])
    return model


def export_manifest(session, output_dir):
    assignments = {i: split for split, ids in session['splits']['ids'].items() for i in ids}
    with (output_dir / 'labels_and_splits.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['id','filename','label','split','pixel_hash'])
        writer.writeheader()
        for r in session['images']:
            writer.writerow({k: assignments.get(r['id'], 'excluded') if k == 'split' else r[k] for k in writer.fieldnames})


def test_model(session, progress):
    dev = device()
    model = selected_model(session).to(dev).eval()
    _, eval_tf = transforms()
    dataset = ImageDataset(session, 'test', eval_tf)
    dl = DataLoader(dataset, batch_size=16, num_workers=0)
    probabilities, targets = [], []
    start = time.perf_counter()
    with torch.inference_mode():
        for index, (x, y) in enumerate(dl):
            probabilities.append(model(x.to(dev)).softmax(1).cpu().numpy())
            targets.append(y.numpy())
            progress((index+1)/len(dl)*80, f'Đang đánh giá test {(index+1)*16 if index+1<len(dl) else len(dataset)}/{len(dataset)} ảnh.')
    probs, y = np.concatenate(probabilities), np.concatenate(targets)
    result = metrics(y, probs)
    result['forward_and_loading_seconds'] = time.perf_counter()-start
    result['device'] = str(dev)
    result['finished_at'] = now()
    result['trial_id'] = session['selected']['trial_id']
    result['confidence_threshold'] = session['training']['settings']['confidence_threshold']
    predicted, confidence = probs.argmax(1), probs.max(1)
    accepted = confidence >= result['confidence_threshold']
    result['coverage'] = float(accepted.mean())
    result['accepted_accuracy'] = float((predicted[accepted] == y[accepted]).mean()) if accepted.any() else None
    result['high_confidence_errors'] = int(((predicted != y) & accepted).sum())
    p, n, z = result['accuracy'], len(y), 1.96
    center = (p + z*z/(2*n))/(1+z*z/n)
    half = z*np.sqrt(p*(1-p)/n+z*z/(4*n*n))/(1+z*z/n)
    result['accuracy_ci95'] = [float(center-half), float(center+half)]
    result['brier_multiclass'] = float(((probs-np.eye(3)[y])**2).sum(1).mean())
    result['predictions'] = [{'id': r['id'], 'filename': r['filename'], 'true_label': r['label'],
                              'predicted_label': CLASSES[int(predicted[i])], 'confidence': float(confidence[i]),
                              'correct': bool(predicted[i] == y[i]),
                              **{f'prob_{c}': float(probs[i,j]) for j,c in enumerate(CLASSES)}}
                             for i,r in enumerate(dataset.records)]
    output_dir = session_dir(session['id']) / 'results'
    output_dir.mkdir(exist_ok=True)
    torch.save({'model_state': {k: v.detach().cpu() for k,v in model.state_dict().items()},
                'classes': CLASSES, 'config': session['selected'],
                'preprocessing': {'size': 224, 'fill': 'white',
                                  'mean': [0.485,0.456,0.406], 'std': [0.229,0.224,0.225]}}, output_dir / 'model.pt')
    (output_dir / 'test_results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    (output_dir / 'locked_config.json').write_text(json.dumps(session['selected'], ensure_ascii=False, indent=2), encoding='utf-8')
    (output_dir / 'training.json').write_text(json.dumps(session['training'], ensure_ascii=False, indent=2), encoding='utf-8')
    export_manifest(session, output_dir)
    with (output_dir / 'test_predictions.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(result['predictions'][0]))
        writer.writeheader()
        writer.writerows(result['predictions'])
    with (output_dir / 'per_class_metrics.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(result['per_class'][0]))
        writer.writeheader()
        writer.writerows(result['per_class'])
    weakest = min(result['per_class'], key=lambda r: r['recall'])
    selected_trial = next(t for t in session['training']['trials'] if t['id'] == session['selected']['trial_id'])
    cm = np.array(result['confusion_matrix'])
    np.fill_diagonal(cm, 0)
    i, j = np.unravel_index(cm.argmax(), cm.shape)
    confusion_text = f'{CLASS_NAMES[CLASSES[i]]} → {CLASS_NAMES[CLASSES[j]]}: {int(cm[i,j])} ảnh' if cm.max() else 'Không có ảnh nhầm lớp trong test.'
    result['observations'] = [
        f'Recall thấp nhất: {weakest["name"]} ({weakest["recall"]:.1%}).',
        f'Cặp nhầm nhiều nhất: {confusion_text}',
        f'Validation macro-F1 {selected_trial["validation"]["macro_f1"]:.3f}; test macro-F1 {result["macro_f1"]:.3f}.',
        f'{result["high_confidence_errors"]} ảnh sai dù confidence ≥ {result["confidence_threshold"]:.2f}.',
        'Kiểm tra ảnh sai theo ánh sáng, nền, góc chụp, che khuất, biến dạng và bề mặt phản chiếu; cần thêm mẫu có nhãn điều kiện để kết luận nguyên nhân.',
        'Sau khi xem test, thay đổi cấu hình cần một tập test mới độc lập.']
    report = f'''# SmartSort — báo cáo bài thực hành

Phiên: {session['title']}
Mô hình: EfficientNet-B0 pretrained ImageNet, backbone đóng băng, học classifier.
Cấu hình đã chốt: {json.dumps(session['selected'], ensure_ascii=False)}
Tập train/validation/test: {len(session['splits']['ids']['train'])}/{len(session['splits']['ids']['validation'])}/{len(y)}.
Accuracy test: {result['accuracy']:.1%}; khoảng Wilson 95% [{result['accuracy_ci95'][0]:.1%}, {result['accuracy_ci95'][1]:.1%}].
Macro-F1 test: {result['macro_f1']:.3f}; log-loss: {result['loss']:.3f}; Brier: {result['brier_multiclass']:.3f}.

## Nhận xét
''' + '\n'.join('- '+s for s in result['observations']) + '''

## Các yếu tố đánh giá
- Hiệu năng tổng thể: accuracy và macro-F1, so với baseline luôn chọn lớp chiếm đa số.
- Từng vật liệu: precision/recall/F1, support và confusion matrix.
- Overfit: learning curves train/validation và chênh validation/test; dữ liệu nhỏ dễ biến động.
- Độ tin cậy: lỗi tự tin cao, log-loss/Brier, coverage và accuracy trên ảnh được chấp nhận.
- Chất lượng nhãn và dữ liệu: ảnh sai nhãn, ảnh gần trùng, cùng vật thể xuất hiện ở nhiều tập.
- Điều kiện ảnh: ánh sáng, nền, góc chụp, che khuất, hình dạng, phản chiếu; xem ảnh sai rồi lập giả thuyết kiểm thử mới.
- Giới hạn: không huấn luyện unknown, confidence không bảo đảm nhận biết vật ngoài ba lớp. Khoảng tin cậy giả định mẫu độc lập.

## Câu hỏi thảo luận
1. Vì sao không dùng test để chọn learning rate hoặc epoch?
2. Lớp nào có recall thấp nhất? Hệ quả với hệ thống phân loại rác là gì?
3. Train loss giảm nhưng validation loss tăng gợi ý điều gì?
4. Vì sao dự đoán sai vẫn có confidence cao?
5. Cần dữ liệu mới nào trước khi cải tiến và đánh giá lại mô hình?
'''
    (output_dir / 'REPORT.md').write_text(report, encoding='utf-8')
    (output_dir / 'test_results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    with zipfile.ZipFile(output_dir / 'SmartSort_Results.zip', 'w', zipfile.ZIP_DEFLATED) as z:
        for p in output_dir.iterdir():
            if p.suffix != '.zip':
                z.write(p, p.name)
    progress(100, 'Hoàn tất test. Đã lưu báo cáo, CSV và mô hình; kết quả test được giữ cố định.')
    return result
