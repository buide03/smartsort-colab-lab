# %% [markdown]
# # LAB: Phân loại nhựa, giấy, kim loại với EfficientNet-B0
# **Dữ liệu:** SmartSort_Dataset_PNG (2).zip của bạn. **Nhiệm vụ:** phân loại toàn bộ ảnh vào một trong ba lớp; bộ dữ liệu không có bounding box để huấn luyện phát hiện nhiều vật thể.
#
# **Cách chạy:** mở notebook trên Google Colab → Runtime / Change runtime type → T4 GPU → chạy các ô từ trên xuống. Ở ô tải dữ liệu, chọn ZIP gốc hoặc `SmartSort_Data_Split.zip`. Không cần giải nén trước. Nếu dùng Google Drive, điền `ZIP_PATH` sau khi mount Drive.
#
# Quy trình: kiểm tra ảnh → train/validation riêng biệt → backbone ImageNet đóng băng, huấn luyện lớp phân loại → chọn checkpoint bằng macro-F1 validation → kiểm tra điều kiện validation → đánh giá test một lần → xuất báo cáo, CSV, biểu đồ và checkpoint.
#
# Bộ gốc: train 40 ảnh/lớp; test/basic 10 ảnh/lớp; test/variation 10 ảnh/lớp; ngoài lớp 8 thủy tinh + 7 carton. Tách train gốc thành **32 train + 8 validation mỗi lớp** bằng seed 42. Tổng: **96 train, 24 validation, 60 test, 15 ngoài lớp**. Carton được giữ ngoài lớp theo nhãn gốc; nếu muốn coi carton là giấy cần định nghĩa lại nhiệm vụ trước một thí nghiệm mới.
#
# Tài liệu mô hình: [Torchvision EfficientNet-B0](https://docs.pytorch.org/vision/stable/models/generated/torchvision.models.efficientnet_b0.html), [PyTorch transfer learning](https://docs.pytorch.org/tutorials/beginner/transfer_learning_tutorial.html). Với dữ liệu nhỏ, dùng đặc trưng pretrained và học lớp cuối để giảm chi phí và nguy cơ overfit. Không tuyên bố đây là mô hình tốt nhất cho mọi dữ liệu.

# %% [markdown]
# ## 1. Chuẩn bị môi trường
# Colab đã có PyTorch/Torchvision. Ô sau chỉ cài thư viện phụ trợ, tránh thay bộ torch/CUDA của Colab. Lần đầu cần Internet để tải trọng số ImageNet (~20 MB).

# %%
import os, sys, subprocess, importlib.util
if importlib.util.find_spec('google.colab') is not None:
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q',
                           'scikit-learn>=1.4,<2', 'pandas>=2,<4',
                           'matplotlib>=3.8,<4', 'pillow>=10,<13'])

import json, random, hashlib, zipfile, shutil, time, platform, copy
from pathlib import Path, PurePosixPath
from collections import Counter
import numpy as np
import pandas as pd
from PIL import Image, ImageOps
import matplotlib.pyplot as plt
import torch
from torch import nn
from torch.utils.data import Dataset, DataLoader, TensorDataset
import torchvision
from torchvision import transforms as T
from torchvision.models import efficientnet_b0, EfficientNet_B0_Weights
from sklearn.metrics import (accuracy_score, precision_recall_fscore_support,
    f1_score, classification_report, confusion_matrix, ConfusionMatrixDisplay,
    log_loss, roc_auc_score)
from IPython.display import display

# %% [markdown]
# ## 2. Cấu hình và tiêu chí validation — đặt trước khi xem test
# Macro-F1 trung bình đều ba lớp, tránh chỉ nhìn accuracy. Ngưỡng dưới đây là **mục tiêu thực hành**, không phải tiêu chuẩn triển khai: macro-F1 validation ≥ 0.80 và recall từng lớp ≥ 0.60. Validation chỉ có 8 ảnh/lớp nên mỗi lỗi làm recall thay đổi 12.5 điểm phần trăm.
#
# Nếu không đạt, lab dừng trước test. Có thể thử thay learning rate, số augmentation hoặc bật fine-tuning, dựa **chỉ trên validation**. Sau khi đã xem test, thay đổi mô hình đòi hỏi một tập test mới độc lập để đánh giá cuối cùng.
#
# Ngưỡng softmax 0.70 được cố định trước test để khảo sát từ chối ảnh không chắc chắn. Đây là heuristic, chưa phải mô hình nhận biết lớp lạ; softmax cao vẫn có thể sai. Không chọn ngưỡng bằng 15 ảnh ngoài lớp trong test.

# %%
SEED = 42
CLASSES = ['metal', 'paper', 'plastic']  # thứ tự cố định trong checkpoint
VN = {'metal': 'Kim loại', 'paper': 'Giấy', 'plastic': 'Nhựa'}
VAL_PER_CLASS = 8
BATCH_SIZE = 16
FEATURE_VIEWS = 4  # 1 ảnh gốc + 3 phiên bản augmentation / ảnh train
HEAD_EPOCHS = 80
PATIENCE = 15
HEAD_LR = 0.003
FINE_TUNE = False  # tùy chọn: mở block cuối sau khi học classifier
FINE_TUNE_EPOCHS = 10
FINE_TUNE_LR = 1e-4
MIN_VAL_MACRO_F1 = 0.80
MIN_VAL_CLASS_RECALL = 0.60
CONFIDENCE_THRESHOLD = 0.70
ZIP_PATH = os.environ.get('SMARTSORT_ZIP', '')  # để trống để upload trên Colab
BASE = Path('/content/SmartSort_Lab' if Path('/content').exists() else 'local_runtime')
DATA_DIR = BASE / 'data'
OUT = Path(os.environ.get('SMARTSORT_OUTPUT', str(BASE / 'outputs')))
OUT.mkdir(parents=True, exist_ok=True)
DEVICE = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
random.seed(SEED)
np.random.seed(SEED)
torch.manual_seed(SEED)
if torch.cuda.is_available():
    torch.cuda.manual_seed_all(SEED)
