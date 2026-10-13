/* Review locally before persistence or inference. Originals never leave this dialog. */
'use strict';
window.PrivacyReview = (() => {
  let busy = false;
  const MAX_BYTES = 120 * 1024 * 1024;
  async function expand(files) {
    const images = [];
    let total = 0;
    const add = file => {
      total += file.size;
      if (total > MAX_BYTES || images.length >= 1000) throw new Error('Tối đa 1.000 ảnh và 120 MB sau giải nén.');
      images.push(file);
    };
    for (const file of files) {
      if (/\.zip$/i.test(file.name)) {
        const entries = fflate.unzipSync(new Uint8Array(await file.arrayBuffer()), {filter: entry => {
          if (!/\.(png|jpe?g|webp|bmp)$/i.test(entry.name)) return false;
          if (entry.originalSize > MAX_BYTES - total) throw new Error('ZIP vượt giới hạn giải nén 120 MB.');
          // Reserve before decompression so several small entries cannot exceed the limit.
          total += entry.originalSize;
          return true;
        }});
        for (const [name, data] of Object.entries(entries)) {
          total -= data.length;
          add(new File([data], name));
        }
      } else add(file);
    }
    if (!images.length) throw new Error('Không có ảnh để kiểm tra PII.');
    return images;
  }
  async function review(file, index, count) {
    const bitmap = await createImageBitmap(file);
    if (bitmap.width * bitmap.height > 25_000_000) {
      bitmap.close();
      throw new Error('Ảnh quá lớn. Hãy giảm xuống dưới 25 triệu pixel trước khi kiểm tra.');
    }
    const dialog = document.createElement('dialog');
    dialog.className = 'privacy-dialog';
    dialog.innerHTML = `<h2>Kiểm tra & che thông tin cá nhân</h2>
      <p>Ảnh ${index + 1} / ${count}. Tìm khuôn mặt, họ tên, số điện thoại, địa chỉ, mã học sinh, biển số, mã QR hoặc thông tin trên giấy tờ.</p>
      <p>Kéo để khoanh vùng cần che. Dùng ô đen phủ kín thông tin; giữ phần vật liệu cần phân loại. Phóng to bằng trình duyệt nếu cần đọc chi tiết.</p>
      <canvas aria-label="Kéo trên ảnh để che PII"></canvas>
      <div class="dialog-actions"><button type="button" class="button ghost" data-undo>Hoàn tác vùng cuối</button><button type="button" class="button ghost" data-skip>Bỏ ảnh này</button></div>
      <label class="privacy-check"><input type="checkbox" data-review> Tôi đã tự kiểm tra toàn bộ ảnh và che hết thông tin cá nhân nhìn thấy. Nếu ảnh không có PII, tôi đã xác nhận bằng cách xem kỹ ảnh.</label>
      <p>Bạn cần tự phát hiện PII và kiểm tra từng ảnh, kể cả chữ nhỏ, khuôn mặt, biển số và mã QR. Nếu che làm mất đặc điểm vật liệu, hãy bỏ ảnh. Chỉ bản đã che và duyệt được lưu/gửi đi, với tên mới và không kèm metadata ảnh gốc.</p>
      <div class="dialog-actions"><button type="button" class="button ghost" data-cancel>Hủy lượt tải</button><button type="button" class="button primary" data-accept disabled>Dùng ảnh đã kiểm tra</button></div>
      <p data-error role="alert"></p>`;
    document.body.append(dialog);
    const canvas = dialog.querySelector('canvas'), ctx = canvas.getContext('2d');
    const check = dialog.querySelector('[data-review]'), accept = dialog.querySelector('[data-accept]');
    canvas.width = bitmap.width; canvas.height = bitmap.height;
    const boxes = [];
    let start = null;
    const point = event => {
      const bounds = canvas.getBoundingClientRect();
      return [Math.max(0, Math.min(canvas.width, (event.clientX - bounds.left) * canvas.width / bounds.width)),
        Math.max(0, Math.min(canvas.height, (event.clientY - bounds.top) * canvas.height / bounds.height))];
    };
    const draw = () => {
      ctx.fillStyle = 'white'; ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(bitmap, 0, 0); ctx.fillStyle = 'black';
      for (const [x, y, w, h] of boxes) ctx.fillRect(x, y, w, h);
    };
    const invalidate = () => { check.checked = false; accept.disabled = true; };
    draw();
    canvas.addEventListener('pointerdown', event => {
      if (event.button !== 0) return;
      start = point(event); canvas.setPointerCapture(event.pointerId); invalidate();
    });
    canvas.addEventListener('pointermove', event => {
      if (!start) return;
      draw(); const end = point(event);
      ctx.fillRect(Math.min(start[0], end[0]), Math.min(start[1], end[1]), Math.abs(end[0] - start[0]), Math.abs(end[1] - start[1]));
    });
    canvas.addEventListener('pointerup', event => {
      if (!start) return;
      const end = point(event), x = Math.floor(Math.min(start[0], end[0])), y = Math.floor(Math.min(start[1], end[1]));
      const w = Math.ceil(Math.max(start[0], end[0])) - x, h = Math.ceil(Math.max(start[1], end[1])) - y;
      if (w && h) boxes.push([x, y, w, h]);
      start = null; draw();
    });
    canvas.addEventListener('pointercancel', () => { start = null; draw(); });
    dialog.querySelector('[data-undo]').onclick = () => { boxes.pop(); invalidate(); draw(); };
    check.onchange = () => { accept.disabled = !check.checked || start !== null; };
    try {
      return await new Promise(resolve => {
        dialog.addEventListener('cancel', event => { event.preventDefault(); resolve(null); });
        dialog.querySelector('[data-cancel]').onclick = () => resolve(null);
        dialog.querySelector('[data-skip]').onclick = () => resolve('skip');
        accept.onclick = async () => {
          if (!check.checked || start) return;
          accept.disabled = true;
          try {
            draw();
            const blob = await new Promise(done => canvas.toBlob(done, 'image/png'));
            if (!blob) throw new Error('Không tạo được ảnh đã che.');
            resolve(new File([blob], `image_${crypto.randomUUID()}.png`, {type:'image/png'}));
          } catch (error) {
            dialog.querySelector('[data-error]').textContent = error.message;
            accept.disabled = false;
          }
        };
        dialog.showModal();
      });
    } finally {
      bitmap.close(); canvas.width = canvas.height = 0; dialog.close(); dialog.remove();
    }
  }
  async function prepare(fileList, limitMB = 64) {
    if (busy) throw new Error('Hãy hoàn tất bước kiểm tra PII đang mở.');
    busy = true;
    try {
      const files = [...fileList];
      if (files.reduce((n, f) => n + f.size, 0) > limitMB * 1024 * 1024) throw new Error(`Mỗi lượt chọn tối đa ${limitMB} MB.`);
      const images = await expand(files), result = [];
      let total = 0;
      for (let i = 0; i < images.length; i++) {
        const safe = await review(images[i], i, images.length);
        if (safe === null) return [];
        if (safe === 'skip') continue;
        total += safe.size;
        if (total > limitMB * 1024 * 1024) throw new Error('Ảnh PNG đã duyệt vượt giới hạn tải. Hãy chọn ít ảnh hơn mỗi lượt.');
        result.push(safe);
      }
      return result;
    } finally { busy = false; }
  }
  return {prepare};
})();
