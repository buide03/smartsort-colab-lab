'use strict';
const $ = (selector, root = document) => root.querySelector(selector);
const names = {metal: 'Kim loại', paper: 'Giấy', plastic: 'Nhựa', exclude: 'Bỏ qua'};
const steps = ['Chuẩn bị & gán nhãn', 'Chia ba tập dữ liệu', 'Huấn luyện mô hình', 'Chốt cấu hình', 'Đánh giá test'];
const phaseSteps = {labeling: 1, split: 2, imported: 3, trained: 3, locked: 4, tested: 5, test_failed: 4};
let appConfig = {allow_local_train:true,colab_notebook:'https://colab.research.google.com/github/buide03/smartsort-colab-lab/blob/main/colab/SmartSort_Train_Colab.ipynb'};
let session = null, page = 1, filter = 'all', offset = 0, selected = new Set(), trialChoice = null;
let pollTimer, toastTimer, uploading = false, loadingSession = false;
const PAGE_SIZE = 12;
let testView = {material:'all', outcome:'all', sort:'confidence', query:'', page:0};
function esc(s) { return String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
function pct(n, digits = 1) { return Number.isFinite(n) ? (n * 100).toFixed(digits) + '%' : '—'; }
function num(n, digits = 3) { return Number.isFinite(n) ? n.toFixed(digits) : '—'; }
function running() { return session?.job?.status === 'running'; }
function url(path) { return path.startsWith("images/") ? BrowserLab.imageURL(session.id,path.slice(7)) : `/api/sessions/${session.id}/${path}`; }
function disabled(yes) { return yes ? ' disabled' : ''; }
function toast(message, error = false) {
  const node = $('#toast'); node.textContent = message; node.className = 'toast' + (error ? ' error' : '');
  clearTimeout(toastTimer); toastTimer = setTimeout(() => node.classList.add('hidden'), error ? 10000 : 4500);
}
async function api(path, method = 'GET', body = undefined) {
  const options = {method};
  if (body instanceof FormData) options.body = body;
  else if (body !== undefined) { options.headers = {'Content-Type': 'application/json'}; options.body = JSON.stringify(body); }
  let response;
  try { response = await BrowserLab.fetch(path, options); }
  catch { throw new Error('Không kết nối được bộ nhớ trình duyệt. Tải lại trang hoặc kiểm tra quyền lưu dữ liệu.'); }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail || 'Tác vụ thất bại.'));
  return data;
}
async function act(fn) { try { await fn(); } catch (error) { toast(error.message, true); } }
async function refresh(repaint = true) {
  if (!session) return;
  session = await api(`/api/sessions/${session.id}`);
  if (repaint) render(); else renderJob();
}
async function loadSessions(preferred) {
  loadingSession = true;
  const list = await api('/api/sessions');
  if (!list.length) { session = await api('/api/sessions', 'POST', {title: 'Bài thực hành 01'}); return loadSessions(session.id); }
  const id = preferred || localStorage.getItem('smartsort.session');
  const chosen = list.find(s => s.id === id) || list[0];
  session = await api(`/api/sessions/${chosen.id}`);
  $('#sessionPicker').innerHTML = list.map(s => `<option value="${s.id}"${s.id === chosen.id ? ' selected' : ''}>${esc(s.title)}</option>`).join('');
  localStorage.setItem('smartsort.session', session.id);
  page = Math.min(5, phaseSteps[session.phase] || 1); selected.clear(); trialChoice = null; filter = 'all'; offset = 0;
  testView = {material:'all', outcome:'all', sort:'confidence', query:'', page:0};
  loadingSession = false; render();
}
function heading(number, title, description, status = '') {
  return `<div class="page-heading"><div><span class="step-label">BƯỚC ${String(number).padStart(2,'0')} / 05</span><h1>${title}</h1><p>${description}</p></div><span class="stage-pill">${status || esc(session.title)}</span></div>`;
}
function question(title, text) { return `<div class="card question-card"><h3>${title}</h3><p>${text}</p></div>`; }
function teaching(title, text) { return `<div class="teaching"><strong>${title}</strong>${text}</div>`; }
function noPrerequisite(text, step, button) { return `<div class="card empty"><strong>${text}</strong><p>Thực hiện theo thứ tự để giữ việc chọn mô hình tách biệt với đánh giá cuối.</p><button class="button primary" data-go="${step}">${button}</button></div>`; }
function stats() {
  const total = session.images.length, labeled = total - session.unlabeled - session.excluded;
  return `<div class="stats"><div class="stat accent"><small>TỔNG ẢNH</small><strong>${total}</strong></div><div class="stat"><small>ĐÃ GÁN BA LỚP</small><strong>${labeled}</strong></div><div class="stat"><small>CHƯA CÓ NHÃN</small><strong>${session.unlabeled}</strong></div><div class="stat"><small>ĐÃ BỎ QUA</small><strong>${session.excluded}</strong></div></div>`;
}
function distribution() {
  const max = Math.max(1, ...Object.values(session.counts));
  return `<div class="card"><h3>Phân bố vật liệu</h3>${['metal','paper','plastic'].map(c => `<div class="class-row"><span class="dot ${c}"></span>${names[c]}<strong>${session.counts[c]}</strong></div><div class="class-bar"><span style="width:${session.counts[c]/max*100}%"></span></div>`).join('')}<p style="margin-top:20px">Tối thiểu 10 ảnh khác nhau mỗi lớp. Khuyến nghị từ 50 ảnh/lớp, nhiều vật thể và điều kiện chụp.</p></div>`;
}
function labelOptions(current, includeNone = true) {
  return (includeNone ? `<option value=""${current === null ? ' selected' : ''}>Chưa gán nhãn</option>` : '') +
    Object.entries(names).map(([v,n]) => `<option value="${v}"${current === v ? ' selected' : ''}>${n}</option>`).join('');
}
function visibleImages() {
  const sealed = session.splits && session.phase !== 'tested' ? new Set(session.splits.ids.test) : new Set();
  return session.images.filter(r => !sealed.has(r.id) && (filter === 'all' || (filter === 'unlabeled' ? r.label === null : r.label === filter)));
}
function imageCards(records, editable = true) {
  return records.map(r => `<article class="image-card${selected.has(r.id)?' selected':''}"><div class="image-wrap" data-enlarge="${r.id}" data-caption="${esc(r.filename)}"><img src="${url('images/'+r.id)}" alt="${esc(r.filename)}" loading="lazy">${editable ? `<input class="image-check" type="checkbox" data-select="${r.id}" aria-label="Chọn ${esc(r.filename)}"${selected.has(r.id)?' checked':''}>` : ''}</div><div class="image-meta"><div class="filename" title="${esc(r.filename)}">${esc(r.filename)}</div><select data-label="${r.id}" aria-label="Gán nhãn ${esc(r.filename)}" class="${r.label===null?'unlabeled':''}"${disabled(!editable)}>${labelOptions(r.label)}</select></div></article>`).join('');
}
function renderLabels() {
  const editable = session.phase === 'labeling' && !running();
  const items = visibleImages(); offset = Math.max(0, Math.min(offset, Math.max(0, Math.ceil(items.length/PAGE_SIZE)-1)));
  const records = items.slice(offset*PAGE_SIZE, (offset+1)*PAGE_SIZE);
  return heading(1, 'Dạy máy bằng những ảnh đầu tiên.', 'Tải ảnh chưa có nhãn, quan sát vật liệu và gán nhãn đúng. Mô hình sẽ học từ lựa chọn của bạn; tên file không được dùng để đoán nhãn.') + stats() +
    `<div class="grid"><div><div class="card"><div class="card-head"><h2>01. Tải dữ liệu của bạn</h2><span class="tag">JPG · PNG · WEBP · ZIP</span></div>${editable ? `<div class="dropzone" id="dropzone"><div class="upload-icon">↑</div><strong>Kéo ảnh hoặc ZIP vào đây</strong><p>Chọn nhiều ảnh trong một lần · Tối đa ${appConfig.upload_limit_mb || 64} MB/lượt<br>Ảnh trong ZIP cũng bắt đầu ở trạng thái chưa gán nhãn.</p><button class="button primary" id="chooseFiles"${disabled(uploading)}>Chọn ảnh / ZIP</button><input class="file-input" id="uploadInput" type="file" accept="image/jpeg,image/png,image/webp,image/bmp,.zip" multiple></div>` : `<div class="notice success">Dữ liệu đã chia và nhãn đã khóa. ${session.phase !== 'tested' ? 'Ảnh test được giữ kín cho đến khi đánh giá cuối.' : 'Phiên này đã đánh giá test; dùng phiên mới với test độc lập khi cải tiến.'}</div>`}${teaching('Vì sao cần nhãn?', 'Huấn luyện có giám sát cần cả ảnh và câu trả lời đúng. Gán Nhựa, Giấy, Kim loại; chọn Bỏ qua nếu ảnh chứa vật ngoài ba lớp, nhiều vật liệu khó xác định hoặc chất lượng quá thấp.')}</div>
    <div class="card"><div class="card-head"><h2>02. Xem ảnh & gán nhãn</h2><a class="button small ghost" href="${url('labels.csv')}">↓ Nhãn CSV</a></div><div class="toolbar"><select id="labelFilter" aria-label="Lọc ảnh"><option value="all"${filter==='all'?' selected':''}>Tất cả ảnh có thể xem</option><option value="unlabeled"${filter==='unlabeled'?' selected':''}>Chưa gán nhãn</option>${Object.entries(names).map(([c,n])=>`<option value="${c}"${filter===c?' selected':''}>${n}</option>`).join('')}</select>${editable ? `<button class="button small ghost" id="selectPage">Chọn trang này</button><button class="button small ghost" id="clearSelection">Bỏ chọn</button>` : ''}<span class="push" style="font-size:10px;color:var(--muted)">${items.length} ảnh</span></div><div id="batchBar" class="batch-bar${selected.size?'':' hidden'}"><strong id="selectionCount">${selected.size} ảnh đã chọn</strong><select id="batchLabel" aria-label="Nhãn gán theo nhóm">${labelOptions('plastic',false)}</select><button class="button small primary" id="applyBatch">Gán cho ảnh đã chọn</button></div>${records.length ? `<div class="gallery">${imageCards(records,editable)}</div>` : `<div class="empty"><strong>${session.images.length?'Không có ảnh ở bộ lọc này':'Bắt đầu với ảnh của bạn'}</strong>Ảnh sẽ xuất hiện ở đây để bạn gán nhãn.</div>`}<div class="pagination"><button class="button small ghost" id="prevPage"${disabled(offset===0)}>← Trước</button><span>Trang ${offset+1} / ${Math.max(1,Math.ceil(items.length/PAGE_SIZE))}</span><button class="button small ghost" id="nextPage"${disabled((offset+1)*PAGE_SIZE>=items.length)}>Sau →</button></div><div class="footer-action"><p>${session.unlabeled ? `Còn ${session.unlabeled} ảnh cần gán nhãn hoặc bỏ qua.` : 'Nhãn đã lưu. Sẵn sàng kiểm tra phân bố và chia ba tập.'}</p><button class="button primary" data-go="2"${disabled(session.images.length===0 || session.unlabeled>0)}>Tiếp: Chia dữ liệu →</button></div></div></div><aside>${distribution()}${question('CÂU HỎI THẢO LUẬN','Một chiếc cốc giấy có lớp nhựa bên trong nên được gán nhãn thế nào? Hãy thống nhất quy tắc nhãn của lớp học trước khi bắt đầu.')}${question('CHẤT LƯỢNG DỮ LIỆU','Ứng dụng bỏ ảnh có pixel trùng hoàn toàn. Các ảnh gần giống hoặc cùng vật thể chụp nhiều góc vẫn cần người học kiểm tra; hãy tránh để cùng vật thể ở nhiều tập.')}</aside></div>`;
}
function splitTable() {
  return `<div class="table-scroll"><table><thead><tr><th>TẬP DỮ LIỆU</th>${['metal','paper','plastic'].map(c=>`<th>${names[c]}</th>`).join('')}<th>TỔNG</th></tr></thead><tbody>${Object.entries(session.split_counts).map(([part,counts])=>`<tr><td><strong>${{train:'Train',validation:'Validation',test:'Test'}[part]}</strong>${part==='test' && session.phase!=='tested'?' <span class="tag sealed">Chưa mở</span>':''}</td>${Object.values(counts).map(n=>`<td>${n}</td>`).join('')}<td><strong>${Object.values(counts).reduce((a,b)=>a+b,0)}</strong></td></tr>`).join('')}</tbody></table></div>`;
}
function renderSplit() {
  const done = !!session.splits;
  return heading(2, 'Ba tập. Ba nhiệm vụ khác nhau.', 'Train để học trọng số, validation để chọn cấu hình, test để đánh giá mô hình đã chốt. Dữ liệu được chia theo từng lớp, không chia sau augmentation.') +
    `<div class="grid"><div><div class="card"><h2>Tỷ lệ chia dữ liệu</h2>${done ? `<div class="notice success"><strong>Đã chốt dữ liệu và nhãn</strong>Seed ${session.splits.seed}. Danh sách train/validation/test được lưu cố định trong phiên.</div><div class="split-bar"><div class="train" style="width:${session.splits.ratios.train*100}%">Train ${pct(session.splits.ratios.train,0)}</div><div class="val" style="width:${session.splits.ratios.validation*100}%">Val ${pct(session.splits.ratios.validation,0)}</div><div class="test" style="width:${session.splits.ratios.test*100}%">Test ${pct(session.splits.ratios.test,0)}</div></div>${splitTable()}<div class="footer-action"><a class="button ghost" href="${url('dataset.zip')}">↓ Tải ba tập dữ liệu</a><button class="button primary" data-go="3">Tiếp: Huấn luyện →</button></div>` : `<div class="form-grid"><label>Train (%)<input id="ratioTrain" type="number" min="1" max="98" value="70"></label><label>Validation (%)<input id="ratioVal" type="number" min="1" max="98" value="15"></label><label>Test (%)<input id="ratioTest" type="number" min="1" max="98" value="15"></label></div><div class="split-bar" id="ratioBar"><div class="train" style="width:70%">Train 70%</div><div class="val" style="width:15%">Val 15%</div><div class="test" style="width:15%">Test 15%</div></div><p id="ratioNote">Tổng 100% · Số ảnh mỗi tập được làm tròn theo từng lớp.</p><div class="form-grid two"><label>Seed chia dữ liệu<input id="splitSeed" type="number" min="0" max="2147483647" value="42"><small>Cố định seed và manifest để tái lập thí nghiệm.</small></label><div></div></div>${session.unlabeled ? `<div class="notice">Còn ${session.unlabeled} ảnh chưa gán nhãn. Quay lại bước 1 trước khi chia.</div>` : ''}<button class="button primary" id="splitAction"${disabled(session.unlabeled>0 || Math.min(...Object.values(session.counts))<10)}>Chốt nhãn & chia ba tập</button>`}${teaching('Giữ test độc lập', 'Không dùng kết quả test để chọn learning rate, epoch hay ngưỡng confidence. Sau khi chia, ứng dụng khóa nhãn và không hiển thị ảnh test cho đến khi đánh giá cuối.')}</div>${done && !['tested','test_failed'].includes(session.phase) ? `<button class="button ghost" id="returnLabels"${disabled(running())}>← Quay lại sửa nhãn / chia dữ liệu</button>` : ''}</div><aside>${distribution()}${question('DÙNG TẬP NÀO KHI NÀO?','<strong>Train:</strong> cập nhật trọng số.<br><strong>Validation:</strong> chọn cấu hình và checkpoint.<br><strong>Test:</strong> đo kết quả cuối, sau khi chốt.')}${question('CÂU HỎI THẢO LUẬN','Tại sao không thể chỉ chia thành train và test rồi thử nhiều cấu hình trên test? Nếu có nhiều ảnh của cùng vật thể, cần tổ chức lại dữ liệu thế nào?')}</aside></div>`;
}
function chart(history, a='train_loss', b='val_loss', labelA='Train loss', labelB='Validation loss') {
  if (!history?.length) return `<div class="empty" style="padding:35px">Biểu đồ xuất hiện khi huấn luyện bắt đầu.</div>`;
  const W=620,H=240,L=46,R=18,T=18,B=36;
  const vals = history.flatMap(h=>[h[a],h[b]]).filter(Number.isFinite);
  const max=Math.max(.01,...vals)*1.08,min=0,n=Math.max(2,history.length);
  const x=i=>L+i/(n-1)*(W-L-R),y=v=>H-B-(v-min)/(max-min)*(H-T-B);
  const points=key=>history.map((h,i)=>`${x(i).toFixed(1)},${y(h[key]).toFixed(1)}`).join(' ');
  const ticks=Array.from({length:5},(_,i)=>{const v=max*i/4,yy=y(v);return `<line x1="${L}" x2="${W-R}" y1="${yy}" y2="${yy}" stroke="#e9eee3"/><text x="${L-9}" y="${yy+4}" text-anchor="end" fill="#85917f" font-size="10">${v.toFixed(2)}</text>`;}).join('');
  return `<div class="chart-box"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(labelA)} và ${esc(labelB)} theo epoch">${ticks}<polyline points="${points(a)}" fill="none" stroke="#126b51" stroke-width="2.5"/><polyline points="${points(b)}" fill="none" stroke="#e18e43" stroke-width="2.5"/><text x="${L}" y="${H-12}" fill="#85917f" font-size="10">Epoch 1</text><text x="${W-R}" y="${H-12}" text-anchor="end" fill="#85917f" font-size="10">Epoch ${history.length}</text></svg></div><div class="chart-legend"><span><i></i>${labelA}</span><span><i class="val"></i>${labelB}</span></div>`;
}
function selectedTrial() {
  const trials=session.training?.trials || [];
  return trials.find(t=>t.id===(trialChoice || session.selected?.trial_id || session.training?.recommended)) || trials[0];
}
function trialTable(selectable=false) {
  return `<div class="table-scroll"><table><thead><tr>${selectable?'<th>CHỌN</th>':''}<th>CẤU HÌNH</th><th>LEARNING RATE</th><th>DROPOUT</th><th>EPOCH TỐT NHẤT</th><th>VAL ACCURACY</th><th>VAL MACRO-F1</th><th>TIÊU CHÍ</th></tr></thead><tbody>${session.training.trials.map((t,i)=>`<tr class="${t.id===session.training.recommended?'best':''} ${t.id===selectedTrial()?.id?'chosen':''}">${selectable?`<td><input type="radio" name="trial" value="${t.id}"${t.id===selectedTrial()?.id?' checked':''}${disabled(!t.eligible || session.phase!=='trained' || running())} aria-label="Chọn cấu hình ${i+1}"></td>`:''}<td><strong>Cấu hình ${i+1}</strong>${t.id===session.training.recommended?' <span class="tag">Đề xuất</span>':''}</td><td>${t.config.lr}</td><td>${t.config.dropout}</td><td>${t.best_epoch}</td><td>${pct(t.validation.accuracy)}</td><td><strong>${num(t.validation.macro_f1)}</strong></td><td><span class="tag${t.eligible?'':' fail'}">${t.eligible?'Đạt':'Chưa đạt'}</span></td></tr>`).join('')}</tbody></table></div>`;
}
function renderTrain() {
  if (!session.splits) return heading(3,'Huấn luyện, quan sát, so sánh.','Mô hình học từ train; mỗi epoch được kiểm tra bằng validation.')+noPrerequisite('Chưa có ba tập dữ liệu',2,'Đi đến bước chia dữ liệu');
  const settings=session.training?.settings || session.colab_request?.settings || {epochs:60,patience:12,views:4,min_f1:.8,min_recall:.6,confidence_threshold:.7};
  const rateValues=session.training?.trials.map(t=>t.config.lr).join(', ') || settings.candidates?.map(t=>t.lr).join(', ') || '0.001, 0.003, 0.01';
  const canTrain=['split','imported','trained'].includes(session.phase) && !running();
  const trial=selectedTrial(), history=session.job?.live?.history || trial?.history;
  return heading(3,'Train trên Colab. Validation trên web.','Xuất chỉ train cho Colab GPU, nhập checkpoint về đây rồi chạy validation để chọn cấu hình/epoch. Test vẫn ở server và chưa được đọc.')+
    `<div class="grid"><div><div class="card"><h2>Mô hình & kế hoạch thí nghiệm</h2><div class="model-banner"><div class="model-icon">▥</div><div><strong>EfficientNet-B0</strong><p>Pretrained ImageNet · Backbone đóng băng · Classifier 3 lớp</p></div><span class="tag">Transfer learning</span></div><div class="form-grid two"><label>Learning rate cần so sánh<input id="learningRates" value="${rateValues}"${disabled(!canTrain)}><small>Ngăn cách bằng dấu phẩy. Tối đa 6 cấu hình.</small></label><label>Dropout<input id="dropout" type="number" min="0" max="0.95" step="0.05" value="${trial?.config.dropout ?? settings.candidates?.[0]?.dropout ?? .2}"${disabled(!canTrain)}></label></div><div class="form-grid"><label>Epoch tối đa<input id="epochs" type="number" min="1" max="200" value="${settings.epochs}"${disabled(!canTrain)}></label><label>Patience (không dùng trên Colab)<input id="patience" type="number" min="1" max="50" value="${settings.patience}" disabled></label><label>Phiên bản / ảnh train<input id="views" type="number" min="1" max="8" value="${settings.views}"${disabled(!canTrain)}><small>1 ảnh gốc + augmentation; không nhân bản test.</small></label></div><details><summary>Tiêu chí chốt mô hình — đặt trước thí nghiệm</summary><div class="form-grid"><label>Validation macro-F1 tối thiểu<input id="minF1" type="number" min="0" max="1" step="0.05" value="${settings.min_f1}"${disabled(!canTrain)}></label><label>Recall tối thiểu mỗi lớp<input id="minRecall" type="number" min="0" max="1" step="0.05" value="${settings.min_recall}"${disabled(!canTrain)}></label><label>Ngưỡng confidence<input id="threshold" type="number" min="0" max="1" step="0.05" value="${settings.confidence_threshold}"${disabled(!canTrain)}></label></div><p>Đây là mục tiêu thực hành do người dạy đặt, không phải tiêu chuẩn triển khai. Đừng hạ ngưỡng chỉ để qua bước test.</p></details><div class="footer-action"><p>Thử nghiệm không đọc ảnh test.<br>Trọng số pretrained được tải trên Colab.</p><button class="button primary" id="colabExportAction"${disabled(!canTrain)}>Tải gói train cho Colab</button>${appConfig.allow_local_train?`<button class="button small ghost" id="trainAction"${disabled(!canTrain || session.phase==='imported')}>Train trên máy (tùy chọn)</button>`:''}</div></div>${colabCard()}<div class="card"><div class="card-head"><h2>Learning curves</h2><span class="tag" id="liveTrialLabel">${session.job?.live?`Cấu hình ${session.job.live.trial}`:trial?`${trial.id} · ${session.training.device.toUpperCase()}`:'Chưa chạy'}</span></div><div id="liveChart">${chart(history)}</div>${teaching('Quan sát overfit','Train loss giảm nhưng validation loss tăng là dấu hiệu cần thảo luận. Train có augmentation và dropout nên hai đường không nhất thiết có cùng mức loss.')}</div>${session.training?`<div class="card"><h2>Kết quả các cấu hình trên validation</h2>${trialTable()}<div class="footer-action"><p>Thời gian trích đặc trưng + train: ${session.training.training_seconds.toFixed(1)} giây.</p><button class="button primary" data-go="4">So sánh & chốt →</button></div></div>`:''}</div><aside>${question('MỤC TIÊU BÀI HỌC','Phân biệt trọng số được học với siêu tham số do người học đặt. Learning rate thay đổi tốc độ cập nhật; epoch tốt nhất không nhất thiết là epoch cuối.')}${question('CÂU HỎI THẢO LUẬN','Cấu hình nào tốt nhất trên validation? Nếu accuracy cao nhưng recall một lớp thấp, mô hình có đạt yêu cầu phân loại rác không?')}${question('VỚI DỮ LIỆU NHỎ','Backbone pretrained được giữ cố định. Ứng dụng trích đặc trưng rồi học lớp cuối để chạy nhanh trên CPU; đây vẫn là mô hình nhận ảnh đầu vào khi suy luận.')}</aside></div>`;
}
function colabCard() {
  const canImport=['split','imported','trained'].includes(session.phase) && !!session.colab_request && !running();
  const canValidate=['imported','trained'].includes(session.phase) && !!session.imported && !running();
  return `<div class="card"><div class="card-head"><h2>Colab → Validation trên web</h2><span class="tag">GPU TRAIN / WEB EVALUATION</span></div><p><strong>1.</strong> Tải gói train bằng nút ở trên. Validation và test không có trong gói.</p><p><strong>2.</strong> Mở notebook, chọn T4 GPU, upload gói train và chạy. Colab trả checkpoint của từng cấu hình ở mỗi epoch.</p><a class="button primary" href="${esc(appConfig.colab_notebook)}" target="_blank" rel="noopener">Mở notebook Colab ↗</a><p style="margin-top:16px"><strong>3.</strong> Nhập <code>SmartSort_Browser_Models.zip</code> vào đúng phiên này.</p><input class="file-input" id="colabImportInput" type="file" accept=".zip"><button class="button ghost" id="chooseColabModels"${disabled(!canImport)}>Nhập mô hình Colab</button>${session.imported?`<div class="notice success" style="margin-top:14px">${session.training?'Đã chạy validation. Có thể sang bước chốt cấu hình.':'Đã nhận checkpoint. Chưa chạy validation; chưa đọc test.'}</div>`:''}<p><strong>4.</strong> Học sinh chạy validation để so sánh cấu hình và chọn epoch tốt nhất; sau đó sang bước chốt.</p><button class="button primary" id="validationAction"${disabled(!canValidate)}>Chạy validation trong trình duyệt</button>${teaching('Chọn bằng validation, đánh giá cuối bằng test','Colab chỉ train theo số epoch đã đặt. Không có early stopping bằng validation trên Colab. Web kiểm tra mọi checkpoint trên validation rồi đề xuất cấu hình/epoch; test chỉ mở sau khi chốt.')}</div>`;
}
function trainingSettings() {
  const rates=$('#learningRates').value.split(',').map(v=>Number(v.trim()));
  if(!rates.length || rates.length>6 || rates.some(n=>!Number.isFinite(n)||n<=0||n>1))throw new Error('Nhập 1–6 learning rate lớn hơn 0 và không quá 1, ngăn cách bằng dấu phẩy.');
  return {epochs:Number($('#epochs').value),patience:Number($('#patience').value),views:Number($('#views').value),min_f1:Number($('#minF1').value),min_recall:Number($('#minRecall').value),confidence_threshold:Number($('#threshold').value),candidates:rates.map(lr=>({lr,dropout:Number($('#dropout').value),weight_decay:.001}))};
}
function perClassTable(rows) {
  return `<div class="table-scroll"><table><thead><tr><th>VẬT LIỆU</th><th>PRECISION</th><th>RECALL</th><th>F1</th><th>SỐ ẢNH</th></tr></thead><tbody>${rows.map(r=>`<tr><td><span class="dot ${r.label}" style="margin-right:6px"></span>${names[r.label]}</td><td>${num(r.precision)}</td><td>${num(r.recall)}</td><td>${num(r.f1)}</td><td>${r.support}</td></tr>`).join('')}</tbody></table></div>`;
}
function renderLock() {
  if (!session.training) return heading(4,'Chốt mô hình trước khi mở test.','Chọn cấu hình bằng validation, không dùng test.')+noPrerequisite('Cần kết quả huấn luyện trước',3,'Đi đến huấn luyện');
  const trial=selectedTrial(), locked=!!session.selected;
  return heading(4,'Chốt mô hình trước khi mở test.','So sánh validation và chọn một checkpoint. Khi chốt, ứng dụng lưu cấu hình, epoch, tiêu chí và bản chia dữ liệu; test vẫn chưa tham gia lựa chọn.')+
    `<div class="card"><h2>Bảng so sánh validation</h2>${trialTable(true)}<p>Đề xuất: đạt tiêu chí trước, rồi macro-F1 cao nhất; nếu bằng nhau chọn validation loss thấp hơn.</p></div><div class="grid"><div><div class="card"><h2>${locked?'Cấu hình đã được chốt':'Chi tiết cấu hình đang chọn'}</h2>${locked?'<div class="notice success"><strong>Đã khóa mô hình</strong>Không huấn luyện lại sau khi chốt. Test đánh giá đúng checkpoint đã chọn.</div>':''}<div class="summary-list"><div><small>MÔ HÌNH</small>EfficientNet-B0</div><div><small>CẤU HÌNH</small>${trial.id}</div><div><small>LEARNING RATE</small>${trial.config.lr}</div><div><small>EPOCH TỐT NHẤT</small>${trial.best_epoch}</div><div><small>VALIDATION MACRO-F1</small>${num(trial.validation.macro_f1)}</div><div><small>VALIDATION LOSS</small>${num(trial.validation.loss)}</div></div>${perClassTable(trial.validation.per_class)}<div class="footer-action"><p>${trial.eligible?'Cấu hình đạt mục tiêu validation đã đặt.':'Chưa đạt tiêu chí. Thu thập/kiểm tra dữ liệu và điều chỉnh dựa trên validation.'}</p>${locked?'<button class="button primary" data-go="5">Đi đến đánh giá test →</button>':`<button class="button primary" id="lockAction"${disabled(!trial.eligible || running())}>Chốt cấu hình ${trial.id.replace('trial_','')}</button>`}</div></div><div class="card"><h2>Learning curves của cấu hình đang chọn</h2>${chart(trial.history)}</div></div><aside><div class="card"><h3>Tiêu chí đã đặt trước</h3><p>Macro-F1 validation ≥ <strong>${num(session.training.settings.min_f1,2)}</strong></p><p>Recall từng lớp ≥ <strong>${num(session.training.settings.min_recall,2)}</strong></p><p>Confidence threshold: <strong>${num(session.training.settings.confidence_threshold,2)}</strong></p><p>Test: <strong>${session.splits.ids.test.length} ảnh, ${session.phase==='tested'?'đã đánh giá':'chưa mở'}</strong></p></div>${question('MỘT QUYẾT ĐỊNH CÓ BẰNG CHỨNG','Trước khi bấm chốt, học viên giải thích vì sao chọn cấu hình này và chấp nhận điểm yếu nào. Ghi lại giả thuyết về hiệu năng trên test.')}${question('KHÔNG “HỌC THUỘC” TEST','Sau khi xem test, thay đổi cấu hình rồi báo lại cùng test không còn là đánh giá cuối độc lập. Cần tập test mới cho lần cải tiến tiếp theo.')}</aside></div>`;
}
function confusion(cm) {
  const max=Math.max(1,...cm.flat());
  return `<div class="axis-label">Cột: nhãn dự đoán</div><div class="confusion"><div></div>${['metal','paper','plastic'].map(c=>`<div class="label">${names[c]}</div>`).join('')}${cm.map((row,i)=>`<div class="label">${names[['metal','paper','plastic'][i]]}</div>${row.map((v,j)=>`<div class="cell" style="background:${i===j?`rgba(18,107,81,${.1+.8*v/max})`:`rgba(225,142,67,${.08+.75*v/max})`};color:${i===j && v/max>.45?'white':'#16372f'}">${v}</div>`).join('')}`).join('')}</div><div class="axis-label">Hàng: nhãn thật · Ô ngoài đường chéo là lỗi phân loại.</div>`;
}
function testProbabilities(p) {
  return `<div class="test-probabilities">${['metal','paper','plastic'].map(c=>{
    const value=p['prob_'+c];
    return `<div class="test-probability"><span>${names[c]}</span><meter min="0" max="1" value="${Number.isFinite(value)?Math.max(0,Math.min(1,value)):0}" aria-label="Xác suất ${names[c]}"></meter><strong>${pct(value)}</strong></div>`;
  }).join('')}</div>`;
}
function filteredTestPredictions() {
  const query=testView.query.trim().toLocaleLowerCase('vi');
  return session.results.predictions.filter(p=>(testView.material==='all'||p.true_label===testView.material)
    &&(testView.outcome==='all'||(testView.outcome==='correct'?p.correct:!p.correct))
    &&(!query||p.filename.toLocaleLowerCase('vi').includes(query)))
    .sort((a,b)=>testView.sort==='filename'?a.filename.localeCompare(b.filename):testView.sort==='uncertain'?a.confidence-b.confidence:b.confidence-a.confidence);
}
function renderTestGallery() {
  const all=session.results.predictions, items=filteredTestPredictions(), pages=Math.max(1,Math.ceil(items.length/PAGE_SIZE));
  testView.page=Math.max(0,Math.min(testView.page,pages-1));
  return `<div class="card" id="testVisualization"><div class="card-head"><h2>Detection · Nhận diện vật liệu trên tập test</h2><span class="tag">${all.length} ảnh</span></div>
    <p>Model phân loại toàn bộ ảnh thành Kim loại, Giấy hoặc Nhựa. Model hiện tại không xác định vị trí hay vẽ khung từng vật thể. Bấm ảnh để xem lớn và so sánh kết quả.</p>
    <div class="test-class-summary">${['metal','paper','plastic'].map(c=>{
      const rows=all.filter(p=>p.true_label===c),right=rows.filter(p=>p.correct).length;
      return `<div class="test-class-stat"><strong><span class="dot ${c}"></span> ${names[c]}</strong><span>${right} đúng · ${rows.length-right} sai / ${rows.length} ảnh thật</span><div class="test-outcome-bar" role="img" aria-label="${names[c]}: ${right} đúng, ${rows.length-right} sai"><span style="width:${rows.length?100*right/rows.length:0}%"></span></div></div>`;
    }).join('')}</div>
    <div class="toolbar test-filters"><label>Nhãn thật<select id="testMaterial"><option value="all">Cả ba vật liệu</option>${['metal','paper','plastic'].map(c=>`<option value="${c}"${testView.material===c?' selected':''}>${names[c]}</option>`).join('')}</select></label>
    <label>Kết quả<select id="testOutcome">${[['all','Tất cả'],['correct','Dự đoán đúng'],['wrong','Dự đoán sai']].map(([v,t])=>`<option value="${v}"${testView.outcome===v?' selected':''}>${t}</option>`).join('')}</select></label>
    <label>Sắp xếp<select id="testSort">${[['confidence','Độ tin cậy cao trước'],['uncertain','Độ tin cậy thấp trước'],['filename','Tên ảnh']].map(([v,t])=>`<option value="${v}"${testView.sort===v?' selected':''}>${t}</option>`).join('')}</select></label>
    <label>Tìm tên ảnh<input id="testSearch" type="search" value="${esc(testView.query)}" placeholder="Nhập tên ảnh"></label></div>
    <p id="testMatchCount" aria-live="polite">Hiển thị ${items.length} / ${all.length} ảnh test · Màu xanh: đúng; màu cam: sai.</p>
    ${items.length?`<div class="gallery test-gallery">${items.slice(testView.page*PAGE_SIZE,(testView.page+1)*PAGE_SIZE).map(p=>`<article class="image-card test-image-card ${p.correct?'test-correct':'test-wrong'}"><button type="button" class="image-wrap test-image-button" data-enlarge="${esc(p.id)}" data-test-result="${esc(p.id)}" data-caption="${esc(p.filename)}" aria-label="Xem ${esc(p.filename)}: thật ${names[p.true_label]}, dự đoán ${names[p.predicted_label]}, ${p.correct?'đúng':'sai'}"><img src="${url('images/'+p.id)}" alt="Ảnh test ${esc(p.filename)}" loading="lazy"><span class="test-result-badge">${p.correct?'✓ Đúng':'✕ Sai'}</span></button><div class="image-meta"><div class="filename" title="${esc(p.filename)}">${esc(p.filename)}</div><div class="test-labels">Nhãn thật: <strong>${names[p.true_label]}</strong><br>Dự đoán: <strong>${names[p.predicted_label]}</strong><br>Độ tin cậy: <strong>${pct(p.confidence)}</strong></div>${testProbabilities(p)}</div></article>`).join('')}</div>`:'<div class="empty"><strong>Không có ảnh phù hợp</strong>Thử đổi bộ lọc hoặc tên ảnh.</div>'}
    <div class="pagination"><button class="button small ghost" id="testPrev"${disabled(testView.page===0)}>← Trước</button><span>Trang ${testView.page+1} / ${pages}</span><button class="button small ghost" id="testNext"${disabled(testView.page+1>=pages)}>Sau →</button></div>
    ${teaching('Quan sát lỗi để đánh giá model','So sánh các ảnh sai có độ tin cậy cao và các ảnh đúng có độ tin cậy thấp. Độ tin cậy không phải mức bảo đảm đúng. Kết quả hiển thị đã được lưu từ lần chạy test; lọc ảnh không chạy lại model và không thay đổi cấu hình.')}</div>`;
}
function renderTest() {
  if (!session.selected) return heading(5,'Đánh giá bằng dữ liệu chưa dùng để chọn mô hình.','Test chỉ được mở khi cấu hình đã chốt.')+noPrerequisite('Hãy chốt mô hình bằng validation',4,'Đi đến bước chốt');
  const r=session.results;
  if (!r) return heading(5,'Mở test. Thu kết quả cuối.', 'Đánh giá checkpoint đã chốt trên các ảnh test chưa được dùng để chọn cấu hình.')+`<div class="grid"><div><div class="card"><div class="lock-visual"><span class="icon">▣</span><div><h3>Mô hình đã khóa · ${session.selected.trial_id}</h3><p>Learning rate ${session.selected.config.lr} · Epoch ${session.selected.best_epoch} · Test ${session.splits.ids.test.length} ảnh</p></div></div><h2>Sẵn sàng cho đánh giá cuối</h2><p>Ứng dụng sẽ tính accuracy, precision/recall/F1 từng lớp, macro-F1, confusion matrix, độ tin cậy và danh sách ảnh sai. Báo cáo và checkpoint được lưu trên máy.</p>${session.phase==='test_failed'?'<div class="notice error">Lần chạy test bị ngắt/lỗi. Chỉ được thử lại cùng mô hình đã chốt; không quay lại chọn cấu hình.</div>':''}${teaching('Trước khi mở test','Hãy ghi dự đoán của bạn về hiệu năng và lớp dễ nhầm. Sau khi có kết quả, so sánh bằng chứng với giả thuyết; không đổi cấu hình để làm đẹp điểm test.')}<div class="footer-action"><p>Test chỉ suy luận; không cập nhật trọng số.</p><button class="button primary" id="testAction"${disabled(running())}>Mở test & thu kết quả</button></div></div></div><aside>${question('CÂU HỎI THẢO LUẬN','Nếu validation rất cao nhưng test thấp, có thể do dữ liệu nhỏ, lệch phân bố hoặc quá nhiều lần thử validation. Cần kiểm tra gì trước khi kết luận?')}</aside></div>`;
  const wrong=r.predictions.filter(p=>!p.correct).sort((a,b)=>b.confidence-a.confidence);
  const downloads=[['SmartSort_Results.zip','Toàn bộ kết quả','ZIP'],['REPORT.md','Báo cáo & câu hỏi thảo luận','MD'],['test_predictions.csv','Dự đoán từng ảnh','CSV'],['SmartSort_Locked_Model.zip','Mô hình đã chốt','ZIP'],['labels_and_splits.csv','Nhãn & danh sách chia','CSV']];
  return heading(5,'Kết quả để hiểu mô hình.', 'Đối chiếu kết quả cuối với validation, xem từng lớp và kiểm tra ảnh sai. Đây là bằng chứng cho thí nghiệm này, không phải bảo đảm hiệu năng ngoài thực tế.', 'TEST ĐÃ HOÀN TẤT')+
    `<div class="metric-grid"><div class="stat accent"><small>TEST ACCURACY</small><strong>${pct(r.accuracy)}</strong><span>${r.n} ảnh</span></div><div class="stat"><small>MACRO-F1</small><strong>${num(r.macro_f1)}</strong></div><div class="stat"><small>VALIDATION MACRO-F1</small><strong>${num(session.selected.validation.macro_f1)}</strong></div><div class="stat"><small>SỐ ẢNH DỰ ĐOÁN SAI</small><strong>${wrong.length}</strong><span>/ ${r.n}</span></div></div><div class="grid"><div><div class="card"><h2>Kết quả từng vật liệu</h2>${perClassTable(r.per_class)}${teaching('Đọc kết quả đúng cách','Precision: các dự đoán thuộc lớp có bao nhiêu ảnh đúng. Recall: các ảnh thật thuộc lớp được nhận ra bao nhiêu. F1 kết hợp precision và recall; macro-F1 cho ba lớp trọng số bằng nhau.')}</div><div class="card"><h2>Ma trận nhầm lẫn</h2>${confusion(r.confusion_matrix)}</div><div class="card"><h2>Những điểm cần đánh giá</h2>${r.observations.map((text,i)=>`<div class="observation"><span>${String(i+1).padStart(2,'0')}</span><div>${esc(text)}</div></div>`).join('')}<div class="summary-list"><div><small>KHOẢNG WILSON 95% CHO ACCURACY</small>${pct(r.accuracy_ci95[0])} — ${pct(r.accuracy_ci95[1])}</div><div><small>LOG-LOSS / BRIER</small>${num(r.loss)} / ${num(r.brier_multiclass)}</div><div><small>COVERAGE TẠI NGƯỠNG ${r.confidence_threshold}</small>${pct(r.coverage)}</div><div><small>ACCURACY TRÊN ẢNH ĐƯỢC CHẤP NHẬN</small>${pct(r.accepted_accuracy)}</div></div></div>${renderTestGallery()}<div class="card"><h2>Thử một ảnh mới</h2><p>Dùng mô hình đã chốt. Confidence cao vẫn có thể sai, đặc biệt với vật ngoài ba lớp.</p><input class="file-input" id="predictInput" type="file" accept="image/*"><button class="button ghost" id="choosePredict">Chọn ảnh mới</button><div id="predictResult"></div></div></div><aside><div class="card"><h3>Lưu kết quả bài thực hành</h3><p>File ZIP chứa báo cáo, CSV, nhãn, danh sách chia, cấu hình và checkpoint.</p><div class="download-list">${downloads.map(([file,title,ext])=>`<a class="button ghost" href="${url('download/'+file)}">↓ ${title}<small>${ext}</small></a>`).join('')}</div></div>${question('THẢO LUẬN KẾT QUẢ','Lớp nào dễ bỏ sót? Lỗi tập trung ở ánh sáng, nền, góc chụp hay hình dạng nào? Bạn cần bổ sung dữ liệu gì để kiểm tra giả thuyết đó?')}${question('KẾT THÚC THÍ NGHIỆM','Phiên này giữ nguyên cấu hình và kết quả test. Tạo phiên mới với dữ liệu test độc lập nếu muốn cải tiến. Không tạo lại cùng dữ liệu chỉ để chọn seed có điểm cao.')}</aside></div>`;
}
function renderJob() {
  const node=$('#jobBanner'),job=session?.job;
  if (!job || (job.status==='completed')) { node.className='job-banner hidden'; return; }
  node.className='job-banner'+(job.status==='failed'?' error':'');
  node.innerHTML=`<div><strong>${job.status==='failed'?'Tác vụ chưa hoàn tất':job.kind==='train'?'Đang huấn luyện':job.kind==='validation'?'Đang validation':'Đang chạy test'}</strong>${esc(job.message)}</div>${job.status==='running'?`<div class="progress"><span style="width:${Math.max(0,Math.min(100,job.progress))}%"></span></div><span>${job.progress}%</span>`:''}`;
  if(page===3 && job.live) { const target=$('#liveChart'); if(target) target.innerHTML=chart(job.live.history); const label=$('#liveTrialLabel'); if(label)label.textContent=`Cấu hình ${job.live.trial}`; }
}
function render() {
  if(!session)return;
  const completed=phaseSteps[session.phase] || 1;
  $('#steps').innerHTML=steps.map((s,i)=>`<button class="step${page===i+1?' active':''}${completed>i+1?' complete':''}" data-go="${i+1}"><span class="number">${completed>i+1?'✓':String(i+1).padStart(2,'0')}</span>${s}</button>`).join('');
  $('#content').innerHTML=[renderLabels,renderSplit,renderTrain,renderLock,renderTest][page-1]();
  renderJob(); bindPage();
}
function go(next) { page=Number(next); selected.clear(); render(); window.scrollTo({top:0,behavior:'smooth'}); }
async function setLabels(ids,label) { session=await api(url('labels'),'PUT',{ids,label}); selected.clear(); render(); }
async function upload(fileList) {
  if (!fileList.length || uploading)return;
  uploading=true; $('#sessionPicker').disabled=true; $('#newSession').disabled=true; const button=$('#chooseFiles'); if(button){button.disabled=true;button.textContent='Đang tải & kiểm tra ảnh...';}
  try {
    const form=new FormData(); for(const f of fileList)form.append('files',f);
    const data=await api(url('images'),'POST',form); session=data.session; filter='unlabeled'; offset=0;
    toast(`Đã thêm ${data.added} ảnh; ${data.duplicates} ảnh trùng được bỏ qua.${data.rejected.length?' Có '+data.rejected.length+' file bị từ chối: '+data.rejected.slice(0,3).map(r=>r.filename+' — '+r.reason).join('; '):''}`,data.rejected.length>0);
  } finally { uploading=false;$('#sessionPicker').disabled=false;$('#newSession').disabled=false;render(); }
}
function bindPage() {
  ['testMaterial','testOutcome','testSort'].forEach((id,i)=>$('#'+id)?.addEventListener('change',e=>{testView[['material','outcome','sort'][i]]=e.target.value;testView.page=0;render();}));
  $('#testSearch')?.addEventListener('input',e=>{const cursor=e.target.selectionStart;testView.query=e.target.value;testView.page=0;render();const input=$('#testSearch');input.focus();input.setSelectionRange(cursor,cursor);});
  $('#testPrev')?.addEventListener('click',()=>{testView.page--;render();});
  $('#testNext')?.addEventListener('click',()=>{testView.page++;render();});
  $('#chooseFiles')?.addEventListener('click',()=>$('#uploadInput').click());
  $('#uploadInput')?.addEventListener('change',e=>act(()=>upload(e.target.files)));
  const drop=$('#dropzone');
  if(drop){drop.addEventListener('dragover',e=>{e.preventDefault();drop.classList.add('dragover');});drop.addEventListener('dragleave',()=>drop.classList.remove('dragover'));drop.addEventListener('drop',e=>{e.preventDefault();drop.classList.remove('dragover');act(()=>upload(e.dataTransfer.files));});}
  $('#labelFilter')?.addEventListener('change',e=>{filter=e.target.value;offset=0;selected.clear();render();});
  $('#prevPage')?.addEventListener('click',()=>{offset--;render();});$('#nextPage')?.addEventListener('click',()=>{offset++;render();});
  $('#selectPage')?.addEventListener('click',()=>{visibleImages().slice(offset*PAGE_SIZE,(offset+1)*PAGE_SIZE).forEach(r=>selected.add(r.id));render();});
  $('#clearSelection')?.addEventListener('click',()=>{selected.clear();render();});
  $('#applyBatch')?.addEventListener('click',()=>act(()=>setLabels([...selected],$('#batchLabel').value)));
  document.querySelectorAll('[data-select]').forEach(n=>{n.addEventListener('click',e=>e.stopPropagation());n.addEventListener('change',e=>{e.target.checked?selected.add(n.dataset.select):selected.delete(n.dataset.select);n.closest('.image-card').classList.toggle('selected',e.target.checked);$('#batchBar').classList.toggle('hidden',!selected.size);$('#selectionCount').textContent=selected.size+' ảnh đã chọn';});});
  document.querySelectorAll('[data-label]').forEach(n=>n.addEventListener('change',()=>act(()=>setLabels([n.dataset.label],n.value||null))));
  $('#splitAction')?.addEventListener('click',()=>act(async()=>{session=await api(url('split'),'POST',{train:Number($('#ratioTrain').value)/100,validation:Number($('#ratioVal').value)/100,test:Number($('#ratioTest').value)/100,seed:Number($('#splitSeed').value)});toast('Đã chia và khóa dữ liệu. Test chưa được mở.');render();}));
  ['ratioTrain','ratioVal','ratioTest'].forEach(id=>$('#'+id)?.addEventListener('input',()=>{const vals=['ratioTrain','ratioVal','ratioTest'].map(k=>Number($('#'+k).value));const sum=vals.reduce((a,b)=>a+b,0);$('#ratioNote').textContent=`Tổng ${sum}% ${sum===100?'· Hợp lệ':'· Cần bằng 100%'}`;$('#ratioBar').innerHTML=vals.map((v,i)=>`<div class="${['train','val','test'][i]}" style="width:${Math.max(0,v)/Math.max(1,sum)*100}%">${['Train','Val','Test'][i]} ${v}%</div>`).join('');}));
  $('#returnLabels')?.addEventListener('click',()=>act(async()=>{if(!confirm('Quay lại gán nhãn sẽ bỏ bản chia và lựa chọn cấu hình hiện tại. Ảnh và nhãn vẫn được giữ. Tiếp tục?'))return;session=await api(url('return-to-labeling'),'POST');go(1);}));
  $('#trainAction')?.addEventListener('click',()=>act(async()=>{
    const rates=$('#learningRates').value.split(',').map(v=>Number(v.trim()));
    if(!rates.length || rates.length>6 || rates.some(n=>!Number.isFinite(n)||n<=0||n>1))throw new Error('Nhập 1–6 learning rate lớn hơn 0 và không quá 1, ngăn cách bằng dấu phẩy.');
    const body={epochs:Number($('#epochs').value),patience:Number($('#patience').value),views:Number($('#views').value),min_f1:Number($('#minF1').value),min_recall:Number($('#minRecall').value),confidence_threshold:Number($('#threshold').value),candidates:rates.map(lr=>({lr,dropout:Number($('#dropout').value),weight_decay:.001}))};
    session=await api(url('train'),'POST',body);trialChoice=null;render();toast('Đã bắt đầu huấn luyện. Bạn có thể quan sát tiến độ trên giao diện.');
  }));
  $('#colabExportAction')?.addEventListener('click',()=>act(async()=>{
    const button=$('#colabExportAction');button.disabled=true;
    try {
      const response=await BrowserLab.fetch(url('colab/export'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(trainingSettings())});
      if(!response.ok){const data=await response.json();throw new Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail));}
      const blob=await response.blob(),objectURL=URL.createObjectURL(blob),a=document.createElement('a');
      a.href=objectURL;a.download='SmartSort_Colab_Train.zip';a.click();setTimeout(()=>URL.revokeObjectURL(objectURL),10000);
      await refresh();toast('Đã xuất chỉ train. Mở notebook Colab và upload gói này.');
    } finally { if(button.isConnected)button.disabled=false; }
  }));
  $('#chooseColabModels')?.addEventListener('click',()=>$('#colabImportInput').click());
  $('#colabImportInput')?.addEventListener('change',e=>act(async()=>{
    const file=e.target.files[0];if(!file)return;
    const form=new FormData();form.append('file',file);
    session=await api(url('colab/import'),'POST',form);trialChoice=null;render();toast('Đã nhập checkpoint. Bấm Chạy validation trong trình duyệt.');
  }));
  $('#validationAction')?.addEventListener('click',()=>act(async()=>{session=await api(url('validation'),'POST');trialChoice=null;render();}));
  document.querySelectorAll('input[name="trial"]').forEach(n=>n.addEventListener('change',()=>{trialChoice=n.value;render();}));
  $('#lockAction')?.addEventListener('click',()=>act(async()=>{session=await api(url('lock'),'POST',{trial_id:selectedTrial().id});trialChoice=null;toast('Đã chốt cấu hình. Bước tiếp theo: mở test để đánh giá cuối.');render();}));
  $('#testAction')?.addEventListener('click',()=>act(async()=>{session=await api(url('test'),'POST');render();}));
  $('#choosePredict')?.addEventListener('click',()=>$('#predictInput').click());
  $('#predictInput')?.addEventListener('change',e=>act(async()=>{const file=e.target.files[0];if(!file)return;$('#choosePredict').disabled=true;try{const form=new FormData();form.append('file',file);const r=await api(url('predict'),'POST',form);const container=$('#predictResult');container.innerHTML=`<div class="predict-result"><img class="predict-preview" alt="Ảnh mới"><div><h3>${esc(r.decision)}</h3><p>Top-1: ${esc(r.name)} · Confidence ${pct(r.confidence)}</p>${Object.entries(r.probabilities).map(([c,p])=>`<p>${names[c]}: ${pct(p)}</p>`).join('')}</div></div>`;const image=$('.predict-preview',container);const objectURL=URL.createObjectURL(file);image.onload=()=>URL.revokeObjectURL(objectURL);image.src=objectURL;}finally{$('#choosePredict').disabled=false;}}));
}
document.addEventListener('click',e=>{
  const nav=e.target.closest('[data-go]');if(nav && !nav.disabled)go(nav.dataset.go);
  const image=e.target.closest('[data-enlarge]');if(image && !e.target.matches('input')){
    $('#largeImage').src=url('images/'+image.dataset.enlarge);$('#largeCaption').textContent=image.dataset.caption;
    const details=$('#largeTestResult');details.innerHTML='';
    const prediction=image.dataset.testResult&&session.results?.predictions.find(p=>p.id===image.dataset.testResult);
    if(prediction)details.innerHTML=`<p class="test-labels">${prediction.correct?'✓ Dự đoán đúng':'✕ Dự đoán sai'} · Nhãn thật: <strong>${names[prediction.true_label]}</strong> · Dự đoán: <strong>${names[prediction.predicted_label]}</strong> · Độ tin cậy: <strong>${pct(prediction.confidence)}</strong></p>${testProbabilities(prediction)}`;
    $('#imageDialog').showModal();
  }
});
$('#sessionPicker').addEventListener('change',e=>act(()=>loadSessions(e.target.value)));
$('#newSession').addEventListener('click',()=>{$('#newTitle').value='';$('#newDialog').showModal();$('#newTitle').focus();});
$('#cancelNew').addEventListener('click',()=>$('#newDialog').close());
$('#confirmNew').addEventListener('click',()=>act(async()=>{const button=$('#confirmNew');button.disabled=true;try{const s=await api('/api/sessions','POST',{title:$('#newTitle').value});await loadSessions(s.id);$('#newDialog').close();}finally{button.disabled=false;}}));
async function poll() {
  if(session && !uploading && !loadingSession){
    try{const id=session.id,previous=session.job?.status,oldPhase=session.phase;const latest=await api(`/api/sessions/${id}`);if(session.id!==id || loadingSession){pollTimer=setTimeout(poll,1800);return;}session=latest;
      if(previous==='running' && latest.job?.status!=='running'){trialChoice=null;if(latest.phase==='tested')page=5;render();toast(latest.job.message,latest.job.status==='failed');}
      else if(oldPhase!==latest.phase)render();else renderJob();
    }catch(error){if(running())toast(error.message,true);}
  }
  pollTimer=setTimeout(poll,1800);
}
$('#content').innerHTML='<div class="loading">Đang mở phòng thực hành…</div>';
act(async()=>{await BrowserLab.ready;appConfig=await api('/api/config');await loadSessions();poll();});

document.addEventListener('click',event=>{const a=event.target.closest('a[href^="/api/"]');if(!a)return;event.preventDefault();act(()=>BrowserLab.download(a.getAttribute('href')));});
$('#backupSession').addEventListener('click',()=>act(()=>BrowserLab.backup(session.id)));
$('#restoreSession').addEventListener('click',()=>$('#restoreInput').click());
$('#restoreInput').addEventListener('change',event=>act(async()=>{const file=event.target.files[0];if(!file)return;const id=await BrowserLab.restore(file);await loadSessions(id);toast('Đã mở phiên từ bản sao lưu.');}));