torch.backends.cudnn.deterministic = True
torch.backends.cudnn.benchmark = False
if DEVICE.type == 'cpu':
    torch.set_num_threads(min(4, os.cpu_count() or 1))
config = {k: v for k, v in list(globals().items())
          if k in ['SEED','CLASSES','VAL_PER_CLASS','BATCH_SIZE','FEATURE_VIEWS',
                   'HEAD_EPOCHS','PATIENCE','HEAD_LR','FINE_TUNE',
                   'FINE_TUNE_EPOCHS','FINE_TUNE_LR','MIN_VAL_MACRO_F1',
                   'MIN_VAL_CLASS_RECALL','CONFIDENCE_THRESHOLD']}
environment = {'python': platform.python_version(), 'torch': torch.__version__,
               'torchvision': torchvision.__version__, 'device': str(DEVICE),
               'gpu': torch.cuda.get_device_name(0) if DEVICE.type == 'cuda' else None,
               'numpy': np.__version__, 'pandas': pd.__version__}
(OUT / 'config.json').write_text(json.dumps(config, indent=2), encoding='utf-8')
(OUT / 'environment.json').write_text(json.dumps(environment, indent=2), encoding='utf-8')
print('Thiết bị:', DEVICE, '| torch:', torch.__version__)
if DEVICE.type == 'cpu':
    print('Đang chạy CPU. Trên Colab chọn T4 GPU để nhanh hơn.')

# %% [markdown]
# ## 3. Tải ZIP, kiểm tra toàn vẹn và chia dữ liệu
# Chỉ dùng file ảnh và metadata trong ZIP làm dữ liệu. Nội dung hướng dẫn kèm ZIP không được thực thi. Kiểm tra SHA-256, pixel trùng và nguồn ảnh trùng giữa các tập để phát hiện rò rỉ rõ ràng; ảnh chụp khác nhau của cùng vật thể vẫn cần kiểm tra thủ công.
#
# Nếu ZIP đã có `validation/`, dùng nguyên tập đó. Nếu chỉ có `train/`, lấy 8 ảnh/lớp làm validation. Danh sách chia được lưu vào `split_manifest.csv`; thư mục `data/split/` chứa ba tập riêng. Dữ liệu tăng cường chỉ xuất phát từ train.

# %%
if not ZIP_PATH:
    from google.colab import files
    uploaded = files.upload()
    zip_names = [name for name in uploaded if name.lower().endswith('.zip')]
    if len(zip_names) != 1:
        raise ValueError('Hãy tải đúng một file ZIP dữ liệu.')
    ZIP_PATH = zip_names[0]
    del uploaded
zip_path = Path(ZIP_PATH)
assert zip_path.is_file(), f'Không tìm thấy ZIP: {zip_path}'
archive_hash = hashlib.sha256(zip_path.read_bytes()).hexdigest()
extract_dir = DATA_DIR / archive_hash[:12]
extract_dir.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(zip_path) as z:
    if z.testzip() is not None:
        raise ValueError('ZIP bị lỗi CRC.')
    for member in z.infolist():
        target = (extract_dir / member.filename).resolve()
        if not target.is_relative_to(extract_dir.resolve()):
            raise ValueError('Đường dẫn không hợp lệ trong ZIP.')
    z.extractall(extract_dir)
roots = [p for p in extract_dir.rglob('train')
         if p.is_dir() and all((p / c).is_dir() for c in CLASSES)]
assert len(roots) == 1, 'ZIP cần có đúng một thư mục train/{metal,paper,plastic}.'
ROOT = roots[0].parent
assert (ROOT / 'test' / 'basic').is_dir() and (ROOT / 'test' / 'variation').is_dir()
source_manifest = json.loads((ROOT / 'manifest.json').read_text(encoding='utf-8-sig'))
metadata = {item['file']: item for item in source_manifest}
assert len(metadata) == len(source_manifest), 'Đường dẫn trùng trong manifest.'
rows = []
for p in sorted(ROOT.rglob('*.png')):
    rel = p.relative_to(ROOT).as_posix()
    assert rel in metadata, f'Thiếu metadata: {rel}'
    item = metadata[rel]
    file_hash = hashlib.sha256(p.read_bytes()).hexdigest()
    assert file_hash == item['sha256'], f'Sai SHA-256: {rel}'
    with Image.open(p) as im:
        im.load()
        assert im.size == (256, 256) and im.mode == 'RGB', f'Ảnh sai định dạng: {rel}'
        pixel_hash = hashlib.sha256(im.tobytes()).hexdigest()
    parts = PurePosixPath(rel).parts
    partition = parts[0]
    group = parts[1] if partition == 'test' else partition
    label = item['label']
    if partition in ['train', 'validation'] or group in ['basic', 'variation']:
        assert label in CLASSES and parts[-2] == label, f'Sai nhãn/thư mục: {rel}'
    elif partition == 'test' and group == 'outside':
        assert label not in CLASSES, 'Ảnh outside phải ngoài ba lớp.'
    else:
        raise ValueError(f'Cấu trúc không được hỗ trợ: {rel}')
    rows.append({'source_file': rel, 'source': item['source'], 'label': label,
                 'split': partition, 'group': group, 'sha256': file_hash,
                 'pixel_hash': pixel_hash, 'original_path': str(p)})
