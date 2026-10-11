# SmartSort Classroom — hướng dẫn dạy học

Giao diện local dùng cho bài học **từ ảnh chưa có nhãn đến huấn luyện, chốt mô hình và đánh giá test**. Mỗi phiên giữ riêng dữ liệu và kết quả. Notebook cũ trong `SmartSort_Lab/` vẫn được giữ làm ví dụ Colab với dữ liệu đã có nhãn.

Bản mới hỗ trợ **train trên Colab GPU → học sinh chạy validation trên web → chốt → test**. Notebook mới nằm trong `colab/`; xem [hướng dẫn Colab và deploy Railway](COLAB_VA_DEPLOY_RAILWAY.md). Có thể dùng Docker/URL Railway cho cả lớp, không cần học sinh cài môi trường.

## Mục tiêu và chuẩn bị

Học viên biết gán nhãn theo quy tắc thống nhất, phân biệt train/validation/test, thay learning rate và quan sát learning curves, chọn checkpoint bằng validation rồi đánh giá test độc lập.

Cần Python 3.10 trở lên; khuyến nghị 3.11/3.12. Chạy được CPU, không bắt buộc GPU. Cần Internet lần đầu để cài thư viện và tải trọng số ImageNet. Giao diện không dùng CDN hay dịch vụ AI bên ngoài; ảnh, nhãn và kết quả được lưu trên máy trong `.smartsort/`.

```powershell
python -m pip install -r requirements.txt
python run_local.py
```

Mở **http://127.0.0.1:8000**, giữ cửa sổ Python chạy; `Ctrl+C` để dừng. Nếu cổng bị dùng: `python run_local.py --port 8001`. Trên Windows cũng có thể chạy `powershell -ExecutionPolicy Bypass -File start_local.ps1`; script không thay đổi chính sách hệ thống.

Ứng dụng cho thực hành từ 10 ảnh khác nhau/lớp. Khuyến nghị từ 50 ảnh/lớp, nhiều vật thể và điều kiện chụp. Không dùng bộ nhỏ để chứng minh hệ thống sẵn sàng triển khai.

## Kịch bản 60–90 phút

| Hoạt động | Thời lượng gợi ý | Sản phẩm học viên |
|---|---:|---|
| Thống nhất nhãn, tải ảnh và gán nhãn | 15–25 phút | Nhãn CSV, quy tắc xử lý ảnh khó |
| Chia ba tập, giải thích vai trò | 5–10 phút | Tỷ lệ chia, seed, bảng số lượng |
| Huấn luyện các cấu hình | 10–20 phút | Learning curves, bảng validation |
| Chốt checkpoint, dự đoán trước test | 5–10 phút | Lý do chọn cấu hình, giả thuyết |
| Mở test, phân tích và thảo luận | 15–25 phút | ZIP báo cáo và đề xuất dữ liệu mới |

Thời gian huấn luyện phụ thuộc máy, số ảnh và số cấu hình; đây là gợi ý tổ chức lớp.

## 1. Tải ảnh và gán nhãn

Tải nhiều ảnh JPG/PNG/WEBP/BMP hoặc ZIP, có thể nhiều lượt. Chỉ ảnh được nhập; tài liệu trong ZIP không được thực thi. **Mọi ảnh bắt đầu chưa có nhãn**, kể cả khi thư mục tên `plastic` hoặc ZIP có manifest. Ứng dụng không đoán nhãn từ tên file.

Chọn Kim loại/Giấy/Nhựa dưới mỗi ảnh. Bấm ảnh để xem lớn; chọn nhiều ảnh rồi dùng thanh gán nhãn nhóm. Lọc “Chưa gán nhãn” để kiểm tra ảnh còn thiếu. Chọn Bỏ qua cho thủy tinh, vật ngoài ba lớp, ảnh nhiều vật liệu hoặc quá khó xác định theo quy tắc đã thống nhất. Nhãn được lưu ngay; tải `labels.csv` để nộp bài.

Ứng dụng loại ảnh có pixel RGB trùng hoàn toàn sau chuẩn hóa EXIF/alpha. Ảnh gần trùng, cùng vật thể hoặc cùng phiên chụp cần người dạy kiểm tra. Không thay quy tắc nhãn chỉ để tăng điểm mô hình.

**Thảo luận:** Carton có được coi là giấy không? Nếu bài học chỉ định giấy mềm là lớp riêng, bỏ qua carton. Nếu gom carton vào giấy, thống nhất ngay từ khi gán nhãn và giữ nguyên trong cả ba tập. Một cốc giấy có lớp nhựa bên trong nên được xử lý thế nào?

## 2. Chia train/validation/test

Mặc định 70%/15%/15%, seed 42, chia theo từng lớp để cả ba tập đều có cả ba vật liệu. Số lượng làm tròn, mỗi lớp có ít nhất một ảnh validation và test.

Bấm “Chốt nhãn & chia ba tập” để khóa nhãn và bản chia. Ảnh test ẩn đến khi đánh giá cuối. Có thể tải ZIP ba tập; manifest lưu chính xác ảnh nào ở mỗi tập. Seed tái lập trên cùng manifest đã lưu, không cam kết cùng seed tạo đúng bản chia khi danh sách ảnh thay đổi.

Trước khi mở test có thể quay lại sửa nhãn/chia lại, nhưng lựa chọn cấu hình hiện tại bị xóa trong phiên. Sau khi mở test không được chỉnh lại thí nghiệm đó.

