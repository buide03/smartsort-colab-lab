"""Persistent local lab sessions and safe image ingestion (no inferred labels)."""
import hashlib
import io
import json
import os
import random
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

CLASSES = ['metal', 'paper', 'plastic']
CLASS_NAMES = {'metal': 'Kim loại', 'paper': 'Giấy', 'plastic': 'Nhựa'}
ROOT = Path(os.environ.get('SMARTSORT_APP_DATA', Path(__file__).resolve().parents[1] / '.smartsort')).resolve()
ROOT.mkdir(parents=True, exist_ok=True)
LOCK = threading.RLock()
MAX_IMAGE_BYTES = 25 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000


def now():
    return datetime.now(timezone.utc).isoformat()


def session_dir(session_id):
    if len(session_id) != 32 or any(c not in '0123456789abcdef' for c in session_id):
        raise ValueError('Mã phiên không hợp lệ.')
    return ROOT / session_id


def load(session_id):
    p = session_dir(session_id) / 'session.json'
    if not p.is_file():
        raise ValueError('Không tìm thấy phiên học.')
    return json.loads(p.read_text(encoding='utf-8'))


def save(session):
    d = session_dir(session['id'])
    d.mkdir(parents=True, exist_ok=True)
    p = d / 'session.json'
    temporary = d / 'session.tmp'
    temporary.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(p)


def create(title=''):
    with LOCK:
        limit=int(os.environ.get('SMARTSORT_MAX_SESSIONS','200'))
        if sum(1 for _ in ROOT.glob('*/session.json'))>=limit:
            raise ValueError(f'Đã đạt giới hạn {limit} phiên trên server. Giáo viên cần sao lưu/dọn phiên hoặc tăng giới hạn.')
        session = {'id': uuid.uuid4().hex, 'title': title.strip()[:100] or 'Bài thực hành mới',
                   'created_at': now(), 'phase': 'labeling', 'images': [], 'splits': None,
                   'training': None, 'selected': None, 'results': None, 'job': None}
        save(session)
        return session


def sessions():
    result = []
    with LOCK:
        for path in ROOT.glob('*/session.json'):
            try:
                s = json.loads(path.read_text(encoding='utf-8'))
                result.append({k: s[k] for k in ['id', 'title', 'created_at', 'phase']})
            except (OSError, json.JSONDecodeError, KeyError):
                continue
    return sorted(result, key=lambda s: s['created_at'], reverse=True)


def rgb_image(data):
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError('Mỗi ảnh tối đa 25 MB.')
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.width * image.height > MAX_IMAGE_PIXELS:
                raise ValueError('Mỗi ảnh tối đa 20 triệu pixel.')
            image.load()
            image = ImageOps.exif_transpose(image)
            if image.mode in ('RGBA', 'LA') or 'transparency' in image.info:
                rgba = image.convert('RGBA')
                background = Image.new('RGBA', rgba.size, 'white')
                image = Image.alpha_composite(background, rgba).convert('RGB')
            else:
                image = image.convert('RGB')
            return image.copy()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError('File không phải ảnh đọc được hoặc ảnh bị hỏng.') from exc


def add_image(session, filename, data):
    image = rgb_image(data)
    pixel_hash = hashlib.sha256(str(image.size).encode() + image.tobytes()).hexdigest()
    if any(r['pixel_hash'] == pixel_hash for r in session['images']):
        return False
    limit=int(os.environ.get('SMARTSORT_MAX_IMAGES','1000'))
    if len(session['images'])>=limit:
        raise ValueError(f'Mỗi phiên tối đa {limit} ảnh; hãy chia thành bài thực hành nhỏ hơn.')
    image_id = uuid.uuid4().hex
    d = session_dir(session['id']) / 'images'
    d.mkdir(exist_ok=True)
    buffer=io.BytesIO()
    image.save(buffer,format='PNG')
    encoded=buffer.getvalue()
    existing=session.get('image_bytes')
    if existing is None:
        existing=sum(p.stat().st_size for p in d.glob('*.png'))
    max_bytes=int(os.environ.get('SMARTSORT_MAX_IMAGE_STORAGE_MB','512'))*1024*1024
    if existing+len(encoded)>max_bytes:
        raise ValueError('Dung lượng ảnh của phiên đã đạt giới hạn server.')
    (d/f'{image_id}.png').write_bytes(encoded)
    session['image_bytes']=existing+len(encoded)
    # Filename is displayed as data; folder names and ZIP instructions are not labels.
    session['images'].append({'id': image_id, 'filename': filename.replace('\\', '/').split('/')[-1][:180],
                              'label': None, 'pixel_hash': pixel_hash,
                              'width': image.width, 'height': image.height})
    return True


def image_path(session_id, image_id):
    s = load(session_id)
    if not any(r['id'] == image_id for r in s['images']):
        raise ValueError('Không tìm thấy ảnh.')
    return session_dir(session_id) / 'images' / f'{image_id}.png'


def class_counts(session):
    return {c: sum(r['label'] == c for r in session['images']) for c in CLASSES}


def split_data(session, train_ratio, val_ratio, test_ratio, seed):
    if session['phase'] != 'labeling':
        raise ValueError('Dữ liệu đã chia. Quay lại gán nhãn trước khi chia lại.')
    if any(r['label'] is None for r in session['images']):
        raise ValueError('Cần gán nhãn hoặc bỏ qua tất cả ảnh trước khi chia dữ liệu.')
    ratios = [train_ratio, val_ratio, test_ratio]
    if any(r <= 0 or r >= 1 for r in ratios) or abs(sum(ratios) - 1) > 1e-6:
        raise ValueError('Ba tỷ lệ phải lớn hơn 0 và cộng lại bằng 100%.')
    counts = class_counts(session)
    if min(counts.values()) < 10:
        raise ValueError('Cần ít nhất 10 ảnh khác nhau cho mỗi lớp; khuyến nghị từ 50 ảnh/lớp.')
    rng = random.Random(seed)
    partitions = {'train': [], 'validation': [], 'test': []}
    for c in CLASSES:
        ids = sorted(r['id'] for r in session['images'] if r['label'] == c)
        rng.shuffle(ids)
        n_val = max(1, round(len(ids) * val_ratio))
        n_test = max(1, round(len(ids) * test_ratio))
        n_train = len(ids) - n_val - n_test
        if n_train < 2:
            raise ValueError('Tỷ lệ chia để lại quá ít ảnh train. Tăng tỷ lệ train.')
        partitions['train'].extend(ids[:n_train])
        partitions['validation'].extend(ids[n_train:n_train+n_val])
        partitions['test'].extend(ids[n_train+n_val:])
    # Reproducible relative to the saved manifest; exporting it preserves the exact split.
    snapshot = json.dumps({'partitions': partitions,
                           'images': [(r['id'], r['label'], r['pixel_hash']) for r in session['images']]}, sort_keys=True)
    session['splits'] = {'ids': partitions, 'seed': seed,
                          'ratios': {'train': train_ratio, 'validation': val_ratio, 'test': test_ratio},
                          'sha256': hashlib.sha256(snapshot.encode()).hexdigest()}
    session['phase'] = 'split'
    save(session)


def public(session):
    result = dict(session)
    result['counts'] = class_counts(session)
    result['unlabeled'] = sum(r['label'] is None for r in session['images'])
    result['excluded'] = sum(r['label'] == 'exclude' for r in session['images'])
    if session['splits']:
        by_id = {r['id']: r for r in session['images']}
        result['split_counts'] = {name: {c: sum(by_id[i]['label'] == c for i in ids) for c in CLASSES}
                                  for name, ids in session['splits']['ids'].items()}
    return result