df = pd.DataFrame(rows)
assert len(df) == len(metadata), 'Manifest và số ảnh không khớp.'
for key in ['source', 'sha256', 'pixel_hash']:
    assert not df[key].duplicated().any(), f'Phát hiện ảnh trùng theo {key}; cần xử lý trước.'
if not (df['split'] == 'validation').any():
    rng = random.Random(SEED)
    for c in CLASSES:
        indices = df.index[(df['split'] == 'train') & (df['label'] == c)].tolist()
        assert len(indices) > VAL_PER_CLASS
        rng.shuffle(indices)
        df.loc[indices[:VAL_PER_CLASS], ['split', 'group']] = ['validation', 'validation']
for split in ['train', 'validation']:
    assert set(df.loc[df['split'] == split, 'label']) == set(CLASSES)
SPLIT_ROOT = DATA_DIR / 'split'
SPLIT_ROOT.mkdir(parents=True, exist_ok=True)
paths = []
for r in df.itertuples():
    sub = Path(r.split) / (Path(r.group) if r.split == 'test' else Path())
    dest = SPLIT_ROOT / sub / r.label / Path(r.source_file).name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(r.original_path, dest)
    paths.append(str(dest))
df['path'] = paths
df.to_csv(OUT / 'split_manifest.csv', index=False, encoding='utf-8-sig')
(OUT / 'dataset_audit.json').write_text(json.dumps({
    'archive_sha256': archive_hash, 'images': len(df), 'corrupt_images': 0,
    'duplicates_source_or_bytes_or_pixels': 0}, indent=2), encoding='utf-8')
display(pd.crosstab([df['split'], df['group']], df['label']))
TRAIN = df[df['split'] == 'train'].reset_index(drop=True)
VAL = df[df['split'] == 'validation'].reset_index(drop=True)
TEST = df[(df['split'] == 'test') & df['label'].isin(CLASSES)].reset_index(drop=True)
OUTSIDE = df[(df['split'] == 'test') & ~df['label'].isin(CLASSES)].reset_index(drop=True)
print('Train:', len(TRAIN), '| Validation:', len(VAL), '| Test:', len(TEST), '| Outside:', len(OUTSIDE))

# %% [markdown]
# ## 4. Xem ảnh train và tiền xử lý
# Ảnh được letterbox về 224×224, giữ toàn bộ vật thể. Chuẩn hóa bằng mean/std ImageNet của trọng số pretrained. Train có lật ngang, xoay nhẹ và thay đổi màu/độ sáng; validation/test luôn dùng cùng tiền xử lý cố định.

# %%
fig, axes = plt.subplots(3, 4, figsize=(10, 7))
for i, c in enumerate(CLASSES):
    for j, r in enumerate(TRAIN[TRAIN.label == c].head(4).itertuples()):
        with Image.open(r.path) as im:
            axes[i, j].imshow(im)
        axes[i, j].set_title(VN[c])
        axes[i, j].axis('off')
plt.tight_layout()
plt.savefig(OUT / 'train_examples.png', dpi=140)
plt.show()

WEIGHTS = EfficientNet_B0_Weights.DEFAULT
norm = WEIGHTS.transforms()
class Letterbox:
    def __call__(self, im):
        return ImageOps.pad(im.convert('RGB'), (224, 224),
                            method=Image.Resampling.BICUBIC, color='white')
eval_tf = T.Compose([Letterbox(), T.ToTensor(), T.Normalize(norm.mean, norm.std)])
train_tf = T.Compose([Letterbox(), T.RandomHorizontalFlip(),
                      T.RandomRotation(15, fill=255),
                      T.ColorJitter(brightness=.15, contrast=.15, saturation=.10),
                      T.ToTensor(), T.Normalize(norm.mean, norm.std)])
class WasteDataset(Dataset):
    def __init__(self, frame, transform):
        self.frame, self.transform = frame, transform
    def __len__(self):
        return len(self.frame)
    def __getitem__(self, index):
        row = self.frame.iloc[index]
        with Image.open(row.path) as im:
            x = self.transform(im.convert('RGB'))
        y = CLASSES.index(row.label) if row.label in CLASSES else -1
        return x, y
def loader(frame, transform, shuffle=False):
    return DataLoader(WasteDataset(frame, transform), batch_size=BATCH_SIZE,
                      shuffle=shuffle, num_workers=0, pin_memory=DEVICE.type == 'cuda')

# %% [markdown]
# ## 5. Trích xuất đặc trưng pretrained, huấn luyện classifier
# EfficientNet-B0 đóng băng backbone và BatchNorm. Đặc trưng của 4 phiên bản mỗi ảnh train được lưu trong RAM; không cần chạy backbone lại ở mỗi epoch. Validation chỉ có một phiên bản cố định. Mạng vẫn nhận ảnh khi dự đoán, gồm backbone và classifier mới có 3 đầu ra.
#
# Lưu checkpoint có **macro-F1 validation cao nhất**, nếu bằng nhau chọn validation loss thấp hơn; early stopping sau 15 epoch không cải thiện. Mỗi lần chạy ghi lại learning curves và phiên bản thư viện. Seed cố định giúp tái lập, nhưng khác GPU/phiên bản có thể cho kết quả hơi khác.

