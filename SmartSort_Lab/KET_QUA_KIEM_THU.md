# Kết quả chạy thử lab trên dữ liệu đã cung cấp

Đã chạy đầy đủ mã notebook trên máy tính bằng CPU, Python 3.13.15, PyTorch 2.14.1 và Torchvision 0.29.1. Chưa chạy trực tiếp trong phiên Google Colab; notebook có luồng upload/download dành cho Colab và được kiểm tra định dạng, cú pháp tất cả cell. Kết quả trên Colab có thể khác đôi chút do thiết bị và phiên bản thư viện.

## Kết quả thực đo

| Chỉ số | Kết quả |
|---|---:|
| Số ảnh train / validation / test | 96 / 24 / 60 |
| Accuracy validation | 100% (24/24) |
| Macro-F1 validation | 1.000 |
| Accuracy test | 78.33% (47/60) |
| Khoảng Wilson 95% cho accuracy test | 66.4%–86.9% |
| Macro-F1 test | 0.769 |
| Accuracy test basic | 93.33% (28/30) |
| Accuracy test variation | 63.33% (19/30) |
| Ngoài lớp bị từ chối, ngưỡng confidence 0.70 | 20% (3/15) |
| Ngoài lớp bị chấp nhận sai vào một trong ba lớp | 80% (12/15) |

| Lớp trên test | Precision | Recall | F1 | Số ảnh |
|---|---:|---:|---:|---:|
| Kim loại | 0.833 | 0.500 | 0.625 | 20 |
| Giấy | 0.818 | 0.900 | 0.857 | 20 |
| Nhựa | 0.731 | 0.950 | 0.826 | 20 |

## Những điểm rút ra từ lần chạy

1. **Độ bền vững cần được đánh giá riêng:** accuracy giảm 30 điểm phần trăm giữa basic và variation. Validation hoàn hảo trên 24 ảnh không dự báo được hiệu năng trên ảnh biến thể.
2. **Kim loại là lớp yếu:** bỏ sót 10/20 ảnh; riêng variation chỉ đúng 1/10 ảnh kim loại. Nhầm kim loại sang nhựa 6 lần, sang giấy 4 lần.
3. **Hình dạng và bề mặt cần bổ sung vào kiểm thử:** khi xem ảnh sai, nhiều ảnh kim loại là giấy bạc vò/nhăn hoặc khay nhôm phản chiếu. Đây là các tình huống cần thêm ảnh train và kiểm thử có kiểm soát; chưa đủ bằng chứng để khẳng định yếu tố nào gây lỗi.
4. **Confidence cao vẫn sai:** 10/13 ảnh sai có confidence ≥ 0.70. Không dùng điểm softmax làm cam kết dự đoán đúng.
5. **Khả năng nhận biết vật ngoài lớp còn yếu:** cả 7 ảnh carton được dự đoán là giấy với confidence cao. Dữ liệu gốc coi carton ngoài lớp; nếu bài toán thực tế muốn gom carton vào giấy, cần định nghĩa lại nhãn trước một thí nghiệm mới. Trong bài toán hiện tại, cần dữ liệu validation ngoài lớp hoặc mô hình bổ sung để học cách từ chối.
6. **Ưu tiên dữ liệu hơn kết luận từ điểm số:** cần nhiều vật thể, nền, ánh sáng, góc chụp, điều kiện che khuất và phản chiếu; chia theo vật thể/phiên chụp, thay vì để ảnh gần giống xuất hiện ở nhiều tập.

Không thay đổi mô hình hoặc ngưỡng theo kết quả test này. Nếu dùng các phát hiện trên để cải tiến mô hình, hãy chuẩn bị tập test mới độc lập cho đánh giá cuối.

Các số đo, dự đoán từng ảnh, biểu đồ, checkpoint và báo cáo đầy đủ nằm trong `verified_run/SmartSort_Results.zip`. Đây là kết quả một lần chạy trên bộ ảnh nhỏ phục vụ thực hành.

## Kiểm tra đã thực hiện

- CRC ZIP, SHA-256, giải mã và kích thước/màu đủ 195 ảnh.
- Không trùng nguồn ảnh, nội dung file hoặc pixel trong bộ dữ liệu.
- ZIP chia sẵn giữ nguyên byte ảnh gốc; danh sách validation giống cách notebook chia từ ZIP gốc.
- Notebook hợp lệ theo nbformat; tất cả code cell biên dịch được.
- Chạy đầy đủ cấu hình mặc định: trích đặc trưng, huấn luyện, lưu/nạp checkpoint, validation gate, test, lớp lạ, tốc độ, phân tích lỗi và xuất ZIP.
- Xem trực tiếp biểu đồ ma trận nhầm lẫn và ảnh sai để kiểm tra nhãn, cách hiển thị.
