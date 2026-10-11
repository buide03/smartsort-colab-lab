# Render Static Site + Colab + đánh giá trong trình duyệt

Đây là bản Browser Lab, giữ luồng **ảnh chưa có nhãn → gán nhãn → chia train/validation/test → train Colab → validation → chốt cấu hình/epoch → test → báo cáo**. Render chỉ phục vụ HTML/CSS/JS và ONNX Runtime Web. Ảnh/model/phiên nằm trong IndexedDB của trình duyệt; validation/test chạy CPU trên máy học sinh.

## 1. Deploy miễn phí từ GitHub

1. Đăng ký/đăng nhập [Render Dashboard](https://dashboard.render.com/) bằng GitHub. Cấp quyền đọc repo `buide03/smartsort-colab-lab`.
2. Chọn **New → Static Site**, chọn repo và nhánh **main**. Không chọn Web Service/Docker cho bản này.
3. Điền:

| Trường | Giá trị |
|---|---|
| Name | `smartsort-browser-lab` hoặc tên bạn muốn |
| Branch | `main` |
| Root Directory | Để trống |
| Build Command | `test -f static_site/index.html` |
| Publish Directory | `static_site` |
| Environment Variables | Không cần |

4. Bấm **Create Static Site**; đợi Live. Render cấp URL `https://<tên-thật>.onrender.com`. Mở URL này để kiểm tra, rồi gửi cho học sinh.
5. Có thể dùng Blueprint từ `render.yaml` thay cho nhập từng trường. Bản này không cần persistent disk, PostgreSQL, Docker hay VM. Chỉ có thể kiểm tra URL thật sau khi bạn tạo/kết nối tài khoản Render.

Static Sites miễn phí trong hạn mức bandwidth/build của workspace, có URL và managed TLS. [Tài liệu Render Static Sites](https://render.com/docs/static-sites), [hạn mức miễn phí](https://render.com/docs/free). Kiểm tra Usage trên Dashboard; không hiểu miễn phí là lưu lượng không giới hạn.

## 2. Chạy thử local

Clone repo rồi chạy Python để phục vụ file tĩnh; không cần cài PyTorch/FastAPI cho việc mở web:

```powershell
git clone https://github.com/buide03/smartsort-colab-lab.git
cd smartsort-colab-lab
python run_browser_lab.py
```

Mở **http://127.0.0.1:8001/**. `python run_local.py` trên port 8000 vẫn là bản backend Docker cũ. Hai bản dùng nơi lưu dữ liệu và định dạng model khác nhau; không tự chuyển phiên giữa hai bản.

Các asset đã được build và commit trong `static_site/`, gồm runtime WASM. Không tải thư viện từ CDN lúc học sinh chạy lab. `browser_lab/build_static.py` là công cụ dành cho người phát triển: sinh giao diện từ frontend chung và ghép engine trình duyệt; nếu thay frontend, chạy lại công cụ trước khi push. ONNX Runtime Web 1.23.2 và fflate 0.8.2 được vendored; giấy phép nằm tại `static_site/vendor/`.

## 3. Thao tác học sinh

1. Dùng Chrome/Edge mới trên laptop/PC, tạo phiên có tên nhóm.
2. Tải ảnh hoặc ZIP. Tất cả ảnh ban đầu **chưa có nhãn**; tên file/thư mục/manifest không được dùng để tự gán nhãn. Chọn Nhựa, Giấy, Kim loại hoặc Bỏ qua.
3. Cần ít nhất 10 ảnh khác nhau mỗi lớp, khuyến nghị từ 50. Ứng dụng bỏ ảnh trùng pixel; ảnh gần trùng/cùng vật thể vẫn cần người học kiểm tra.
4. Chia train/validation/test. Seed và danh sách/hash bản chia lưu cùng phiên. Seed đơn lẻ không đủ để tái tạo bản chia trong phiên mới có ID ảnh khác; dùng bản sao lưu/manifest khi cần giữ nguyên. Thuật toán chia của bản Browser khác bản Python, không so trực tiếp điểm giữa hai bản chia.
5. Đặt cấu hình, epoch, augmentation views, ngưỡng macro-F1/recall và confidence trước khi xuất train. Patience không áp dụng trong Colab train-only.
6. Bấm **Tải gói train cho Colab**; chỉ train có trong ZIP. Bấm **Mở notebook Colab**, dùng [SmartSort_Browser_Colab.ipynb](https://colab.research.google.com/github/buide03/smartsort-colab-lab/blob/main/colab/SmartSort_Browser_Colab.ipynb).
7. Trên Colab chọn **Runtime → Change runtime type → T4 GPU**, chạy từng ô và upload gói train. Notebook dừng nếu chưa có CUDA. Colab chỉ train, không có validation/test, không tự chọn epoch hoặc early stopping bằng validation.
8. Tải **SmartSort_Browser_Models.zip**. Quay lại đúng phiên trên web, bấm **Nhập mô hình Colab**. Gói model của phiên/yêu cầu/bản chia khác sẽ bị từ chối. Nếu xuất train lại, gói model trước đó không còn khớp.
9. Bấm **Chạy validation trong trình duyệt**. Backbone EfficientNet-B0 trích đặc trưng validation một lần; đánh giá classifier ở mọi epoch/cấu hình. Chọn epoch macro-F1 cao nhất, tie-break bằng loss; cấu hình được đánh dấu đạt theo tiêu chí đã đặt.
10. So sánh, giải thích lý do chọn rồi **chốt cấu hình**. Chỉ cấu hình đạt validation mới chốt được.
11. Chạy test. Chỉ checkpoint đã chốt được đánh giá, không cập nhật trọng số. Xem accuracy, per-class precision/recall/F1, macro-F1, confusion matrix, Wilson CI, log-loss/Brier, coverage, lỗi tự tin cao và ảnh sai.
12. Tải **SmartSort_Results.zip** để nộp giáo viên, gồm báo cáo/CSV/nhãn/bản chia/cấu hình và **SmartSort_Locked_Model.zip**. Model cuối gồm ONNX backbone, classifier JSON, cấu hình và tiền xử lý; không phải file PyTorch `.pt`.

Sau chốt không chạy validation lại; sau test không sửa nhãn, bản chia hoặc cấu hình. Test bị ngắt chỉ được thử lại model đã chốt. Gallery giữ kín ảnh test đến khi test hoàn tất. Nút tải dữ liệu chỉ xuất train/validation trước test; sau test mới gồm cả ba tập. Bản sao lưu cần giữ đầy đủ dữ liệu để phục hồi nên chứa test; giáo viên dùng quy tắc này để dạy phương pháp đánh giá, không xem frontend là cơ chế chống gian lận kỳ thi.

## 4. Lưu phiên và đổi máy

- Reload hoặc đóng/mở lại trên **cùng browser profile và cùng domain** vẫn giữ phiên nếu dữ liệu trang chưa bị xóa/thu hồi.
- Bấm **Sao lưu phiên** sau chia tập, sau xuất train và sau có kết quả. ZIP chứa ảnh, trạng thái, split, yêu cầu train, model đã nhập và kết quả; chỉ báo cáo ZIP không đủ phục hồi toàn phiên.
- Trên máy/browser khác, bấm **Mở bản sao lưu**, chọn `SmartSort_Browser_Session.zip`. Phiên trùng ID được tạo thành bản khôi phục riêng, không ghi đè phiên đang có; gói Colab đã xuất vẫn khớp yêu cầu lưu trong backup.
- Không dùng tab ẩn danh cho bài cần giữ lâu. Xóa site data, đổi domain hoặc browser profile sẽ không thấy phiên cũ; nhập backup để phục hồi.
- Chỉ mở một tab Browser Lab trên cùng browser profile. Đóng tab cũ trước khi mở tab mới. Không đóng/reload khi validation/test đang chạy. Nếu bị ngắt, ứng dụng đánh dấu thất bại khi mở lại.
- Ảnh/model không được upload lên Render; chỉ gói train được upload Colab khi học sinh thực hiện. Giáo viên nhận kết quả qua file học sinh nộp; chưa có dashboard/tài khoản/lưu trữ tập trung của lớp.

## 5. Lớp khoảng 40 học sinh

Khuyến nghị 8–10 nhóm và mỗi nhóm một laptop. Các nhóm có thể đánh giá độc lập trên máy mình, không chờ CPU server chung. Dùng 200–500 ảnh vừa phải, 2–3 cấu hình, 10–30 epoch cho lần đầu. Với bộ mẫu hiện tại 195 ảnh, cần tự gán nhãn và bỏ qua ảnh ngoài ba lớp.

Giới hạn mỗi lượt upload 64 MB, mỗi ảnh 25 MB/20 triệu pixel, tối đa 1.000 ảnh và 512 MB ảnh PNG mỗi phiên. Model ZIP tối đa 100 MB; giới hạn thực tế còn phụ thuộc RAM/dung lượng browser. Browser báo thiếu quota khi không lưu được; tải backup trước khi dọn dữ liệu. Không đưa private key, thông tin thẻ hoặc dữ liệu cá nhân vào dataset.

Thời gian phụ thuộc CPU máy học sinh; chưa đo tải 40 người/40 thiết bị thực tế. Số người truy cập không tạo hàng đợi suy luận server, nhưng vẫn tiêu thụ bandwidth asset của Render. Máy yếu/điện thoại có thể chậm; notebook cần GPU do Colab cấp phát và không cam kết luôn có tài nguyên. Hiệu năng mẫu kiểm thử không phải bằng chứng chất lượng triển khai model ngoài thực tế.

## 6. Kiểm thử kỹ thuật

`tests/verify_static_browser.py` dùng trainer CPU **chỉ cho fixture kiểm thử**. Nó chạy model thật, kiểm tra tiền xử lý Pillow/bicubic trên ảnh vuông và chữ nhật, xuất train-only, ONNX parity, import, số ảnh thật được decode khi validation/test, gate chốt/test, ZIP kết quả, reload, backup/restore và giao diện hẹp. Fixture đặt min-F1/min-recall bằng 0 để kiểm tra luồng, không thay mặc định 0.80/0.60 của sản phẩm.

Notebook người dùng vẫn yêu cầu CUDA; chưa tuyên bố đã chạy hosted Colab GPU. Runtime browser CPU dùng ONNX Runtime Web/WASM một thread để chạy được trên static host mà không cần cấu hình cross-origin isolation. [Tài liệu ONNX Runtime Web](https://onnxruntime.ai/docs/tutorials/web/).

Xem workflow **Static browser lab checks** tại [GitHub Actions](https://github.com/buide03/smartsort-colab-lab/actions). Trước khi phát URL, giáo viên hoàn thành một vòng train GPU thật và kiểm tra lưu/khôi phục trên URL Render.