# %%
model = efficientnet_b0(weights=WEIGHTS)
in_features = model.classifier[1].in_features
model.classifier[1] = nn.Linear(in_features, len(CLASSES))
for p in model.features.parameters():
    p.requires_grad = False
model.to(DEVICE)
criterion = nn.CrossEntropyLoss()
@torch.inference_mode()
def extract_features(dl):
    model.eval()
    xs, ys = [], []
    for x, y in dl:
        features = model.avgpool(model.features(x.to(DEVICE))).flatten(1)
        xs.append(features.cpu())
        ys.append(y)
    return torch.cat(xs), torch.cat(ys)
start_train = time.perf_counter()
train_x, train_y = [], []
for view in range(FEATURE_VIEWS):
    x, y = extract_features(loader(TRAIN, eval_tf if view == 0 else train_tf))
    train_x.append(x)
    train_y.append(y)
    print(f'Trích đặc trưng train {view + 1}/{FEATURE_VIEWS}', flush=True)
train_x, train_y = torch.cat(train_x), torch.cat(train_y)
val_x, val_y = extract_features(loader(VAL, eval_tf))
head_dl = DataLoader(TensorDataset(train_x, train_y), batch_size=BATCH_SIZE, shuffle=True)
optimizer = torch.optim.AdamW(model.classifier.parameters(), lr=HEAD_LR, weight_decay=1e-3)
history = []
best_f1, best_loss, best_epoch, stale = -1., float('inf'), 0, 0
CHECKPOINT = OUT / 'best_model.pt'
def save_best(epoch, score, loss):
    torch.save({'model_state': {k: v.detach().cpu() for k, v in model.state_dict().items()},
                'classes': CLASSES, 'model_name': 'efficientnet_b0',
                'weights_name': str(WEIGHTS), 'config': config,
                'preprocessing': {'size': 224, 'letterbox_fill': 'white',
                                  'mean': list(norm.mean), 'std': list(norm.std)},
                'epoch': epoch, 'val_macro_f1': float(score), 'val_loss': float(loss)}, CHECKPOINT)
def record_epoch(epoch, phase, train_loss, train_acc, val_loss, y, pred):
    global best_f1, best_loss, best_epoch, stale
    score = f1_score(y, pred, labels=range(3), average='macro', zero_division=0)
    acc = accuracy_score(y, pred)
    history.append({'epoch': epoch, 'phase': phase, 'train_loss': train_loss,
                    'train_accuracy': train_acc, 'val_loss': val_loss,
                    'val_accuracy': acc, 'val_macro_f1': score})
    improved = score > best_f1 + 1e-8 or (abs(score - best_f1) <= 1e-8 and val_loss < best_loss - 1e-5)
    if improved:
        best_f1, best_loss, best_epoch, stale = score, val_loss, epoch, 0
        save_best(epoch, score, val_loss)
    else:
        stale += 1
    if epoch == 1 or epoch % 5 == 0 or improved:
        print(f'{phase} epoch {epoch:02d}: loss={train_loss:.4f}, val_loss={val_loss:.4f}, '
              f'val_acc={acc:.3f}, val_F1={score:.3f}', flush=True)
for epoch in range(1, HEAD_EPOCHS + 1):
    model.eval()
    model.classifier.train()
    loss_sum = correct = count = 0
    for x, y in head_dl:
        x, y = x.to(DEVICE), y.to(DEVICE)
        optimizer.zero_grad(set_to_none=True)
        logits = model.classifier(x)
        loss = criterion(logits, y)
        loss.backward()
        optimizer.step()
        loss_sum += loss.item() * len(y)
        correct += (logits.argmax(1) == y).sum().item()
        count += len(y)
    model.eval()
    with torch.inference_mode():
        logits = model.classifier(val_x.to(DEVICE))
        val_loss = criterion(logits, val_y.to(DEVICE)).item()
        pred = logits.argmax(1).cpu().numpy()
    record_epoch(epoch, 'head', loss_sum / count, correct / count, val_loss, val_y.numpy(), pred)
    if stale >= PATIENCE:
        print('Early stopping.')
        break

# %% [markdown]
# ## 6. Fine-tuning tùy chọn
# Mặc định bỏ qua. Khi `FINE_TUNE=True`, nạp checkpoint tốt nhất, mở block cuối, học với learning rate nhỏ. BatchNorm vẫn đóng băng vì batch/dữ liệu nhỏ. Chỉ lưu nếu validation tốt hơn checkpoint hiện có. Bật tùy chọn này trước khi chạy test, không dùng kết quả test để quyết định.

# %%
checkpoint = torch.load(CHECKPOINT, map_location=DEVICE, weights_only=True)
model.load_state_dict(checkpoint['model_state'])
if FINE_TUNE:
    for p in model.features[-1].parameters():
        p.requires_grad = True
    optimizer_ft = torch.optim.AdamW(
        [p for p in model.parameters() if p.requires_grad], lr=FINE_TUNE_LR, weight_decay=1e-3)
    stale = 0
    offset = history[-1]['epoch']
    for step in range(1, FINE_TUNE_EPOCHS + 1):
        model.eval()  # BatchNorm của backbone giữ thống kê pretrained
        model.classifier.train()
        loss_sum = correct = count = 0
        for x, y in loader(TRAIN, train_tf, shuffle=True):
            x, y = x.to(DEVICE), y.to(DEVICE)
            optimizer_ft.zero_grad(set_to_none=True)
            logits = model(x)
            loss = criterion(logits, y)
            loss.backward()
            optimizer_ft.step()
            loss_sum += loss.item() * len(y)
            correct += (logits.argmax(1) == y).sum().item()
            count += len(y)
        model.eval()
        logits_list, y_list = [], []
        with torch.inference_mode():
            for x, y in loader(VAL, eval_tf):
                logits_list.append(model(x.to(DEVICE)).cpu())
                y_list.append(y)
        logits, targets = torch.cat(logits_list), torch.cat(y_list)
        record_epoch(offset + step, 'fine_tune', loss_sum/count, correct/count,
                     criterion(logits, targets).item(), targets.numpy(), logits.argmax(1).numpy())
        if stale >= PATIENCE:
            break