**Thảo luận:** Nếu cùng một chai nhựa xuất hiện ở cả train và test, mô hình đang học vật liệu hay ghi nhớ chiếc chai? Cần chia theo vật thể/phiên chụp; ứng dụng hiện chưa tự nhận biết các nhóm vật thể.

## 3. Huấn luyện và validation

Mô hình là EfficientNet-B0 pretrained ImageNet, backbone đóng băng, classifier mới có ba đầu ra. Đặc trưng train được cache để chạy nhanh trên CPU. Phiên bản gốc và augmentation chỉ xuất phát từ train; validation/test không augmentation. Ảnh letterbox 224×224, chuẩn hóa ImageNet.

Mặc định so sánh learning rate 0.001, 0.003, 0.01, dropout 0.2 và 60 epoch. Trong luồng Colab, xuất chỉ train; Colab lưu checkpoint từng epoch, không có validation/test và không early stopping bằng validation. Học sinh nhập gói mô hình và chạy validation trên web để chọn checkpoint macro-F1 cao nhất, nếu bằng nhau chọn loss thấp hơn. Các cấu hình dùng cùng một bản chia, không đọc test. Patience 12 chỉ dùng cho tùy chọn train local cũ.

Tiêu chí chốt mặc định: macro-F1 validation ≥ 0.80, recall mỗi lớp ≥ 0.60. Đây là mục tiêu thực hành, người dạy đặt trước thí nghiệm; không hạ ngưỡng chỉ để qua test. Ngưỡng confidence 0.70 cũng đặt trước test; softmax chưa được hiệu chỉnh thành xác suất dự đoán đúng.

**Thảo luận:** Vì sao epoch tốt nhất có thể khác epoch cuối? Train loss giảm nhưng validation loss tăng gợi ý gì? Vì train có augmentation/dropout, hai đường loss không hoàn toàn cùng điều kiện.

## 4. Chốt cấu hình

Xem bảng validation, precision/recall/F1 từng lớp và learning curves. Chọn cấu hình đạt tiêu chí; ứng dụng đề xuất cấu hình đạt tiêu chí có macro-F1 cao nhất, tie-break bằng loss. Học viên ghi lý do lựa chọn và dự đoán test trước khi bấm chốt.

Khi chốt, ứng dụng lưu siêu tham số, checkpoint, epoch, validation, ngưỡng, thời gian chốt và hash bản chia. Test đánh giá đúng checkpoint đó; không cập nhật trọng số.

**Phiếu trả lời:** Tôi chọn cấu hình ___ vì ___. Điểm yếu trên validation là ___. Tôi dự đoán accuracy test khoảng ___ và lớp dễ nhầm là ___.

## 5. Mở test và đánh giá

Test chỉ suy luận. Kết quả giữ cố định; gọi lại test trả kết quả đã lưu, không ngầm huấn luyện/chia lại.

| Số đo | Ý nghĩa |
|---|---|
| Accuracy | Số dự đoán đúng / tổng ảnh |
| Precision mỗi lớp | Trong dự đoán thuộc lớp, bao nhiêu ảnh đúng |
| Recall mỗi lớp | Trong ảnh thật thuộc lớp, bao nhiêu ảnh được nhận ra |
| F1 / macro-F1 | Cân bằng precision/recall; trung bình đều ba lớp |
| Confusion matrix | Hàng: nhãn thật; cột: nhãn dự đoán; ngoài đường chéo: lỗi |
| Wilson 95% | Khoảng ước lượng accuracy, giả định các ảnh độc lập |
| Log-loss / Brier | Phạt xác suất dự đoán sai; thấp tốt |
| Coverage / accepted accuracy | Tỷ lệ ảnh qua ngưỡng confidence và độ đúng trong số đó |
| Lỗi tự tin cao | Ảnh sai dù confidence ≥ ngưỡng |

Không có lớp unknown; confidence không bảo đảm nhận ra vật ngoài ba lớp. Tải ZIP kết quả gồm báo cáo, JSON, dự đoán từng ảnh CSV, metrics từng lớp, nhãn/bản chia, lịch sử train, cấu hình và `model.pt`. Sau test có thể thử ảnh mới bằng mô hình đã chốt.

**Thảo luận tổng kết:** Lớp nào recall thấp nhất? Ảnh sai có đặc điểm nào? Đó là quan sát hay bằng chứng nguyên nhân? Cần dữ liệu mới nào để kiểm tra giả thuyết? Khi cải tiến sau test, cần **test mới độc lập**; không chọn lại seed từ cùng bộ để tìm điểm cao.

## Lưu phiên và chấm bài

Nhãn, bản chia, cấu hình và kết quả lưu trên đĩa. Mở lại server tiếp tục được phiên đã lưu. Train đang chạy khi tắt máy không tiếp tục trong nền; cần chạy lại. Nếu test bị ngắt, chỉ được chạy lại cùng mô hình đã chốt.

| Thành phần | Điểm gợi ý |
|---|---:|
| Quy tắc nhãn và kiểm tra dữ liệu | 20 |
| Giải thích ba tập và rò rỉ dữ liệu | 20 |
| Chọn cấu hình có bằng chứng | 25 |
| Đọc metrics, ảnh sai và giới hạn | 25 |
| Lưu kết quả và tái lập | 10 |

Không chấm chỉ bằng accuracy: phân tích đúng một mô hình yếu vẫn đạt mục tiêu hiểu phương pháp.