train_seconds = time.perf_counter() - start_train
history_df = pd.DataFrame(history)
history_df.to_csv(OUT / 'history.csv', index=False)
fig, axes = plt.subplots(1, 2, figsize=(11, 4))
history_df.plot(x='epoch', y=['train_loss', 'val_loss'], ax=axes[0], title='Learning curves: loss')
history_df.plot(x='epoch', y=['train_accuracy', 'val_accuracy', 'val_macro_f1'], ax=axes[1], title='Accuracy / F1')
plt.tight_layout()
plt.savefig(OUT / 'learning_curves.png', dpi=140)
plt.show()

# %% [markdown]
# ## 7. Nạp mô hình tốt nhất và kiểm tra validation
# Nếu validation không đạt tiêu chí đã đặt, cell báo lỗi và chưa đọc ảnh test. Dữ liệu test chỉ được dùng trong các cell sau khi mô hình được chọn.

# %%
checkpoint = torch.load(CHECKPOINT, map_location=DEVICE, weights_only=True)
model.load_state_dict(checkpoint['model_state'])
model.eval()
@torch.inference_mode()
def predict_frame(frame):
    probs, targets = [], []
    for x, y in loader(frame, eval_tf):
        probs.append(model(x.to(DEVICE)).softmax(1).cpu().numpy())
        targets.append(y.numpy())
    return np.concatenate(targets), np.concatenate(probs)
val_true, val_probs = predict_frame(VAL)
val_pred = val_probs.argmax(1)
val_f1 = f1_score(val_true, val_pred, labels=range(3), average='macro', zero_division=0)
_, val_recall, _, _ = precision_recall_fscore_support(val_true, val_pred, labels=range(3), zero_division=0)
validation_ok = bool(val_f1 >= MIN_VAL_MACRO_F1 and val_recall.min() >= MIN_VAL_CLASS_RECALL)
validation_summary = {'best_epoch': checkpoint['epoch'], 'macro_f1': float(val_f1),
                      'accuracy': float(accuracy_score(val_true, val_pred)),
                      'recall': dict(zip(CLASSES, map(float, val_recall))),
                      'passed': validation_ok, 'training_seconds': train_seconds}
(OUT / 'validation.json').write_text(json.dumps(validation_summary, indent=2), encoding='utf-8')
print(classification_report(val_true, val_pred, labels=range(3), target_names=[VN[c] for c in CLASSES], zero_division=0))
print('Checkpoint epoch:', checkpoint['epoch'], '| Validation đạt:', validation_ok)
if not validation_ok:
    raise RuntimeError('Validation chưa đạt. Chưa chạy test. Điều chỉnh dựa trên train/validation, rồi chạy lại từ ô huấn luyện.')

# %% [markdown]
# ## 8. Đánh giá test cuối cùng: basic, variation và tổng hợp
# **Accuracy**: tỷ lệ đúng. **Precision**: trong ảnh được dự đoán thuộc lớp, bao nhiêu ảnh đúng. **Recall**: trong ảnh thật thuộc lớp, bao nhiêu ảnh được tìm đúng. **F1**: trung bình điều hòa precision/recall. **Macro-F1**: mỗi lớp có trọng số bằng nhau. **Confusion matrix**: hàng là nhãn thật, cột là nhãn dự đoán.
#
# Báo cáo thêm cross-entropy/log-loss (phạt dự đoán sai nhưng tự tin), Brier score đa lớp (tổng bình phương sai số xác suất, thấp tốt), ECE 10 bins (chênh độ tin cậy và độ đúng), ROC-AUC one-vs-rest, và khoảng tin cậy Wilson 95% cho accuracy. Đây là số đo mô tả trên tập test nhỏ, không chứng minh hiệu năng ngoài thực tế.
#
# `basic` và `variation` là nhóm đã có trong dữ liệu, không phải cùng ảnh được biến đổi có kiểm soát. Chênh lệch hiệu năng gợi ý độ bền vững; chưa thể quy nguyên nhân cho một yếu tố ảnh cụ thể.

# %%
assert validation_ok, 'Phải đạt validation trước khi chạy test.'
def wilson_ci(correct, n, z=1.96):
    p = correct / n
    denom = 1 + z*z/n
    center = (p + z*z/(2*n)) / denom
    half = z * np.sqrt(p*(1-p)/n + z*z/(4*n*n)) / denom
    return [float(center - half), float(center + half)]
def probability_metrics(y, probs):
    conf, pred = probs.max(1), probs.argmax(1)
    ece = 0.
    for lo, hi in zip(np.linspace(0, 1, 11)[:-1], np.linspace(0, 1, 11)[1:]):
        mask = (conf >= lo) & ((conf < hi) if hi < 1 else (conf <= hi))
        if mask.any():
            ece += mask.mean() * abs((pred[mask] == y[mask]).mean() - conf[mask].mean())
    return {'log_loss': float(log_loss(y, probs, labels=range(3))),
            'brier_multiclass': float(((probs - np.eye(3)[y])**2).sum(1).mean()),
            'ece_10_bins': float(ece),
            'roc_auc_ovr_macro': float(roc_auc_score(y, probs, labels=range(3), multi_class='ovr', average='macro'))}
test_true, test_probs = predict_frame(TEST)
test_pred = test_probs.argmax(1)
test_conf = test_probs.max(1)
predictions = TEST[['source_file','source','label','group','path']].copy()
predictions['predicted'] = [CLASSES[i] for i in test_pred]
predictions['confidence'] = test_conf
predictions['correct'] = test_true == test_pred
predictions['accepted'] = test_conf >= CONFIDENCE_THRESHOLD
for i, c in enumerate(CLASSES):
    predictions[f'prob_{c}'] = test_probs[:, i]
predictions.to_csv(OUT / 'test_predictions.csv', index=False, encoding='utf-8-sig')
summaries, per_class_rows = [], []
fig, axes = plt.subplots(1, 3, figsize=(15, 4))
for ax, group in zip(axes, ['all', 'basic', 'variation']):
    mask = np.ones(len(TEST), dtype=bool) if group == 'all' else (TEST.group == group).to_numpy()
    y, pred, probs = test_true[mask], test_pred[mask], test_probs[mask]
    pr, re, f1, support = precision_recall_fscore_support(y, pred, labels=range(3), zero_division=0)
    acc = accuracy_score(y, pred)
    ci = wilson_ci(int((y == pred).sum()), len(y))
    accepted = probs.max(1) >= CONFIDENCE_THRESHOLD
    summary = {'group': group, 'n': len(y), 'accuracy': float(acc),
               'macro_precision': float(pr.mean()), 'macro_recall': float(re.mean()),
               'macro_f1': float(f1.mean()), 'accuracy_ci95_low': ci[0], 'accuracy_ci95_high': ci[1],
               'coverage_at_threshold': float(accepted.mean()),
               'accuracy_accepted': float((y[accepted] == pred[accepted]).mean()) if accepted.any() else None,
               **probability_metrics(y, probs)}
    summaries.append(summary)
    for i, c in enumerate(CLASSES):
        per_class_rows.append({'group': group, 'class': c, 'precision': pr[i],
                               'recall': re[i], 'f1': f1[i], 'support': int(support[i])})
    cm = confusion_matrix(y, pred, labels=range(3))
    pd.DataFrame(cm, index=CLASSES, columns=CLASSES).to_csv(OUT / f'confusion_{group}.csv')
    ConfusionMatrixDisplay(cm, display_labels=[VN[c] for c in CLASSES]).plot(ax=ax, colorbar=False)
    ax.set_title(f'{group}: accuracy={acc:.1%}')
plt.tight_layout()
plt.savefig(OUT / 'confusion_matrices.png', dpi=140)
plt.show()
summary_df = pd.DataFrame(summaries)
class_df = pd.DataFrame(per_class_rows)
summary_df.to_csv(OUT / 'test_metrics.csv', index=False)
class_df.to_csv(OUT / 'per_class_metrics.csv', index=False)
display(summary_df.round(4))
display(class_df.round(4))
print(classification_report(test_true, test_pred, labels=range(3), target_names=[VN[c] for c in CLASSES], zero_division=0))

# %% [markdown]
# ## 9. Kiểm thử ảnh ngoài ba lớp và tốc độ suy luận
# Không gộp 15 ảnh ngoài lớp vào accuracy ba lớp. Vì không huấn luyện lớp `unknown`, mô hình luôn có dự đoán top-1 là một trong ba lớp. Lab chỉ gắn nhãn `CẦN KIỂM TRA` nếu confidence < ngưỡng.
#
# Báo cáo tỷ lệ từ chối ngoài lớp và tỷ lệ chấp nhận sai ngoài lớp ở ngưỡng cố định; đối chiếu với tỷ lệ từ chối ảnh đúng miền. Chưa có validation ngoài lớp để hiệu chỉnh bộ từ chối. Tốc độ là forward pass batch=1, đã warm-up, không gồm đọc ảnh/tiền xử lý; phụ thuộc thiết bị, không phải tốc độ toàn hệ thống.

# %%
outside_summary = {}
if len(OUTSIDE):
    _, outside_probs = predict_frame(OUTSIDE)
    outside_conf = outside_probs.max(1)
    outside_rejected = outside_conf < CONFIDENCE_THRESHOLD
    outside_predictions = OUTSIDE[['source_file','label','path']].copy()
    outside_predictions['predicted'] = [CLASSES[i] for i in outside_probs.argmax(1)]
    outside_predictions['confidence'] = outside_conf
    outside_predictions['rejected'] = outside_rejected
    outside_predictions.to_csv(OUT / 'outside_predictions.csv', index=False, encoding='utf-8-sig')
    outside_summary = {'n': len(OUTSIDE), 'threshold': CONFIDENCE_THRESHOLD,
                       'rejection_rate': float(outside_rejected.mean()),
                       'false_acceptance_rate': float((~outside_rejected).mean()),
                       'in_domain_rejection_rate': float((test_conf < CONFIDENCE_THRESHOLD).mean())}
    display(outside_predictions[['source_file','label','predicted','confidence','rejected']])
sample_x, _ = WasteDataset(TEST.iloc[:1].reset_index(drop=True), eval_tf)[0]
sample_x = sample_x.unsqueeze(0).to(DEVICE)
def sync_device():
    if DEVICE.type == 'cuda':
        torch.cuda.synchronize()
latencies = []
with torch.inference_mode():
    for _ in range(10):
        model(sample_x)
    sync_device()
    for _ in range(50):
        sync_device()
        start = time.perf_counter()
        model(sample_x)
        sync_device()
        latencies.append(1000 * (time.perf_counter() - start))
speed = {'device': str(DEVICE), 'batch_size': 1,
         'median_forward_ms': float(np.median(latencies)),
         'p95_forward_ms': float(np.percentile(latencies, 95)),
         'parameters': sum(p.numel() for p in model.parameters()),
         'checkpoint_mb': CHECKPOINT.stat().st_size / 1024**2}
print('Ngoài lớp:', outside_summary)
print('Tốc độ:', speed)

# %% [markdown]
# ## 10. Phân tích lỗi và rút ra yếu tố đánh giá
# Xem ảnh sai theo confidence giảm dần; ảnh sai nhưng tự tin cần được ưu tiên. Ghi chú bằng chứng nhìn thấy về ánh sáng, nền, góc chụp, vật bị che, vật biến dạng, vật trong suốt và bề mặt phản chiếu vào CSV. Đây là phiếu phân tích để người học điền, không phải nhãn điều kiện đã được xác minh.
#
# Để kết luận yếu tố nào gây lỗi, cần thêm dữ liệu được gắn nhãn theo từng điều kiện và đủ mẫu mỗi nhóm, hoặc chụp cùng vật thể trong điều kiện được kiểm soát. Không suy luận nguyên nhân chỉ từ tên nhóm variation.

# %%
errors = predictions[~predictions.correct].sort_values('confidence', ascending=False).copy()
review = predictions.copy()
for field in ['lighting','background','view_angle','occlusion','deformation','transparent_or_reflective','notes']:
    review[field] = ''
review.to_csv(OUT / 'error_review_template.csv', index=False, encoding='utf-8-sig')
show = errors.head(12)
if len(show):
    cols = 4
    rows_n = (len(show) + cols - 1) // cols
    fig, axes = plt.subplots(rows_n, cols, figsize=(12, 3.5 * rows_n), squeeze=False)
    for ax in axes.flat:
        ax.axis('off')
    for ax, r in zip(axes.flat, show.itertuples()):
        with Image.open(r.path) as im:
            ax.imshow(im)
        ax.set_title(f'{r.group}\nThật: {VN[r.label]} / Đoán: {VN[r.predicted]}\nConfidence: {r.confidence:.1%}', fontsize=9)
    plt.tight_layout()
    plt.savefig(OUT / 'misclassified_examples.png', dpi=140)
    plt.show()
else:
    print('Không có ảnh test bị phân loại sai trong lần chạy này.')
all_stats = summaries[0]
basic_stats, variation_stats = summaries[1:]
all_classes = class_df[class_df.group == 'all']
weakest = all_classes.loc[all_classes['recall'].idxmin()]
cm_all = confusion_matrix(test_true, test_pred, labels=range(3))
offdiag = cm_all.copy()
np.fill_diagonal(offdiag, 0)
if offdiag.max():
    i, j = np.unravel_index(offdiag.argmax(), offdiag.shape)
    confusion_text = f'Cặp nhầm nhiều nhất theo chiều thật → dự đoán: {VN[CLASSES[i]]} → {VN[CLASSES[j]]} ({offdiag[i,j]} ảnh).'
else:
    confusion_text = 'Không có nhầm lớp trên 60 ảnh test.'
gap = basic_stats['accuracy'] - variation_stats['accuracy']
report = f'''# Báo cáo SmartSort — kết quả đo thực tế của lần chạy

## Cấu hình và dữ liệu
- EfficientNet-B0/ImageNet; seed {SEED}; fine-tuning: {FINE_TUNE}.
- Train {len(TRAIN)}, validation {len(VAL)}, test ba lớp {len(TEST)}, ngoài lớp {len(OUTSIDE)}.
- SHA-256 ZIP: {archive_hash}.
- Thiết bị: {DEVICE}; torch {torch.__version__}; torchvision {torchvision.__version__}.
- Checkpoint tốt nhất epoch {checkpoint['epoch']}; thời gian trích đặc trưng + train {train_seconds:.1f} giây.
- Validation: macro-F1 {val_f1:.3f}, đạt tiêu chí đặt trước: {validation_ok}.

## Kết quả test
- Accuracy: {all_stats['accuracy']:.1%}; khoảng Wilson 95% [{all_stats['accuracy_ci95_low']:.1%}, {all_stats['accuracy_ci95_high']:.1%}].
- Macro precision/recall/F1: {all_stats['macro_precision']:.3f} / {all_stats['macro_recall']:.3f} / {all_stats['macro_f1']:.3f}.
- Basic: {basic_stats['accuracy']:.1%}; variation: {variation_stats['accuracy']:.1%}; chênh basic - variation {gap*100:.1f} điểm phần trăm.
- Recall thấp nhất: {VN[weakest['class']]} ({weakest['recall']:.1%}).
- {confusion_text}
- Log-loss {all_stats['log_loss']:.3f}; Brier {all_stats['brier_multiclass']:.3f}; ECE {all_stats['ece_10_bins']:.3f}; ROC-AUC OVR {all_stats['roc_auc_ovr_macro']:.3f}.
- Với ngưỡng {CONFIDENCE_THRESHOLD:.2f}: coverage {all_stats['coverage_at_threshold']:.1%}; accuracy trên ảnh được chấp nhận {all_stats['accuracy_accepted']}.
- Số lỗi test: {len(errors)}; sai nhưng confidence ≥ ngưỡng: {int((~predictions.correct & predictions.accepted).sum())}.

## Ngoài lớp và tài nguyên
- Kết quả ngoài lớp: {json.dumps(outside_summary, ensure_ascii=False)}.
- Forward batch=1: median {speed['median_forward_ms']:.2f} ms, p95 {speed['p95_forward_ms']:.2f} ms.
- Tham số {speed['parameters']:,}; checkpoint {speed['checkpoint_mb']:.2f} MB.

## Những yếu tố cần đánh giá
1. Hiệu năng tổng thể: accuracy và macro-F1, so với baseline chọn ngẫu nhiên đều ~33.3% trên ba lớp cân bằng.
2. Khả năng từng vật liệu: precision, recall, F1, support; ưu tiên recall lớp yếu và cặp nhầm trong confusion matrix.
3. Overfit: so sánh learning curves train/validation và kết quả test; train accuracy đo khi dropout bật/ảnh tăng cường nên chỉ là chỉ dấu.
4. Độ bền vững: so sánh basic/variation; tiếp tục ghi chú nền, ánh sáng, góc chụp, che khuất, biến dạng, trong suốt/phản chiếu trong error_review_template.csv. Chênh lệch nhóm chưa xác định nguyên nhân.
5. Độ tin cậy: log-loss, Brier, ECE; kiểm tra lỗi tự tin cao. Confidence softmax chưa được hiệu chỉnh, không coi là xác suất chắc chắn đúng.
6. Giới hạn lớp lạ: tỷ lệ từ chối ngoài lớp và từ chối ảnh trong miền tại ngưỡng đã cố định. Carton/thủy tinh không được tính vào accuracy ba lớp.
7. Hiệu suất: thời gian huấn luyện, forward latency, số tham số và kích thước mô hình; đo thêm pipeline đầy đủ trước khi triển khai.
8. Độ vững của kết luận: chỉ 60 ảnh test, 20 ảnh/lớp; một lỗi thay đổi recall lớp 5 điểm phần trăm. Khoảng tin cậy giả định các ảnh độc lập; kiểm tra cùng vật thể/nguồn chụp trước khi suy rộng.

## Kết luận thực hành
Ưu tiên thu thập thêm ảnh độc lập cho lớp có recall thấp và các điều kiện hay sai. Tách theo vật thể/phiên chụp để tránh rò rỉ. Nếu thay đổi mô hình sau báo cáo này, đánh giá cuối cần một tập test mới, không dùng lại test để chọn tham số. Bộ dữ liệu nhỏ phù hợp thực hành, chưa đủ kết luận hệ thống dùng ngoài thực tế.
'''
(OUT / 'REPORT.md').write_text(report, encoding='utf-8')
(OUT / 'results.json').write_text(json.dumps({'validation': validation_summary,
    'test': summaries, 'outside': outside_summary, 'speed': speed}, indent=2), encoding='utf-8')
print(report)

# %% [markdown]
# ## 11. Thử nhận diện ảnh mới (tùy chọn)
# Sau khi đã hoàn tất test, có thể tải ảnh chụp mới. Nhãn `CẦN KIỂM TRA` chỉ dựa trên ngưỡng confidence; vật ngoài lớp vẫn có thể được mô hình chấp nhận sai. Ô định nghĩa hàm dưới đây không tự bật hộp upload để `Run all` chạy đến hết.

# %%
@torch.inference_mode()
def predict_image(image_path):
    model.eval()
    with Image.open(image_path) as im:
        x = eval_tf(im.convert('RGB')).unsqueeze(0).to(DEVICE)
    probs = model(x).softmax(1)[0].cpu().numpy()
    i = int(probs.argmax())
    return {'label': VN[CLASSES[i]], 'confidence': float(probs[i]),
            'decision': VN[CLASSES[i]] if probs[i] >= CONFIDENCE_THRESHOLD else 'CẦN KIỂM TRA',
            'probabilities': {VN[c]: float(probs[j]) for j, c in enumerate(CLASSES)}}
def upload_and_predict():
    from google.colab import files
    images = files.upload()
    for name in images:
        display(Image.open(name))
        print(name, predict_image(name))
# Bỏ dấu # ở dòng dưới để tải ảnh mới:
# upload_and_predict()

# %% [markdown]
# ## 12. Xuất toàn bộ kết quả
# ZIP chứa checkpoint, báo cáo, dự đoán từng ảnh, lịch sử huấn luyện, chia dữ liệu, kiểm tra toàn vẹn, cấu hình và biểu đồ. Tải ZIP sau khi chạy xong để tránh mất kết quả khi Colab ngắt phiên. `best_model.pt` lưu thứ tự lớp và tiền xử lý; để nạp lại, tạo `efficientnet_b0(weights=None)`, thay classifier thành 3 đầu ra và nạp `model_state`, dùng letterbox/mean/std đã lưu.

# %%
export_path = Path(shutil.make_archive(str(OUT.parent / 'SmartSort_Results'), 'zip', OUT))
print('Kết quả:', export_path)
if importlib.util.find_spec('google.colab') is not None:
    from google.colab import files
    files.download(str(export_path))
